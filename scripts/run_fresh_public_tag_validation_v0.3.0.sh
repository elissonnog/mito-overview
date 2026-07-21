#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 GITHUB_HTTPS_URL FINAL_SHA WORK_ROOT EVIDENCE_ROOT" >&2
  exit 2
fi

REPOSITORY_URL="${1%/}"
FINAL_SHA="$2"
WORK_ROOT="$3"
EVIDENCE_ROOT="$4"
TAG="v0.3.0"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
THREADS=4

if [[ ! "${REPOSITORY_URL}" =~ ^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "Repository must be a public GitHub HTTPS URL without credentials or .git" >&2
  exit 2
fi
if [[ ! "${FINAL_SHA}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "FINAL_SHA must be exactly 40 lowercase hexadecimal characters" >&2
  exit 2
fi
if [[ -e "${WORK_ROOT}" || -e "${EVIDENCE_ROOT}" ]]; then
  echo "WORK_ROOT and EVIDENCE_ROOT must not already exist" >&2
  exit 2
fi

CLONE_ROOT="${WORK_ROOT}/public-tag-clone"
DIST_ROOT="${WORK_ROOT}/dist"
SDIST_ROOT="${WORK_ROOT}/sdist"
VENV_ROOT="${WORK_ROOT}/venv"
PROBE_ROOT="${WORK_ROOT}/installed-probe"
EXAMPLE_ROOT="${WORK_ROOT}/examples"
HOME_ROOT="${WORK_ROOT}/home"
TMP_ROOT="${WORK_ROOT}/tmp"
CACHE_ROOT="${WORK_ROOT}/cache"
COMMAND_ROOT="${EVIDENCE_ROOT}/commands"
LOG_ROOT="${EVIDENCE_ROOT}/logs"
CASES_PATH="${EVIDENCE_ROOT}/cases.tsv"

mkdir -p "${WORK_ROOT}" "${EVIDENCE_ROOT}" "${COMMAND_ROOT}" "${LOG_ROOT}" \
  "${DIST_ROOT}" "${SDIST_ROOT}" "${PROBE_ROOT}" "${EXAMPLE_ROOT}" \
  "${HOME_ROOT}" "${TMP_ROOT}" "${CACHE_ROOT}"
printf 'case_id\tverdict\tdetail\n' > "${CASES_PATH}"

clean_env() {
  env -i \
    HOME="${HOME_ROOT}" \
    TMPDIR="${TMP_ROOT}" \
    XDG_CACHE_HOME="${CACHE_ROOT}" \
    PATH="${PATH}" \
    PYTHONNOUSERSITE=1 \
    PYTHONPATH= \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LC_ALL=C \
    LANG=C \
    TZ=UTC \
    THREADS="${THREADS}" \
    "$@"
}

write_command() {
  local case_id="$1"
  cat > "${COMMAND_ROOT}/${case_id}.sh"
  chmod +x "${COMMAND_ROOT}/${case_id}.sh"
}

run_case() {
  local case_id="$1"
  local detail="$2"
  local command_file="${COMMAND_ROOT}/${case_id}.sh"
  local log_file="${LOG_ROOT}/${case_id}.log"
  if clean_env bash "${command_file}" > "${log_file}" 2>&1; then
    printf '%s\tPASS\t%s\n' "${case_id}" "${detail}" >> "${CASES_PATH}"
    return 0
  fi
  printf '%s\tFAIL\tsee logs/%s.log\n' "${case_id}" "${case_id}" >> "${CASES_PATH}"
  tail -100 "${log_file}" >&2
  return 1
}

write_command public_https_tag_clone <<EOF
#!/usr/bin/env bash
set -euo pipefail
git clone --no-checkout $(printf '%q' "${REPOSITORY_URL}") $(printf '%q' "${CLONE_ROOT}")
test "\$(git -C $(printf '%q' "${CLONE_ROOT}") remote get-url origin)" = $(printf '%q' "${REPOSITORY_URL}")
git -C $(printf '%q' "${CLONE_ROOT}") fsck --full
EOF
run_case public_https_tag_clone "public HTTPS clone completed"

write_command annotated_tag_identity <<EOF
#!/usr/bin/env bash
set -euo pipefail
test "\$(git -C $(printf '%q' "${CLONE_ROOT}") cat-file -t refs/tags/${TAG})" = tag
TAG_OBJECT_SHA="\$(git -C $(printf '%q' "${CLONE_ROOT}") rev-parse refs/tags/${TAG}^{tag})"
test "\${#TAG_OBJECT_SHA}" -eq 40
test "\$(git -C $(printf '%q' "${CLONE_ROOT}") rev-parse refs/tags/${TAG}^{commit})" = $(printf '%q' "${FINAL_SHA}")
git -C $(printf '%q' "${CLONE_ROOT}") checkout --detach $(printf '%q' "${FINAL_SHA}")
test "\$(git -C $(printf '%q' "${CLONE_ROOT}") rev-parse HEAD)" = $(printf '%q' "${FINAL_SHA}")
printf '%s\n' "\${TAG_OBJECT_SHA}" > $(printf '%q' "${WORK_ROOT}/tag_object_sha.txt")
EOF
run_case annotated_tag_identity "annotated tag peeled to FINAL_SHA"

write_command locked_environment <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") - <<'PY'
import platform
from importlib.metadata import version

assert platform.python_version() == "3.12.13"
expected = {
    "pysam": "0.24.0", "pandas": "3.0.3", "numpy": "2.5.1",
    "matplotlib": "3.11.0", "requests": "2.34.2", "pytest": "9.1.1",
    "build": "1.5.0", "setuptools": "82.0.1", "wheel": "0.47.0",
    "python-docx": "1.2.0",
}
observed = {name: version(name) for name in expected}
assert observed == expected, (observed, expected)
PY
test "\$(samtools --version | sed -n '1p')" = 'samtools 1.23.1'
test "\$(samtools --version | sed -n '2p')" = 'Using htslib 1.23.1'
test "\$(minimap2 --version)" = '2.31-r1302'
BWA_VERSION="\$(bwa 2>&1 || true)"
grep -F 'Version: 0.7.19-r1273' <<< "\${BWA_VERSION}" >/dev/null
EOF
run_case locked_environment "pinned interpreter, packages, and command-line tools matched"

cat > "${EVIDENCE_ROOT}/environment.txt" <<EOF
python=3.12.13
samtools=1.23.1
htslib=1.23.1
minimap2=2.31-r1302
bwa=0.7.19-r1273
threads=4
EOF

write_command wheel_sdist_build <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") -m build --no-isolation --outdir $(printf '%q' "${DIST_ROOT}") $(printf '%q' "${CLONE_ROOT}")
test "\$(find $(printf '%q' "${DIST_ROOT}") -maxdepth 1 -type f -name 'mito_overview-0.3.0-py3-none-any.whl' | wc -l | tr -d ' ')" = 1
test "\$(find $(printf '%q' "${DIST_ROOT}") -maxdepth 1 -type f -name 'mito_overview-0.3.0.tar.gz' | wc -l | tr -d ' ')" = 1
EOF
run_case wheel_sdist_build "wheel and source distribution built from public tag"

write_command installed_cli <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") -m venv --system-site-packages $(printf '%q' "${VENV_ROOT}")
$(printf '%q' "${VENV_ROOT}/bin/python") -m pip install --no-deps --force-reinstall $(printf '%q' "${DIST_ROOT}/mito_overview-0.3.0-py3-none-any.whl")
cd $(printf '%q' "${PROBE_ROOT}")
$(printf '%q' "${VENV_ROOT}/bin/python") -I -c 'from importlib.metadata import version; import mito_overview; assert version("mito-overview") == "0.3.0"; assert "site-packages" in mito_overview.__file__'
$(printf '%q' "${VENV_ROOT}/bin/python") -I -m mito_overview.cli --list-steps > installed_steps.tsv
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 $(printf '%q' "${CLONE_ROOT}/scripts/run_mito_pipeline.sh") --list-steps > launcher_steps.tsv
diff -u installed_steps.tsv launcher_steps.tsv
EOF
run_case installed_cli "installed wheel executed outside the source checkout"

write_command unit_tests <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") - \
  $(printf '%q' "${DIST_ROOT}/mito_overview-0.3.0.tar.gz") \
  $(printf '%q' "${SDIST_ROOT}") <<'PY'
import tarfile
import sys
from pathlib import Path
archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
with tarfile.open(archive, "r:gz") as handle:
    handle.extractall(destination, filter="data")
PY
cd $(printf '%q' "${SDIST_ROOT}/mito_overview-0.3.0")
$(printf '%q' "${PYTHON_BIN}") -m pytest -q
EOF
run_case unit_tests "complete source-distribution test suite passed"

write_command smoke_longread <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "${CLONE_ROOT}")
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_public_pipeline.sh
EOF
run_case smoke_longread "synthetic long-read workflow passed"

write_command smoke_shortread <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "${CLONE_ROOT}")
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_public_pipeline_shortread.sh
EOF
run_case smoke_shortread "synthetic reduced short-read workflow passed"

write_command smoke_longread_nomethyl <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "${CLONE_ROOT}")
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_public_pipeline_longread_nomethyl.sh
EOF
run_case smoke_longread_nomethyl "long-read no-methylation workflow passed"

write_command smoke_standalone <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "${CLONE_ROOT}")
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./tests/smoke_standalone_minimal.sh
EOF
run_case smoke_standalone "minimal standalone workflow passed"

