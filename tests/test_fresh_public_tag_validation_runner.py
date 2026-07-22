from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import textwrap
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).parents[1]
RUNNER = ROOT / "scripts" / "run_fresh_public_tag_validation_v0.3.0.sh"
PUBLIC_FIXTURE_URL = "https://github.com/fixture/mito-overview"
ASSET_SOURCE_NAMES = {
    "mito-overview-v0.3.0-validation.zip",
    "MitoOverview_v0.3.0_release_validation_report.md",
    "MitoOverview_v0.3.0_release_validation_report.docx",
    "MitoOverview_v0.3.0_release_validation_report.pdf",
    "MitoOverview_v0.3.0_release_validation_report_assets.tar.gz",
    "mito-overview-v0.3.0-verification.json",
    "RELEASE_NOTES_v0.3.0.md",
    "mito-overview-v0.3.0-environment.txt",
    "mito-overview-v0.3.0-environment-locks.tar.gz",
}
CANONICAL_ASSET_NAMES = ASSET_SOURCE_NAMES | {
    "mito_overview-0.3.0-py3-none-any.whl",
    "mito_overview-0.3.0.tar.gz",
    "SHA256SUMS",
}
REPORT_ASSET_NAMES = ASSET_SOURCE_NAMES - {
    "mito-overview-v0.3.0-validation.zip",
    "mito-overview-v0.3.0-verification.json",
}


def _write_executable(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _build_fixture_repository(root: Path, *, report_pages: int) -> tuple[Path, str, str]:
    repository = root / "fixture-source"
    repository.mkdir(parents=True)
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)

    smoke = "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n"
    for name in (
        "smoke_public_pipeline.sh",
        "smoke_public_pipeline_shortread.sh",
        "smoke_public_pipeline_longread_nomethyl.sh",
        "smoke_standalone_minimal.sh",
    ):
        _write_executable(repository / "tests" / name, smoke)

    builder = f"""\
#!/usr/bin/env bash
set -euo pipefail
target="$1"
mkdir -p "${{target}}/report"
for index in $(seq 1 {report_pages}); do
  if [[ "${{index}}" -eq 1 ]]; then
    name="01_mito_qc.html"
  elif [[ "${{index}}" -eq 14 ]]; then
    name="14_mito_mvtool_annotation.html"
  else
    name="$(printf '%02d_fixture.html' "${{index}}")"
  fi
  printf '<html><body>fixture %s</body></html>\n' "${{index}}" > "${{target}}/report/${{name}}"
done
"""
    _write_executable(repository / "scripts" / "build_public_example_bundle.sh", builder)
    _write_executable(
        repository / "scripts" / "build_public_shortread_example_bundle.sh", builder
    )
    _write_executable(
        repository / "scripts" / "run_mito_pipeline.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\nprintf 'validate\\n'\n",
    )
    shutil.copyfile(
        ROOT / "scripts" / "sanitize_validation_evidence.py",
        repository / "scripts" / "sanitize_validation_evidence.py",
    )
    shutil.copyfile(
        ROOT / "scripts" / "safe_extract_validation_zip.py",
        repository / "scripts" / "safe_extract_validation_zip.py",
    )
    shutil.copyfile(
        ROOT / "scripts" / "verify_release_asset_identity_v0.3.0.py",
        repository / "scripts" / "verify_release_asset_identity_v0.3.0.py",
    )

    _git(repository, "add", ".")
    _git(
        repository,
        "-c",
        "user.name=MitoOverview fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-m",
        "release validation fixture",
    )
    _git(repository, "branch", "-M", "main")
    _git(
        repository,
        "-c",
        "user.name=MitoOverview fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "tag",
        "-a",
        "v0.3.0",
        "-m",
        "MitoOverview v0.3.0 fixture",
    )
    return (
        repository,
        _git(repository, "rev-parse", "HEAD"),
        _git(repository, "rev-parse", "refs/tags/v0.3.0^{tag}"),
    )


