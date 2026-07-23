from __future__ import annotations

import hashlib
import gzip
import json
from pathlib import Path

import pysam
import pytest

from mito_overview.validation_provenance import (
    ProvenanceError,
    create_alignment_provenance,
    create_deterministic_subset,
    create_deterministic_fastq_subset,
    digest_file,
    verify_alignment_provenance,
    verify_deterministic_subset,
    verify_deterministic_fastq_subset,
    tool_version,
)
from tests._helpers import ReadSpec, write_alignment, write_fasta


def _alignment_fixture(tmp_path: Path, *, read_count: int = 20) -> tuple[Path, Path, Path]:
    reference = write_fasta(tmp_path / "mt.fa", {"MT": "A" * 500})
    reads = [
        ReadSpec(
            name=f"read-{index:03d}",
            contig="MT",
            start=index,
            sequence="A" * 50,
        )
        for index in range(read_count)
    ]
    alignment = write_alignment(tmp_path / "source.bam", {"MT": 500}, reads)
    fastq = tmp_path / "reads.fastq"
    fastq.write_text("@read-000\nAAAA\n+\nIIII\n", encoding="ascii")
    return reference, alignment, fastq


def _record_source(tmp_path: Path, reference: Path, alignment: Path, fastq: Path) -> Path:
    manifest = tmp_path / "source.provenance.json"
    create_alignment_provenance(
        manifest_path=manifest,
        dataset_id="PUBLIC-001",
        alignment_path=alignment,
        reference_path=reference,
        inputs={"run_1": fastq},
        derivation_id="test-aligner-v1",
        command_template="test-aligner {reference} {fastq} | test-sort {alignment}",
        parameters={"threads": "1"},
        tools=(),
    )
    return manifest


def test_alignment_provenance_binds_alignment_reference_and_public_input(tmp_path: Path) -> None:
    reference, alignment, fastq = _alignment_fixture(tmp_path)
    manifest = _record_source(tmp_path, reference, alignment, fastq)

    payload = verify_alignment_provenance(
        manifest_path=manifest,
        dataset_id="PUBLIC-001",
        alignment_path=alignment,
        reference_path=reference,
        inputs={"run_1": fastq},
        derivation_id="test-aligner-v1",
        command_template="test-aligner {reference} {fastq} | test-sort {alignment}",
        parameters={"threads": "1"},
        tools=(),
    )
    assert payload["alignment"]["sha256"]
    assert payload["public_inputs"][0]["md5"]

    fastq.write_text("@changed\nTTTT\n+\nIIII\n", encoding="ascii")
    with pytest.raises(ProvenanceError, match="public input run_1"):
        verify_alignment_provenance(
            manifest_path=manifest,
            dataset_id="PUBLIC-001",
            alignment_path=alignment,
            reference_path=reference,
            inputs={"run_1": fastq},
            derivation_id="test-aligner-v1",
            command_template="test-aligner {reference} {fastq} | test-sort {alignment}",
            parameters={"threads": "1"},
            tools=(),
        )


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    (
        ("command_template", "different command", "command_template mismatch"),
        ("parameters", {"threads": "2"}, "parameters mismatch"),
        ("tool_versions", {"samtools": "different"}, "tool_versions mismatch"),
    ),
)
def test_alignment_provenance_rejects_derivation_tampering(
    tmp_path: Path,
    field: str,
    replacement: object,
    message: str,
) -> None:
    reference, alignment, fastq = _alignment_fixture(tmp_path)
    manifest = _record_source(tmp_path, reference, alignment, fastq)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["derivation"][field] = replacement
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match=message):
        verify_alignment_provenance(
            manifest_path=manifest,
            dataset_id="PUBLIC-001",
            alignment_path=alignment,
            reference_path=reference,
            inputs={"run_1": fastq},
            derivation_id="test-aligner-v1",
            command_template="test-aligner {reference} {fastq} | test-sort {alignment}",
            parameters={"threads": "1"},
            tools=(),
        )


def test_alignment_provenance_rejects_duplicate_public_input_labels(
    tmp_path: Path,
) -> None:
    reference, alignment, fastq = _alignment_fixture(tmp_path)
    manifest = _record_source(tmp_path, reference, alignment, fastq)
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["public_inputs"].append(dict(payload["public_inputs"][0]))
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match="Duplicate public input label"):
        verify_alignment_provenance(
            manifest_path=manifest,
            dataset_id="PUBLIC-001",
            alignment_path=alignment,
            reference_path=reference,
            inputs={"run_1": fastq},
            derivation_id="test-aligner-v1",
            command_template="test-aligner {reference} {fastq} | test-sort {alignment}",
            parameters={"threads": "1"},
            tools=(),
        )


