from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pysam
import pytest

from mito_overview.validation_provenance import (
    ProvenanceError,
    create_alignment_provenance,
    create_deterministic_subset,
    verify_alignment_provenance,
    verify_deterministic_subset,
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
