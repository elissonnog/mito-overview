#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run_public_validation_matrix_v0.3.0.sh \
  --mode offline --cache SEALED_RAW_CACHE --work WORK_ROOT \
  --output OUTPUT_ROOT --oracle ORACLE_TSV

Only sealed-cache execution is accepted. Prepare the seven-FASTQ raw cache
first with scripts/prepare_public_validation_cache_v0.3.0.sh. The "offline"
mode guards known project network entrypoints; it is not an operating-system
network sandbox.
EOF
}

MODE=""
CACHE_ROOT=""
WORK_ROOT=""
OUTPUT_ROOT=""
ORACLE_TSV=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode|--cache|--work|--output|--oracle)
      [[ $# -ge 2 ]] || { echo "$1 requires a value" >&2; exit 2; }
      case "$1" in
        --mode) MODE="$2" ;;
        --cache) CACHE_ROOT="$2" ;;
        --work) WORK_ROOT="$2" ;;
        --output) OUTPUT_ROOT="$2" ;;
        --oracle) ORACLE_TSV="$2" ;;
      esac
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown or legacy argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "${MODE}" == offline ]] || {
  echo "Public validation matrix requires --mode offline" >&2
  usage >&2
  exit 2
}
for value in CACHE_ROOT WORK_ROOT OUTPUT_ROOT ORACLE_TSV; do
  [[ -n "${!value}" ]] || { echo "Missing required argument: ${value}" >&2; exit 2; }
done
[[ -d "${CACHE_ROOT}" ]] || { echo "Sealed raw cache not found: ${CACHE_ROOT}" >&2; exit 1; }
[[ -f "${ORACLE_TSV}" ]] || { echo "Oracle TSV not found: ${ORACLE_TSV}" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_REQUEST="${MITO_OVERVIEW_PYTHON:-python3}"
PYTHON_BIN="$(command -v "${PYTHON_REQUEST}")"
BASE_PATH="${PATH}"

case "$(uname -s)/$(uname -m)" in
  Linux/x86_64) DETECTED_PLATFORM="linux-64" ;;
  Darwin/x86_64) DETECTED_PLATFORM="osx-64" ;;
  Darwin/arm64) DETECTED_PLATFORM="osx-arm64" ;;
  *)
    echo "Unsupported validation platform: $(uname -s)/$(uname -m)" >&2
    exit 1
    ;;
esac
EXPECTED_PLATFORM="${MITO_OVERVIEW_EXPECTED_PLATFORM:-${DETECTED_PLATFORM}}"
if [[ "${EXPECTED_PLATFORM}" != "${DETECTED_PLATFORM}" ]]; then
  echo "Validation platform mismatch: expected ${EXPECTED_PLATFORM}, detected ${DETECTED_PLATFORM}" >&2
  exit 1
fi

# Hidden MITO_OVERVIEW_* settings make a public replay non-auditable. The
# interpreter is the only allowed launcher override; every scientific setting
# below is explicit and recorded in each replay command.
while IFS='=' read -r name _; do
  case "${name}" in
    MITO_OVERVIEW_PYTHON|MITO_OVERVIEW_REQUIRE_INSTALLED|MITO_OVERVIEW_EXPECTED_PLATFORM) ;;
    MITO_OVERVIEW_*)
      echo "Unexpected ambient validation setting: ${name}" >&2
      exit 1
      ;;
  esac
done < <(env)

