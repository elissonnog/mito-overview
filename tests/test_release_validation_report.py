from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "build_release_validation_report_v0.3.0.py"
SPEC = importlib.util.spec_from_file_location("build_release_report_v030", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
report_builder = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = report_builder
SPEC.loader.exec_module(report_builder)

COMMIT = "a" * 40
REPOSITORY = "https://github.com/elissonnog/mito-overview"
RUN_ID = 987654321


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_tsv(path: Path, columns: tuple[str, ...], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def write_report_figure(path: Path, accent: str, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (800, 450), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 800, 55), fill=accent)
    draw.line((80, 370, 750, 370), fill="black", width=3)
    draw.line((80, 85, 80, 370), fill="black", width=3)
    points = [(90, 330), (200, 290), (310, 305), (420, 180), (530, 215), (650, 120), (740, 145)]
    draw.line(points, fill=accent, width=6)
    draw.text((25, 18), label, fill="white")
    image.save(path)


def rewrite_artifact_manifest(packet: Path) -> None:
    rows = []
    for path in sorted(packet.rglob("*")):
        if path.is_file() and path.relative_to(packet).as_posix() != "artifacts.sha256":
            rows.append(f"{digest(path)}  {path.relative_to(packet).as_posix()}")
    (packet / "artifacts.sha256").write_text(
        "\n".join(rows) + "\n", encoding="utf-8"
    )


def make_packet(tmp_path: Path) -> tuple[Path, Path, list[Path]]:
    packet = tmp_path / "packet"
    packet.mkdir()
    source_metadata_path = packet / report_builder.GM11906_SOURCE_METADATA_PACKET_PATH
    source_metadata_path.parent.mkdir(parents=True)
    source_metadata_path.write_bytes(
        (
            ROOT
            / "resources/public_validation/"
            "gm11906_ncbi_source_metadata_v0.3.0.json"
        ).read_bytes()
    )
    source_metadata = json.loads(source_metadata_path.read_text(encoding="utf-8"))
    source_metadata_identity = {
        "path": report_builder.GM11906_SOURCE_METADATA_PACKET_PATH,
        "sha256": digest(source_metadata_path),
        "records_sha256": source_metadata["records_sha256"],
        "retrieval_completed_utc": source_metadata["retrieval_completed_utc"],
        "authority": source_metadata["authority"],
    }
    case_ids = sorted(report_builder.REQUIRED_CASE_IDS)
    cases = [
        [case_id, "release_validation", "1", "1", "PASS", "evidence available"]
        for case_id in case_ids
    ]
    write_tsv(packet / "cases.tsv", report_builder.EVIDENCE_COLUMNS["cases.tsv"], cases)

    run = {
        "schema_version": "2.0",
        "validation_profile": "github_release_validation_v1",
        "release_version": "v0.3.0",
        "git_commit": COMMIT,
        "repository": REPOSITORY,
        "github_actions_run_id": RUN_ID,
        "generated_utc": "2026-07-21T12:00:00+00:00",
        "case_count": len(cases),
        "verdict_counts": {
            "PASS": len(cases),
            "FAIL": 0,
            "SKIP": 0,
            "XFAIL": 0,
            "BLOCKED": 0,
        },
        "public_source_metadata": source_metadata_identity,
        "claim_scope": "reproducible mode-gated mtDNA reporting workflow/resource",
        "diagnostic_validation_claimed": False,
    }
    (packet / "run.json").write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    release = {
        "schema_version": "2.0",
        "validation_profile": "github_release_validation_v1",
        "release_version": "v0.3.0",
        "package_name": "mito-overview",
        "package_version": "0.3.0",
        "repository": REPOSITORY,
        "git_commit": COMMIT,
        "public_source_metadata": source_metadata_identity,
    }
    (packet / "release_identity.json").write_text(
        json.dumps(release, indent=2) + "\n", encoding="utf-8"
    )

    normalized_paths: list[Path] = []
    figures: list[Path] = []
    figure_rows: list[list[str]] = []
    table_rows: list[list[str]] = []
    for index, (dataset, case_id, filename, accent) in enumerate(
        (
            (
                "GM11906",
                "gm11906_default_run1",
                "mito_heteroplasmy_landscape.png",
                "#1F77B4",
            ),
            (
                "GM12878",
                "gm12878_default_run1",
                "mito_deletion_clusters.png",
                "#D95F02",
            ),
        ),
        1,
    ):
        normalized = packet / "observed_normalized" / case_id / "summary.tsv"
        write_tsv(normalized, ("metric", "value"), [["status", "ok"], ["candidate_sites", str(30 + index)]])
        normalized_paths.append(normalized)
        visual_inventory = normalized.parent / "visual_artifact_inventory.tsv"
        write_tsv(
            visual_inventory,
            ("relative_path", "artifact_type", "width_px", "height_px", "integrity_status"),
            [[f"figures/{filename}", "png", "800", "450", "ok"]],
        )
        figure = packet / "figures" / case_id / filename
        write_report_figure(figure, accent, f"{dataset} report-native panel")
        figures.append(figure)
        figure_rows.append(
            [
                f"F{index}",
                dataset,
                case_id,
                figure.relative_to(packet).as_posix(),
                digest(figure),
                str(figure.stat().st_size),
                "800",
                "450",
                "ok",
                visual_inventory.relative_to(packet).as_posix(),
            ]
        )
        table_rows.append(
            [
                f"T{index}",
                dataset,
                case_id,
                normalized.relative_to(packet).as_posix(),
                digest(normalized),
                "2",
                "2",
                "normalized public result",
            ]
        )

    write_tsv(
        packet / "figure_provenance.tsv",
        report_builder.EVIDENCE_COLUMNS["figure_provenance.tsv"],
        figure_rows,
    )
    write_tsv(
        packet / "table_provenance.tsv",
        report_builder.EVIDENCE_COLUMNS["table_provenance.tsv"],
        table_rows,
    )
    for row in figure_rows:
        dataset = row[1]
        filename = Path(row[3]).name
        with Image.open(packet / row[3]) as image:
            image.load()
            decoded_digest = hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()
        write_tsv(
            packet / "decoded_pixel_hashes" / f"{dataset}.tsv",
            ("path", "width_px", "height_px", "decoded_rgba_sha256"),
            [[filename, row[6], row[7], decoded_digest]],
        )
    write_tsv(
        packet / "claim_evidence_matrix.tsv",
        report_builder.EVIDENCE_COLUMNS["claim_evidence_matrix.tsv"],
        [
            [
                "C1",
                "Fixed-input workflow execution is repeatable",
                "gm11906_repeatability; gm12878_repeatability",
                "No diagnostic performance inference",
            ]
        ],
    )
    write_tsv(
        packet / "module_status_matrix.tsv",
        report_builder.EVIDENCE_COLUMNS["module_status_matrix.tsv"],
        [
            [
                "GM11906",
                "gm11906_default_run1",
                "mito_qc",
                "ok",
                "",
                "observed_normalized/gm11906_default_run1/summary.tsv",
            ],
            [
                "GM12878",
                "gm12878_default_run1",
                "numt_interpretation",
                "not_evaluable",
                "reference_scope_mt_only",
                "observed_normalized/gm12878_default_run1/summary.tsv",
            ],
        ],
    )
    resource_rows = []
    for index, case_id in enumerate(
        sorted(report_builder.REQUIRED_RESOURCE_CASE_IDS), start=1
    ):
        command = packet / "commands" / f"{case_id}.sh"
        log = packet / "logs" / f"{case_id}.log"
        command.parent.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        command.write_text(f"echo {case_id}\n", encoding="utf-8")
        log.write_text(f"{case_id}=PASS\n", encoding="utf-8")
        resource_rows.append(
            [
                f"20000000-0000-4000-8000-{index:012d}",
                case_id,
                COMMIT,
                f"commands/{case_id}.sh",
                digest(command),
                f"logs/{case_id}.log",
                digest(log),
                "12.4",
                "10.0",
                "1.2",
                "204800",
                "2033558460",
                "3000000000" if case_id == "public_cache_prepare" else "2097152",
                "repository_root;cache_root;validation_root",
                "cache_root;validation_root",
                "broad_declared_inputs_and_changed_or_new_outputs_v2",
                "4",
                "osx-arm64",
                "measured",
                "",
            ]
        )
    write_tsv(
        packet / "resource_usage.tsv",
        report_builder.EVIDENCE_COLUMNS["resource_usage.tsv"],
        resource_rows,
    )
    sha_short = hashlib.sha256(b"short-input").hexdigest()
    sha_long = hashlib.sha256(b"long-input").hexdigest()
    raw_rows = [
        [
            "1.0",
            "GM11906_pooled_scATAC",
            "SRR10804585",
            "SAMN13699362",
            "GSM4238454",
            "MERFF-29-S42",
            "GM11906",
            "ATAC-seq",
            "single_cell_library",
            "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM4238454",
            "SRR10804585_1.fastq.gz",
            "8795676",
            "3f5ea26a5791894071462d4970bc9e5a",
            sha_short,
            "377587",
            "https://ftp.sra.ebi.ac.uk/example/SRR10804585_1.fastq.gz",
        ],
        [
            "1.0",
            "GM12878_ONT",
            "SRR18110025",
            "SAMN26195906",
            "GM12878_mtDNA",
            "Human GM12878 Cell Line",
            "GM12878",
            "OTHER",
            "targeted_mt_library",
            "https://www.ebi.ac.uk/ena/browser/view/SRR18110025",
            "SRR18110025.fastq.gz",
            "2033558460",
            "d5bfb9aeba04cae5f3dd79462a42e5b0",
            sha_long,
            "193043",
            "https://ftp.sra.ebi.ac.uk/example/SRR18110025.fastq.gz",
        ],
    ]
    write_tsv(packet / "raw_inputs.tsv", report_builder.RAW_INPUT_COLUMNS, raw_rows)
    (packet / "inputs.sha256").write_text(
        f"{sha_short}  SRR10804585_1.fastq.gz\n"
        f"{sha_long}  SRR18110025.fastq.gz\n",
        encoding="utf-8",
    )
    (packet / "CACHE_SEAL.sha256").write_text(
        f"{digest(packet / 'raw_inputs.tsv')}  raw_inputs.tsv\n",
        encoding="utf-8",
    )
    write_tsv(
        packet / "public_data_sources.tsv",
        report_builder.EVIDENCE_COLUMNS["public_data_sources.tsv"],
        [
            [
                "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
                "SRR10804585",
                "PRJNA598179",
                "SAMN13699362",
                "GM11906",
                "ILLUMINA",
                "NextSeq 550",
                "ATAC-seq",
                raw_rows[0][-1],
                raw_rows[0][12],
                sha_short,
                raw_rows[0][11],
                "2026-07-21T12:00:00+00:00",
                "fixed-input marker representation",
                "raw reads excluded",
            ],
            [
                "GM12878 ONT targeted-mt proof-of-principle",
                "SRR18110025",
                "PRJNA809571",
                "SAMN26195906",
                "GM12878",
                "OXFORD_NANOPORE",
                "GridION",
                "OTHER",
                raw_rows[1][-1],
                raw_rows[1][12],
                sha_long,
                raw_rows[1][11],
                "2026-07-21T12:00:00+00:00",
                "bounded long-read reproduction",
                "raw reads excluded",
            ],
        ],
    )
    write_tsv(
        packet / "manuscript_handoff.tsv",
        report_builder.EVIDENCE_COLUMNS["manuscript_handoff.tsv"],
        [
            ["R1", "GM11906", "m.8344A>G allele fraction", "0.720545", "fraction", "filter_profile_results.tsv", "descriptive marker representation only"],
            ["R2", "GM12878", "default candidate sites", "16", "sites", "filter_profile_results.tsv", "fixed-input descriptive count"],
        ],
    )
    write_tsv(
        packet / "limitations.tsv",
        report_builder.EVIDENCE_COLUMNS["limitations.tsv"],
        [
            ["L1", "clinical", "No clinical validation", "No diagnostic claim"],
            ["L2", "public data", "Reduced fixed-input examples", "No population generalization"],
        ],
    )
    write_tsv(
        packet / "filter_profile_results.tsv",
        report_builder.EVIDENCE_COLUMNS["filter_profile_results.tsv"],
        [
            ["gm11906_default", "GM11906", "default", "13", "20", "10", "33", "44052664", "7293106", "1", "0.720545"],
            ["gm12878_default", "GM12878", "default", "13", "20", "10", "16", "7143152", "2047476", "0", ""],
        ],
    )
    write_tsv(
        packet / "public_validation_oracle_v0.3.0.tsv",
        report_builder.EVIDENCE_COLUMNS["public_validation_oracle_v0.3.0.tsv"],
        [
            ["GM11906", "default", "33", "44052664", "7293106", "0.720545", "44", "14", "7"],
            ["GM12878", "default", "16", "7143152", "2047476", "", "44", "14", "15"],
        ],
    )
    write_tsv(
        packet / "oracle_assertions.tsv",
        report_builder.EVIDENCE_COLUMNS["oracle_assertions.tsv"],
        [
            ["gm11906_m8344", "PASS", "0.720545", "0.720545", "marker represented"],
            ["gm12878_candidates", "PASS", "16", "16", "default profile"],
        ],
    )

    normalized_hash = digest(normalized_paths[0])
    write_tsv(
        packet / "cross_platform_comparison.tsv",
        report_builder.EVIDENCE_COLUMNS["cross_platform_comparison.tsv"],
        [
            [
                "normalized_scientific_table",
                "observed_normalized/gm11906_default_run1/summary.tsv",
                normalized_hash,
                normalized_hash,
                "PASS",
                "byte-identical normalized content",
            ],
            [
                "visual_structure",
                "observed_normalized/gm11906_default_run1/visual_artifact_inventory.tsv",
                "not_compared",
                "not_compared",
                "PASS",
                "path/type/dimensions/integrity",
            ],
        ],
    )
    acceptance = packet / "acceptance" / "cross_platform_public_reproduction.json"
    acceptance.parent.mkdir(parents=True)
    acceptance.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "validation_profile": "github_release_validation_v1",
                "evidence_type": "cross_platform_public_reproduction",
                "verdict": "PASS",
                "git_commit": COMMIT,
                "ubuntu_public_validation_run_id": 123456789,
                "macos_platform": "osx-arm64",
                "ubuntu_platform": "linux-64",
                "normalized_scientific_tables_compared": 1,
                "visual_inventories_compared": 1,
                "comparison_table": "cross_platform_comparison.tsv",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (packet / "environment.txt").write_text(
        "release_version=v0.3.0\n"
        f"git_commit={COMMIT}\n"
        "python=3.12.13\n"
        "samtools=1.23.1\n"
        "threads=4\n"
        "LC_ALL=C\n"
        "TZ=UTC\n",
        encoding="utf-8",
    )
    public_environment = packet / report_builder.PUBLIC_ENVIRONMENT_ROOT
    public_environment.mkdir(parents=True, exist_ok=True)
    (public_environment / "runtime_versions.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "platform_id": "osx-arm64",
                "system": "Darwin",
                "machine": "arm64",
                "python": "3.12.13",
                "python_executable": "/opt/mito-validation/bin/python",
                "mito_overview_module": (
                    "/opt/mito-validation/lib/python3.12/site-packages/"
                    "mito_overview/__init__.py"
                ),
                "packages": report_builder.EXPECTED_RUNTIME_PACKAGES,
                "samtools": "samtools 1.23.1",
                "htslib": "Using htslib 1.23.1",
                "minimap2": "2.31-r1302",
                "bwa": "0.7.19-r1273",
                "threads": 4,
                "installed_distribution_required": True,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    write_tsv(
        public_environment / "network_isolation.tsv",
        ("field", "value"),
        [
            ["schema_version", "1.0"],
            ["platform", "Darwin/arm64"],
            ["isolation_method", "macos_sandbox_exec_deny_network"],
            ["isolation_scope", "process_tree"],
            ["parent_loopback_control", "reachable"],
            ["isolated_loopback_probe", "blocked"],
            ["probe_target", "parent_loopback_listener"],
            ["probe_error", "PermissionError:1"],
            ["invoking_uid", "501"],
            ["invoking_gid", "20"],
            ["child_uid", "501"],
            ["child_gid", "20"],
            ["network_isolation_verdict", "PASS"],
        ],
    )
    (packet / "verify_bundle.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\necho PASS\n",
        encoding="utf-8",
    )
    rewrite_artifact_manifest(packet)

    publication = tmp_path / "github_publication.json"
    publication.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "release_version": "v0.3.0",
                "git_commit": COMMIT,
                "repository": REPOSITORY,
                "release_tag": "v0.3.0",
                "github_release_url": f"{REPOSITORY}/releases/tag/v0.3.0",
                "github_actions_run_id": RUN_ID,
                "publication_state": "prepublication",
                "verification_state": "verified_prepublication_identity",
                "verified": True,
                "github_api_read_only": True,
                "mutations_performed": False,
                "asset_publication_verified": False,
                "release_absent": True,
                "tag_ref": {
                    "ref": "refs/tags/v0.3.0",
                    "object_type": "tag",
                    "object_sha": "b" * 40,
                },
                "tag_object": {
                    "tag": "v0.3.0",
                    "tag_object_sha": "b" * 40,
                    "target_type": "commit",
                    "peeled_target_sha": COMMIT,
                },
                "hosting_protection": {
                    "supported": True,
                    "enabled": False,
                    "reason": "disabled",
                },
                "release": {
                    "id": None,
                    "url": f"{REPOSITORY}/releases/tag/v0.3.0",
                    "tag_name": "v0.3.0",
                    "target_commitish": COMMIT,
                    "draft": None,
                    "immutable": None,
                    "published_at": None,
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return packet, publication, figures


def test_builds_markdown_docx_and_embeds_verified_packet_figures(tmp_path: Path) -> None:
    packet, publication, source_figures = make_packet(tmp_path)
    output = tmp_path / "report"

    generated = report_builder.generate_report(packet, publication, output)

    assert generated["markdown"].is_file()
    assert generated["docx"].is_file()
    assert generated["assets"].is_dir()
    assert generated["build_provenance"].is_file()
    markdown = generated["markdown"].read_text(encoding="utf-8")
    assert "Five v0.3.0 scientific corrections" in markdown
    assert "AF_alt = N_alt / (N_A + N_C + N_G + N_T)" in markdown
    assert "R_mt:nuclear = mean(D_mt) / mean(D_nuclear windows)" in markdown
    assert "metadata_recorded_utc" in markdown
    assert "macos_sandbox_exec_deny_network" in markdown
    assert "isolated_loopback_probe" in markdown
    assert "blocked" in markdown
    assert "Pinned Python packages" in markdown
    assert "publication state" not in markdown.lower()
    assert "generated before GitHub release creation" in markdown
    assert "github_publication.json" in markdown
    assert COMMIT in markdown
    assert "No simplified replacement chart is generated" in markdown
    assert markdown.count("![Figure") == 2

    manifest = generated["assets"] / "figure_manifest.tsv"
    rows = list(csv.DictReader(manifest.open(encoding="utf-8"), delimiter="\t"))
    assert len(rows) == 2
    assert {row["sha256"] for row in rows} == {digest(path) for path in source_figures}

    provenance = json.loads(generated["build_provenance"].read_text())
    assert provenance["provenance_type"] == "mito_overview_release_report_build"
    assert provenance["git_commit"] == COMMIT
    assert provenance["packet_identity"]["artifacts.sha256"]["sha256"] == digest(
        packet / "artifacts.sha256"
    )
    assert provenance["report_outputs"]["markdown"]["sha256"] == digest(
        generated["markdown"]
    )
    assert provenance["report_outputs"]["docx"]["sha256"] == digest(
        generated["docx"]
    )
    assert provenance["figure_manifest"]["sha256"] == digest(manifest)
    assert {row["packet_sha256"] for row in provenance["figures"]} == {
        digest(path) for path in source_figures
    }
    assert provenance["rendered_page_qa_required"] is True

    with zipfile.ZipFile(generated["docx"]) as archive:
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        embedded_hashes = {hashlib.sha256(archive.read(name)).hexdigest() for name in media}
        document_xml = archive.read("word/document.xml").decode("utf-8")
        settings_xml = archive.read("word/settings.xml").decode("utf-8")
    assert {digest(path) for path in source_figures} <= embedded_hashes
    assert "Five v0.3.0 scientific corrections" in document_xml
    assert "macos_sandbox_exec_deny_network" in document_xml
    assert document_xml.count("w:cantSplit") >= 1
    assert "w:evenAndOddHeaders" in settings_xml
    assert 'w:headerReference w:type="even"' in document_xml
    assert 'w:footerReference w:type="even"' in document_xml


@pytest.mark.parametrize(
    ("target", "field", "value", "message"),
    [
        ("publication", "git_commit", "b" * 40, "identity mismatch"),
        ("run", "validation_profile", "wrong_profile", "validation profile"),
        ("release", "release_version", "v0.3.1", "release must be v0.3.0"),
    ],
)
def test_fails_closed_on_release_identity_drift(
    tmp_path: Path, target: str, field: str, value: str, message: str
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    identity_paths = {
        "run": packet / "run.json",
        "release": packet / "release_identity.json",
    }
    path = publication if target == "publication" else identity_paths[target]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if target != "publication":
        rewrite_artifact_manifest(packet)

    with pytest.raises(report_builder.ReportValidationError, match=message):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_report_rejects_rehashed_official_metadata_mutation(tmp_path: Path) -> None:
    packet, publication, _ = make_packet(tmp_path)
    metadata_path = packet / report_builder.GM11906_SOURCE_METADATA_PACKET_PATH
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload["records"][0]["cell_line"] = "GM00000"
    canonical = json.dumps(
        payload["records"], sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    payload["records_sha256"] = hashlib.sha256(canonical).hexdigest()
    metadata_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rewrite_artifact_manifest(packet)

    with pytest.raises(
        report_builder.ReportValidationError,
        match="official NCBI metadata snapshot SHA-256 mismatch",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_report_rejects_public_cache_output_inventory_below_raw_bytes(
    tmp_path: Path,
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    resource_path = packet / "resource_usage.tsv"
    columns = report_builder.EVIDENCE_COLUMNS["resource_usage.tsv"]
    with resource_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    row = next(item for item in rows if item["case_id"] == "public_cache_prepare")
    row["changed_or_new_output_inventory_bytes"] = "1"
    write_tsv(
        resource_path,
        columns,
        [[item[column] for column in columns] for item in rows],
    )
    rewrite_artifact_manifest(packet)

    with pytest.raises(
        report_builder.ReportValidationError,
        match="changed/new output inventory excludes raw downloads",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_report_rejects_resource_command_or_commit_drift(tmp_path: Path) -> None:
    packet, publication, _ = make_packet(tmp_path)
    command = packet / "commands/unit_known_answer.sh"
    command.write_text("echo altered\n", encoding="utf-8")
    rewrite_artifact_manifest(packet)
    with pytest.raises(
        report_builder.ReportValidationError,
        match="command_sha256 does not bind command_path",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "command-report")

    commit_root = tmp_path / "commit"
    commit_root.mkdir()
    packet, publication, _ = make_packet(commit_root)
    resource_path = packet / "resource_usage.tsv"
    columns = report_builder.EVIDENCE_COLUMNS["resource_usage.tsv"]
    with resource_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    rows[0]["candidate_commit"] = "f" * 40
    write_tsv(
        resource_path,
        columns,
        [[row[column] for column in columns] for row in rows],
    )
    rewrite_artifact_manifest(packet)
    with pytest.raises(
        report_builder.ReportValidationError,
        match="candidate commit mismatch",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "commit-report")


def test_fails_closed_on_nonpass_case(tmp_path: Path) -> None:
    packet, publication, _ = make_packet(tmp_path)
    rows = list(csv.DictReader((packet / "cases.tsv").open(encoding="utf-8"), delimiter="\t"))
    rows[0]["verdict"] = "FAIL"
    write_tsv(
        packet / "cases.tsv",
        report_builder.EVIDENCE_COLUMNS["cases.tsv"],
        [[row[column] for column in report_builder.EVIDENCE_COLUMNS["cases.tsv"]] for row in rows],
    )
    rewrite_artifact_manifest(packet)

    with pytest.raises(report_builder.ReportValidationError, match="Non-PASS"):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_fails_closed_on_cross_platform_difference(tmp_path: Path) -> None:
    packet, publication, _ = make_packet(tmp_path)
    rows = list(
        csv.DictReader(
            (packet / "cross_platform_comparison.tsv").open(encoding="utf-8"),
            delimiter="\t",
        )
    )
    rows[0]["ubuntu_sha256"] = "f" * 64
    rows[0]["verdict"] = "FAIL"
    columns = report_builder.EVIDENCE_COLUMNS["cross_platform_comparison.tsv"]
    write_tsv(
        packet / "cross_platform_comparison.tsv",
        columns,
        [[row[column] for column in columns] for row in rows],
    )
    rewrite_artifact_manifest(packet)

    with pytest.raises(report_builder.ReportValidationError, match="Cross-platform comparison failed"):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_fails_closed_on_report_figure_hash_drift(tmp_path: Path) -> None:
    packet, publication, figures = make_packet(tmp_path)
    with figures[0].open("ab") as handle:
        handle.write(b"tampered")
    rewrite_artifact_manifest(packet)

    with pytest.raises(report_builder.ReportValidationError, match="Figure hash mismatch"):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_fails_closed_without_public_runtime_evidence(tmp_path: Path) -> None:
    packet, publication, _ = make_packet(tmp_path)
    (packet / report_builder.RUNTIME_VERSIONS_PACKET_PATH).unlink()
    rewrite_artifact_manifest(packet)

    with pytest.raises(
        report_builder.ReportValidationError, match="runtime_versions.json"
    ):
        report_builder.generate_report(packet, publication, tmp_path / "report")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("python", "3.12.12", "Python mismatch"),
        ("threads", 8, "exactly four threads"),
        ("installed_distribution_required", False, "installed mito-overview"),
    ],
)
def test_fails_closed_on_invalid_public_runtime(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    path = packet / report_builder.RUNTIME_VERSIONS_PACKET_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rewrite_artifact_manifest(packet)

    with pytest.raises(report_builder.ReportValidationError, match=message):
        report_builder.generate_report(packet, publication, tmp_path / "report")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("platform", "Linux/x86_64", "platform mismatch"),
        ("isolation_method", "curl_canary_only", "isolation_method mismatch"),
        ("isolated_loopback_probe", "reachable", "isolated_loopback_probe mismatch"),
        ("network_isolation_verdict", "FAIL", "network_isolation_verdict mismatch"),
    ],
)
def test_fails_closed_on_invalid_os_level_network_isolation(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    path = packet / report_builder.NETWORK_ISOLATION_PACKET_PATH
    rows = list(csv.DictReader(path.open(encoding="utf-8"), delimiter="\t"))
    for row in rows:
        if row["field"] == field:
            row["value"] = value
            break
    else:
        raise AssertionError(f"fixture lacks isolation field {field}")
    write_tsv(path, ("field", "value"), [[row["field"], row["value"]] for row in rows])
    rewrite_artifact_manifest(packet)

    with pytest.raises(report_builder.ReportValidationError, match=message):
        report_builder.generate_report(packet, publication, tmp_path / "report")


@pytest.mark.parametrize(
    ("state", "verification_state"),
    [
        ("draft", "verified_empty_draft"),
        ("published", "verified_published"),
    ],
)
def test_release_asset_report_rejects_self_referential_publication_states(
    tmp_path: Path, state: str, verification_state: str
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    payload = json.loads(publication.read_text(encoding="utf-8"))
    payload["publication_state"] = state
    payload["verification_state"] = verification_state
    publication.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        report_builder.ReportValidationError,
        match="require a prepublication identity receipt",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "report")


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("verified", False, "not verified"),
        (
            "verification_state",
            "published_transition_recorded",
            "not read-only or has an invalid state",
        ),
    ],
)
def test_report_rejects_unverified_publication_receipt(
    tmp_path: Path, field: str, value: object, message: str
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    payload = json.loads(publication.read_text(encoding="utf-8"))
    payload[field] = value
    publication.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(report_builder.ReportValidationError, match=message):
        report_builder.generate_report(packet, publication, tmp_path / "report")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("github_api_read_only", False),
        ("mutations_performed", True),
        ("asset_publication_verified", True),
        ("release_absent", False),
    ],
)
def test_report_rejects_mutated_or_postpublication_preflight_state(
    tmp_path: Path, field: str, value: object
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    payload = json.loads(publication.read_text(encoding="utf-8"))
    payload[field] = value
    publication.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        report_builder.ReportValidationError,
        match="not read-only or has an invalid state",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_report_rejects_prepublication_receipt_when_release_already_exists(
    tmp_path: Path,
) -> None:
    packet, publication, _ = make_packet(tmp_path)
    payload = json.loads(publication.read_text(encoding="utf-8"))
    payload["release"]["id"] = 7
    publication.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(
        report_builder.ReportValidationError,
        match="prepublication release identity is invalid",
    ):
        report_builder.generate_report(packet, publication, tmp_path / "report")


def test_cli_exposes_optional_pdf_handoff(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--emit-pdf" in result.stdout
    assert "separate rendered-page QA workflow" in " ".join(result.stdout.split())
