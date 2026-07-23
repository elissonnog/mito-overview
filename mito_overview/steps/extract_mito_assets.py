"""Extract mitochondrial BAM and bedmethyl assets for mito-overview."""

from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
from io import TextIOBase
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-align-file", required=True)
    parser.add_argument("--align-mode", required=True, choices=("bam", "cram"))
    parser.add_argument("--ref-fasta", required=True)
    parser.add_argument("--read-mode", default="long", choices=("long", "short"))
    parser.add_argument("--mito-bam", required=True)
    parser.add_argument("--mito-region-bed", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--np-bedmethyl-source-gz")
    parser.add_argument("--hp1-bedmethyl-source-gz")
    parser.add_argument("--hp2-bedmethyl-source-gz")
    parser.add_argument("--ungrouped-bedmethyl-source-gz")
    parser.add_argument("--mito-mods-np", required=True)
    parser.add_argument("--mito-mods-hp1", required=True)
    parser.add_argument("--mito-mods-hp2", required=True)
    parser.add_argument("--mito-mods-ungrouped", required=True)
    return parser


def _plain_path(path: str | Path | None) -> Path | None:
    if not path:
        return None
    path = Path(path)
    if path.suffix == ".gz":
        return Path(str(path)[:-3])
    return path


def _resolve_bedmethyl_source(path: str | Path | None) -> Path | None:
    """Resolve a configured source, including the legacy ``.gz`` fallback."""

    if not path:
        return None
    configured_path = Path(path)
    if configured_path.is_file():
        return configured_path
    plain_path = _plain_path(configured_path)
    if plain_path != configured_path and plain_path is not None and plain_path.is_file():
        return plain_path
    return None


def _open_bedmethyl(path: str | Path | None) -> TextIOBase | None:
    """Open plain or gzip-compressed bedMethyl based on file magic, not suffix."""

    source = _resolve_bedmethyl_source(path)
    if source is None:
        return None
    with source.open("rb") as probe:
        is_gzip = probe.read(2) == b"\x1f\x8b"
    if is_gzip:
        return gzip.open(source, "rt", encoding="utf-8")
    return source.open("r", encoding="utf-8")


def _bedmethyl_source_exists(path: str | Path | None) -> bool:
    return _resolve_bedmethyl_source(path) is not None


def _write_empty_table(path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def write_mito_region_bed(path: str | Path, mt_contig: str, mt_length: int) -> Path:
    """Write one zero-based, half-open interval spanning the mitochondrial contig."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{mt_contig}\t0\t{mt_length}\n", encoding="utf-8")
    return path


def subset_bedmethyl(
    *,
    source_gz: str | Path | None,
    destination: str | Path,
    contig: str,
) -> int:
    """Write contig-matching bedmethyl rows and return the number written."""

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle = _open_bedmethyl(source_gz)
    if handle is None:
        destination.write_text("", encoding="utf-8")
        return 0

    written = 0
    with handle:
        with destination.open("w", encoding="utf-8") as out_handle:
            for line in handle:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if line.split("\t", 1)[0] != contig:
                    continue
                out_handle.write(line)
                written += 1
    return written


def extract_mito_bam(
    *,
    source_align_file: str | Path,
    align_mode: str,
    ref_fasta: str | Path,
    mito_bam: str | Path,
    mt_contig: str,
    threads: int,
) -> None:
    """Run samtools to extract the mitochondrial contig into a compact BAM."""

    if shutil.which("samtools") is None:
        raise RuntimeError("samtools is required for the extract step but was not found in PATH")

    mito_bam = Path(mito_bam)
    mito_bam.parent.mkdir(parents=True, exist_ok=True)
    command = ["samtools", "view", "-@", str(threads)]
    if align_mode == "cram":
        command.extend(["-T", str(ref_fasta)])
    command.extend(["-bh", "-o", str(mito_bam), str(source_align_file), mt_contig])
    print(f"[extract] extracting mitochondrial BAM with: {' '.join(command)}")
    subprocess.run(command, check=True)

    index_command = ["samtools", "index", "-@", str(threads), str(mito_bam)]
    print(f"[extract] indexing mitochondrial BAM with: {' '.join(index_command)}")
    subprocess.run(index_command, check=True)


def run_step(
    *,
    source_align_file: str | Path,
    align_mode: str,
    ref_fasta: str | Path,
    mito_bam: str | Path,
    mito_region_bed: str | Path,
    sample_id: str,
    mt_contig: str,
    mt_length: int,
    threads: int,
    read_mode: str = "long",
    np_bedmethyl_source_gz: str | Path | None,
    hp1_bedmethyl_source_gz: str | Path | None,
    hp2_bedmethyl_source_gz: str | Path | None,
    ungrouped_bedmethyl_source_gz: str | Path | None,
    mito_mods_np: str | Path,
    mito_mods_hp1: str | Path,
    mito_mods_hp2: str | Path,
    mito_mods_ungrouped: str | Path,
) -> dict[str, Path | int]:
    """Run the portable mitochondrial extraction step."""

    print(
        f"[extract] starting sample={sample_id} contig={mt_contig} "
        f"length={mt_length} align_mode={align_mode} read_mode={read_mode} threads={threads}"
    )
    if read_mode == "long":
        missing_tracks = [
            label
            for label, source in (
                ("hp1", hp1_bedmethyl_source_gz),
                ("hp2", hp2_bedmethyl_source_gz),
                ("ungrouped", ungrouped_bedmethyl_source_gz),
            )
            if not _bedmethyl_source_exists(source)
        ]
        if missing_tracks:
            missing_str = ", ".join(missing_tracks)
            # Real ONT mitochondrial runs may be available without exported bedmethyl
            # sidecars. Keep the core long-read workflow usable and let the dedicated
            # methylation step emit a status-only page from the empty subsets.
            print(
                "[extract] long-read mode detected but missing phased/ungrouped "
                f"bedmethyl sources for {missing_str}; proceeding with empty mitochondrial "
                "bedmethyl subsets for the missing tracks",
                flush=True,
            )
    extract_mito_bam(
        source_align_file=source_align_file,
        align_mode=align_mode,
        ref_fasta=ref_fasta,
        mito_bam=mito_bam,
        mt_contig=mt_contig,
        threads=threads,
    )

    mito_region_bed = write_mito_region_bed(mito_region_bed, mt_contig, mt_length)
    print(f"[extract] wrote region BED to {mito_region_bed}")

    np_rows = hp1_rows = hp2_rows = ungrouped_rows = 0
    if read_mode == "short":
        print("[extract] short-read mode detected; skipping bedmethyl subsetting", flush=True)
        for destination in (mito_mods_np, mito_mods_hp1, mito_mods_hp2, mito_mods_ungrouped):
            _write_empty_table(destination)
    else:
        print("[extract] subsetting mitochondrial bedmethyl tracks")
        np_rows = subset_bedmethyl(source_gz=np_bedmethyl_source_gz, destination=mito_mods_np, contig=mt_contig)
        hp1_rows = subset_bedmethyl(source_gz=hp1_bedmethyl_source_gz, destination=mito_mods_hp1, contig=mt_contig)
        hp2_rows = subset_bedmethyl(source_gz=hp2_bedmethyl_source_gz, destination=mito_mods_hp2, contig=mt_contig)
        ungrouped_rows = subset_bedmethyl(
            source_gz=ungrouped_bedmethyl_source_gz,
            destination=mito_mods_ungrouped,
            contig=mt_contig,
        )
        print(
            "[extract] bedmethyl rows "
            f"np={np_rows} hp1={hp1_rows} hp2={hp2_rows} ungrouped={ungrouped_rows}"
        )

    return {
        "mito_bam": Path(mito_bam),
        "mito_bai": Path(f"{mito_bam}.bai"),
        "mito_region_bed": mito_region_bed,
        "mito_mods_np": Path(mito_mods_np),
        "mito_mods_hp1": Path(mito_mods_hp1),
        "mito_mods_hp2": Path(mito_mods_hp2),
        "mito_mods_ungrouped": Path(mito_mods_ungrouped),
        "np_rows": np_rows,
        "hp1_rows": hp1_rows,
        "hp2_rows": hp2_rows,
        "ungrouped_rows": ungrouped_rows,
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        source_align_file=args.source_align_file,
        align_mode=args.align_mode,
        ref_fasta=args.ref_fasta,
        mito_bam=args.mito_bam,
        mito_region_bed=args.mito_region_bed,
        sample_id=args.sample_id,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        threads=args.threads,
        read_mode=args.read_mode,
        np_bedmethyl_source_gz=args.np_bedmethyl_source_gz,
        hp1_bedmethyl_source_gz=args.hp1_bedmethyl_source_gz,
        hp2_bedmethyl_source_gz=args.hp2_bedmethyl_source_gz,
        ungrouped_bedmethyl_source_gz=args.ungrouped_bedmethyl_source_gz,
        mito_mods_np=args.mito_mods_np,
        mito_mods_hp1=args.mito_mods_hp1,
        mito_mods_hp2=args.mito_mods_hp2,
        mito_mods_ungrouped=args.mito_mods_ungrouped,
    )
    for key, value in outputs.items():
        print(f"{key}\t{value}")


if __name__ == "__main__":
    main()
