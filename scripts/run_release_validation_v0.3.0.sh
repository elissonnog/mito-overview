#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: MITO_OVERVIEW_GITHUB_RUN_ID=PUSH_RUN_ID \
  MITO_OVERVIEW_PR_NUMBER=PR_NUMBER \
  MITO_OVERVIEW_PR_RUN_ID=PR_SMOKE_RUN_ID \
  MITO_OVERVIEW_PUBLIC_RUN_ID=PUBLIC_VALIDATION_RUN_ID \
  $0 VALIDATION_ROOT RAW_CACHE_ROOT PACKET_ROOT \
  mito-overview-v0.3.0-validation.zip

This is the GitHub-only v0.3.0 release-validation interface. Manuscript,
Zenodo, DOI, archive, and fixed release-date inputs are not accepted.
RAW_CACHE_ROOT must not exist when this command is invoked.
EOF
}

if [[ $# -eq 5 ]]; then
  echo "Legacy fifth/archive input is not supported; supply exactly four paths." >&2
  usage
  exit 2
fi
if [[ $# -ne 4 ]]; then
  usage
  exit 2
fi
for legacy_name in   MITO_OVERVIEW_ARCHIVE_DOI   MITO_OVERVIEW_ZENODO_RESERVATION_EVIDENCE; do
  if [[ -n "${!legacy_name:-}" ]]; then
    echo "${legacy_name} is a legacy archive input and is not accepted by the core GitHub release gate." >&2
    exit 2
  fi
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
REPOSITORY="https://github.com/elissonnog/mito-overview"
PUBLIC_REMOTE="${REPOSITORY}.git"
GITHUB_REPOSITORY="elissonnog/mito-overview"
GITHUB_RUN_ID="${MITO_OVERVIEW_GITHUB_RUN_ID:-}"
PR_NUMBER="${MITO_OVERVIEW_PR_NUMBER:-}"
PR_RUN_ID="${MITO_OVERVIEW_PR_RUN_ID:-}"
PUBLIC_RUN_ID="${MITO_OVERVIEW_PUBLIC_RUN_ID:-}"
EXPECTED_PR_NUMBER="3"
FRESH_CLONE_CASE_ID="fresh_clone_candidate_commit"
EXPECTED_AUDIT_ZIP="mito-overview-v0.3.0-validation.zip"
SCHEMA_VERSION="2.0"
VALIDATION_PROFILE="github_release_validation_v1"

require_positive_integer() {
  local name="$1"
  local value="$2"
  local purpose="$3"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "${name} must be a positive integer identifying ${purpose}." >&2
    exit 2
  fi
}

require_positive_integer \
  MITO_OVERVIEW_GITHUB_RUN_ID "${GITHUB_RUN_ID}" \
  "the completed post-merge push smoke-tests run"
require_positive_integer \
  MITO_OVERVIEW_PR_NUMBER "${PR_NUMBER}" \
  "the merged release pull request"
require_positive_integer \
  MITO_OVERVIEW_PR_RUN_ID "${PR_RUN_ID}" \
  "the completed pull_request smoke-tests run"
require_positive_integer \
  MITO_OVERVIEW_PUBLIC_RUN_ID "${PUBLIC_RUN_ID}" \
  "the completed workflow_dispatch public-validation run"
if [[ "${PR_NUMBER}" != "${EXPECTED_PR_NUMBER}" ]]; then
  echo "MITO_OVERVIEW_PR_NUMBER must be ${EXPECTED_PR_NUMBER} for the v0.3.0 release gate." >&2
  exit 2
fi

resolve_path() {
  local label="$1"
  local value="$2"
  if [[ -z "${value}" || "${value}" == *$'\n'* || "${value}" == *$'\r'* ||     "${value}" == *$'\t'* ]]; then
    echo "${label} must be a non-empty path without control characters." >&2
    return 1
  fi
  PYTHONPYCACHEPREFIX="${TMPDIR:-/tmp}/mito-overview-pycache"     "${PYTHON_BIN}" - "${value}" <<'PY'
import sys
from pathlib import Path

print(Path(sys.argv[1]).expanduser().resolve(strict=False))
PY
}

VALIDATION_ROOT="$(resolve_path "Validation root" "$1")"
RAW_CACHE_ARGUMENT="$2"
"${PYTHON_BIN}" - "${RAW_CACHE_ARGUMENT}" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser()
if path.exists() or path.is_symlink():
    raise SystemExit(
        f"Raw cache root must be absent at invocation (directories, files, and "
        f"symlinks are rejected): {path}"
    )
PY
CACHE_ROOT="$(resolve_path "Raw cache root" "${RAW_CACHE_ARGUMENT}")"
PACKET_ROOT="$(resolve_path "Packet root" "$3")"
AUDIT_ZIP="$(resolve_path "Audit ZIP" "$4")"
PACKET_BUILD_LOG="${AUDIT_ZIP}.build.log"
PACKET_VERIFY_LOG="${AUDIT_ZIP}.verify.log"
PACKET_SHA256="${AUDIT_ZIP}.sha256"
PACKET_RECEIPT="${AUDIT_ZIP}.verification.json"

"${PYTHON_BIN}" -   "${REPO_ROOT}" "${VALIDATION_ROOT}" "${CACHE_ROOT}"   "${PACKET_ROOT}" "${AUDIT_ZIP}" "${EXPECTED_AUDIT_ZIP}" <<'PY'
import sys
from pathlib import Path

repo_root, validation_root, cache_root, packet_root, audit_zip = map(
    Path, sys.argv[1:6]
)
expected_zip = sys.argv[6]
directory_roots = {
    "validation root": validation_root,
    "raw cache root": cache_root,
    "packet root": packet_root,
}
for label, path in directory_roots.items():
    if path == Path(path.anchor):
        raise SystemExit(f"{label} must not be a filesystem root: {path}")
if audit_zip.name != expected_zip:
    raise SystemExit(f"Audit ZIP must be named {expected_zip!r}, not {audit_zip.name!r}")

def contains(parent: Path, child: Path) -> bool:
    return child == parent or parent in child.parents

items = list(directory_roots.items())
for index, (left_label, left) in enumerate(items):
    for right_label, right in items[index + 1 :]:
        if contains(left, right) or contains(right, left):
            raise SystemExit(
                f"{left_label} and {right_label} must not overlap: {left}; {right}"
            )
for label, path in items:
    if contains(path, audit_zip):
        raise SystemExit(f"Audit ZIP must be outside {label}: {path}")
    if contains(repo_root, path) or contains(path, repo_root):
        raise SystemExit(f"{label} must be outside the release repository: {path}")
if contains(repo_root, audit_zip):
    raise SystemExit(f"Audit ZIP must be outside the release repository: {audit_zip}")
PY

if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all)" ]]; then
  echo "Release validation requires a clean Git worktree." >&2
  exit 1
fi
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/check_release_hygiene.py" "${REPO_ROOT}"
CANDIDATE_COMMIT="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
if [[ ! "${CANDIDATE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Release candidate must resolve to a full 40-character Git commit." >&2
  exit 1
fi

for directory in "${VALIDATION_ROOT}" "${PACKET_ROOT}"; do
  if [[ -d "${directory}" && -n "$(find "${directory}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Release output directory must be absent or empty: ${directory}" >&2
    exit 1
  fi
  if [[ -e "${directory}" && ! -d "${directory}" ]]; then
    echo "Release output path exists and is not a directory: ${directory}" >&2
    exit 1
  fi
done
if [[ -e "${CACHE_ROOT}" || -L "${CACHE_ROOT}" ]]; then
  echo "Raw cache root must remain absent through preflight: ${CACHE_ROOT}" >&2
  exit 1
fi
for output in   "${AUDIT_ZIP}" "${PACKET_BUILD_LOG}" "${PACKET_VERIFY_LOG}"   "${PACKET_SHA256}" "${PACKET_RECEIPT}"; do
  if [[ -e "${output}" || -L "${output}" ]]; then
    echo "Release output must not already exist: ${output}" >&2
    exit 1
  fi
done
if ! command -v gh >/dev/null 2>&1; then
  echo "The GitHub CLI (gh) is required to retrieve Actions evidence." >&2
  exit 1
fi

mkdir -p   "${VALIDATION_ROOT}/acceptance"   "${VALIDATION_ROOT}/commands"   "${VALIDATION_ROOT}/logs"   "${VALIDATION_ROOT}/resources"   "${VALIDATION_ROOT}/expected"   "${VALIDATION_ROOT}/work"   "${VALIDATION_ROOT}/dist"
mkdir -p "$(dirname "${AUDIT_ZIP}")"

FRESH_CLONE_ROOT="${VALIDATION_ROOT}/work/fresh_clone"
FRESH_ENV_ROOT="${VALIDATION_ROOT}/work/fresh_environment"
FRESH_VENV_ROOT="${FRESH_ENV_ROOT}/venv"
FRESH_PYTHON="${FRESH_VENV_ROOT}/bin/python"

CASES_TSV="${VALIDATION_ROOT}/cases.tsv"
printf 'case_id\tcategory\tinput_available\texpected_available\tverdict\tdetail\n' > "${CASES_TSV}"

record_case() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" >> "${CASES_TSV}"
}

measure_command() {
  local case_id="$1"
  local log_file="$2"
  shift 2
  "${PYTHON_BIN}" -     "${VALIDATION_ROOT}/resources/${case_id}.json" "${log_file}" "$@" <<'PY'
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

resource_path = Path(sys.argv[1])
log_path = Path(sys.argv[2])
command = sys.argv[3:]
before = resource.getrusage(resource.RUSAGE_CHILDREN)
started = time.monotonic()
with log_path.open("wb") as log:
    completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
elapsed = time.monotonic() - started
after = resource.getrusage(resource.RUSAGE_CHILDREN)
max_rss = after.ru_maxrss
if sys.platform == "darwin":
    max_rss = max_rss / 1024.0
record = {
    "schema_version": "2.0",
    "case_id": resource_path.stem,
    "wall_seconds": round(elapsed, 6),
    "user_cpu_seconds": round(after.ru_utime - before.ru_utime, 6),
    "system_cpu_seconds": round(after.ru_stime - before.ru_stime, 6),
    "max_rss_kb": round(max_rss, 3),
    "threads": os.environ.get("THREADS", "4"),
    "platform": platform.platform(),
    "measurement_status": "measured",
    "reason": "",
    "exit_code": completed.returncode,
}
resource_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
raise SystemExit(completed.returncode)
PY
}

run_logged() {
  local case_id="$1"
  local category="$2"
  shift 2
  local command_file="${VALIDATION_ROOT}/commands/${case_id}.sh"
  local log_file="${VALIDATION_ROOT}/logs/${case_id}.log"
  {
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'cd %q\n' "${REPO_ROOT}"
    printf '%q ' "$@"
    printf '\n'
  } > "${command_file}"
  chmod +x "${command_file}"
  if measure_command "${case_id}" "${log_file}" bash "${command_file}"; then
    record_case "${case_id}" "${category}" 1 1 PASS "see logs/${case_id}.log"
  else
    record_case "${case_id}" "${category}" 1 1 FAIL "see logs/${case_id}.log"
    tail -100 "${log_file}" >&2
    return 1
  fi
}

fetch_github_actions_evidence() {
  local command_file="${VALIDATION_ROOT}/commands/github_actions_candidate_commit.sh"
  local log_file="${VALIDATION_ROOT}/logs/github_actions_candidate_commit.log"
  local run_tmp="${VALIDATION_ROOT}/acceptance/github_actions_run.json.tmp"
  local jobs_tmp="${VALIDATION_ROOT}/acceptance/github_actions_jobs.json.tmp"
  local artifacts_tmp="${VALIDATION_ROOT}/acceptance/github_actions_artifacts.json.tmp"
  local artifacts_root="${VALIDATION_ROOT}/acceptance/resolved_ci_environments"
  {
    printf 'gh api %q > %q\n'       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"       "acceptance/github_actions_run.json"
    printf 'gh api %q > %q\n'       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100"       "acceptance/github_actions_jobs.json"
    printf 'gh api %q > %q\n'       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts?per_page=100"       "acceptance/github_actions_artifacts.json"
    printf 'gh run download %q --repo %q --dir %q\n'       "${GITHUB_RUN_ID}" "${GITHUB_REPOSITORY}"       "acceptance/resolved_ci_environments"
  } > "${command_file}"
  if {
    echo "candidate_commit=${CANDIDATE_COMMIT}"
    echo "github_actions_run_id=${GITHUB_RUN_ID}"
    gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}" > "${run_tmp}"
    gh api       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100"       > "${jobs_tmp}"
    gh api       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/artifacts?per_page=100"       > "${artifacts_tmp}"
    mv "${run_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_run.json"
    mv "${jobs_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_jobs.json"
    mv "${artifacts_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_artifacts.json"
    "${PYTHON_BIN}" -       "${VALIDATION_ROOT}/acceptance/github_actions_artifacts.json"       "${GITHUB_RUN_ID}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
run_id = sys.argv[2]
expected = {
    f"resolved-environment-linux-64-{run_id}",
    f"resolved-environment-osx-64-{run_id}",
    f"resolved-environment-osx-arm64-{run_id}",
}
observed = {
    item["name"]
    for item in payload.get("artifacts", [])
    if not item.get("expired", False)
}
missing = sorted(expected - observed)
if missing:
    raise SystemExit(f"Missing resolved CI environment artifacts: {missing}")
PY
    mkdir -p "${artifacts_root}"
    for platform in linux-64 osx-64 osx-arm64; do
      artifact="resolved-environment-${platform}-${GITHUB_RUN_ID}"
      destination="${artifacts_root}/${platform}"
      mkdir -p "${destination}"
      gh run download "${GITHUB_RUN_ID}" --repo "${GITHUB_REPOSITORY}" \
        --name "${artifact}" --dir "${destination}"
      test -s "${destination}/conda-${platform}.explicit.txt"
      test -s "${destination}/pip-${platform}.txt"
      test -s "${destination}/environment-${platform}.yml"
      test -s "${destination}/platform-${platform}.json"
      "${PYTHON_BIN}" - "${destination}/platform-${platform}.json" \
        "${platform}" "${CANDIDATE_COMMIT}" "${GITHUB_RUN_ID}" <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if record.get("platform_id") != sys.argv[2]:
    raise SystemExit("Resolved CI artifact platform identity mismatch")
if record.get("git_commit") != sys.argv[3]:
    raise SystemExit("Resolved CI artifact commit identity mismatch")
if record.get("github_run_id") != int(sys.argv[4]):
    raise SystemExit("Resolved CI artifact run identity mismatch")
if record.get("resolved_environment") is not True:
    raise SystemExit("Resolved CI artifact did not attest environment resolution")
PY
    done
    echo "github_actions_metadata_ingestion=PASS"
    echo "github_actions_platform_artifacts=linux-64,osx-64,osx-arm64"
  } > "${log_file}" 2>&1; then
    return 0
  fi
  tail -100 "${log_file}" >&2
  return 1
}

fetch_pull_request_evidence() {
  local command_file="${VALIDATION_ROOT}/commands/pull_request_release_evidence.sh"
  local log_file="${VALIDATION_ROOT}/logs/pull_request_release_evidence.log"
  local pull_tmp="${VALIDATION_ROOT}/acceptance/pull_request.json.tmp"
  local comments_pages_tmp="${VALIDATION_ROOT}/acceptance/pull_request_comments.pages.json.tmp"
  local comments_tmp="${VALIDATION_ROOT}/acceptance/pull_request_comments.json.tmp"
  local run_tmp="${VALIDATION_ROOT}/acceptance/pull_request_github_actions_run.json.tmp"
  local jobs_tmp="${VALIDATION_ROOT}/acceptance/pull_request_github_actions_jobs.json.tmp"
  local pull_path="${VALIDATION_ROOT}/acceptance/pull_request.json"
  local comments_path="${VALIDATION_ROOT}/acceptance/pull_request_comments.json"
  local run_path="${VALIDATION_ROOT}/acceptance/pull_request_github_actions_run.json"
  local jobs_path="${VALIDATION_ROOT}/acceptance/pull_request_github_actions_jobs.json"
  {
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}" \
      "acceptance/pull_request.json"
    printf 'gh api --paginate --slurp %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments?per_page=100" \
      "acceptance/pull_request_comments.json"
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${PR_RUN_ID}" \
      "acceptance/pull_request_github_actions_run.json"
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${PR_RUN_ID}/jobs?filter=latest&per_page=100" \
      "acceptance/pull_request_github_actions_jobs.json"
  } > "${command_file}"

  if {
    gh api "repos/${GITHUB_REPOSITORY}/pulls/${PR_NUMBER}" > "${pull_tmp}"
    gh api --paginate --slurp \
      "repos/${GITHUB_REPOSITORY}/issues/${PR_NUMBER}/comments?per_page=100" \
      > "${comments_pages_tmp}"
    gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${PR_RUN_ID}" > "${run_tmp}"
    gh api \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${PR_RUN_ID}/jobs?filter=latest&per_page=100" \
      > "${jobs_tmp}"
    mv "${pull_tmp}" "${pull_path}"
    mv "${run_tmp}" "${run_path}"
    mv "${jobs_tmp}" "${jobs_path}"
    if "${PYTHON_BIN}" - \
      "${pull_path}" "${comments_pages_tmp}" "${comments_tmp}" \
      "${run_path}" "${jobs_path}" \
      "${PR_NUMBER}" "${PR_RUN_ID}" "${CANDIDATE_COMMIT}" \
      "${GITHUB_REPOSITORY}" <<'PY'
import json
import re
import sys
from pathlib import Path

pull_path, comments_pages_path, comments_path, run_path, jobs_path = map(
    Path, sys.argv[1:6]
)
expected_pr_number = int(sys.argv[6])
expected_run_id = int(sys.argv[7])
expected_commit = sys.argv[8]
repository = sys.argv[9]
api_root = f"https://api.github.com/repos/{repository}"
html_root = f"https://github.com/{repository}"

pull = json.loads(pull_path.read_text(encoding="utf-8"))
if not isinstance(pull, dict):
    raise SystemExit("Pull-request evidence must be a JSON object")
if pull.get("number") != expected_pr_number:
    raise SystemExit("Pull-request number does not match MITO_OVERVIEW_PR_NUMBER")
if pull.get("state") != "closed" or pull.get("merged") is not True:
    raise SystemExit("Release pull request is not merged")
if pull.get("merge_commit_sha") != expected_commit:
    raise SystemExit("Pull-request merge commit does not match the release candidate")
if pull.get("url") != f"{api_root}/pulls/{expected_pr_number}":
    raise SystemExit("Pull-request API URL does not match the canonical repository")
if pull.get("html_url") != f"{html_root}/pull/{expected_pr_number}":
    raise SystemExit("Pull-request HTML URL does not match the canonical repository")
base = pull.get("base")
head = pull.get("head")
if not isinstance(base, dict) or not isinstance(head, dict):
    raise SystemExit("Pull-request head/base identity is missing")
if base.get("ref") != "main":
    raise SystemExit("Release pull request was not merged into main")
for label, value in (("base", base), ("head", head)):
    repo = value.get("repo")
    if not isinstance(repo, dict) or repo.get("full_name") != repository:
        raise SystemExit(f"Pull-request {label} repository is not canonical")
pr_head_sha = head.get("sha")
if not isinstance(pr_head_sha, str) or not re.fullmatch(r"[0-9a-f]{40}", pr_head_sha):
    raise SystemExit("Pull-request head SHA is not a full lowercase commit")
pr_head_branch = head.get("ref")
if not isinstance(pr_head_branch, str) or not pr_head_branch.strip():
    raise SystemExit("Pull-request head branch is missing")

comment_pages = json.loads(comments_pages_path.read_text(encoding="utf-8"))
if not isinstance(comment_pages, list) or not all(
    isinstance(page, list) for page in comment_pages
):
    raise SystemExit("Paginated pull-request comments must be a JSON list of pages")
comments = [comment for page in comment_pages for comment in page]
if not all(isinstance(comment, dict) for comment in comments):
    raise SystemExit("Pull-request comment evidence contains a non-object entry")
comment_ids = []
expected_issue_url = f"{api_root}/issues/{expected_pr_number}"
for comment in comments:
    comment_id = comment.get("id")
    if not isinstance(comment_id, int) or isinstance(comment_id, bool) or comment_id <= 0:
        raise SystemExit("Pull-request comment ID must be a positive integer")
    if comment.get("issue_url") != expected_issue_url:
        raise SystemExit("Pull-request comment is not associated with the selected PR")
    comment_ids.append(comment_id)
if len(comment_ids) != len(set(comment_ids)):
    raise SystemExit("Pull-request comment evidence contains duplicate IDs")
comments.sort(key=lambda comment: comment["id"])
comments_path.write_text(
    json.dumps(comments, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

run = json.loads(run_path.read_text(encoding="utf-8"))
if not isinstance(run, dict) or run.get("id") != expected_run_id:
    raise SystemExit("Pull-request smoke run does not match MITO_OVERVIEW_PR_RUN_ID")
expected_run_fields = {
    "name": "smoke-tests",
    "path": ".github/workflows/smoke-tests.yml",
    "event": "pull_request",
    "status": "completed",
    "conclusion": "success",
    "head_sha": pr_head_sha,
    "head_branch": pr_head_branch,
}
for field, expected in expected_run_fields.items():
    if run.get(field) != expected:
        raise SystemExit(
            f"Pull-request smoke run identity mismatch for {field}: "
            f"{run.get(field)!r} != {expected!r}"
        )
for field in ("repository", "head_repository"):
    value = run.get(field)
    if not isinstance(value, dict) or value.get("full_name") != repository:
        raise SystemExit(f"Pull-request smoke run {field} is not canonical")
run_api_url = f"{api_root}/actions/runs/{expected_run_id}"
if run.get("url") != run_api_url or run.get("jobs_url") != f"{run_api_url}/jobs":
    raise SystemExit("Pull-request smoke run API URLs are not bound to the selected run")
if run.get("html_url") != f"{html_root}/actions/runs/{expected_run_id}":
    raise SystemExit("Pull-request smoke run HTML URL is not canonical")
associations = run.get("pull_requests")
if not isinstance(associations, list) or not any(
    isinstance(item, dict)
    and item.get("number") == expected_pr_number
    and item.get("url") == f"{api_root}/pulls/{expected_pr_number}"
    for item in associations
):
    raise SystemExit("Pull-request smoke run is not associated with the selected PR")
run_attempt = run.get("run_attempt")
if not isinstance(run_attempt, int) or isinstance(run_attempt, bool) or run_attempt <= 0:
    raise SystemExit("Pull-request smoke run attempt is invalid")

jobs_payload = json.loads(jobs_path.read_text(encoding="utf-8"))
jobs = jobs_payload.get("jobs") if isinstance(jobs_payload, dict) else None
if not isinstance(jobs, list) or not all(isinstance(job, dict) for job in jobs):
    raise SystemExit("Pull-request smoke jobs evidence must contain an object list")
if jobs_payload.get("total_count") != len(jobs):
    raise SystemExit("Pull-request smoke jobs total_count does not match its inventory")
expected_jobs = {
    "Unit and synthetic tests (ubuntu-24.04)",
    "Unit and synthetic tests (macos-15-intel)",
    "Unit and synthetic tests (macos-15)",
}
for expected_name in expected_jobs:
    matches = [job for job in jobs if job.get("name") == expected_name]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one successful PR smoke job {expected_name!r}")
    job = matches[0]
    if (
        job.get("run_id") != expected_run_id
        or job.get("run_attempt") != run_attempt
        or job.get("head_sha") != pr_head_sha
        or job.get("workflow_name") != "smoke-tests"
        or job.get("status") != "completed"
        or job.get("conclusion") != "success"
    ):
        raise SystemExit(f"Pull-request smoke job identity is invalid: {expected_name}")
print(f"pull_request_evidence=PASS comments={len(comments)} pr_head_sha={pr_head_sha}")
PY
    then
      mv "${comments_tmp}" "${comments_path}"
      rm "${comments_pages_tmp}"
      echo "pull_request_review_policy=structured_issue_comments_no_review_approval_gate"
    else
      false
    fi
  } > "${log_file}" 2>&1; then
    return 0
  fi
  tail -100 "${log_file}" >&2
  return 1
}

preflight_public_validation_evidence() {
  local command_file="${VALIDATION_ROOT}/commands/public_validation_run_preflight.sh"
  local log_file="${VALIDATION_ROOT}/logs/public_validation_run_preflight.log"
  local acceptance_root="${VALIDATION_ROOT}/acceptance/ubuntu_public_validation"
  local run_tmp="${acceptance_root}/workflow_run.json.tmp"
  local run_path="${acceptance_root}/workflow_run.json"
  local artifacts_tmp="${acceptance_root}/artifacts.json.tmp"
  local artifacts_path="${acceptance_root}/artifacts.json"
  local artifact_name="public-validation-derived-${CANDIDATE_COMMIT}-${PUBLIC_RUN_ID}"

  mkdir -p "${acceptance_root}"
  {
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${PUBLIC_RUN_ID}" \
      "acceptance/ubuntu_public_validation/workflow_run.json"
    printf 'gh api %q > %q\n' \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${PUBLIC_RUN_ID}/artifacts?per_page=100" \
      "acceptance/ubuntu_public_validation/artifacts.json"
  } > "${command_file}"

  if {
    gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${PUBLIC_RUN_ID}" > "${run_tmp}"
    gh api \
      "repos/${GITHUB_REPOSITORY}/actions/runs/${PUBLIC_RUN_ID}/artifacts?per_page=100" \
      > "${artifacts_tmp}"
    mv "${run_tmp}" "${run_path}"
    mv "${artifacts_tmp}" "${artifacts_path}"
    "${PYTHON_BIN}" - \
      "${run_path}" "${artifacts_path}" "${PUBLIC_RUN_ID}" \
      "${CANDIDATE_COMMIT}" "${GITHUB_REPOSITORY}" "${artifact_name}" <<'PY'
import json
import sys
from pathlib import Path

run_path = Path(sys.argv[1])
artifacts_path = Path(sys.argv[2])
expected_run_id = int(sys.argv[3])
expected_commit = sys.argv[4]
repository = sys.argv[5]
expected_artifact = sys.argv[6]
api_root = f"https://api.github.com/repos/{repository}"
html_root = f"https://github.com/{repository}"

run = json.loads(run_path.read_text(encoding="utf-8"))
if not isinstance(run, dict) or run.get("id") != expected_run_id:
    raise SystemExit("Public-validation run does not match MITO_OVERVIEW_PUBLIC_RUN_ID")
expected_fields = {
    "name": "public-validation",
    "path": ".github/workflows/public-validation.yml",
    "event": "workflow_dispatch",
    "status": "completed",
    "conclusion": "success",
    "head_sha": expected_commit,
    "head_branch": "main",
}
for field, expected in expected_fields.items():
    if run.get(field) != expected:
        raise SystemExit(
            f"Public-validation run identity mismatch for {field}: "
            f"{run.get(field)!r} != {expected!r}"
        )
for field in ("repository", "head_repository"):
    value = run.get(field)
    if not isinstance(value, dict) or value.get("full_name") != repository:
        raise SystemExit(f"Public-validation run {field} is not canonical")
run_api_url = f"{api_root}/actions/runs/{expected_run_id}"
if run.get("url") != run_api_url:
    raise SystemExit("Public-validation run API URL is not bound to the selected ID")
if run.get("html_url") != f"{html_root}/actions/runs/{expected_run_id}":
    raise SystemExit("Public-validation run HTML URL is not canonical")

payload = json.loads(artifacts_path.read_text(encoding="utf-8"))
artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
if not isinstance(artifacts, list):
    raise SystemExit("Public-validation artifact evidence lacks an artifact list")
matches = [
    artifact
    for artifact in artifacts
    if isinstance(artifact, dict)
    and artifact.get("name") == expected_artifact
    and artifact.get("workflow_run", {}).get("id") == expected_run_id
    and not artifact.get("expired", False)
]
if len(matches) != 1:
    raise SystemExit(
        f"Expected exactly one unexpired derived artifact {expected_artifact!r} "
        f"from run {expected_run_id}"
    )
print(f"public_validation_run_preflight=PASS run_id={expected_run_id}")
PY
  } > "${log_file}" 2>&1; then
    return 0
  fi
  tail -100 "${log_file}" >&2
  return 1
}

validate_github_preflight_evidence() {
  local command_file="${VALIDATION_ROOT}/commands/github_acceptance_preflight.sh"
  local log_file="${VALIDATION_ROOT}/logs/github_acceptance_preflight.log"
  cat > "${command_file}" <<EOF
#!/usr/bin/env bash
# Revalidate final push CI, merged PR identity, exact PR-head CI, and the three
# structured read-only agent-role audit comments before creating RAW_CACHE_ROOT.
EOF
  chmod +x "${command_file}"
  if "${PYTHON_BIN}" - \
    "${REPO_ROOT}" "${VALIDATION_ROOT}" "${CANDIDATE_COMMIT}" \
    "${REPOSITORY}" "${GITHUB_RUN_ID}" "${PR_NUMBER}" "${PR_RUN_ID}" \
    > "${log_file}" 2>&1 <<'PY'
import importlib.util
import json
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
validation_root = Path(sys.argv[2])
commit = sys.argv[3]
repository = sys.argv[4]
expected_push_run_id = int(sys.argv[5])
expected_pr_number = int(sys.argv[6])
expected_pr_run_id = int(sys.argv[7])
script = repo_root / "scripts/build_validation_packet_v0.3.0.py"
spec = importlib.util.spec_from_file_location("validation_packet_builder", script)
if spec is None or spec.loader is None:
    raise SystemExit(f"Unable to import acceptance validator: {script}")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)

builder.validate_github_actions_evidence(validation_root, commit, repository)
push_run = json.loads(
    (validation_root / "acceptance/github_actions_run.json").read_text(
        encoding="utf-8"
    )
)
if push_run.get("id") != expected_push_run_id:
    raise SystemExit("Final push run does not match MITO_OVERVIEW_GITHUB_RUN_ID")
pull_request = builder.validate_pull_request_evidence(
    validation_root,
    repo_root,
    commit,
    repository,
)
if pull_request.get("number") != expected_pr_number:
    raise SystemExit("Merged PR does not match MITO_OVERVIEW_PR_NUMBER")
_, pr_ci = builder.validate_pull_request_github_actions_evidence(
    validation_root,
    pull_request,
    repository,
)
if pr_ci.get("run_id") != expected_pr_run_id:
    raise SystemExit("PR smoke run does not match MITO_OVERVIEW_PR_RUN_ID")
audit_rows, _ = builder.validate_read_only_audit_comments(
    validation_root,
    pull_request,
    repository,
)
if len(audit_rows) != 3:
    raise SystemExit("Exactly three structured read-only agent-role audits are required")
print(
    "github_acceptance_preflight=PASS "
    f"push_run_id={expected_push_run_id} pr={expected_pr_number} "
    f"pr_run_id={expected_pr_run_id} read_only_audits={len(audit_rows)}"
)
PY
  then
    return 0
  fi
  tail -100 "${log_file}" >&2
  return 1
}

validate_public_main_tip() {
  local command_file="${VALIDATION_ROOT}/commands/public_main_tip.sh"
  local log_file="${VALIDATION_ROOT}/logs/public_main_tip.log"
  printf 'git ls-remote --exit-code %q refs/heads/main\n' "${PUBLIC_REMOTE}" > "${command_file}"
  chmod +x "${command_file}"
  local observed
  if ! observed="$(git ls-remote --exit-code "${PUBLIC_REMOTE}" refs/heads/main 2>"${log_file}")"; then
    echo "Unable to resolve the public main branch from ${PUBLIC_REMOTE}." >&2
    cat "${log_file}" >&2
    return 1
  fi
  if ! "${PYTHON_BIN}" - "${observed}" "${CANDIDATE_COMMIT}" >> "${log_file}" 2>&1 <<'PY'
import re
import sys

lines = [line for line in sys.argv[1].splitlines() if line.strip()]
if len(lines) != 1:
    raise SystemExit(f"Expected one public main ref, observed {len(lines)}")
fields = lines[0].split("\t")
if len(fields) != 2 or fields[1] != "refs/heads/main":
    raise SystemExit("Public main ref response is malformed")
if re.fullmatch(r"[0-9a-f]{40}", fields[0]) is None:
    raise SystemExit("Public main ref is not a full commit SHA")
if fields[0] != sys.argv[2]:
    raise SystemExit(
        f"Public main drift: expected release candidate {sys.argv[2]}, observed {fields[0]}"
    )
print(f"public_main_commit={fields[0]}")
PY
  then
    cat "${log_file}" >&2
    return 1
  fi
}

run_fresh_clone_validation() {
  local clone_root="${FRESH_CLONE_ROOT}"
  local env_root="${FRESH_ENV_ROOT}"
  local home_root="${FRESH_ENV_ROOT}/home"
  local tmp_root="${FRESH_ENV_ROOT}/tmp"
  local cache_root="${FRESH_ENV_ROOT}/cache"
  local venv_root="${FRESH_VENV_ROOT}"
  local probe_root="${VALIDATION_ROOT}/work/installed_probe"
  local command_file="${VALIDATION_ROOT}/commands/${FRESH_CLONE_CASE_ID}.sh"
  local log_file="${VALIDATION_ROOT}/logs/${FRESH_CLONE_CASE_ID}.log"

  mkdir -p "${home_root}" "${tmp_root}" "${cache_root}" "${probe_root}" \
    "${VALIDATION_ROOT}/acceptance/fresh_clone_environment"
  cat > "${command_file}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
export PATH=$(printf '%q' "${PATH}")
run_clean() {
  env -i \
    HOME=$(printf '%q' "${home_root}") \
    TMPDIR=$(printf '%q' "${tmp_root}") \
    XDG_CACHE_HOME=$(printf '%q' "${cache_root}") \
    PATH="\${PATH}" \
    PYTHONNOUSERSITE=1 PYTHONPATH= PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LC_ALL=C LANG=C TZ=UTC THREADS=4 \
    "\$@"
}

run_clean git clone --no-checkout $(printf '%q' "${PUBLIC_REMOTE}") $(printf '%q' "${clone_root}")
run_clean git -C $(printf '%q' "${clone_root}") cat-file -e $(printf '%q' "${CANDIDATE_COMMIT}^{commit}")
test "\$(run_clean git -C $(printf '%q' "${clone_root}") rev-parse refs/remotes/origin/main)" = $(printf '%q' "${CANDIDATE_COMMIT}")
run_clean git -C $(printf '%q' "${clone_root}") checkout --detach $(printf '%q' "${CANDIDATE_COMMIT}")
test "\$(run_clean git -C $(printf '%q' "${clone_root}") rev-parse HEAD)" = $(printf '%q' "${CANDIDATE_COMMIT}")
test "\$(run_clean git -C $(printf '%q' "${clone_root}") remote get-url origin)" = $(printf '%q' "${PUBLIC_REMOTE}")
run_clean git -C $(printf '%q' "${clone_root}") fsck --full
test -z "\$(run_clean git -C $(printf '%q' "${clone_root}") status --porcelain --untracked-files=all)"
run_clean $(printf '%q' "${PYTHON_BIN}") -m venv $(printf '%q' "${venv_root}")
FRESH_PYTHON=$(printf '%q' "${venv_root}/bin/python")
run_clean "\${FRESH_PYTHON}" -m pip install --force-reinstall \
  pip==26.1.2 build==1.5.0 setuptools==82.0.1 wheel==0.47.0 \
  pytest==9.1.1 python-docx==1.2.0
run_clean "\${FRESH_PYTHON}" -m build --no-isolation \
  --outdir $(printf '%q' "${VALIDATION_ROOT}/dist") $(printf '%q' "${clone_root}")
WHEEL="\$(find $(printf '%q' "${VALIDATION_ROOT}/dist") -maxdepth 1 -type f -name '*.whl' -print -quit)"
SDIST="\$(find $(printf '%q' "${VALIDATION_ROOT}/dist") -maxdepth 1 -type f -name '*.tar.gz' -print -quit)"
test -n "\${WHEEL}" && test -n "\${SDIST}"
run_clean "\${FRESH_PYTHON}" -m pip install --force-reinstall "\${WHEEL}"
run_clean "\${FRESH_PYTHON}" -I -c \
  'import platform,sys; assert tuple(sys.version_info[:3]) == (3,12,13), platform.python_version()'
run_clean "\${FRESH_PYTHON}" -I -c \
  'from importlib.metadata import version; expected={"mito-overview":"0.3.0","pysam":"0.24.0","pandas":"3.0.3","numpy":"2.5.1","matplotlib":"3.11.0","requests":"2.34.2","pytest":"9.1.1","build":"1.5.0","setuptools":"82.0.1","wheel":"0.47.0","python-docx":"1.2.0"}; observed={k:version(k) for k in expected}; assert observed == expected, (observed, expected)'
test "\$(run_clean samtools --version | sed -n '1p')" = 'samtools 1.23.1'
test "\$(run_clean samtools --version | sed -n '2p')" = 'Using htslib 1.23.1'
test "\$(run_clean minimap2 --version)" = '2.31-r1302'
BWA_VERSION="\$(run_clean bwa 2>&1 || true)"
grep -F 'Version: 0.7.19-r1273' <<< "\${BWA_VERSION}" >/dev/null
run_clean "\${FRESH_PYTHON}" -m pip freeze --all > $(printf '%q' "${VALIDATION_ROOT}/acceptance/fresh_clone_environment/pip-freeze.txt")
cd $(printf '%q' "${probe_root}")
run_clean "\${FRESH_PYTHON}" -I -c \
  'from pathlib import Path; import mito_overview; p=Path(mito_overview.__file__).resolve(); assert "site-packages" in p.parts; print(p)'
run_clean "\${FRESH_PYTHON}" -I -m mito_overview.cli --list-steps
cd $(printf '%q' "${clone_root}")
run_clean "\${FRESH_PYTHON}" -m pytest -q
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_public_pipeline.sh
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_public_pipeline_shortread.sh
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_public_pipeline_longread_nomethyl.sh
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_standalone_minimal.sh
test -z "\$(run_clean git -C $(printf '%q' "${clone_root}") status --porcelain --untracked-files=all)"
echo fresh_clone_validation=PASS
EOF
  chmod +x "${command_file}"

  if measure_command "${FRESH_CLONE_CASE_ID}" "${log_file}" bash "${command_file}"; then
    "${PYTHON_BIN}" -       "${VALIDATION_ROOT}/acceptance/fresh_clone.json"       "${CANDIDATE_COMMIT}" "${REPOSITORY}" "${PUBLIC_REMOTE}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
evidence = {
    "schema_version": "2.0",
    "validation_profile": "github_release_validation_v1",
    "evidence_type": "fresh_clone_validation",
    "case_id": "fresh_clone_candidate_commit",
    "verdict": "PASS",
    "repository": sys.argv[3],
    "source_remote": sys.argv[4],
    "candidate_commit": sys.argv[2],
    "checked_out_commit": sys.argv[2],
    "public_main_commit": sys.argv[2],
    "detached_head": True,
    "clone_worktree_clean": True,
    "public_https_clone": True,
    "isolated_home": True,
    "isolated_tmpdir": True,
    "built_wheel": True,
    "built_sdist": True,
    "installed_wheel": True,
    "executed_outside_checkout": True,
    "command_path": "commands/fresh_clone_candidate_commit.sh",
    "log_path": "logs/fresh_clone_candidate_commit.log",
}
path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
PY
    return 0
  fi
  record_case "${FRESH_CLONE_CASE_ID}" release_acceptance 1 1 FAIL     "fresh public clone failed; see logs/${FRESH_CLONE_CASE_ID}.log"
  tail -100 "${log_file}" >&2
  return 1
}

fetch_and_compare_ubuntu_public_evidence() {
  local command_file="${VALIDATION_ROOT}/commands/cross_platform_public_reproduction.sh"
  local log_file="${VALIDATION_ROOT}/logs/cross_platform_public_reproduction.log"
  local acceptance_root="${VALIDATION_ROOT}/acceptance/ubuntu_public_validation"
  local artifacts_json="${acceptance_root}/artifacts.json"
  local artifact_root="${acceptance_root}/artifact"
  local comparison_tsv="${VALIDATION_ROOT}/acceptance/cross_platform_comparison.tsv"
  local comparison_json="${VALIDATION_ROOT}/acceptance/cross_platform_public_reproduction.json"
  local public_run_id="${PUBLIC_RUN_ID}"
  local artifact_name="public-validation-derived-${CANDIDATE_COMMIT}-${PUBLIC_RUN_ID}"

  mkdir -p "${acceptance_root}" "${artifact_root}"
  cat > "${command_file}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
gh run download ${PUBLIC_RUN_ID} --repo ${GITHUB_REPOSITORY} \
  --name ${artifact_name} --dir acceptance/ubuntu_public_validation/artifact
# The exact run and artifact identities were validated by
# commands/public_validation_run_preflight.sh before RAW_CACHE_ROOT was created.
EOF
  chmod +x "${command_file}"

  if {
    "${PYTHON_BIN}" - \
      "${artifacts_json}" "${artifact_name}" "${public_run_id}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = sys.argv[2]
expected_run_id = int(sys.argv[3])
matches = [
    artifact for artifact in payload.get("artifacts", [])
    if artifact.get("name") == expected
    and artifact.get("workflow_run", {}).get("id") == expected_run_id
    and not artifact.get("expired", False)
]
if len(matches) != 1:
    raise SystemExit(f"Expected one unexpired public-validation artifact {expected!r}")
PY
    gh run download "${public_run_id}" --repo "${GITHUB_REPOSITORY}" \
      --name "${artifact_name}" --dir "${artifact_root}"
    test -s "${artifact_root}/SHA256SUMS"
    (cd "${artifact_root}" && shasum -a 256 -c SHA256SUMS)
    test -s "${artifact_root}/environment/identity.txt"
    grep -Fx "git_commit=${CANDIDATE_COMMIT}" \
      "${artifact_root}/environment/identity.txt" >/dev/null
    grep -Fx 'runner_os=Linux' "${artifact_root}/environment/identity.txt" >/dev/null
    grep -Fx 'runner_arch=X64' "${artifact_root}/environment/identity.txt" >/dev/null
    test -s "${artifact_root}/results/oracle_assertions.tsv"
    test -s "${artifact_root}/results/environment/runtime_versions.json"

    "${PYTHON_BIN}" - \
      "${PUBLIC_ROOT}" "${artifact_root}/results" \
      "${comparison_tsv}" "${comparison_json}" \
      "${CANDIDATE_COMMIT}" "${public_run_id}" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

local_root = Path(sys.argv[1])
ubuntu_root = Path(sys.argv[2])
report_path = Path(sys.argv[3])
json_path = Path(sys.argv[4])
commit = sys.argv[5]
public_run_id = int(sys.argv[6])

def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()

def scientific_paths(root: Path) -> set[Path]:
    paths = {
        path.relative_to(root)
        for path in (root / "observed_normalized").rglob("*.tsv")
        if path.name != "visual_artifact_inventory.tsv"
    }
    for name in (
        "cases.tsv",
        "filter_profile_results.tsv",
        "inputs.sha256",
        "oracle_assertions.tsv",
        "raw_inputs.tsv",
        "CACHE_SEAL.sha256",
    ):
        if (root / name).is_file():
            paths.add(Path(name))
    return paths

local_paths = scientific_paths(local_root)
ubuntu_paths = scientific_paths(ubuntu_root)
if local_paths != ubuntu_paths:
    raise SystemExit(
        "Cross-platform scientific path inventories differ: "
        f"local_only={sorted(map(str, local_paths - ubuntu_paths))}; "
        f"ubuntu_only={sorted(map(str, ubuntu_paths - local_paths))}"
    )

rows = []
for relative in sorted(local_paths, key=lambda path: path.as_posix()):
    local = local_root / relative
    ubuntu = ubuntu_root / relative
    local_hash = digest(local)
    ubuntu_hash = digest(ubuntu)
    status = "PASS" if local_hash == ubuntu_hash else "FAIL"
    rows.append(
        {
            "evidence_type": "normalized_scientific_table",
            "relative_path": relative.as_posix(),
            "macos_sha256": local_hash,
            "ubuntu_sha256": ubuntu_hash,
            "verdict": status,
            "comparison": "byte-identical normalized content",
        }
    )
    if status != "PASS":
        raise SystemExit(f"Cross-platform normalized result differs: {relative}")

visual_fields = (
    "relative_path",
    "artifact_type",
    "width_px",
    "height_px",
    "integrity_status",
)
local_visuals = sorted(
    (local_root / "observed_normalized").rglob("visual_artifact_inventory.tsv")
)
ubuntu_visuals = sorted(
    (ubuntu_root / "observed_normalized").rglob("visual_artifact_inventory.tsv")
)
local_visual_rel = [path.relative_to(local_root) for path in local_visuals]
ubuntu_visual_rel = [path.relative_to(ubuntu_root) for path in ubuntu_visuals]
if local_visual_rel != ubuntu_visual_rel:
    raise SystemExit("Cross-platform visual-inventory paths differ")
for relative in local_visual_rel:
    def selected(root: Path) -> list[tuple[str, ...]]:
        with (root / relative).open(encoding="utf-8", newline="") as handle:
            parsed = csv.DictReader(handle, delimiter="\t")
            return sorted(tuple(row.get(field, "") for field in visual_fields) for row in parsed)
    local_structure = selected(local_root)
    ubuntu_structure = selected(ubuntu_root)
    status = "PASS" if local_structure == ubuntu_structure else "FAIL"
    rows.append(
        {
            "evidence_type": "visual_structure",
            "relative_path": relative.as_posix(),
            "macos_sha256": "not_compared",
            "ubuntu_sha256": "not_compared",
            "verdict": status,
            "comparison": "path/type/dimensions/integrity; pixel hashes are not cross-platform gates",
        }
    )
    if status != "PASS":
        raise SystemExit(f"Cross-platform visual structure differs: {relative}")

with report_path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(
        handle,
        fieldnames=(
            "evidence_type",
            "relative_path",
            "macos_sha256",
            "ubuntu_sha256",
            "verdict",
            "comparison",
        ),
        delimiter="\t",
        lineterminator="\n",
    )
    writer.writeheader()
    writer.writerows(rows)

local_environment = json.loads(
    (local_root / "environment/runtime_versions.json").read_text(encoding="utf-8")
)
ubuntu_environment = json.loads(
    (ubuntu_root / "environment/runtime_versions.json").read_text(encoding="utf-8")
)
if not local_environment["platform_id"].startswith("osx-"):
    raise SystemExit("The release-side public matrix must be reproduced on macOS")
if ubuntu_environment["platform_id"] != "linux-64":
    raise SystemExit("The hosted public matrix must be reproduced on linux-64")
json_path.write_text(
    json.dumps(
        {
            "schema_version": "2.0",
            "validation_profile": "github_release_validation_v1",
            "evidence_type": "cross_platform_public_reproduction",
            "verdict": "PASS",
            "git_commit": commit,
            "ubuntu_public_validation_run_id": public_run_id,
            "macos_platform": local_environment["platform_id"],
            "ubuntu_platform": ubuntu_environment["platform_id"],
            "normalized_scientific_tables_compared": sum(
                row["evidence_type"] == "normalized_scientific_table" for row in rows
            ),
            "visual_inventories_compared": sum(
                row["evidence_type"] == "visual_structure" for row in rows
            ),
            "comparison_table": "cross_platform_comparison.tsv",
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY
    echo "cross_platform_public_reproduction=PASS"
  } > "${log_file}" 2>&1; then
    record_case cross_platform_public_reproduction cross_platform 1 1 PASS \
      "Ubuntu and macOS normalized scientific outputs and visual structures matched"
    return 0
  fi
  record_case cross_platform_public_reproduction cross_platform 1 1 FAIL \
    "see logs/cross_platform_public_reproduction.log"
  tail -100 "${log_file}" >&2
  return 1
}

append_acceptance_cases() {
  "${PYTHON_BIN}" - "${REPO_ROOT}" "${VALIDATION_ROOT}"     "${CANDIDATE_COMMIT}" "${REPOSITORY}" <<'PY'
import csv
import importlib.util
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
validation_root = Path(sys.argv[2])
script = repo_root / "scripts/build_validation_packet_v0.3.0.py"
spec = importlib.util.spec_from_file_location("validation_packet_builder", script)
if spec is None or spec.loader is None:
    raise SystemExit(f"Unable to import acceptance validator: {script}")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
rows = builder.validate_acceptance_evidence(
    validation_root, repo_root, sys.argv[3], sys.argv[4]
)
writer = csv.DictWriter(
    sys.stdout,
    fieldnames=(
        "case_id", "category", "input_available", "expected_available",
        "verdict", "detail",
    ),
    delimiter="\t",
    lineterminator="\n",
)
writer.writerows(rows)
PY
}

{
  echo "release_version=v0.3.0"
  echo "git_commit=${CANDIDATE_COMMIT}"
  echo "git_branch=$(git -C "${REPO_ROOT}" branch --show-current)"
  echo "repository=${REPOSITORY}"
  echo "github_actions_run_id=${GITHUB_RUN_ID}"
  echo "final_push_github_actions_run_id=${GITHUB_RUN_ID}"
  echo "pull_request_number=${PR_NUMBER}"
  echo "pull_request_github_actions_run_id=${PR_RUN_ID}"
  echo "public_validation_github_actions_run_id=${PUBLIC_RUN_ID}"
  echo "validation_profile=${VALIDATION_PROFILE}"
  echo "generated_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  uname -a
  if command -v sw_vers >/dev/null 2>&1; then sw_vers; fi
  "${PYTHON_BIN}" --version
  "${PYTHON_BIN}" -m pip freeze
  for tool in samtools minimap2 bwa; do
    if command -v "${tool}" >/dev/null 2>&1; then
      echo "--- ${tool} ---"
      "${tool}" --version 2>&1 | head -n 4 || true
    fi
  done
} > "${VALIDATION_ROOT}/environment.txt" 2>&1

fetch_github_actions_evidence
fetch_pull_request_evidence
preflight_public_validation_evidence
validate_github_preflight_evidence
validate_public_main_tip
if [[ -e "${CACHE_ROOT}" || -L "${CACHE_ROOT}" ]]; then
  echo "Raw cache root appeared during preflight and will not be reused: ${CACHE_ROOT}" >&2
  exit 1
fi
mkdir -p "$(dirname "${CACHE_ROOT}")"
mkdir "${CACHE_ROOT}"
run_fresh_clone_validation

run_logged unit_known_answer unit "${PYTHON_BIN}" -m pytest -q
run_logged cli_step_listing cli "${PYTHON_BIN}" -m mito_overview.cli --list-steps

source "${REPO_ROOT}/scripts/lib/prepare_synthetic_toy_sample.sh"
STRICT_ROOT="${VALIDATION_ROOT}/work/strict_generic"
mkdir -p "${STRICT_ROOT}"
prepare_synthetic_toy_sample "${REPO_ROOT}" "${STRICT_ROOT}"
cat > "${STRICT_ROOT}/standalone.env" <<EOF
WORK_ROOT=${STRICT_ROOT}/runs
RUN_NAME=strict_generic
SAMPLE_ID=TOY-001
REF_FASTA=${STRICT_ROOT}/tiny_GRCh38.fa
SOURCE_ALIGN_FILE=${STRICT_ROOT}/sample/human_variation/TOY-001.input.bam
MT_CONTIG=MT
EOF
run_logged strict_generic_dry_run cli   "${PYTHON_BIN}" -m mito_overview.cli   --config "${STRICT_ROOT}/standalone.env" --dry-run --strict-files
run_logged synthetic_longread_smoke synthetic   env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_public_pipeline.sh"
run_logged synthetic_shortread_smoke synthetic   env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_public_pipeline_shortread.sh"
run_logged synthetic_longread_nomethyl_smoke synthetic   env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_public_pipeline_longread_nomethyl.sh"
run_logged standalone_minimal_smoke synthetic   env MITO_OVERVIEW_PYTHON="${PYTHON_BIN}" "${REPO_ROOT}/tests/smoke_standalone_minimal.sh"

cat > "${VALIDATION_ROOT}/commands/package_build.sh" <<EOF
#!/usr/bin/env bash
echo 'Distribution artifacts were built by commands/${FRESH_CLONE_CASE_ID}.sh'
EOF
printf 'wheel and sdist built from public clone at %s\n' "${CANDIDATE_COMMIT}"   > "${VALIDATION_ROOT}/logs/package_build.log"
cp "${VALIDATION_ROOT}/resources/${FRESH_CLONE_CASE_ID}.json"   "${VALIDATION_ROOT}/resources/package_build.json"
sed -i.bak 's/"case_id": "fresh_clone_candidate_commit"/"case_id": "package_build"/' \
  "${VALIDATION_ROOT}/resources/package_build.json"
rm "${VALIDATION_ROOT}/resources/package_build.json.bak"
record_case package_build package 1 1 PASS   "wheel and sdist built from exact public clone; see logs/package_build.log"

cp "${REPO_ROOT}/examples/synthetic_data/TOY-WGS-001/expected_copy_proxy.tsv"   "${VALIDATION_ROOT}/expected/TOY-WGS-001.expected_copy_proxy.tsv"
cp "${REPO_ROOT}/examples/synthetic_data/TOY-SR-001/expected_alleles.tsv"   "${VALIDATION_ROOT}/expected/TOY-SR-001.expected_alleles.tsv"

PREPARE_SCRIPT="${FRESH_CLONE_ROOT}/scripts/prepare_public_validation_cache_v0.3.0.sh"
PUBLIC_MATRIX="${FRESH_CLONE_ROOT}/scripts/run_public_validation_matrix_v0.3.0.sh"
ISOLATION_WRAPPER="${FRESH_CLONE_ROOT}/scripts/run_network_isolated_v0.3.0.sh"
ORACLE="${FRESH_CLONE_ROOT}/examples/public_validation/public_validation_oracle_v0.3.0.tsv"
for required in "${PREPARE_SCRIPT}" "${PUBLIC_MATRIX}" "${ISOLATION_WRAPPER}" "${ORACLE}"; do
  if [[ ! -e "${required}" ]]; then
    echo "Required clean-room validation component is missing: ${required}" >&2
    exit 1
  fi
done
if [[ ! -d "${CACHE_ROOT}" || -L "${CACHE_ROOT}" ]] || \
   [[ -n "$(find "${CACHE_ROOT}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "Raw cache root must still be an empty regular directory immediately before download: ${CACHE_ROOT}" >&2
  exit 1
fi
run_logged public_cache_prepare public_input \
  "${PREPARE_SCRIPT}" --cache "${CACHE_ROOT}"

case "$(uname -s)/$(uname -m)" in
  Darwin/x86_64) LOCAL_PUBLIC_PLATFORM="osx-64" ;;
  Darwin/arm64) LOCAL_PUBLIC_PLATFORM="osx-arm64" ;;
  *)
    echo "Release-side public reproduction must run on macOS, observed $(uname -s)/$(uname -m)." >&2
    exit 1
    ;;
esac

PUBLIC_ROOT="${VALIDATION_ROOT}/public"
NETWORK_ISOLATION_EVIDENCE="${VALIDATION_ROOT}/work/public_network_isolation.tsv"
mkdir -p "${VALIDATION_ROOT}/work/public_home" \
  "${VALIDATION_ROOT}/work/public_tmp" \
  "${VALIDATION_ROOT}/work/public_xdg_cache"
run_logged public_validation_matrix public \
  env -i \
    HOME="${VALIDATION_ROOT}/work/public_home" \
    TMPDIR="${VALIDATION_ROOT}/work/public_tmp" \
    XDG_CACHE_HOME="${VALIDATION_ROOT}/work/public_xdg_cache" \
    PATH="${PATH}" PYTHONNOUSERSITE=1 PYTHONPATH= \
    PIP_DISABLE_PIP_VERSION_CHECK=1 LC_ALL=C LANG=C TZ=UTC THREADS=4 \
    MITO_OVERVIEW_PYTHON="${FRESH_PYTHON}" \
    MITO_OVERVIEW_REQUIRE_INSTALLED=1 \
    MITO_OVERVIEW_EXPECTED_PLATFORM="${LOCAL_PUBLIC_PLATFORM}" \
    "${ISOLATION_WRAPPER}" \
      --evidence "${NETWORK_ISOLATION_EVIDENCE}" -- \
      "${PUBLIC_MATRIX}" \
        --mode offline \
        --cache "${CACHE_ROOT}" \
        --work "${VALIDATION_ROOT}/work/public_matrix" \
        --output "${PUBLIC_ROOT}" \
        --oracle "${ORACLE}"
grep -Fqx $'network_isolation_verdict\tPASS' \
  "${PUBLIC_ROOT}/environment/network_isolation.tsv" || {
  echo "Public validation did not preserve valid OS-level network-isolation evidence" >&2
  exit 1
}
grep -Fq $'offline_isolation\tos_network_isolation\t1\t1\tPASS\t' \
  "${PUBLIC_ROOT}/cases.tsv" || {
  echo "Public validation did not record a passing OS-level isolation case" >&2
  exit 1
}
tail -n +2 "${PUBLIC_ROOT}/cases.tsv" >> "${CASES_TSV}"
cp -R "${PUBLIC_ROOT}/environment" \
  "${VALIDATION_ROOT}/acceptance/macos_public_environment"
fetch_and_compare_ubuntu_public_evidence
append_acceptance_cases >> "${CASES_TSV}"

"${PYTHON_BIN}" - "${VALIDATION_ROOT}" "${PUBLIC_ROOT}" <<'PY'
import csv
import hashlib
import json
import shutil
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

validation_root = Path(sys.argv[1])
public_root = Path(sys.argv[2])

def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

def write_table(name: str, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    if not rows:
        raise SystemExit(f"Cannot create empty release evidence table: {name}")
    with (validation_root / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)

claim_rows = [
    {
        "claim_id": "C1",
        "bounded_claim": "Shared filtered allele counting is deterministic on known-answer fixtures",
        "evidence": "unit_known_answer; synthetic_longread_smoke; expected/TOY-SR-001.expected_alleles.tsv",
        "limitation": "Reporting thresholds are not clinically calibrated",
    },
    {
        "claim_id": "C2",
        "bounded_claim": "mvTool is offline by default with deterministic fixture coverage",
        "evidence": "unit_known_answer; synthetic_longread_smoke",
        "limitation": "No claim of live service availability",
    },
    {
        "claim_id": "C3",
        "bounded_claim": "Minimal standalone alignment contracts are preflighted",
        "evidence": "unit_known_answer; strict_generic_dry_run; standalone_minimal_smoke",
        "limitation": "Optional sidecars remain user supplied",
    },
    {
        "claim_id": "C4",
        "bounded_claim": "The WGS fixture reports a 100/10 mt:nuclear depth ratio of 10.0",
        "evidence": "unit_known_answer; expected/TOY-WGS-001.expected_copy_proxy.tsv",
        "limitation": "Experimental depth proxy, not absolute copies per diploid cell",
    },
    {
        "claim_id": "C5",
        "bounded_claim": "mt-only references suppress categorical NUMT interpretation",
        "evidence": "unit_known_answer; gm12878_default_run1; gm12878_repeatability",
        "limitation": "Alignment-ambiguity QC is not a formal NUMT classifier",
    },
    {
        "claim_id": "C6",
        "bounded_claim": "Public proof-of-principle workflows reproduce normalized TSVs",
        "evidence": "gm11906_repeatability; gm12878_repeatability; filter_profile_results.tsv",
        "limitation": "Not an analytical-performance or diagnostic benchmark",
    },
]
write_table(
    "claim_evidence_matrix.tsv",
    ["claim_id", "bounded_claim", "evidence", "limitation"],
    claim_rows,
)

module_rows = []
for case_id in ("gm11906_default_run1", "gm12878_default_run1"):
    dataset = "GM11906" if case_id.startswith("gm11906") else "GM12878"
    case_root = public_root / "observed_normalized" / case_id
    for table in sorted(case_root.glob("*.tsv")):
        try:
            with table.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle, delimiter="\t"))
        except UnicodeDecodeError:
            continue
        if not rows or rows[0][:2] != ["metric", "value"]:
            continue
        values = {row[0]: row[1] for row in rows[1:] if len(row) >= 2}
        if "status" not in values:
            continue
        module_rows.append(
            {
                "dataset": dataset,
                "case_id": case_id,
                "module": table.stem,
                "status": values["status"],
                "reason_code": values.get("reason_code", ""),
                "source_table": (
                    "observed_normalized/"
                    + table.relative_to(public_root / "observed_normalized").as_posix()
                ),
            }
        )
write_table(
    "module_status_matrix.tsv",
    ["dataset", "case_id", "module", "status", "reason_code", "source_table"],
    module_rows,
)

resource_rows = []
for resource_path in sorted((validation_root / "resources").glob("*.json")):
    value = json.loads(resource_path.read_text(encoding="utf-8"))
    resource_rows.append(
        {
            key: value.get(key, "")
            for key in (
                "case_id", "wall_seconds", "user_cpu_seconds", "system_cpu_seconds",
                "max_rss_kb", "threads", "platform", "measurement_status", "reason",
            )
        }
    )
write_table(
    "resource_usage.tsv",
    [
        "case_id", "wall_seconds", "user_cpu_seconds", "system_cpu_seconds",
        "max_rss_kb", "threads", "platform", "measurement_status", "reason",
    ],
    resource_rows,
)

figure_root = validation_root / "figures"
figure_rows = []
for case_id in ("gm11906_default_run1", "gm12878_default_run1"):
    dataset = "GM11906" if case_id.startswith("gm11906") else "GM12878"
    inventory = (
        public_root / "observed_normalized" / case_id / "visual_artifact_inventory.tsv"
    )
    with inventory.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    for row in rows:
        if row.get("artifact_type") != "png":
            continue
        source = public_root / "outputs" / case_id / row["relative_path"]
        destination = figure_root / case_id / Path(row["relative_path"]).name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        if digest(destination) != row["sha256"]:
            raise SystemExit(f"Figure hash changed during evidence copy: {source}")
        figure_rows.append(
            {
                "figure_id": f"{case_id}:{destination.name}",
                "dataset": dataset,
                "case_id": case_id,
                "packet_path": destination.relative_to(validation_root).as_posix(),
                "sha256": digest(destination),
                "bytes": destination.stat().st_size,
                "width": row["width_px"],
                "height": row["height_px"],
                "visual_status": row["integrity_status"],
                "source_inventory": (
                    "observed_normalized/"
                    + inventory.relative_to(public_root / "observed_normalized").as_posix()
                ),
            }
        )
write_table(
    "figure_provenance.tsv",
    [
        "figure_id", "dataset", "case_id", "packet_path", "sha256", "bytes",
        "width", "height", "visual_status", "source_inventory",
    ],
    figure_rows,
)

table_rows = []
normalized_root = public_root / "observed_normalized"
for table in sorted(normalized_root.rglob("*.tsv")):
    relative = table.relative_to(normalized_root)
    with table.open(encoding="utf-8", newline="") as handle:
        parsed = list(csv.reader(handle, delimiter="\t"))
    case_id = relative.parts[0]
    dataset = "GM11906" if case_id.startswith("gm11906") else "GM12878"
    table_rows.append(
        {
            "table_id": relative.as_posix(),
            "dataset": dataset,
            "case_id": case_id,
            "packet_path": f"observed_normalized/{relative.as_posix()}",
            "sha256": digest(table),
            "rows": max(0, len(parsed) - 1),
            "columns": len(parsed[0]) if parsed else 0,
            "purpose": "normalized scientific or visual-inventory evidence",
        }
    )
write_table(
    "table_provenance.tsv",
    [
        "table_id", "dataset", "case_id", "packet_path", "sha256", "rows",
        "columns", "purpose",
    ],
    table_rows,
)

recorded = datetime.now(timezone.utc).isoformat()
public_rows = [
    {
        "dataset": "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        "run_accession": "SRR10804585",
        "study_accession": "PRJNA598179",
        "sample_accession": "SAMN13699362",
        "cell_line": "GM11906",
        "platform": "ILLUMINA",
        "instrument_model": "NextSeq 550",
        "library_strategy": "ATAC-seq",
        "fastq_url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/085/SRR10804585/SRR10804585_2.fastq.gz",
        "fastq_md5": "3f5ea26a5791894071462d4970bc9e5a;c5b408425612f63b33cefd2d49c157d1",
        "fastq_sha256": "b69746cb61d8bf3bc25887d6ece3c60db3acc7baaefd84a9a8b5d6ffce33288d;1fca2c35a955a4ed232465d8392bc04683828229178aee7915929e67b2aac961",
        "fastq_bytes": "8795676;8817420",
    },
    {
        "dataset": "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        "run_accession": "SRR10804590",
        "study_accession": "PRJNA598179",
        "sample_accession": "SAMN13699398",
        "cell_line": "GM11906",
        "platform": "ILLUMINA",
        "instrument_model": "NextSeq 550",
        "library_strategy": "ATAC-seq",
        "fastq_url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/090/SRR10804590/SRR10804590_2.fastq.gz",
        "fastq_md5": "e8b5132a8be8c179bfc6dbc0f3e1bee9;4d6977526136739de2d90baa8d45b484",
        "fastq_sha256": "e47ceceb03d44483b4948fe9c631ebff307f5ec68a1deec978f1122695fa58fc;05b2375b30b02c02e9206981eb2fe2d08babbc2a5809f8354ef56d0ac1550776",
        "fastq_bytes": "1006749;795885",
    },
    {
        "dataset": "GM11906 pooled single-cell ATAC-seq pseudo-bulk",
        "run_accession": "SRR10804657",
        "study_accession": "PRJNA598179",
        "sample_accession": "SAMN13699338",
        "cell_line": "GM11906",
        "platform": "ILLUMINA",
        "instrument_model": "NextSeq 550",
        "library_strategy": "ATAC-seq",
        "fastq_url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_1.fastq.gz;https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR108/057/SRR10804657/SRR10804657_2.fastq.gz",
        "fastq_md5": "8f082f73cb64bf56ea8a053fe80eeb06;62b7d1b2294a580c021f5fa1f52609be",
        "fastq_sha256": "1afaf310ce9ffa77e1c3d61a0714e839d21000941d414cc7bf6fb590c3b665f2;bfc555c7e722695b02110027757bba4d7fc88f487798423cd6809e8a771a5184",
        "fastq_bytes": "21510555;21573731",
    },
    {
        "dataset": "GM12878 ONT targeted-mt proof-of-principle",
        "run_accession": "SRR18110025",
        "study_accession": "PRJNA809571",
        "sample_accession": "SAMN26195906",
        "cell_line": "GM12878",
        "platform": "OXFORD_NANOPORE",
        "instrument_model": "GridION",
        "library_strategy": "OTHER",
        "fastq_url": "https://ftp.sra.ebi.ac.uk/vol1/fastq/SRR181/025/SRR18110025/SRR18110025_1.fastq.gz",
        "fastq_md5": "d5bfb9aeba04cae5f3dd79462a42e5b0",
        "fastq_sha256": "c0872ee9ceb772ee5a4b76735c0d670e2159764b23dd800b6eb1f4933da11320",
        "fastq_bytes": "2033558460",
    },
]
for row in public_rows:
    row.update(
        {
            "metadata_recorded_utc": recorded,
            "role": "fixed-input reproducibility and descriptive filter profile",
            "redistribution": "raw reads excluded from Git and validation ZIP",
        }
    )
write_table(
    "public_data_sources.tsv",
    [
        "dataset", "run_accession", "study_accession", "sample_accession",
        "cell_line", "platform", "instrument_model", "library_strategy",
        "fastq_url", "fastq_md5", "fastq_sha256", "fastq_bytes",
        "metadata_recorded_utc", "role", "redistribution",
    ],
    public_rows,
)

handoff_rows = []
with (public_root / "filter_profile_results.tsv").open(
    encoding="utf-8", newline=""
) as handle:
    profiles = list(csv.DictReader(handle, delimiter="\t"))
for profile in profiles:
    for metric, unit in (
        ("candidate_sites", "sites"),
        ("accepted_observations", "observations"),
        ("excluded_observations", "observations"),
        ("m8344_A_G_alt_allele_fraction", "fraction"),
    ):
        if profile.get(metric, "") == "":
            continue
        handoff_rows.append(
            {
                "result_id": f"{profile['case_id']}:{metric}",
                "dataset": profile["dataset"],
                "metric": metric,
                "value": profile[metric],
                "unit": unit,
                "source_table": "filter_profile_results.tsv",
                "claim_boundary": "descriptive fixed-input result; not diagnostic performance",
            }
        )
write_table(
    "manuscript_handoff.tsv",
    [
        "result_id", "dataset", "metric", "value", "unit", "source_table",
        "claim_boundary",
    ],
    handoff_rows,
)

limitation_rows = [
    {
        "limitation_id": "L1",
        "scope": "public data",
        "limitation": "The public datasets are reduced proof-of-principle inputs without orthogonal truth sets.",
        "release_effect": "No sensitivity, specificity, precision, recall, or limit-of-detection claim.",
    },
    {
        "limitation_id": "L2",
        "scope": "structural variation",
        "limitation": "Deletion output is not benchmarked against a truth set.",
        "release_effect": "No deletion-calling accuracy claim.",
    },
    {
        "limitation_id": "L3",
        "scope": "copy-number proxy",
        "limitation": "The mt:nuclear depth ratio is an experimental within-sample proxy.",
        "release_effect": "No absolute copies-per-cell claim.",
    },
    {
        "limitation_id": "L4",
        "scope": "reference scope",
        "limitation": "mt-only alignment cannot support categorical NUMT interpretation.",
        "release_effect": "Status remains not_evaluable for the reduced long-read example.",
    },
    {
        "limitation_id": "L5",
        "scope": "clinical use",
        "limitation": "The workflow has not undergone clinical analytical validation.",
        "release_effect": "Research workflow/resource claims only.",
    },
]
write_table(
    "limitations.tsv",
    ["limitation_id", "scope", "limitation", "release_effect"],
    limitation_rows,
)
PY

if [[ "$(git -C "${REPO_ROOT}" rev-parse HEAD)" != "${CANDIDATE_COMMIT}" ]] ||   [[ -n "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all)" ]]; then
  echo "Release repository changed while validating candidate ${CANDIDATE_COMMIT}." >&2
  exit 1
fi
validate_public_main_tip

if ! "${PYTHON_BIN}" "${REPO_ROOT}/scripts/build_validation_packet_v0.3.0.py"   "${VALIDATION_ROOT}" "${PACKET_ROOT}" "${AUDIT_ZIP}"   --repo-root "${REPO_ROOT}"   --commit "${CANDIDATE_COMMIT}"   --cache-root "${CACHE_ROOT}"   --version "v0.3.0"   --repository "${REPOSITORY}" > "${PACKET_BUILD_LOG}" 2>&1; then
  cat "${PACKET_BUILD_LOG}" >&2
  exit 1
fi
cat "${PACKET_BUILD_LOG}"

if [[ ! -s "${AUDIT_ZIP}" ]]; then
  echo "Audit ZIP was not created or is empty: ${AUDIT_ZIP}" >&2
  exit 1
fi
if [[ ! -x "${PACKET_ROOT}/verify_bundle.sh" ]]; then
  echo "Packet verifier was not created or is not executable: ${PACKET_ROOT}/verify_bundle.sh" >&2
  exit 1
fi

: > "${PACKET_VERIFY_LOG}"
echo "[packet-root-verifier] verify_bundle.sh" >> "${PACKET_VERIFY_LOG}"
if ! "${PACKET_ROOT}/verify_bundle.sh" >> "${PACKET_VERIFY_LOG}" 2>&1; then
  cat "${PACKET_VERIFY_LOG}" >&2
  exit 1
fi

ZIP_VERIFY_ROOT="${VALIDATION_ROOT}/work/audit_zip_verify"
"${PYTHON_BIN}" "${REPO_ROOT}/scripts/safe_extract_validation_zip.py"   "${AUDIT_ZIP}" "${ZIP_VERIFY_ROOT}"
echo "[fresh-extract-verifier] verify_bundle.sh" >> "${PACKET_VERIFY_LOG}"
if ! bash "${ZIP_VERIFY_ROOT}/verify_bundle.sh" >> "${PACKET_VERIFY_LOG}" 2>&1; then
  cat "${PACKET_VERIFY_LOG}" >&2
  exit 1
fi

"${PYTHON_BIN}" - \
  "${ZIP_VERIFY_ROOT}/run.json" "${ZIP_VERIFY_ROOT}/environment.txt" \
  "${PACKET_VERIFY_LOG}" "${CANDIDATE_COMMIT}" "${GITHUB_RUN_ID}" \
  "${PR_NUMBER}" "${PR_RUN_ID}" "${PUBLIC_RUN_ID}" <<'PY'
import json
import sys
from pathlib import Path

run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
environment_lines = Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()
log = Path(sys.argv[3]).read_text(encoding="utf-8")
commit = sys.argv[4]
run_id = int(sys.argv[5])
pr_number = int(sys.argv[6])
pr_run_id = int(sys.argv[7])
public_run_id = int(sys.argv[8])
if run.get("schema_version") != "2.0":
    raise SystemExit("Audit ZIP schema version mismatch")
if run.get("validation_profile") != "github_release_validation_v1":
    raise SystemExit("Audit ZIP validation profile mismatch")
if run.get("git_commit") != commit:
    raise SystemExit("Audit ZIP commit does not match the validated candidate")
if run.get("github_actions_run_id") != run_id:
    raise SystemExit("Audit ZIP GitHub Actions run does not match the release gate")
if run.get("final_push_github_actions_run_id") != run_id:
    raise SystemExit("Audit ZIP final push run does not match the release gate")
if run.get("pull_request_number") != pr_number:
    raise SystemExit("Audit ZIP pull-request number does not match the release gate")
if run.get("pull_request_github_actions_run_id") != pr_run_id:
    raise SystemExit("Audit ZIP pull-request run does not match the release gate")
if run.get("public_validation_github_actions_run_id") != public_run_id:
    raise SystemExit("Audit ZIP public-validation run does not match the release gate")
environment = {}
for line in environment_lines:
    key, separator, value = line.partition("=")
    if separator:
        environment[key] = value
expected_ids = {
    "github_actions_run_id": run_id,
    "final_push_github_actions_run_id": run_id,
    "pull_request_number": pr_number,
    "pull_request_github_actions_run_id": pr_run_id,
    "public_validation_github_actions_run_id": public_run_id,
}
for key, expected_id in expected_ids.items():
    if environment.get(key) != str(expected_id):
        raise SystemExit(f"Audit ZIP environment identity mismatch for {key}")
expected = (
    f"verified mito-overview v0.3.0 github_release_validation_v1 "
    f"packet at commit {commit}"
)
if log.count(expected) != 2:
    raise SystemExit("Both packet-root and fresh-extract verifier evidence are required")
PY
cat "${PACKET_VERIFY_LOG}"

AUDIT_ZIP_SHA256="$("${PYTHON_BIN}" - "${AUDIT_ZIP}" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"
printf '%s  %s\n' "${AUDIT_ZIP_SHA256}" "${EXPECTED_AUDIT_ZIP}" > "${PACKET_SHA256}"

if [[ "$(git -C "${REPO_ROOT}" rev-parse HEAD)" != "${CANDIDATE_COMMIT}" ]] ||   [[ -n "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all)" ]]; then
  echo "Release repository changed while packaging candidate ${CANDIDATE_COMMIT}." >&2
  exit 1
fi
validate_public_main_tip

"${PYTHON_BIN}" - \
  "${PACKET_RECEIPT}" "${CANDIDATE_COMMIT}" "${GITHUB_RUN_ID}" \
  "${PR_NUMBER}" "${PR_RUN_ID}" "${PUBLIC_RUN_ID}" \
  "${EXPECTED_AUDIT_ZIP}" "${AUDIT_ZIP_SHA256}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

receipt = {
    "schema_version": "2.0",
    "validation_profile": "github_release_validation_v1",
    "evidence_type": "release_validation_archive_verification",
    "verdict": "PASS",
    "release_version": "v0.3.0",
    "git_commit": sys.argv[2],
    "github_actions_run_id": int(sys.argv[3]),
    "final_push_github_actions_run_id": int(sys.argv[3]),
    "pull_request_number": int(sys.argv[4]),
    "pull_request_github_actions_run_id": int(sys.argv[5]),
    "public_validation_github_actions_run_id": int(sys.argv[6]),
    "audit_zip": sys.argv[7],
    "audit_zip_sha256": sys.argv[8],
    "verifier_runs": ["packet_root", "fresh_audit_zip_extraction"],
    "generated_utc": datetime.now(timezone.utc).isoformat(),
}
Path(sys.argv[1]).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
PY

echo "[release-validation] PASS"
echo "[release-validation] candidate commit: ${CANDIDATE_COMMIT}"
echo "[release-validation] audit ZIP: ${AUDIT_ZIP}"
echo "[release-validation] SHA-256: ${AUDIT_ZIP_SHA256}"
echo "[release-validation] verification receipt: ${PACKET_RECEIPT}"
