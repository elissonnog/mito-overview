#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<EOF
Usage: MITO_OVERVIEW_GITHUB_RUN_ID=RUN_ID \
  $0 VALIDATION_ROOT RAW_CACHE_ROOT PACKET_ROOT \
  mito-overview-v0.3.0-validation.zip

This is the GitHub-only v0.3.0 release-validation interface. Manuscript,
Zenodo, DOI, archive, and fixed release-date inputs are not accepted.
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
FRESH_CLONE_CASE_ID="fresh_clone_candidate_commit"
EXPECTED_AUDIT_ZIP="mito-overview-v0.3.0-validation.zip"
SCHEMA_VERSION="2.0"
VALIDATION_PROFILE="github_release_validation_v1"

if [[ ! "${GITHUB_RUN_ID}" =~ ^[1-9][0-9]*$ ]]; then
  echo "MITO_OVERVIEW_GITHUB_RUN_ID must identify a completed GitHub Actions run." >&2
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
CACHE_ROOT="$(resolve_path "Raw cache root" "$2")"
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
if [[ -e "${CACHE_ROOT}" && ! -d "${CACHE_ROOT}" ]]; then
  echo "Raw cache root exists and is not a directory: ${CACHE_ROOT}" >&2
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

mkdir -p   "${VALIDATION_ROOT}/acceptance"   "${VALIDATION_ROOT}/commands"   "${VALIDATION_ROOT}/logs"   "${VALIDATION_ROOT}/resources"   "${VALIDATION_ROOT}/expected"   "${VALIDATION_ROOT}/work"   "${VALIDATION_ROOT}/dist"   "${CACHE_ROOT}"
mkdir -p "$(dirname "${AUDIT_ZIP}")"

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
  {
    printf 'gh api %q > %q\n'       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"       "acceptance/github_actions_run.json"
    printf 'gh api %q > %q\n'       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100"       "acceptance/github_actions_jobs.json"
  } > "${command_file}"
  if {
    echo "candidate_commit=${CANDIDATE_COMMIT}"
    echo "github_actions_run_id=${GITHUB_RUN_ID}"
    gh api "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}" > "${run_tmp}"
    gh api       "repos/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}/jobs?filter=latest&per_page=100"       > "${jobs_tmp}"
    mv "${run_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_run.json"
    mv "${jobs_tmp}" "${VALIDATION_ROOT}/acceptance/github_actions_jobs.json"
    echo "github_actions_metadata_ingestion=PASS"
  } > "${log_file}" 2>&1; then
    return 0
  fi
  tail -100 "${log_file}" >&2
  return 1
}

run_fresh_clone_validation() {
  local clone_root="${VALIDATION_ROOT}/work/fresh_clone"
  local env_root="${VALIDATION_ROOT}/work/fresh_environment"
  local home_root="${env_root}/home"
  local tmp_root="${env_root}/tmp"
  local cache_root="${env_root}/cache"
  local venv_root="${env_root}/venv"
  local probe_root="${VALIDATION_ROOT}/work/installed_probe"
  local command_file="${VALIDATION_ROOT}/commands/${FRESH_CLONE_CASE_ID}.sh"
  local log_file="${VALIDATION_ROOT}/logs/${FRESH_CLONE_CASE_ID}.log"

  mkdir -p "${home_root}" "${tmp_root}" "${cache_root}" "${probe_root}"
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
    PYTHONNOUSERSITE=1 PYTHONPATH= LC_ALL=C TZ=UTC THREADS=4 \
    "\$@"
}
run_clean git clone --no-checkout $(printf '%q' "${PUBLIC_REMOTE}") $(printf '%q' "${clone_root}")
run_clean git -C $(printf '%q' "${clone_root}") cat-file -e $(printf '%q' "${CANDIDATE_COMMIT}^{commit}")
run_clean git -C $(printf '%q' "${clone_root}") checkout --detach $(printf '%q' "${CANDIDATE_COMMIT}")
test "\$(run_clean git -C $(printf '%q' "${clone_root}") rev-parse HEAD)" = $(printf '%q' "${CANDIDATE_COMMIT}")
test "\$(run_clean git -C $(printf '%q' "${clone_root}") remote get-url origin)" = $(printf '%q' "${PUBLIC_REMOTE}")
run_clean git -C $(printf '%q' "${clone_root}") fsck --full
test -z "\$(run_clean git -C $(printf '%q' "${clone_root}") status --porcelain --untracked-files=all)"
run_clean $(printf '%q' "${PYTHON_BIN}") -m venv $(printf '%q' "${venv_root}")
FRESH_PYTHON=$(printf '%q' "${venv_root}/bin/python")
run_clean "\${FRESH_PYTHON}" -m pip install --disable-pip-version-check \
  build==1.5.0 setuptools==82.0.1 wheel==0.47.0 \
  pytest==9.1.1 python-docx==1.2.0