assert_absent_or_empty() {
  local path="$1"
  local label="$2"
  if [[ -d "${path}" && -n "$(find "${path}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "${label} must be absent or empty: ${path}" >&2
    exit 1
  fi
  if [[ -e "${path}" && ! -d "${path}" ]]; then
    echo "${label} must be a directory path: ${path}" >&2
    exit 1
  fi
}

assert_absent_or_empty "${WORK_ROOT}" "Validation work root"
assert_absent_or_empty "${OUTPUT_ROOT}" "Validation output root"
mkdir -p "${WORK_ROOT}" "${OUTPUT_ROOT}"
WORK_ROOT="$(cd "${WORK_ROOT}" && pwd)"
OUTPUT_ROOT="$(cd "${OUTPUT_ROOT}" && pwd)"
CACHE_ROOT="$(cd "${CACHE_ROOT}" && pwd)"
ORACLE_TSV="$(cd "$(dirname "${ORACLE_TSV}")" && pwd)/$(basename "${ORACLE_TSV}")"

ISOLATED_HOME="${WORK_ROOT}/home"
ISOLATED_TMP="${WORK_ROOT}/tmp"
ISOLATED_CACHE="${WORK_ROOT}/xdg-cache"
MPL_CONFIG="${WORK_ROOT}/matplotlib"
CANARY_BIN="${WORK_ROOT}/network-canary/bin"
CANARY_LOG="${WORK_ROOT}/network-canary/project-entrypoint-attempts.log"
DERIVED_ROOT="${WORK_ROOT}/derivatives"
mkdir -p \
  "${ISOLATED_HOME}" "${ISOLATED_TMP}" "${ISOLATED_CACHE}" "${MPL_CONFIG}" "${CANARY_BIN}" \
  "${DERIVED_ROOT}/GM11906" "${DERIVED_ROOT}/GM12878" \
  "${OUTPUT_ROOT}/commands" "${OUTPUT_ROOT}/logs" "${OUTPUT_ROOT}/outputs" \
  "${OUTPUT_ROOT}/observed_normalized" "${OUTPUT_ROOT}/environment"

for guarded_command in curl wget; do
cat > "${CANARY_BIN}/${guarded_command}" <<'EOF'
#!/usr/bin/env bash
printf 'blocked project network entrypoint %s:' "$(basename "$0")" >> "${MITO_OVERVIEW_NETWORK_CANARY_LOG:?}"
printf ' %q' "$@" >> "${MITO_OVERVIEW_NETWORK_CANARY_LOG}"
printf '\n' >> "${MITO_OVERVIEW_NETWORK_CANARY_LOG}"
exit 97
EOF
chmod +x "${CANARY_BIN}/${guarded_command}"
done
CLEAN_PATH="${CANARY_BIN}:$(dirname "${PYTHON_BIN}"):${BASE_PATH}"

common_environment=(
  "PATH=${CLEAN_PATH}"
  "HOME=${ISOLATED_HOME}"
  "TMPDIR=${ISOLATED_TMP}"
  "XDG_CACHE_HOME=${ISOLATED_CACHE}"
  "MPLCONFIGDIR=${MPL_CONFIG}"
  "PYTHONNOUSERSITE=1"
  "PYTHONPATH="
  "PIP_DISABLE_PIP_VERSION_CHECK=1"
  "LC_ALL=C"
  "LANG=C"
  "TZ=UTC"
  "MPLBACKEND=Agg"
  "MITO_OVERVIEW_PYTHON=${PYTHON_BIN}"
  "MITO_OVERVIEW_REQUIRE_INSTALLED=1"
  "MITO_OVERVIEW_EXPECTED_PLATFORM=${EXPECTED_PLATFORM}"
  "MITO_OVERVIEW_PUBLIC_INPUT_MODE=offline"
  "MITO_OVERVIEW_PUBLIC_OUTPUT_MODE=evidence"
  "MITO_OVERVIEW_NETWORK_CANARY_LOG=${CANARY_LOG}"
  "HTTP_PROXY=http://127.0.0.1:9"
  "HTTPS_PROXY=http://127.0.0.1:9"
  "ALL_PROXY=http://127.0.0.1:9"
  "NO_PROXY="
)

env -i "${common_environment[@]}" "${PYTHON_BIN}" -I - \
  "${REPO_ROOT}" "${OUTPUT_ROOT}/environment/runtime_versions.json" \
  "${EXPECTED_PLATFORM}" <<'PY'
import json
import platform
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2])
expected_platform = sys.argv[3]

if tuple(sys.version_info[:3]) != (3, 12, 13):
    raise SystemExit(f"Python version mismatch: {platform.python_version()} != 3.12.13")

expected_packages = {
    "mito-overview": "0.3.0",
    "pysam": "0.24.0",
    "pandas": "3.0.3",
    "numpy": "2.5.1",
    "matplotlib": "3.11.0",
    "requests": "2.34.2",
    "pytest": "9.1.1",
    "build": "1.5.0",
    "setuptools": "82.0.1",
    "wheel": "0.47.0",
    "python-docx": "1.2.0",
}
observed_packages = {name: version(name) for name in expected_packages}
for name, expected in expected_packages.items():
    if observed_packages[name] != expected:
        raise SystemExit(
            f"{name} version mismatch: {observed_packages[name]} != {expected}"
        )