write_command example_builders <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd $(printf '%q' "${CLONE_ROOT}")
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./scripts/build_public_example_bundle.sh $(printf '%q' "${EXAMPLE_ROOT}/longread")
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 ./scripts/build_public_shortread_example_bundle.sh $(printf '%q' "${EXAMPLE_ROOT}/shortread")
test -s $(printf '%q' "${EXAMPLE_ROOT}/longread/report/index.html")
test -s $(printf '%q' "${EXAMPLE_ROOT}/shortread/report/index.html")
EOF
run_case example_builders "both tracked-mode example builders passed"

write_command clean_tag_checkout <<EOF
#!/usr/bin/env bash
set -euo pipefail
test "\$(git -C $(printf '%q' "${CLONE_ROOT}") rev-parse HEAD)" = $(printf '%q' "${FINAL_SHA}")
test -z "\$(git -C $(printf '%q' "${CLONE_ROOT}") status --porcelain --untracked-files=all)"
EOF
run_case clean_tag_checkout "detached public-tag checkout remained clean"

TAG_OBJECT_SHA="$(cat "${WORK_ROOT}/tag_object_sha.txt")"
"${PYTHON_BIN}" - "${EVIDENCE_ROOT}/tag_identity.json" "${FINAL_SHA}" "${TAG}" "${TAG_OBJECT_SHA}" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "annotated_tag": True,
            "checked_out_commit": sys.argv[2],
            "git_commit": sys.argv[2],
            "release_tag": sys.argv[3],
            "tag_object_sha": sys.argv[4],
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
PY