def test_deterministic_subset_selects_exact_seeded_query_names(tmp_path: Path) -> None:
    reference, alignment, fastq = _alignment_fixture(tmp_path, read_count=20)
    source_manifest = _record_source(tmp_path, reference, alignment, fastq)
    subset = tmp_path / "subset.bam"
    subset_manifest = tmp_path / "subset.provenance.json"
    names_path = tmp_path / "subset.selected_qnames.txt"
    seed = "mito-overview-v0.3.0-test"

    payload = create_deterministic_subset(
        source_alignment=alignment,
        source_manifest=source_manifest,
        output_alignment=subset,
        output_manifest=subset_manifest,
        selected_names_path=names_path,
        dataset_id="PUBLIC-001",
        requested_count=5,
        seed=seed,
    )
    expected = sorted(
        (f"read-{index:03d}" for index in range(20)),
        key=lambda name: hashlib.sha256(f"{seed}\0{name}".encode()).digest(),
    )[:5]
    selected = names_path.read_text(encoding="utf-8").splitlines()
    assert selected == sorted(expected)
    assert payload["selection"]["selected_primary_query_names"] == 5
    assert payload["selection"]["mapped_records_written"] == 5

    with pysam.AlignmentFile(str(subset), "rb") as handle:
        observed = sorted(record.query_name for record in handle.fetch(until_eof=True))
    assert observed == sorted(expected)
    verify_deterministic_subset(
        source_alignment=alignment,
        source_manifest=source_manifest,
        output_alignment=subset,
        output_manifest=subset_manifest,
        selected_names_path=names_path,
        dataset_id="PUBLIC-001",
        requested_count=5,
        seed=seed,
    )


def test_subset_verification_rejects_seed_or_manifest_tampering(tmp_path: Path) -> None:
    reference, alignment, fastq = _alignment_fixture(tmp_path, read_count=8)
    source_manifest = _record_source(tmp_path, reference, alignment, fastq)
    subset = tmp_path / "subset.bam"
    subset_manifest = tmp_path / "subset.provenance.json"
    names_path = tmp_path / "subset.selected_qnames.txt"
    create_deterministic_subset(
        source_alignment=alignment,
        source_manifest=source_manifest,
        output_alignment=subset,
        output_manifest=subset_manifest,
        selected_names_path=names_path,
        dataset_id="PUBLIC-001",
        requested_count=3,
        seed="seed-a",
    )

    with pytest.raises(ProvenanceError, match="seed mismatch"):
        verify_deterministic_subset(
            source_alignment=alignment,
            source_manifest=source_manifest,
            output_alignment=subset,
            output_manifest=subset_manifest,
            selected_names_path=names_path,
            dataset_id="PUBLIC-001",
            requested_count=3,
            seed="seed-b",
        )

    payload = json.loads(subset_manifest.read_text(encoding="utf-8"))
    payload["subset_alignment"]["sha256"] = "0" * 64
    subset_manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProvenanceError, match="subset alignment sha256 mismatch"):
        verify_deterministic_subset(
            source_alignment=alignment,
            source_manifest=source_manifest,
            output_alignment=subset,
            output_manifest=subset_manifest,
            selected_names_path=names_path,
            dataset_id="PUBLIC-001",
            requested_count=3,
            seed="seed-a",
        )


def test_tool_version_ignores_failed_version_flag_and_parses_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    responses = iter(
        [
            Result(1, stderr="unrecognized --version"),
            Result(1, stderr="unrecognized version"),
            Result(1, stderr="Program: bwa\nVersion: 0.7.19-r1273\nUsage: bwa"),
        ]
    )
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: next(responses))
    assert tool_version("bwa") == "0.7.19-r1273"