import mito_overview

module_path = Path(mito_overview.__file__).resolve()
if module_path == repo_root or repo_root in module_path.parents:
    raise SystemExit(f"Checkout code shadowed the installed package: {module_path}")

samtools_lines = subprocess.run(
    ["samtools", "--version"], check=True, text=True, capture_output=True
).stdout.splitlines()
if not samtools_lines or samtools_lines[0] != "samtools 1.23.1":
    raise SystemExit(f"samtools version mismatch: {samtools_lines[:1]}")
if len(samtools_lines) < 2 or samtools_lines[1] != "Using htslib 1.23.1":
    raise SystemExit(f"htslib version mismatch: {samtools_lines[:2]}")
minimap2 = subprocess.run(
    ["minimap2", "--version"], check=True, text=True, capture_output=True
).stdout.strip()
if minimap2 != "2.31-r1302":
    raise SystemExit(f"minimap2 version mismatch: {minimap2}")
bwa_stderr = subprocess.run(
    ["bwa"], check=False, text=True, capture_output=True
).stderr
if "Version: 0.7.19-r1273" not in bwa_stderr:
    raise SystemExit("bwa version mismatch; expected 0.7.19-r1273")

platform_map = {
    ("Linux", "x86_64"): "linux-64",
    ("Darwin", "x86_64"): "osx-64",
    ("Darwin", "arm64"): "osx-arm64",
}
observed_platform = platform_map.get((platform.system(), platform.machine()))
if observed_platform != expected_platform:
    raise SystemExit(
        f"Platform identity mismatch: {observed_platform} != {expected_platform}"
    )

record = {
    "schema_version": "1.0",
    "platform_id": observed_platform,
    "system": platform.system(),
    "machine": platform.machine(),
    "python": platform.python_version(),
    "python_executable": sys.executable,
    "mito_overview_module": str(module_path),
    "packages": observed_packages,
    "samtools": samtools_lines[0],
    "htslib": samtools_lines[1],
    "minimap2": minimap2,
    "bwa": "0.7.19-r1273",
    "threads": 4,
    "installed_distribution_required": True,
}
output.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

env -i "${common_environment[@]}" "${PYTHON_BIN}" -m pip freeze --all \
  > "${OUTPUT_ROOT}/environment/pip-freeze.txt"
if command -v conda >/dev/null 2>&1; then
  env -i "${common_environment[@]}" conda list --explicit \
    > "${OUTPUT_ROOT}/environment/conda-explicit.txt"
else
  printf 'conda unavailable; exact runtime versions are recorded in runtime_versions.json\n' \
    > "${OUTPUT_ROOT}/environment/conda-explicit.txt"
fi
cat > "${OUTPUT_ROOT}/environment/network_entrypoint_contract.tsv" <<'EOF'
entrypoint	control	scope
curl	PATH canary	release public-data runners
wget	PATH canary	defensive command guard
mvTool requests	MVTOOL_MODE=disabled	pipeline external annotation module
socket/network namespace	not controlled	not an operating-system network sandbox
EOF

env -i "${common_environment[@]}" \
  "${SCRIPT_DIR}/prepare_public_validation_cache_v0.3.0.sh" \
  --verify --cache "${CACHE_ROOT}" \
  > "${OUTPUT_ROOT}/logs/cache_preflight.log" 2>&1

CASES_TSV="${OUTPUT_ROOT}/cases.tsv"
printf 'case_id\tcategory\tinput_available\texpected_available\tverdict\tdetail\n' > "${CASES_TSV}"

record_case() {
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$1" "$2" "$3" "$4" "$5" "$6" >> "${CASES_TSV}"
}

write_replay_command() {
  local destination="$1"
  shift
  {
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'env -i'
    printf ' %q' "$@"
    printf '\n'
  } > "${destination}"
  chmod +x "${destination}"
}