"${PYTHON_BIN}" "${CLONE_ROOT}/scripts/sanitize_validation_evidence.py" \
  "${EVIDENCE_ROOT}" \
  --replace "${CLONE_ROOT}=\${PUBLIC_TAG_CHECKOUT}" \
  --replace "${WORK_ROOT}=\${TAG_VALIDATION_WORK}" \
  --replace "${EVIDENCE_ROOT}=\${TAG_VALIDATION_EVIDENCE}" \
  --replace "${HOME_ROOT}=\${HOME}" \
  --replace "${TMP_ROOT}=\${TMPDIR}"

(
  cd "${EVIDENCE_ROOT}"
  find . -type f \
    ! -name evidence.sha256 \
    ! -name fresh_public_tag_validation.json \
    -print0 | sort -z | xargs -0 shasum -a 256 | sed 's#  \./#  #' > evidence.sha256
  shasum -a 256 -c evidence.sha256
)

REPOSITORY_SLUG="${REPOSITORY_URL#https://github.com/}"
"${PYTHON_BIN}" - \
  "${EVIDENCE_ROOT}/fresh_public_tag_validation.json" \
  "${EVIDENCE_ROOT}/evidence.sha256" \
  "${REPOSITORY_URL}" "${REPOSITORY_SLUG}" "${FINAL_SHA}" "${TAG}" \
  "${TAG_OBJECT_SHA}" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

receipt = Path(sys.argv[1])
manifest = Path(sys.argv[2])
with (receipt.parent / "cases.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
if not rows or any(row["verdict"] != "PASS" for row in rows):
    raise SystemExit("fresh public-tag validation contains a non-PASS case")
payload = {
    "schema_version": "1.0",
    "validation_profile": "fresh_public_tag_validation_v1",
    "evidence_type": "fresh_public_tag_validation",
    "repository": sys.argv[3],
    "repository_slug": sys.argv[4],
    "release_tag": sys.argv[6],
    "git_commit": sys.argv[5],
    "checked_out_commit": sys.argv[5],
    "tag_object_sha": sys.argv[7],
    "public_https_clone": True,
    "detached_head": True,
    "clean_worktree": True,
    "verdict": "PASS",
    "verified": True,
    "case_count": len(rows),
    "cases_path": "cases.tsv",
    "environment_path": "environment.txt",
    "tag_identity_path": "tag_identity.json",
    "evidence_manifest_path": "evidence.sha256",
    "evidence_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
}
receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "[fresh-tag] PASS: ${EVIDENCE_ROOT}/fresh_public_tag_validation.json"
