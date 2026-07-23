"""Sync final mito-overview outputs into a persistent destination."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--log-dir", required=True)
    parser.add_argument("--mito-bam", required=True)
    parser.add_argument("--mito-bai", required=True)
    parser.add_argument("--config-file", required=True)
    parser.add_argument("--final-dir", required=True)
    parser.add_argument("--sample-id", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--mt-contig", required=True)
    parser.add_argument("--mt-length", type=int, required=True)
    parser.add_argument("--species", required=True)
    parser.add_argument("--build", required=True)
    return parser


def _replace_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def run_step(
    *,
    output_dir: str | Path,
    log_dir: str | Path,
    mito_bam: str | Path,
    mito_bai: str | Path,
    config_file: str | Path,
    final_dir: str | Path,
    sample_id: str,
    run_name: str,
    mt_contig: str,
    mt_length: int,
    species: str,
    build: str,
) -> dict[str, Path]:
    """Copy the finished run products into a persistent final directory."""

    output_dir = Path(output_dir)
    log_dir = Path(log_dir)
    mito_bam = Path(mito_bam)
    mito_bai = Path(mito_bai)
    config_file = Path(config_file)
    final_dir = Path(final_dir)
    if final_dir.exists():
        raise FileExistsError(
            f"Final output directory already exists and will not be overwritten: {final_dir}"
        )
    final_dir.mkdir(parents=True, exist_ok=False)

    print(f"[sync] syncing run={run_name} sample={sample_id} to {final_dir}")
    _replace_tree(output_dir, final_dir / "output")
    _replace_tree(log_dir, final_dir / "logs")
    shutil.copy2(mito_bam, final_dir / "mito.bam")
    shutil.copy2(mito_bai, final_dir / "mito.bam.bai")
    shutil.copy2(config_file, final_dir / "config.env.snapshot")

    manifest_path = final_dir / "sync_manifest.tsv"
    manifest_path.write_text(
        "\n".join(
            [
                "key\tpath",
                f"sample_id\t{sample_id}",
                f"run_name\t{run_name}",
                f"mt_contig\t{mt_contig}",
                f"mt_length\t{mt_length}",
                f"species\t{species}",
                f"build\t{build}",
                f"report_dir\t{final_dir / 'output' / 'report'}",
                f"mito_bam\t{final_dir / 'mito.bam'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"[sync] wrote manifest to {manifest_path}")
    return {
        "final_dir": final_dir,
        "manifest_path": manifest_path,
        "report_dir": final_dir / "output" / "report",
    }


def main() -> None:
    args = build_arg_parser().parse_args()
    outputs = run_step(
        output_dir=args.output_dir,
        log_dir=args.log_dir,
        mito_bam=args.mito_bam,
        mito_bai=args.mito_bai,
        config_file=args.config_file,
        final_dir=args.final_dir,
        sample_id=args.sample_id,
        run_name=args.run_name,
        mt_contig=args.mt_contig,
        mt_length=args.mt_length,
        species=args.species,
        build=args.build,
    )
    for key, value in outputs.items():
        print(f"{key}\t{value}")


if __name__ == "__main__":
    main()