run_short_case() {
  local case_id="$1" profile="$2" baseq="$3" mapq="$4" readq="$5" require_8344="$6"
  local case_work="${WORK_ROOT}/cases/${case_id}"
  local output_dir="${OUTPUT_ROOT}/outputs/${case_id}"
  local log="${OUTPUT_ROOT}/logs/${case_id}.log"
  local command_file="${OUTPUT_ROOT}/commands/${case_id}.sh"
  local alignment="${DERIVED_ROOT}/GM11906/GM11906_MERRF_shortread.mt.bam"
  mkdir -p "${case_work}"
  local -a case_environment=(
    "${common_environment[@]}"
    "MITO_OVERVIEW_SHORTREAD_WORKDIR=${case_work}"
    "MITO_OVERVIEW_SHORTREAD_RAW_DATA_DIR=${CACHE_ROOT}"
    "MITO_OVERVIEW_SHORTREAD_DERIVED_DIR=${DERIVED_ROOT}/GM11906"
    "MITO_OVERVIEW_SHORTREAD_ALIGN_BAM=${alignment}"
    "MITO_OVERVIEW_SHORTREAD_THREADS=4"
    "MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_BASE_QUALITY=${baseq}"
    "MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_MAPPING_QUALITY=${mapq}"
    "MITO_OVERVIEW_SHORTREAD_ALLELE_MIN_READ_MEAN_QUALITY=${readq}"
    "MITO_OVERVIEW_SHORTREAD_REQUIRE_8344=${require_8344}"
    "MITO_OVERVIEW_SHORTREAD_MVTOOL_MODE=disabled"
  )
  write_replay_command "${command_file}" \
    "${case_environment[@]}" \
    "${REPO_ROOT}/scripts/run_public_shortread_validation_gm11906.sh" "${output_dir}"
  echo "[validation-matrix] running ${case_id} (${profile})"
  if ! env -i "${case_environment[@]}" \
    "${REPO_ROOT}/scripts/run_public_shortread_validation_gm11906.sh" "${output_dir}" \
    > "${log}" 2>&1; then
    record_case "${case_id}" "public_${profile}" 1 1 FAIL "runner failed; see logs/${case_id}.log"
    tail -80 "${log}" >&2
    return 1
  fi
}

run_long_case() {
  local case_id="$1" profile="$2" baseq="$3" mapq="$4" readq="$5"
  local case_work="${WORK_ROOT}/cases/${case_id}"
  local output_dir="${OUTPUT_ROOT}/outputs/${case_id}"
  local log="${OUTPUT_ROOT}/logs/${case_id}.log"
  local command_file="${OUTPUT_ROOT}/commands/${case_id}.sh"
  local derived="${DERIVED_ROOT}/GM12878"
  local subset="${derived}/SRR18110025.deterministic-qnames-1000.fastq.gz"
  local alignment="${derived}/GM12878_ONT_longread.deterministic-qnames-1000.mt.bam"
  mkdir -p "${case_work}"
  local -a case_environment=(
    "${common_environment[@]}"
    "MITO_OVERVIEW_LONGREAD_WORKDIR=${case_work}"
    "MITO_OVERVIEW_LONGREAD_RAW_DATA_DIR=${CACHE_ROOT}"
    "MITO_OVERVIEW_LONGREAD_DERIVED_DIR=${derived}"
    "MITO_OVERVIEW_LONGREAD_FASTQ_GZ=${CACHE_ROOT}/SRR18110025.fastq.gz"
    "MITO_OVERVIEW_LONGREAD_SUBSET_FASTQ=${subset}"
    "MITO_OVERVIEW_LONGREAD_SUBSET_FASTQ_PROVENANCE=${subset}.provenance.json"
    "MITO_OVERVIEW_LONGREAD_SUBSET_NAMES=${subset}.selected_qnames.txt"
    "MITO_OVERVIEW_LONGREAD_ALIGN_BAM=${alignment}"
    "MITO_OVERVIEW_LONGREAD_SUBSET_READ_NAMES=1000"
    "MITO_OVERVIEW_LONGREAD_SUBSET_SEED=mito-overview-v0.3.0-GM12878-SRR18110025"
    "MITO_OVERVIEW_LONGREAD_THREADS=4"
    "MITO_OVERVIEW_LONGREAD_ALLELE_MIN_BASE_QUALITY=${baseq}"
    "MITO_OVERVIEW_LONGREAD_ALLELE_MIN_MAPPING_QUALITY=${mapq}"
    "MITO_OVERVIEW_LONGREAD_ALLELE_MIN_READ_MEAN_QUALITY=${readq}"
    "MITO_OVERVIEW_LONGREAD_MVTOOL_MODE=disabled"
  )
  write_replay_command "${command_file}" \
    "${case_environment[@]}" \
    "${REPO_ROOT}/scripts/run_public_longread_validation_gm12878.sh" "${output_dir}"
  echo "[validation-matrix] running ${case_id} (${profile})"
  if ! env -i "${case_environment[@]}" \
    "${REPO_ROOT}/scripts/run_public_longread_validation_gm12878.sh" "${output_dir}" \
    > "${log}" 2>&1; then
    record_case "${case_id}" "public_${profile}" 1 1 FAIL "runner failed; see logs/${case_id}.log"
    tail -80 "${log}" >&2
    return 1
  fi
}