def _build_command_shims(root: Path, fixture_repository: Path) -> Path:
    shim_root = root / "shims"
    shim_root.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    _write_executable(
        shim_root / "git",
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${{1:-}}" == clone && "${{2:-}}" == --no-checkout && "${{3:-}}" == {shlex.quote(PUBLIC_FIXTURE_URL)} ]]; then
              {shlex.quote(real_git)} clone --no-checkout {shlex.quote(str(fixture_repository))} "$4"
              {shlex.quote(real_git)} -C "$4" remote set-url origin "$3"
              exit 0
            fi
            exec {shlex.quote(real_git)} "$@"
            """
        ),
    )

    fake_python = textwrap.dedent(
        f"""\
        #!{sys.executable}
        import os
        import sys
        import tarfile
        from pathlib import Path

        REAL_PYTHON = {sys.executable!r}
        args = sys.argv[1:]
        if args == ["-"]:
            sys.stdin.read()
            raise SystemExit(0)
        if args[:2] == ["-m", "build"]:
            output = Path(args[args.index("--outdir") + 1])
            output.mkdir(parents=True, exist_ok=True)
            (output / "mito_overview-0.3.0-py3-none-any.whl").write_bytes(b"fixture wheel\\n")
            with tarfile.open(output / "mito_overview-0.3.0.tar.gz", "w:gz") as archive:
                directory = tarfile.TarInfo("mito_overview-0.3.0")
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o755
                archive.addfile(directory)
            raise SystemExit(0)
        if args[:2] == ["-m", "venv"]:
            target = Path(args[-1]) / "bin" / "python"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(Path(__file__).resolve())
            raise SystemExit(0)
        if args[:2] in (["-m", "pip"], ["-m", "pytest"]):
            raise SystemExit(0)
        if "mito_overview.cli" in args and "--list-steps" in args:
            print("validate")
            raise SystemExit(0)
        if "-c" in args:
            raise SystemExit(0)
        os.execv(REAL_PYTHON, [REAL_PYTHON, *args])
        """
    )
    _write_executable(shim_root / "fixture-python", fake_python)
    _write_executable(
        shim_root / "samtools",
        "#!/usr/bin/env bash\nprintf 'samtools 1.23.1\\nUsing htslib 1.23.1\\n'\n",
    )
    _write_executable(
        shim_root / "minimap2",
        "#!/usr/bin/env bash\nprintf '2.31-r1302\\n'\n",
    )
    _write_executable(
        shim_root / "bwa",
        "#!/usr/bin/env bash\nprintf 'Version: 0.7.19-r1273\\n' >&2\n",
    )
    return shim_root


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _build_release_asset_source(
    root: Path,
    final_sha: str,
    *,
    identity_sha: str | None = None,
    substitute_asset: str | None = None,
) -> Path:
    source = root / "release-asset-source"
    source.mkdir()
    bound_sha = identity_sha or final_sha
    (source / "MitoOverview_v0.3.0_release_validation_report.md").write_text(
        f"# MitoOverview v0.3.0 release validation\n\nCommit: `{bound_sha}`\n",
        encoding="utf-8",
    )
    (source / "RELEASE_NOTES_v0.3.0.md").write_text(
        f"# MitoOverview v0.3.0\n\nValidated commit: `{bound_sha}`\n",
        encoding="utf-8",
    )
    (source / "mito-overview-v0.3.0-environment.txt").write_text(
        f"release_version=v0.3.0\ngit_commit={bound_sha}\n",
        encoding="utf-8",
    )
    with zipfile.ZipFile(
        source / "MitoOverview_v0.3.0_release_validation_report.docx", "w"
    ) as document:
        document.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        document.writestr(
            "word/document.xml",
            f'<document><body><p>MitoOverview v0.3.0 {bound_sha}</p></body></document>',
        )
    (source / "MitoOverview_v0.3.0_release_validation_report.pdf").write_bytes(
        (
            "%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\n"
            f"% MitoOverview v0.3.0 {bound_sha}\n%%EOF\n"
        ).encode("ascii")
    )

    def write_tar(path: Path, files: dict[str, bytes]) -> None:
        with tarfile.open(path, "w:gz") as archive:
            for name, payload in sorted(files.items()):
                info = tarfile.TarInfo(name)
                info.size = len(payload)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(payload))

    write_tar(
        source / "mito-overview-v0.3.0-environment-locks.tar.gz",
        {
            "environment.yml": (
                f"name: mito-overview-v0.3.0\n# commit: {bound_sha}\n"
            ).encode("ascii")
        },
    )

    run = {
        "schema_version": "2.0",
        "validation_profile": "github_release_validation_v1",
        "release_version": "v0.3.0",
        "git_commit": bound_sha,
        "repository": PUBLIC_FIXTURE_URL,
    }
    release_identity = {
        **run,
        "package_name": "mito-overview",
        "package_version": "0.3.0",
    }
    figure_payload = b"\x89PNG\r\n\x1a\nfixture-figure\n"
    packet_files = {
        "run.json": (json.dumps(run, sort_keys=True) + "\n").encode("utf-8"),
        "release_identity.json": (
            json.dumps(release_identity, sort_keys=True) + "\n"
        ).encode("utf-8"),
        "figures/source.png": figure_payload,
    }
    manifest_text = "".join(
        f"{_sha256_bytes(payload)}  {name}\n"
        for name, payload in sorted(packet_files.items())
    )
    packet_files["artifacts.sha256"] = manifest_text.encode("ascii")
    packet_files["verify_bundle.sh"] = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "cd \"$(dirname \"$0\")\"\n"
        "shasum -a 256 -c artifacts.sha256\n"
    ).encode("ascii")
    archive_path = source / "mito-overview-v0.3.0-validation.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, payload in sorted(packet_files.items()):
            archive.writestr(name, payload)

    report_root_name = "MitoOverview_v0.3.0_release_validation_report_assets"
    report_md = source / "MitoOverview_v0.3.0_release_validation_report.md"
    report_docx = source / "MitoOverview_v0.3.0_release_validation_report.docx"
    report_pdf = source / "MitoOverview_v0.3.0_release_validation_report.pdf"

    def content_record(path: Path, name: str) -> dict[str, object]:
        return {
            "name": name,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    figure_name = f"{report_root_name}/figure01.png"
    figure_hash = _sha256_bytes(figure_payload)
    manifest_name = f"{report_root_name}/figure_manifest.tsv"
    manifest_payload = (
        "figure_number\tdataset\tcase_id\treport_asset\tpacket_path\tsha256\twidth_px\theight_px\tsource_inventory\n"
        f"1\tGM11906\tcase\t{figure_name}\tfigures/source.png\t{figure_hash}\t800\t450\tvisual.tsv\n"
    ).encode("ascii")
    figure_row = {
        "name": figure_name,
        "bytes": len(figure_payload),
        "sha256": figure_hash,
        "figure_number": 1,
        "dataset": "GM11906",
        "case_id": "case",
        "packet_path": "figures/source.png",
        "packet_sha256": figure_hash,
        "width_px": 800,
        "height_px": 450,
        "source_inventory": "visual.tsv",
    }
    build = {
        "schema_version": "1.0",
        "provenance_type": "mito_overview_release_report_build",
        "repository": PUBLIC_FIXTURE_URL,
        "release_version": "v0.3.0",
        "release_tag": "v0.3.0",
        "git_commit": bound_sha,
        "validation_profile": "github_release_validation_v1",
        "packet_identity": {
            name: {
                "name": name,
                "bytes": len(packet_files[name]),
                "sha256": _sha256_bytes(packet_files[name]),
            }
            for name in ("run.json", "release_identity.json", "artifacts.sha256")
        },
        "publication_input": {"name": "fixture.json", "bytes": 1, "sha256": "0" * 64},
        "report_outputs": {
            "markdown": content_record(report_md, report_md.name),
            "docx": content_record(report_docx, report_docx.name),
        },
        "figure_manifest": {
            "name": manifest_name,
            "bytes": len(manifest_payload),
            "sha256": _sha256_bytes(manifest_payload),
        },
        "figures": [figure_row],
        "pdf_included": False,
        "rendered_page_qa_required": True,
    }
    build_name = f"{report_root_name}/report_build_provenance.json"
    build_payload = (json.dumps(build, indent=2, sort_keys=True) + "\n").encode("utf-8")
    page_name = f"{report_root_name}/rendered_pages/page-1.png"
    page_payload = b"\x89PNG\r\n\x1a\nfixture-page\n"
    page_row = {
        "name": page_name,
        "bytes": len(page_payload),
        "sha256": _sha256_bytes(page_payload),
        "page_number": 1,
        "width_px": 1275,
        "height_px": 1650,
        "visual_review_status": "PASS",
    }
    report_outputs = {
        "markdown": content_record(report_md, report_md.name),
        "docx": content_record(report_docx, report_docx.name),
        "pdf": content_record(report_pdf, report_pdf.name),
    }
    final_provenance = {
        "schema_version": "1.0",
        "provenance_type": "mito_overview_finalized_release_report",
        "repository": PUBLIC_FIXTURE_URL,
        "release_version": "v0.3.0",
        "release_tag": "v0.3.0",
        "git_commit": bound_sha,
        "validation_profile": "github_release_validation_v1",
        "validation_archive": {
            "name": archive_path.name,
            "bytes": archive_path.stat().st_size,
            "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        },
        "packet_verification": {"name": "fixture.json", "bytes": 1, "sha256": "0" * 64},
        "packet_verification_verdict": "PASS",
        "packet_verifier_executed": True,
        "packet_artifacts_manifest_sha256": _sha256_bytes(packet_files["artifacts.sha256"]),
        "report_build_provenance": {
            "name": build_name,
            "bytes": len(build_payload),
            "sha256": _sha256_bytes(build_payload),
        },
        "report_outputs": report_outputs,
        "figure_manifest": build["figure_manifest"],
        "figures": [figure_row],
        "rendered_page_qa": {
            "status": "PASS",
            "all_pages_inspected": True,
            "reviewer": "fixture-reviewer",
            "page_count": 1,
            "pdf_page_count": 1,
            "page_count_matches_pdf": True,
            "source_docx_sha256": report_outputs["docx"]["sha256"],
            "rendered_pdf_sha256": report_outputs["pdf"]["sha256"],
            "pages": [page_row],
        },
    }
    provenance_name = f"{report_root_name}/report_provenance.json"
    provenance_payload = (
        json.dumps(final_provenance, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    report_archive = source / "MitoOverview_v0.3.0_release_validation_report_assets.tar.gz"
    write_tar(
        report_archive,
        {
            manifest_name: manifest_payload,
            figure_name: figure_payload,
            build_name: build_payload,
            provenance_name: provenance_payload,
            page_name: page_payload,
        },
    )

    report_assets = []
    for name in sorted(REPORT_ASSET_NAMES):
        path = source / name
        report_assets.append(
            {
                "name": name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
        )
    verification = {
        "schema_version": "2.0",
        "validation_profile": "github_release_validation_v1",
        "evidence_type": "release_validation_archive_verification",
        "verdict": "PASS",
        "release_version": "v0.3.0",
        "git_commit": bound_sha,
        "audit_zip": archive_path.name,
        "audit_zip_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
        "verifier_runs": ["packet_root", "fresh_audit_zip_extraction"],
        "report_build_provenance": {
            "schema_version": "1.0",
            "provenance_type": "release_report_provenance_binding",
            "repository": PUBLIC_FIXTURE_URL,
            "release_version": "v0.3.0",
            "release_tag": "v0.3.0",
            "git_commit": bound_sha,
            "validation_zip_sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            "report_provenance_archive_path": provenance_name,
            "report_provenance_sha256": _sha256_bytes(provenance_payload),
            "report_asset_archive_sha256": hashlib.sha256(report_archive.read_bytes()).hexdigest(),
            "report_outputs": report_outputs,
            "figure_count": 1,
            "rendered_page_count": 1,
            "visual_review_status": "PASS",
        },
        "report_asset_manifest": {
            "schema_version": "1.0",
            "manifest_type": "report_asset_manifest",
            "repository": PUBLIC_FIXTURE_URL,
            "repository_slug": "fixture/mito-overview",
            "release_version": "v0.3.0",
            "release_tag": "v0.3.0",
            "git_commit": bound_sha,
            "assets": report_assets,
        },
    }
    (source / "mito-overview-v0.3.0-verification.json").write_text(
        json.dumps(verification, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if substitute_asset is not None:
        with (source / substitute_asset).open("ab") as handle:
            handle.write(b"substituted-after-manifest\n")
    return source


def _execute_fixture_runner(
    tmp_path: Path,
    *,
    report_pages: int,
    identity_sha: str | None = None,
    substitute_asset: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path, str, str]:
    fixture, final_sha, tag_object_sha = _build_fixture_repository(
        tmp_path, report_pages=report_pages
    )
    shim_root = _build_command_shims(tmp_path, fixture)
    asset_source = _build_release_asset_source(
        tmp_path,
        final_sha,
        identity_sha=identity_sha,
        substitute_asset=substitute_asset,
    )
    work_root = tmp_path / "release-work"
    evidence_root = tmp_path / "release-evidence"
    environment = os.environ.copy()
    environment["PATH"] = f"{shim_root}{os.pathsep}{environment['PATH']}"
    environment["MITO_OVERVIEW_PYTHON"] = "fixture-python"
    completed = subprocess.run(
        [
            "bash",
            str(RUNNER),
            PUBLIC_FIXTURE_URL,
            final_sha,
            str(work_root),
            str(evidence_root),
            str(asset_source),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return completed, work_root, evidence_root, final_sha, tag_object_sha


def test_runner_is_valid_shell_and_encodes_all_required_release_gates() -> None:
    subprocess.run(["bash", "-n", str(RUNNER)], check=True)
    text = RUNNER.read_text(encoding="utf-8")

    required_cases = {
        "public_https_tag_clone",
        "annotated_tag_identity",
        "clean_tag_checkout",
        "locked_environment",
        "wheel_sdist_build",
        "installed_cli",
        "installed_sdist_cli",
        "unit_tests",
        "smoke_longread",
        "smoke_shortread",
        "smoke_longread_nomethyl",
        "smoke_standalone",
        "example_builders",
        "release_asset_semantic_identity",
        "trusted_release_assets",
    }
    for case_id in required_cases:
        assert f"run_case {case_id} " in text
    for required in (
        "git clone --no-checkout",
        "cat-file -t refs/tags/${TAG}",
        "refs/tags/${TAG}^{commit}",
        "python=3.12.13",
        "samtools=1.23.1",
        "mito_overview-0.3.0.tar.gz",
        "-m pytest -q",
        "smoke_public_pipeline.sh",
        "smoke_public_pipeline_shortread.sh",
        "smoke_public_pipeline_longread_nomethyl.sh",
        "smoke_standalone_minimal.sh",
        "build_public_example_bundle.sh",
        "build_public_shortread_example_bundle.sh",
        "longread/report/01_mito_qc.html",
        "longread/report/14_mito_mvtool_annotation.html",
        "shortread/report/01_mito_qc.html",
        "shortread/report/14_mito_mvtool_annotation.html",
        "sanitize_validation_evidence.py",
        "evidence.sha256",
        "fresh_public_tag_validation.json",
        "trusted_release_assets.json",
        "release_asset_semantic_identity.json",
        "safe_extract_validation_zip.py",
        "verify_release_asset_identity_v0.3.0.py",
        "RELEASE_ASSET_SOURCE",
    ):
        assert required in text
    assert "Zenodo" not in text
    assert "DOI" not in text
    assert "report/index.html" not in text


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["http://github.com/owner/repo", "1" * 40, "work", "evidence"],
        ["https://github.com/owner/repo", "short", "work", "evidence"],
    ],
)
def test_runner_rejects_invalid_invocations_without_network(
    tmp_path: Path, arguments: list[str]
) -> None:
    resolved = [
        str(tmp_path / value) if value in {"work", "evidence"} else value
        for value in arguments
    ]
    completed = subprocess.run(
        ["bash", str(RUNNER), *resolved],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2


def test_runner_success_path_emits_hash_verified_tag_bound_evidence(tmp_path: Path) -> None:
    completed, work_root, evidence_root, final_sha, tag_object_sha = (
        _execute_fixture_runner(tmp_path, report_pages=14)
    )
    assert completed.returncode == 0, completed.stderr

    with (evidence_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 15
    assert len({row["case_id"] for row in rows}) == 15
    assert {row["verdict"] for row in rows} == {"PASS"}

    receipt = json.loads(
        (evidence_root / "fresh_public_tag_validation.json").read_text(encoding="utf-8")
    )
    assert receipt["verified"] is True
    assert receipt["verdict"] == "PASS"
    assert receipt["case_count"] == 15
    assert receipt["git_commit"] == final_sha
    assert receipt["tag_object_sha"] == tag_object_sha
    assert receipt["trusted_asset_count"] == len(CANONICAL_ASSET_NAMES)
    environment_lines = (evidence_root / "environment.txt").read_text(
        encoding="utf-8"
    ).splitlines()
    assert any(line.startswith("operating_system=") for line in environment_lines)
    assert any(line.startswith("architecture=") for line in environment_lines)

    semantic = json.loads(
        (evidence_root / "release_asset_semantic_identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert semantic["verified"] is True
    assert semantic["git_commit"] == final_sha
    assert semantic["repository"] == PUBLIC_FIXTURE_URL
    assert semantic["report_asset_count"] == len(REPORT_ASSET_NAMES)
    assert {row["name"] for row in semantic["report_assets"]} == REPORT_ASSET_NAMES

    manifest = evidence_root / "evidence.sha256"
    assert receipt["evidence_manifest_sha256"] == hashlib.sha256(
        manifest.read_bytes()
    ).hexdigest()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        evidence_file = evidence_root / relative
        assert hashlib.sha256(evidence_file.read_bytes()).hexdigest() == expected
        try:
            evidence_text = evidence_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert str(work_root) not in evidence_text
        assert str(evidence_root) not in evidence_text

    trusted_path = evidence_root / "trusted_release_assets.json"
    trusted = json.loads(trusted_path.read_text(encoding="utf-8"))
    assert receipt["trusted_asset_manifest_sha256"] == hashlib.sha256(
        trusted_path.read_bytes()
    ).hexdigest()
    assert trusted["git_commit"] == final_sha
    assert trusted["tag_object_sha"] == tag_object_sha
    assert trusted["asset_count"] == len(CANONICAL_ASSET_NAMES)
    assert [item["name"] for item in trusted["assets"]] == sorted(
        CANONICAL_ASSET_NAMES
    )
    release_assets = work_root / "release-assets"
    assert {path.name for path in release_assets.iterdir()} == CANONICAL_ASSET_NAMES
    for item in trusted["assets"]:
        path = release_assets / item["name"]
        assert path.stat().st_size == item["size"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_runner_rejects_incomplete_example_inventory_without_pass_receipt(
    tmp_path: Path,
) -> None:
    completed, _, evidence_root, _, _ = _execute_fixture_runner(
        tmp_path, report_pages=13
    )
    assert completed.returncode != 0
    assert not (evidence_root / "fresh_public_tag_validation.json").exists()
    with (evidence_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[-1]["case_id"] == "example_builders"
    assert rows[-1]["verdict"] == "FAIL"


def test_runner_rejects_valid_but_stale_prior_commit_asset_bundle(
    tmp_path: Path,
) -> None:
    completed, _, evidence_root, _, _ = _execute_fixture_runner(
        tmp_path,
        report_pages=14,
        identity_sha="f" * 40,
    )
    assert completed.returncode != 0
    assert "identity mismatch for git_commit" in completed.stderr
    assert not (evidence_root / "fresh_public_tag_validation.json").exists()
    with (evidence_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[-1]["case_id"] == "release_asset_semantic_identity"
    assert rows[-1]["verdict"] == "FAIL"


@pytest.mark.parametrize(
    "asset_name",
    sorted(REPORT_ASSET_NAMES | {"mito-overview-v0.3.0-validation.zip"}),
)
def test_runner_rejects_asset_substitution_after_semantic_manifest(
    tmp_path: Path,
    asset_name: str,
) -> None:
    completed, _, evidence_root, _, _ = _execute_fixture_runner(
        tmp_path,
        report_pages=14,
        substitute_asset=asset_name,
    )
    assert completed.returncode != 0
    assert (
        "SHA-256 mismatch" in completed.stderr
        or "size mismatch" in completed.stderr
        or "audit_zip_sha256" in completed.stderr
        or "Safe ZIP extraction failed" in completed.stderr
    )
    assert not (evidence_root / "fresh_public_tag_validation.json").exists()
    with (evidence_root / "cases.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert rows[-1]["case_id"] == "release_asset_semantic_identity"
    assert rows[-1]["verdict"] == "FAIL"