def test_deterministic_fastq_subset_is_exact_and_reproducible(tmp_path: Path) -> None:
    source = tmp_path / "source.fastq.gz"
    with gzip.open(source, "wt", encoding="ascii", newline="") as handle:
        for index in range(20):
            handle.write(f"@read-{index:03d} metadata\nAAAA\n+\nIIII\n")
    subset = tmp_path / "subset.fastq.gz"
    manifest = tmp_path / "subset.fastq.provenance.json"
    names = tmp_path / "subset.fastq.selected_qnames.txt"
    seed = "fastq-test-seed"
    payload = create_deterministic_fastq_subset(
        source_fastq=source,
        output_fastq=subset,
        output_manifest=manifest,
        selected_names_path=names,
        dataset_id="FASTQ-001",
        requested_count=5,
        seed=seed,
    )
    expected = sorted(
        (f"read-{index:03d}" for index in range(20)),
        key=lambda name: hashlib.sha256(f"{seed}\0{name}".encode()).digest(),
    )[:5]
    assert names.read_text(encoding="utf-8").splitlines() == sorted(expected)
    with gzip.open(subset, "rt", encoding="ascii") as handle:
        headers = [line[1:].split()[0] for line in handle if line.startswith("@")]
    assert headers == [name for name in (f"read-{index:03d}" for index in range(20)) if name in expected]
    assert payload["selection"]["source_records_seen"] == 20
    assert payload["selected_query_names"]["md5"] == hashlib.md5(
        names.read_bytes()
    ).hexdigest()
    verify_deterministic_fastq_subset(
        source_fastq=source,
        output_fastq=subset,
        output_manifest=manifest,
        selected_names_path=names,
        dataset_id="FASTQ-001",
        requested_count=5,
        seed=seed,
    )

    source.write_bytes(source.read_bytes() + b"tamper")
    with pytest.raises(ProvenanceError, match="source FASTQ"):
        verify_deterministic_fastq_subset(
            source_fastq=source,
            output_fastq=subset,
            output_manifest=manifest,
            selected_names_path=names,
            dataset_id="FASTQ-001",
            requested_count=5,
            seed=seed,
        )


def test_fastq_subset_verification_rejects_self_consistent_nonminimum_ledger(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.fastq.gz"
    with gzip.open(source, "wt", encoding="ascii", newline="") as handle:
        for index in range(20):
            handle.write(f"@read-{index:03d}\nAAAA\n+\nIIII\n")
    subset = tmp_path / "subset.fastq.gz"
    manifest = tmp_path / "subset.fastq.provenance.json"
    names = tmp_path / "subset.fastq.selected_qnames.txt"
    seed = "fastq-test-seed"
    create_deterministic_fastq_subset(
        source_fastq=source,
        output_fastq=subset,
        output_manifest=manifest,
        selected_names_path=names,
        dataset_id="FASTQ-001",
        requested_count=5,
        seed=seed,
    )

    names.write_text(
        "".join(f"read-{index:03d}\n" for index in range(15, 20)),
        encoding="utf-8",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["selected_query_names"] = digest_file(names)
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match="minimum-score selection"):
        verify_deterministic_fastq_subset(
            source_fastq=source,
            output_fastq=subset,
            output_manifest=manifest,
            selected_names_path=names,
            dataset_id="FASTQ-001",
            requested_count=5,
            seed=seed,
        )


def test_fastq_subset_verification_rejects_self_consistent_wrong_subset_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.fastq.gz"
    with gzip.open(source, "wt", encoding="ascii", newline="") as handle:
        for index in range(20):
            handle.write(f"@read-{index:03d}\nAAAA\n+\nIIII\n")
    subset = tmp_path / "subset.fastq.gz"
    manifest = tmp_path / "subset.fastq.provenance.json"
    names = tmp_path / "subset.fastq.selected_qnames.txt"
    seed = "fastq-test-seed"
    create_deterministic_fastq_subset(
        source_fastq=source,
        output_fastq=subset,
        output_manifest=manifest,
        selected_names_path=names,
        dataset_id="FASTQ-001",
        requested_count=5,
        seed=seed,
    )

    with gzip.open(subset, "wt", encoding="ascii", newline="") as handle:
        for index in range(15, 20):
            handle.write(f"@wrong-{index:03d}\nAAAA\n+\nIIII\n")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["subset_fastq"] = digest_file(subset, include_md5=True)
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProvenanceError, match="Subset FASTQ records"):
        verify_deterministic_fastq_subset(
            source_fastq=source,
            output_fastq=subset,
            output_manifest=manifest,
            selected_names_path=names,
            dataset_id="FASTQ-001",
            requested_count=5,
            seed=seed,
        )