run_short_case gm11906_default_run1 default 13 20 10 1
run_short_case gm11906_default_run2 default 13 20 10 1
run_short_case gm11906_lenient lenient 0 0 0 0
run_short_case gm11906_strict strict 20 30 15 0
run_long_case gm12878_default_run1 default 13 20 10
run_long_case gm12878_default_run2 default 13 20 10
run_long_case gm12878_lenient lenient 0 0 0
run_long_case gm12878_strict strict 20 30 15

repeatability_details=()
visual_details=()
for dataset in gm11906 gm12878; do
  for repeat in run1 run2; do
    env -i "${common_environment[@]}" \
      "${PYTHON_BIN}" "${REPO_ROOT}/scripts/normalize_validation_outputs.py" \
      "${OUTPUT_ROOT}/outputs/${dataset}_default_${repeat}/summary" \
      "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_${repeat}"
  done
  if ! diff -ru \
    "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_run1" \
    "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_run2" \
    > "${OUTPUT_ROOT}/logs/${dataset}_repeatability.diff"; then
    record_case "${dataset}_repeatability" repeatability 1 1 FAIL "normalized TSVs differed"
    cat "${OUTPUT_ROOT}/logs/${dataset}_repeatability.diff" >&2
    exit 1
  fi
  repeatability_details+=("${dataset}:normalized TSVs matched")

  for repeat in run1 run2; do
    env -i "${common_environment[@]}" \
      "${PYTHON_BIN}" "${REPO_ROOT}/scripts/inventory_visual_artifacts.py" \
      "${OUTPUT_ROOT}/outputs/${dataset}_default_${repeat}" \
      "${OUTPUT_ROOT}/observed_normalized/${dataset}_default_${repeat}/visual_artifact_inventory.tsv" \
      "${OUTPUT_ROOT}/logs/${dataset}_visual_structure_${repeat}.tsv"
  done
  if ! diff -u \
    "${OUTPUT_ROOT}/logs/${dataset}_visual_structure_run1.tsv" \
    "${OUTPUT_ROOT}/logs/${dataset}_visual_structure_run2.tsv" \
    > "${OUTPUT_ROOT}/logs/${dataset}_visual_structure.diff"; then
    record_case "${dataset}_visual_integrity" visual_integrity 1 1 FAIL "visual structures differed"
    cat "${OUTPUT_ROOT}/logs/${dataset}_visual_structure.diff" >&2
    exit 1
  fi

  env -i "${common_environment[@]}" "${PYTHON_BIN}" - \
    "${OUTPUT_ROOT}/outputs/${dataset}_default_run1/figures" \
    "${OUTPUT_ROOT}/outputs/${dataset}_default_run2/figures" \
    "${OUTPUT_ROOT}/logs/${dataset}_decoded_pixel_hashes.tsv" <<'PY'
import hashlib
import sys
from pathlib import Path

from PIL import Image

left, right, report = map(Path, sys.argv[1:])
left_names = sorted(path.name for path in left.glob("*.png"))
right_names = sorted(path.name for path in right.glob("*.png"))
if left_names != right_names:
    raise SystemExit("PNG path inventories differ across default repeats")
rows = []
for name in left_names:
    values = []
    for root in (left, right):
        with Image.open(root / name) as image:
            image.load()
            payload = image.convert("RGBA").tobytes()
            values.append((image.size, hashlib.sha256(payload).hexdigest()))
    if values[0] != values[1]:
        raise SystemExit(f"decoded PNG pixels differ across repeats: {name}")
    rows.append((name, values[0][0][0], values[0][0][1], values[0][1]))
report.write_text(
    "path\twidth_px\theight_px\tdecoded_rgba_sha256\n"
    + "".join(f"{name}\t{width}\t{height}\t{digest}\n" for name, width, height, digest in rows),
    encoding="utf-8",
)
PY
  visual_details+=("${dataset}:HTML structures and decoded PNG pixels matched")
