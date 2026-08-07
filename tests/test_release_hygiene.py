from __future__ import annotations

import base64
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "check_release_hygiene.py"
SPEC = importlib.util.spec_from_file_location("check_release_hygiene", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
hygiene = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = hygiene
SPEC.loader.exec_module(hygiene)


def make_repo(tmp_path: Path, relative_path: str, payload: bytes) -> Path:
    repo = tmp_path / "repo"
    target = repo / relative_path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", relative_path], cwd=repo, check=True)
    return repo


def test_current_tracked_tree_passes_release_hygiene() -> None:
    assert hygiene.find_violations(Path(__file__).parents[1]) == []


@pytest.mark.parametrize(
    ("relative_path", "payload", "rule"),
    [
        ("examples/report.html", b"sample R20" + b"99-999", "internal_sample_id"),
        (
            "run.txt",
            b"/group/" + base64.b64decode("eGdhaQ==") + b"/work/bioinfo",
            "mcw_group_path",
        ),
        (
            "binary.bam",
            b"prefix\x00/Users/" + b"elopes/private\x00",
            "absolute_user_home_path",
        ),
        (
            "logs/linux.txt",
            b"output=/ho" + b"me/realresearcher/run/output.tsv",
            "absolute_user_home_path",
        ),
        (
            "logs/windows.txt",
            b"output=C:\\Us" + b"ers\\realresearcher\\run\\output.tsv",
            "absolute_user_home_path",
        ),
        (
            "logs/root.txt",
            b"output=/ro" + b"ot/private/output.tsv",
            "absolute_user_home_path",
        ),
        (
            "logs/volume.txt",
            b"output=/Vol" + b"umes/research-volume/private/output.tsv",
            "absolute_local_volume_path",
        ),
        (
            "credentials/key.pem",
            b"----" + b"-BEGIN OPENSSH PRIVATE KEY-" + b"----\n",
            "private_key_header",
        ),
        (
            "credentials/github.txt",
            b"value=gh" + b"p_0123456789abcdefghijklmnopqrstuvwxyz",
            "github_token",
        ),
        (
            "credentials/github-fine.txt",
            b"value=github" + b"_pat_11_0123456789abcdefghijklmnopqrstuvwxyzABCD",
            "github_token",
        ),
        (
            "credentials/aws.txt",
            b"value=AK" + b"IA0123456789ABCDEF",
            "aws_access_key",
        ),
        (
            "config/remote.txt",
            b"url=https://release-bot:V3ryL0ngCred3ntial@" + b"example.org/archive",
            "credential_bearing_url",
        ),
        (
            "config/runtime.env",
            b"API_" + b"TOKEN=live-looking-secret-value",
            "secret_literal_assignment",
        ),
        (
            "config/runtime.yaml",
            b"client_" + b"secret: CorrectHorseBatteryStaple",
            "secret_literal_assignment",
        ),
    ],
)
def test_release_hygiene_rejects_tracked_private_material(
    tmp_path: Path, relative_path: str, payload: bytes, rule: str
) -> None:
    repo = make_repo(tmp_path, relative_path, payload)
    assert hygiene.find_violations(repo) == [f"{relative_path}: {rule}"]


def test_manuscript_wording_is_opt_in_and_not_a_software_release_gate(
    tmp_path: Path,
) -> None:
    repo = make_repo(tmp_path, "paper/draft.md", b"Edited with Chat" + b"GPT")

    assert hygiene.find_violations(repo) == []
    assert hygiene.find_violations(repo, include_manuscript_rules=True) == [
        "paper/draft.md: manuscript_process_wording"
    ]


def test_ignored_private_output_is_not_scanned(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, ".gitignore", b"private/\n")
    private = repo / "private" / ("R20" + "99-999.html")
    private.parent.mkdir()
    private.write_text("/Vol" + "umes/research-volume/work", encoding="utf-8")
    assert hygiene.find_violations(repo) == []


def test_deleted_tracked_file_is_not_scanned(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, "obsolete.txt", b"safe at index time\n")
    (repo / "obsolete.txt").unlink()
    assert hygiene.tracked_paths(repo) == []
    assert hygiene.find_violations(repo) == []


def test_extracted_archive_without_git_scans_every_shipped_file(tmp_path: Path) -> None:
    root = tmp_path / "source-distribution"
    safe = root / "README.md"
    unsafe = root / "payload.bin"
    root.mkdir()
    safe.write_text("public release\n", encoding="utf-8")
    unsafe.write_bytes(b"/Users/" + b"elopes/private")

    assert hygiene.tracked_paths(root) == ["README.md", "payload.bin"]
    assert hygiene.find_violations(root) == ["payload.bin: absolute_user_home_path"]


def test_extracted_sdist_uses_sources_manifest_not_runtime_cache(tmp_path: Path) -> None:
    root = tmp_path / "source-distribution"
    manifest = root / "mito_overview.egg-info" / "SOURCES.txt"
    shipped = root / "README.md"
    runtime_cache = root / "tests" / "__pycache__" / "generated.pyc"
    manifest.parent.mkdir(parents=True)
    runtime_cache.parent.mkdir(parents=True)
    shipped.write_text("public release\n", encoding="utf-8")
    runtime_cache.write_bytes(b"/Users/" + b"elopes/private")
    manifest.write_text(
        "README.md\nmito_overview.egg-info/SOURCES.txt\n",
        encoding="utf-8",
    )

    assert hygiene.tracked_paths(root) == [
        "README.md",
        "mito_overview.egg-info/SOURCES.txt",
    ]
    assert hygiene.find_violations(root) == []


@pytest.mark.parametrize(
    "payload",
    [
        b"macOS example: /Users/" + b"alice/project/output.tsv",
        b"Linux example: /home/" + b"<username>/project/output.tsv",
        b"Windows example: C:" + b"\\Users\\username\\project\\output.tsv",
        b"macOS volume example: /Volumes/institution-private/project/output.tsv",
        b"url=https://user:" + b"REDACTED@example.org/archive",
        b"API_" + b"TOKEN=${API_TOKEN}",
        b"password=" + b"changeme",
        b"client_" + b"secret=<secret>",
        b"TOKEN_" + b"ENV=ZENODO_TOKEN",
        b"CONTROL_" + b'TOKEN="mito-overview-v0.3.0-parent-control"',
    ],
)
def test_documented_placeholders_and_control_values_are_safe(
    tmp_path: Path, payload: bytes
) -> None:
    repo = make_repo(tmp_path, "safe-example.txt", payload)
    assert hygiene.find_violations(repo) == []


def test_cli_does_not_echo_secret_payload(tmp_path: Path) -> None:
    payload = b"API_" + b"TOKEN=do-not-print-this-credential"
    repo = make_repo(tmp_path, "config.env", payload)

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(repo)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "config.env: secret_literal_assignment" in result.stdout
    assert "do-not-print" not in result.stdout
    assert "do-not-print" not in result.stderr