run_clean "\${FRESH_PYTHON}" -m build --no-isolation \
  --outdir $(printf '%q' "${VALIDATION_ROOT}/dist") $(printf '%q' "${clone_root}")
WHEEL="\$(find $(printf '%q' "${VALIDATION_ROOT}/dist") -maxdepth 1 -type f -name '*.whl' -print -quit)"
SDIST="\$(find $(printf '%q' "${VALIDATION_ROOT}/dist") -maxdepth 1 -type f -name '*.tar.gz' -print -quit)"
test -n "\${WHEEL}" && test -n "\${SDIST}"
run_clean "\${FRESH_PYTHON}" -m pip install --disable-pip-version-check "\${WHEEL}"
cd $(printf '%q' "${probe_root}")
run_clean "\${FRESH_PYTHON}" -I -c \
  'from pathlib import Path; import mito_overview; p=Path(mito_overview.__file__).resolve(); assert "site-packages" in p.parts; print(p)'
run_clean "\${FRESH_PYTHON}" -I -m mito_overview.cli --list-steps
cd $(printf '%q' "${clone_root}")
run_clean "\${FRESH_PYTHON}" -m pytest -q
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" ./tests/smoke_public_pipeline.sh
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" ./tests/smoke_public_pipeline_shortread.sh
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" ./tests/smoke_public_pipeline_longread_nomethyl.sh
run_clean env MITO_OVERVIEW_PYTHON="\${FRESH_PYTHON}" ./tests/smoke_standalone_minimal.sh
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
    validation_root, sys.argv[3], sys.argv[4]
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
run_fresh_clone_validation
append_acceptance_cases >> "${CASES_TSV}"

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

PREPARE_SCRIPT="${REPO_ROOT}/scripts/prepare_public_validation_cache_v0.3.0.sh"
PUBLIC_MATRIX="${REPO_ROOT}/scripts/run_public_validation_matrix_v0.3.0.sh"
ORACLE="${REPO_ROOT}/examples/public_validation/public_validation_oracle_v0.3.0.tsv"
for required in "${PREPARE_SCRIPT}" "${PUBLIC_MATRIX}" "${ORACLE}"; do
  if [[ ! -e "${required}" ]]; then
    echo "Required clean-room validation component is missing: ${required}" >&2
    exit 1
  fi
done
run_logged public_cache_prepare public_input   "${PREPARE_SCRIPT}" --cache "${CACHE_ROOT}"

PUBLIC_ROOT="${VALIDATION_ROOT}/public"
mkdir -p "${VALIDATION_ROOT}/work/public_home" \
  "${VALIDATION_ROOT}/work/public_tmp" \
  "${VALIDATION_ROOT}/work/public_xdg_cache"
run_logged public_validation_matrix public   env -i     HOME="${VALIDATION_ROOT}/work/public_home"     TMPDIR="${VALIDATION_ROOT}/work/public_tmp"     XDG_CACHE_HOME="${VALIDATION_ROOT}/work/public_xdg_cache"     PATH="${PATH}" PYTHONNOUSERSITE=1 PYTHONPATH= LC_ALL=C TZ=UTC THREADS=4     MITO_OVERVIEW_PYTHON="${PYTHON_BIN}"     "${PUBLIC_MATRIX}"     --mode offline     --cache "${CACHE_ROOT}"     --work "${VALIDATION_ROOT}/work/public_matrix"     --output "${PUBLIC_ROOT}"     --oracle "${ORACLE}"
tail -n +2 "${PUBLIC_ROOT}/cases.tsv" >> "${CASES_TSV}"

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

checked = datetime.now(timezone.utc).isoformat()
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
            "metadata_checked_utc": checked,
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
        "metadata_checked_utc", "role", "redistribution",
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

"${PYTHON_BIN}" -   "${ZIP_VERIFY_ROOT}/run.json" "${PACKET_VERIFY_LOG}"   "${CANDIDATE_COMMIT}" "${GITHUB_RUN_ID}" <<'PY'
import json
import sys
from pathlib import Path

run = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
log = Path(sys.argv[2]).read_text(encoding="utf-8")
commit = sys.argv[3]
run_id = int(sys.argv[4])
if run.get("schema_version") != "2.0":
    raise SystemExit("Audit ZIP schema version mismatch")
if run.get("validation_profile") != "github_release_validation_v1":
    raise SystemExit("Audit ZIP validation profile mismatch")
if run.get("git_commit") != commit:
    raise SystemExit("Audit ZIP commit does not match the validated candidate")
if run.get("github_actions_run_id") != run_id:
    raise SystemExit("Audit ZIP GitHub Actions run does not match the release gate")
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

"${PYTHON_BIN}" -   "${PACKET_RECEIPT}" "${CANDIDATE_COMMIT}" "${GITHUB_RUN_ID}"   "${EXPECTED_AUDIT_ZIP}" "${AUDIT_ZIP_SHA256}" <<'PY'
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
    "audit_zip": sys.argv[4],
    "audit_zip_sha256": sys.argv[5],
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