done

env -i "${common_environment[@]}" \
  "${PYTHON_BIN}" "${REPO_ROOT}/scripts/summarize_filter_profiles.py" \
  --output "${OUTPUT_ROOT}/filter_profile_results.tsv" \
  "gm11906_default=GM11906:default:${OUTPUT_ROOT}/outputs/gm11906_default_run1" \
  "gm11906_lenient=GM11906:lenient:${OUTPUT_ROOT}/outputs/gm11906_lenient" \
  "gm11906_strict=GM11906:strict:${OUTPUT_ROOT}/outputs/gm11906_strict" \
  "gm12878_default=GM12878:default:${OUTPUT_ROOT}/outputs/gm12878_default_run1" \
  "gm12878_lenient=GM12878:lenient:${OUTPUT_ROOT}/outputs/gm12878_lenient" \
  "gm12878_strict=GM12878:strict:${OUTPUT_ROOT}/outputs/gm12878_strict"

# The cache must remain byte-identical and raw-only after all runners finish.
env -i "${common_environment[@]}" \
  "${SCRIPT_DIR}/prepare_public_validation_cache_v0.3.0.sh" \
  --verify --cache "${CACHE_ROOT}" \
  > "${OUTPUT_ROOT}/logs/cache_postflight.log" 2>&1
if [[ -s "${CANARY_LOG}" ]]; then
  record_case project_network_entrypoints cache_only_execution 1 1 FAIL "a guarded project network entrypoint was invoked"
  cat "${CANARY_LOG}" >&2
  exit 1
fi

awk -F '\t' 'NR > 1 {print $14 "  " $11}' \
  "${CACHE_ROOT}/raw_inputs.tsv" > "${OUTPUT_ROOT}/inputs.sha256"
cp "${CACHE_ROOT}/raw_inputs.tsv" "${OUTPUT_ROOT}/raw_inputs.tsv"
cp "${CACHE_ROOT}/CACHE_SEAL.sha256" "${OUTPUT_ROOT}/CACHE_SEAL.sha256"

if ! env -i "${common_environment[@]}" \
  "${PYTHON_BIN}" "${REPO_ROOT}/scripts/assert_public_validation_oracle_v0.3.0.py" \
  --matrix-root "${OUTPUT_ROOT}" \
  --oracle "${ORACLE_TSV}" \
  --report "${OUTPUT_ROOT}/oracle_assertions.tsv" \
  > "${OUTPUT_ROOT}/logs/public_oracle.log" 2>&1; then
  record_case public_oracle exact_oracle 1 1 FAIL "see oracle_assertions.tsv and logs/public_oracle.log"
  cat "${OUTPUT_ROOT}/logs/public_oracle.log" >&2
  exit 1
fi

# PASS verdicts are deliberately emitted only after the frozen oracle passes.
for specification in \
  'gm11906_default_run1 public_default' \
  'gm11906_default_run2 public_default' \
  'gm11906_lenient public_lenient' \
  'gm11906_strict public_strict' \
  'gm12878_default_run1 public_default' \
  'gm12878_default_run2 public_default' \
  'gm12878_lenient public_lenient' \
  'gm12878_strict public_strict'; do
  read -r case_id category <<< "${specification}"
  record_case "${case_id}" "${category}" 1 1 PASS "runner and exact v0.3.0 oracle passed"
done
record_case gm11906_repeatability repeatability 1 1 PASS "${repeatability_details[0]}"
record_case gm12878_repeatability repeatability 1 1 PASS "${repeatability_details[1]}"
record_case gm11906_visual_integrity visual_integrity 1 1 PASS "${visual_details[0]}"
record_case gm12878_visual_integrity visual_integrity 1 1 PASS "${visual_details[1]}"
record_case filter_profiles filter_dependence 1 1 PASS "all six frozen filter-profile oracles passed"
record_case public_oracle exact_oracle 1 1 PASS "all expected values, inventories, and statuses matched"
record_case raw_cache_seal input_integrity 1 1 PASS "seven-FASTQ sealed cache passed preflight and postflight"
record_case project_network_entrypoints cache_only_execution 1 1 PASS \
  "curl/wget canaries were not invoked and mvTool was disabled; this is not an OS network sandbox"

echo "[validation-matrix] PASS output=${OUTPUT_ROOT} work=${WORK_ROOT}"
