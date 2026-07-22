from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


RUNNER = Path(__file__).parents[1] / "scripts" / "run_release_validation_v0.3.0.sh"
PACKET_BUILDER = RUNNER.with_name("build_validation_packet_v0.3.0.py")
REPOSITORY = "elissonnog/mito-overview"
DEFAULT_IDS = {
    "MITO_OVERVIEW_GITHUB_RUN_ID": "4001",
    "MITO_OVERVIEW_PR_NUMBER": "3",
    "MITO_OVERVIEW_PR_RUN_ID": "4002",
    "MITO_OVERVIEW_PUBLIC_RUN_ID": "4003",
}


def invoke(
    tmp_path: Path,
    *extra: str,
    environment: dict[str, str | None] | None = None,
) -> subprocess.CompletedProcess[str]:
    paths = [
        str(tmp_path / "validation"),
        str(tmp_path / "cache"),
        str(tmp_path / "packet"),
        str(tmp_path / "mito-overview-v0.3.0-validation.zip"),
    ]
    env = os.environ.copy()
    env.pop("MITO_OVERVIEW_ARCHIVE_DOI", None)
    env.pop("MITO_OVERVIEW_ZENODO_RESERVATION_EVIDENCE", None)
    env.update(DEFAULT_IDS)
    for name, value in (environment or {}).items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    return subprocess.run(
        ["bash", str(RUNNER), *paths, *extra],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def run_git(repo: Path, *arguments: str) -> str:
    completed = subprocess.run(
        [shutil.which("git") or "git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def create_fake_gh_harness(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    repo = tmp_path / "fixture-repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(RUNNER, scripts / RUNNER.name)
    shutil.copy2(PACKET_BUILDER, scripts / PACKET_BUILDER.name)
    (scripts / "check_release_hygiene.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    locks = repo / "locks"
    locks.mkdir()
    for platform in ("linux-64", "osx-64", "osx-arm64"):
        (locks / f"environment-{platform}.yml").write_text(
            "fixture\n", encoding="utf-8"
        )
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.name", "Runner Test")
    run_git(repo, "config", "user.email", "runner-test@example.org")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "runner fixture base")
    run_git(repo, "branch", "-M", "main")
    run_git(repo, "checkout", "-q", "-b", "codex/preprint-hardening-v0.3.0")
    (repo / "RELEASE_CANDIDATE").write_text("v0.3.0\n", encoding="utf-8")
    run_git(repo, "add", "RELEASE_CANDIDATE")
    run_git(repo, "commit", "-q", "-m", "runner fixture release head")
    pr_head = run_git(repo, "rev-parse", "HEAD")
    run_git(repo, "checkout", "-q", "main")
    run_git(
        repo,
        "merge",
        "-q",
        "--no-ff",
        "codex/preprint-hardening-v0.3.0",
        "-m",
        "Merge runner fixture release head",
    )
    candidate = run_git(repo, "rev-parse", "HEAD")
    parent_fields = run_git(repo, "rev-list", "--parents", "-n", "1", candidate).split()
    assert len(parent_fields) == 3
    pr_base = parent_fields[1]
    assert parent_fields[2] == pr_head
    candidate_tree = run_git(repo, "rev-parse", f"{candidate}^{{tree}}")

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    write_executable(
        fake_bin / "git",
        "#!/usr/bin/env bash\n"
        "if [[ ${1:-} == -C && ${3:-} == rev-parse && ${4:-} == HEAD:paper ]]; then\n"
        "  observed=bfb5664db9c8b43ed5de33ecbddef88071fc6378\n"
        "  [[ ${FAKE_GH_MODE:-valid} == wrong_paper_tree ]] && observed=ffffffffffffffffffffffffffffffffffffffff\n"
        "  printf '%s\\n' \"$observed\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ ${1:-} == ls-remote ]]; then\n"
        "  observed=${FAKE_CANDIDATE_COMMIT}\n"
        "  [[ ${FAKE_GH_MODE:-valid} == wrong_public_main ]] && observed=ffffffffffffffffffffffffffffffffffffffff\n"
        "  printf '%s\\trefs/heads/main\\n' \"$observed\"\n"
        "  exit 0\n"
        "fi\n"
        "if [[ ${1:-} == clone ]]; then\n"
        "  echo 'intentional fake-git clone stop' >&2\n"
        "  exit 97\n"
        "fi\n"
        f"exec {real_git!s} \"$@\"\n",
    )

    gh_source = f"""#!{sys.executable}
import hashlib
import json
import os
import sys
from pathlib import Path

repository = {REPOSITORY!r}
api_root = f"https://api.github.com/repos/{{repository}}"
html_root = f"https://github.com/{{repository}}"
candidate = os.environ["FAKE_CANDIDATE_COMMIT"]
push_run_id = int(os.environ["MITO_OVERVIEW_GITHUB_RUN_ID"])
pr_number = int(os.environ["MITO_OVERVIEW_PR_NUMBER"])
pr_run_id = int(os.environ["MITO_OVERVIEW_PR_RUN_ID"])
public_run_id = int(os.environ["MITO_OVERVIEW_PUBLIC_RUN_ID"])
mode = os.environ.get("FAKE_GH_MODE", "valid")
pr_head = os.environ["FAKE_PR_HEAD_COMMIT"]
pr_base = os.environ["FAKE_PR_BASE_COMMIT"]
candidate_tree = os.environ["FAKE_CANDIDATE_TREE"]
pr_branch = "codex/preprint-hardening-v0.3.0"
log_path = Path(os.environ["FAKE_GH_LOG"])
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")

def repository_object():
    return {{
        "full_name": repository,
        "html_url": html_root,
        "url": api_root,
    }}

def run_record(run_id, *, event, workflow, path, head_sha, head_branch):
    return {{
        "id": run_id,
        "run_attempt": 1,
        "name": workflow,
        "event": event,
        "head_branch": head_branch,
        "path": path,
        "head_sha": head_sha,
        "status": "completed",
        "conclusion": "success",
        "html_url": f"{{html_root}}/actions/runs/{{run_id}}",
        "url": f"{{api_root}}/actions/runs/{{run_id}}",
        "jobs_url": f"{{api_root}}/actions/runs/{{run_id}}/jobs",
        "repository": repository_object(),
        "head_repository": repository_object(),
    }}

job_matrix = (
    ("ubuntu-24.04", "Unit and synthetic tests (ubuntu-24.04)"),
    ("macos-15-intel", "Unit and synthetic tests (macos-15-intel)"),
    ("macos-15", "Unit and synthetic tests (macos-15)"),
)

def jobs_record(run_id, head_sha):
    run_url = f"{{html_root}}/actions/runs/{{run_id}}"
    run_api = f"{{api_root}}/actions/runs/{{run_id}}"
    jobs = []
    for index, (label, name) in enumerate(job_matrix, start=1):
        job_id = run_id * 10 + index
        jobs.append({{
            "id": job_id,
            "run_id": run_id,
            "run_attempt": 1,
            "workflow_name": "smoke-tests",
            "head_sha": head_sha,
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "labels": [label],
            "html_url": f"{{run_url}}/job/{{job_id}}",
            "url": f"{{api_root}}/actions/jobs/{{job_id}}",
            "run_url": run_api,
        }})
    return {{"total_count": len(jobs), "jobs": jobs}}

args = sys.argv[1:]
if not args:
    raise SystemExit(2)
if args[0] == "api":
    endpoint = args[-1]
    if endpoint == f"repos/{{repository}}/actions/runs/{{push_run_id}}":
        payload = run_record(
            push_run_id,
            event="push",
            workflow="smoke-tests",
            path=".github/workflows/smoke-tests.yml",
            head_sha=candidate,
            head_branch="main",
        )
    elif endpoint == f"repos/{{repository}}/actions/runs/{{push_run_id}}/jobs?filter=latest&per_page=100":
        payload = jobs_record(push_run_id, candidate)
    elif endpoint == f"repos/{{repository}}/actions/runs/{{push_run_id}}/artifacts?per_page=100":
        payload = {{
            "artifacts": [
                {{
                    "name": f"resolved-environment-{{platform}}-{{push_run_id}}",
                    "expired": False,
                    "workflow_run": {{"id": push_run_id}},
                }}
                for platform in ("linux-64", "osx-64", "osx-arm64")
            ]
        }}
    elif endpoint == f"repos/{{repository}}/pulls/{{pr_number}}":
        head_repo = repository_object()
        if mode == "wrong_pr_identity":
            head_repo = {{**head_repo, "full_name": "someone-else/mito-overview"}}
        payload = {{
            "number": pr_number,
            "state": "closed",
            "merged": True,
            "merged_at": "2026-07-21T12:00:00Z",
            "merge_commit_sha": candidate,
            "url": f"{{api_root}}/pulls/{{pr_number}}",
            "html_url": f"{{html_root}}/pull/{{pr_number}}",
            "issue_url": f"{{api_root}}/issues/{{pr_number}}",
            "comments_url": f"{{api_root}}/issues/{{pr_number}}/comments",
            "base": {{"ref": "main", "sha": pr_base, "repo": repository_object()}},
            "head": {{"ref": pr_branch, "sha": pr_head, "repo": head_repo}},
        }}
    elif endpoint == f"repos/{{repository}}/issues/{{pr_number}}/comments?per_page=100":
        comments = []
        for index, role in enumerate(
            ("release_engineering", "bioinformatics", "reproducibility"), start=1
        ):
            comment_id = 7000 + index
            audit = {{
                "schema_version": "1.1",
                "review_method": "read_only_agent_role_audit",
                "audit_instance_id": f"00000000-0000-4000-8000-{{index:012d}}",
                "role": role,
                "reviewed_commit": pr_head,
                "reviewed_tree": candidate_tree,
                "verdict": "PASS",
                "unresolved_blockers": 0,
                "summary": f"{{role}} fixture audit passed.",
            }}
            comments.append({{
                "id": comment_id,
                "url": f"{{api_root}}/issues/comments/{{comment_id}}",
                "html_url": (
                    f"{{html_root}}/pull/{{pr_number}}#issuecomment-{{comment_id}}"
                ),
                "issue_url": f"{{api_root}}/issues/{{pr_number}}",
                "user": {{
                    "login": "elissonnog",
                    "html_url": "https://github.com/elissonnog",
                }},
                "author_association": "OWNER",
                "created_at": f"2026-07-21T10:0{{index}}:00Z",
                "updated_at": f"2026-07-21T10:0{{index}}:00Z",
                "body": (
                    "<!-- mito-overview-read-only-audit-v1 -->\\n"
                    "```json\\n"
                    + json.dumps(audit, indent=2)
                    + "\\n```"
                ),
            }})
        payload = [comments]
    elif endpoint == f"repos/{{repository}}/actions/runs/{{pr_run_id}}":
        observed_head = candidate if mode == "pr_run_uses_merge_sha" else pr_head
        payload = run_record(
            pr_run_id,
            event="pull_request",
            workflow="smoke-tests",
            path=".github/workflows/smoke-tests.yml",
            head_sha=observed_head,
            head_branch=pr_branch,
        )
        payload["pull_requests"] = [{{
            "number": pr_number,
            "url": f"{{api_root}}/pulls/{{pr_number}}",
            "head": {{
                "ref": pr_branch,
                "sha": pr_head,
                "repo": {{"name": "mito-overview", "url": api_root}},
            }},
            "base": {{
                "ref": "main",
                "sha": pr_base,
                "repo": {{"name": "mito-overview", "url": api_root}},
            }},
        }}]
    elif endpoint == f"repos/{{repository}}/actions/runs/{{pr_run_id}}/jobs?filter=latest&per_page=100":
        payload = jobs_record(pr_run_id, pr_head)
    elif endpoint == f"repos/{{repository}}/actions/runs/{{public_run_id}}":
        observed_id = public_run_id + 1 if mode == "wrong_public_id" else public_run_id
        payload = run_record(
            observed_id,
            event="workflow_dispatch",
            workflow="public-validation",
            path=".github/workflows/public-validation.yml",
            head_sha=candidate,
            head_branch="main",
        )
    elif endpoint == f"repos/{{repository}}/actions/runs/{{public_run_id}}/artifacts?per_page=100":
        payload = {{"artifacts": [{{
            "name": f"public-validation-derived-{{candidate}}-{{public_run_id}}",
            "expired": False,
            "workflow_run": {{"id": public_run_id}},
        }}]}}
    else:
        raise SystemExit(f"unexpected fake-gh API endpoint: {{endpoint}}")
    print(json.dumps(payload))
    raise SystemExit(0)

if args[:2] == ["run", "download"]:
    run_id = int(args[2])
    name = args[args.index("--name") + 1]
    destination = Path(args[args.index("--dir") + 1])
    destination.mkdir(parents=True, exist_ok=True)
    if run_id == push_run_id and name.startswith("resolved-environment-"):
        platform = name.removeprefix("resolved-environment-").removesuffix(
            f"-{{push_run_id}}"
        )
        (destination / f"conda-{{platform}}.explicit.txt").write_text("fixture\\n")
        (destination / f"pip-{{platform}}.txt").write_text("fixture\\n")
        (destination / f"environment-{{platform}}.yml").write_text("fixture\\n")
        (destination / f"python-{{platform}}.txt").write_text("Python 3.12.13\\n")
        evidence_names = (
            f"conda-{{platform}}.explicit.txt",
            f"pip-{{platform}}.txt",
            f"environment-{{platform}}.yml",
            f"python-{{platform}}.txt",
        )
        evidence_files = {{}}
        for evidence_name in evidence_names:
            payload = (destination / evidence_name).read_bytes()
            evidence_files[evidence_name] = {{
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            }}
        manifest_payload = "".join(
            f"{{evidence_name}}\\t{{evidence_files[evidence_name]['sha256']}}\\t"
            f"{{evidence_files[evidence_name]['size_bytes']}}\\n"
            for evidence_name in sorted(evidence_files)
        ).encode("utf-8")
        (destination / f"platform-{{platform}}.json").write_text(
            json.dumps({{
                "schema_version": "2.0",
                "platform_id": platform,
                "git_commit": candidate,
                "github_run_id": push_run_id,
                "resolved_environment": True,
                "evidence_files": evidence_files,
                "evidence_manifest_sha256": hashlib.sha256(manifest_payload).hexdigest(),
                "source_lock_sha256": evidence_files[f"environment-{{platform}}.yml"]["sha256"],
            }}) + "\\n",
            encoding="utf-8",
        )
        raise SystemExit(0)
    raise SystemExit(f"unexpected fake-gh artifact download: run={{run_id}} name={{name}}")

raise SystemExit(f"unexpected fake-gh command: {{args}}")
"""
    write_executable(fake_bin / "gh", gh_source)
    call_log = tmp_path / "fake-gh-calls.log"
    env = {
        **DEFAULT_IDS,
        "MITO_OVERVIEW_PYTHON": sys.executable,
        "FAKE_CANDIDATE_COMMIT": candidate,
        "FAKE_CANDIDATE_TREE": candidate_tree,
        "FAKE_PR_BASE_COMMIT": pr_base,
        "FAKE_PR_HEAD_COMMIT": pr_head,
        "FAKE_GH_LOG": str(call_log),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
    }
    return scripts / RUNNER.name, call_log, env


def invoke_harness(
    tmp_path: Path,
    *,
    mode: str = "valid",
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    runner, call_log, env = create_fake_gh_harness(tmp_path)
    env["FAKE_GH_MODE"] = mode
    output_root = tmp_path / "runner-output"
    paths = [
        output_root / "validation",
        output_root / "raw-cache",
        output_root / "packet",
        output_root / "mito-overview-v0.3.0-validation.zip",
    ]
    completed = subprocess.run(
        ["bash", str(runner), *(str(path) for path in paths)],
        cwd=tmp_path,
        env={**os.environ, **env},
        capture_output=True,
        text=True,
        check=False,
    )
    return completed, call_log, paths[1]


def test_runner_requires_exactly_four_paths(tmp_path: Path) -> None:
    completed = invoke(tmp_path, "10.5281/zenodo.123")
    assert completed.returncode == 2
    assert "Legacy fifth/archive input is not supported" in completed.stderr


def test_runner_rejects_legacy_archive_environment(tmp_path: Path) -> None:
    completed = invoke(
        tmp_path,
        environment={"MITO_OVERVIEW_ARCHIVE_DOI": "10.5281/zenodo.123"},
    )
    assert completed.returncode == 2
    assert "legacy archive input" in completed.stderr


@pytest.mark.parametrize(
    "name",
    (
        "MITO_OVERVIEW_GITHUB_RUN_ID",
        "MITO_OVERVIEW_PR_NUMBER",
        "MITO_OVERVIEW_PR_RUN_ID",
        "MITO_OVERVIEW_PUBLIC_RUN_ID",
    ),
)
@pytest.mark.parametrize("value", (None, "0", "-1", "not-an-id"))
def test_runner_requires_every_positive_numeric_id(
    tmp_path: Path,
    name: str,
    value: str | None,
) -> None:
    completed = invoke(tmp_path, environment={name: value})
    assert completed.returncode == 2
    assert name in completed.stderr
    assert "positive integer" in completed.stderr


@pytest.mark.parametrize("kind", ("directory", "file", "symlink"))
def test_runner_rejects_any_existing_raw_cache(
    tmp_path: Path,
    kind: str,
) -> None:
    cache = tmp_path / "cache"
    if kind == "directory":
        cache.mkdir()
    elif kind == "file":
        cache.write_text("must not be reused\n", encoding="utf-8")
    else:
        cache.symlink_to(tmp_path / "dangling-cache-target", target_is_directory=True)
    completed = invoke(tmp_path)
    assert completed.returncode == 1
    assert "Raw cache root must be absent at invocation" in completed.stderr


def test_wrong_public_run_id_identity_fails_before_cache_creation(tmp_path: Path) -> None:
    completed, _, cache = invoke_harness(tmp_path, mode="wrong_public_id")
    assert completed.returncode != 0
    assert "does not match MITO_OVERVIEW_PUBLIC_RUN_ID" in completed.stderr
    assert not cache.exists()


def test_runner_rejects_nonrelease_pull_request_number(tmp_path: Path) -> None:
    completed = invoke(
        tmp_path,
        environment={"MITO_OVERVIEW_PR_NUMBER": "31"},
    )
    assert completed.returncode == 2
    assert "must be 3 for the v0.3.0 release gate" in completed.stderr


def test_public_main_drift_fails_before_cache_creation(tmp_path: Path) -> None:
    completed, _, cache = invoke_harness(tmp_path, mode="wrong_public_main")
    assert completed.returncode != 0
    assert "Public main drift" in completed.stderr
    assert not cache.exists()


def test_wrong_pull_request_repository_fails_before_cache_creation(tmp_path: Path) -> None:
    completed, _, cache = invoke_harness(tmp_path, mode="wrong_pr_identity")
    assert completed.returncode != 0
    assert "Pull-request head repository is not canonical" in completed.stderr
    assert not cache.exists()


def test_frozen_paper_tree_drift_fails_before_cache_creation(tmp_path: Path) -> None:
    completed, _, cache = invoke_harness(tmp_path, mode="wrong_paper_tree")
    assert completed.returncode != 0
    assert "Frozen paper tree mismatch" in completed.stderr
    assert not cache.exists()


def test_pr_smoke_run_is_bound_to_exact_pr_head_not_merge_sha(tmp_path: Path) -> None:
    completed, _, cache = invoke_harness(tmp_path, mode="pr_run_uses_merge_sha")
    assert completed.returncode != 0
    assert "Pull-request smoke run identity mismatch for head_sha" in completed.stderr
    assert not cache.exists()


def test_fake_gh_preflight_uses_exact_ids_without_list_or_search_fallback(
    tmp_path: Path,
) -> None:
    completed, call_log, cache = invoke_harness(tmp_path)
    assert completed.returncode != 0
    assert "intentional fake-git clone stop" in completed.stderr
    assert cache.is_dir()
    calls = call_log.read_text(encoding="utf-8").splitlines()
    public_run_endpoint = (
        f"api repos/{REPOSITORY}/actions/runs/{DEFAULT_IDS['MITO_OVERVIEW_PUBLIC_RUN_ID']}"
    )
    assert calls.count(public_run_endpoint) == 1
    assert not any("actions/workflows/public-validation.yml/runs" in call for call in calls)
    assert not any(call.startswith("run list") for call in calls)
    assert not any("/search/" in call for call in calls)
    assert not any("/reviews" in call for call in calls)
    acceptance = tmp_path / "runner-output" / "validation" / "acceptance"
    for name in (
        "pull_request.json",
        "pull_request_comments.json",
        "pull_request_github_actions_run.json",
        "pull_request_github_actions_jobs.json",
    ):
        assert (acceptance / name).is_file()
    comments = json.loads(
        (acceptance / "pull_request_comments.json").read_text(encoding="utf-8")
    )
    assert len(comments) == 3
    assert all("mito-overview-read-only-audit-v1" in item["body"] for item in comments)


def test_runner_declares_public_clone_and_isolated_installed_probe() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'PUBLIC_REMOTE="${REPOSITORY}.git"' in text
    assert "git clone --no-checkout" in text
    assert "refs/remotes/origin/main" in text
    assert "public_main_commit" in text
    assert "env -i" in text
    assert "python -m venv" not in text  # executable is shell-expanded, not ambient.
    assert "-m venv" in text
    assert "-m build --no-isolation" in text
    assert "SDIST_PYTHON" in text
    assert "pip install --force-reinstall --no-build-isolation" in text
    assert '"installed_sdist": True' in text
    assert '"separate_distribution_environments": True' in text
    assert "-I -m mito_overview.cli --list-steps" in text
    assert "executed_outside_checkout" in text
    assert '"broad_declared_input_inventory_bytes"' in text
    assert '"changed_or_new_output_inventory_bytes"' in text
    assert "repository_root;cache_root;validation_root" in text
    assert "cache_root;validation_root" in text
    assert "broad_declared_inputs_and_changed_or_new_outputs_v2" in text
    assert "measure_command package_build" in text
    assert "resources/package_build.json" in text
    assert 'cp "${VALIDATION_ROOT}/resources/${FRESH_CLONE_CASE_ID}.json"' not in text
    assert "--zenodo-reservation-evidence" not in text
    assert "--doi" not in text


def test_runner_records_factual_threads_and_uses_fresh_installed_smokes() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert '"threads": thread_setting' in text
    assert 'os.environ.get("THREADS", "4")' not in text
    expected_calls = (
        "run_logged unit_known_answer unit mixed",
        "run_logged cli_step_listing cli not_applicable",
        "run_logged strict_generic_dry_run cli 4",
        "run_logged synthetic_longread_smoke synthetic 1",
        "run_logged synthetic_shortread_smoke synthetic 1",
        "run_logged synthetic_longread_nomethyl_smoke synthetic 1",
        "run_logged standalone_minimal_smoke synthetic 4",
        "run_logged public_cache_prepare public_input not_applicable",
        "run_logged public_validation_matrix public 4",
    )
    for call in expected_calls:
        assert call in text
    smoke_block = text[
        text.index("run_logged synthetic_longread_smoke") :
        text.index('"${PYTHON_BIN}" - "${VALIDATION_ROOT}/resources/package_build.json"')
    ]
    assert 'MITO_OVERVIEW_PYTHON="${FRESH_PYTHON}"' in smoke_block
    assert "MITO_OVERVIEW_REQUIRE_INSTALLED=1" in smoke_block
    assert 'MITO_OVERVIEW_PYTHON="${PYTHON_BIN}"' not in smoke_block


def test_resource_measurement_counts_exact_declared_and_changed_inventories(
    tmp_path: Path,
) -> None:
    text = RUNNER.read_text(encoding="utf-8")
    match = re.search(
        r"# BEGIN RESOURCE_MEASUREMENT_PYTHON\n(?P<code>.*?)"
        r"\n# END RESOURCE_MEASUREMENT_PYTHON",
        text,
        re.DOTALL,
    )
    assert match is not None

    repository = tmp_path / "repository"
    cache = tmp_path / "cache"
    validation = tmp_path / "validation"
    repository.mkdir()
    cache.mkdir()
    validation.mkdir()
    (repository / "input.bin").write_bytes(b"abc")
    (validation / "existing.bin").write_bytes(b"xy")
    resource_path = validation / "resources" / "probe.json"
    resource_path.parent.mkdir()
    log_path = validation / "logs" / "probe.log"
    log_path.parent.mkdir()
    cache_output = cache / "download.fastq.gz"
    validation_output = validation / "result.tsv"
    command_code = (
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_bytes(b'12345'); "
        "Path(sys.argv[2]).write_bytes(b'1234567')"
    )
    command_path = validation / "commands" / "probe.sh"
    command_path.parent.mkdir()
    command_argv = [
        sys.executable,
        "-c",
        command_code,
        str(cache_output),
        str(validation_output),
    ]
    command_path.write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\n"
        + " ".join(shlex.quote(value) for value in command_argv)
        + "\n",
        encoding="utf-8",
    )
    candidate_commit = "a" * 40
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            match.group("code"),
            str(resource_path),
            str(log_path),
            str(repository),
            str(cache),
            str(validation),
            candidate_commit,
            "not_applicable",
            "bash",
            str(command_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    observed = json.loads(resource_path.read_text(encoding="utf-8"))
    assert observed["case_id"] == "probe"
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
        observed["measurement_id"],
        flags=re.IGNORECASE,
    )
    assert observed["candidate_commit"] == candidate_commit
    assert observed["command_path"] == "commands/probe.sh"
    assert observed["command_sha256"] == hashlib.sha256(
        command_path.read_bytes()
    ).hexdigest()
    assert observed["packaged_command_sha256"] == observed["command_sha256"]
    assert observed["log_path"] == "logs/probe.log"
    assert observed["log_sha256"] == hashlib.sha256(log_path.read_bytes()).hexdigest()
    assert observed["packaged_log_sha256"] == observed["log_sha256"]
    assert observed["threads"] == "not_applicable"
    assert observed["broad_declared_input_inventory_bytes"] == (
        5 + command_path.stat().st_size
    )
    assert observed["changed_or_new_output_inventory_bytes"] == 12
    assert observed["broad_declared_input_inventory_scope"] == (
        "repository_root;cache_root;validation_root"
    )
    assert observed["changed_or_new_output_inventory_scope"] == (
        "cache_root;validation_root"
    )
    assert observed["io_measurement_method"] == (
        "broad_declared_inputs_and_changed_or_new_outputs_v2"
    )


def test_runner_machine_enforces_frozen_paper_tree() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert (
        'FROZEN_PAPER_TREE="bfb5664db9c8b43ed5de33ecbddef88071fc6378"'
        in text
    )
    assert "rev-parse HEAD:paper" in text
    assert "Frozen paper tree mismatch" in text


def test_public_matrix_is_bound_to_public_clone_and_force_installed_wheel() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'PREPARE_SCRIPT="${FRESH_CLONE_ROOT}/scripts/' in text
    assert 'PUBLIC_MATRIX="${FRESH_CLONE_ROOT}/scripts/' in text
    assert 'ISOLATION_WRAPPER="${FRESH_CLONE_ROOT}/scripts/' in text
    assert 'ORACLE="${FRESH_CLONE_ROOT}/examples/' in text
    assert 'MITO_OVERVIEW_PYTHON="${FRESH_PYTHON}"' in text
    assert "MITO_OVERVIEW_REQUIRE_INSTALLED=1" in text
    assert "PYTHONPATH=" in text
    assert "pip install --force-reinstall" in text
    assert '"mito-overview":"0.3.0"' in text
    assert '"${ISOLATION_WRAPPER}"' in text
    assert "--evidence" in text
    assert "network_isolation_verdict" in text
    assert "offline_isolation" in text
    assert "direct_url.json" in text
    assert "direct_url_archive_sha256" in text
    assert "PEP 610 archive hash does not match post-test" in text
    assert 'artifact.relative_to(validation_root).as_posix()' in text
    assert "WHEEL_SHA256_BEFORE_TESTS" in text
    assert "SDIST_SHA256_BEFORE_TESTS" in text


def test_runner_binds_ci_evidence_and_receipt_to_all_explicit_ids() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    for platform in ("linux-64", "osx-64", "osx-arm64"):
        assert f"resolved-environment-${{platform}}" in text or platform in text
        assert f"platform-${{platform}}.json" in text
        assert f"python-${{platform}}.txt" in text
    assert "Resolved CI environment inventory mismatch" in text
    assert "Resolved CI evidence-file digest mismatch" in text
    assert "Resolved CI evidence manifest digest mismatch" in text
    assert "Resolved CI solver lock differs from the exact candidate" in text
    assert "evidence_manifest_sha256" in text
    assert "source_lock_sha256" in text
    assert "Python 3.12.13" in text
    assert 'gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${PUBLIC_RUN_ID}"' in text
    assert "actions/workflows/public-validation.yml/runs" not in text
    assert "cross_platform_comparison.tsv" in text
    assert "normalized_scientific_table" in text
    assert "visual_structure" in text
    assert "The release-side public matrix must be reproduced on macOS" in text
    for field in (
        "final_push_github_actions_run_id",
        "pull_request_number",
        "pull_request_github_actions_run_id",
        "public_validation_github_actions_run_id",
    ):
        assert f'echo "{field}=' in text
        assert f'"{field}": int(' in text


def test_acceptance_cases_are_appended_only_after_ubuntu_evidence_exists() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    fetch = text.index("\nfetch_and_compare_ubuntu_public_evidence\n")
    append = text.index("\nappend_acceptance_cases >>", fetch)
    packet = text.index("scripts/build_validation_packet_v0.3.0.py", append)
    assert fetch < append < packet


def test_public_main_is_rechecked_at_packet_and_receipt_finalization() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    calls = [
        index
        for index in range(len(text))
        if text.startswith("\nvalidate_public_main_tip\n", index)
    ]
    assert len(calls) >= 3
    fetch = text.index("\nfetch_and_compare_ubuntu_public_evidence\n")
    packet = text.index('scripts/build_validation_packet_v0.3.0.py"', fetch)
    receipt = text.index('"${PACKET_RECEIPT}" "${CANDIDATE_COMMIT}"', packet)
    assert any(fetch < index < packet for index in calls)
    assert any(packet < index < receipt for index in calls)


def test_raw_cache_is_created_only_after_all_github_preflights() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    push = text.index("\nfetch_github_actions_evidence\n")
    pull = text.index("\nfetch_pull_request_evidence\n", push)
    public = text.index("\npreflight_public_validation_evidence\n", pull)
    validate = text.index("\nvalidate_github_preflight_evidence\n", public)
    create = text.index('\nmkdir "${CACHE_ROOT}"', validate)
    assert push < pull < public < validate < create
    preflight_prefix = text[text.index("mkdir -p   "):push]
    assert re.search(r"mkdir(?: -p)?[^\n]*\$\{CACHE_ROOT\}", preflight_prefix) is None


def test_raw_cache_is_rechecked_immediately_before_download() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    prepare = text.index("\nrun_logged public_cache_prepare public_input")
    empty_check = text.rindex("Raw cache root must still be an empty regular directory", 0, prepare)
    required_loop = text.rindex("\ndone\n", 0, prepare)
    assert required_loop < empty_check < prepare
