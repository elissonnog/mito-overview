#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "Usage: $0 GITHUB_HTTPS_URL FINAL_SHA WORK_ROOT EVIDENCE_ROOT RELEASE_ASSET_SOURCE" >&2
  exit 2
fi

REPOSITORY_URL="${1%/}"
FINAL_SHA="$2"
WORK_ROOT="$3"
EVIDENCE_ROOT="$4"
ASSET_SOURCE_ROOT="$5"
RELEASE_VERSION="v0.3.1"
PACKAGE_VERSION="0.3.1"
SCIENTIFIC_PROTOCOL_VERSION="v0.3.0"
TAG="${RELEASE_VERSION}"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
THREADS=4
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

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
if [[ -L "${ASSET_SOURCE_ROOT}" || ! -d "${ASSET_SOURCE_ROOT}" ]]; then
  echo "RELEASE_ASSET_SOURCE must be an existing non-symlink directory" >&2
  exit 2
fi
ASSET_SOURCE_ROOT="$(cd "${ASSET_SOURCE_ROOT}" && pwd -P)"

"${PYTHON_BIN}" -I -S "${REPO_ROOT}/scripts/verify_release_environment_v0.3.1.py" \
  --repo-root "${REPO_ROOT}" \
  --expected-commit "${FINAL_SHA}" >/dev/null

"${PYTHON_BIN}" - "${ASSET_SOURCE_ROOT}" "${WORK_ROOT}" "${EVIDENCE_ROOT}" <<'PY'
import sys
from pathlib import Path

source = Path(sys.argv[1]).resolve(strict=True)
work = Path(sys.argv[2]).resolve(strict=False)
evidence = Path(sys.argv[3]).resolve(strict=False)
for other, label in ((work, "WORK_ROOT"), (evidence, "EVIDENCE_ROOT")):
    if source == other or source.is_relative_to(other) or other.is_relative_to(source):
        raise SystemExit(f"RELEASE_ASSET_SOURCE must be disjoint from {label}")

expected = {
    "mito_overview-0.3.1-py3-none-any.whl",
    "mito_overview-0.3.1.tar.gz",
    "mito-overview-v0.3.1-validation.zip",
    "MitoOverview_v0.3.1_release_validation_report.md",
    "MitoOverview_v0.3.1_release_validation_report.docx",
    "MitoOverview_v0.3.1_release_validation_report.pdf",
    "MitoOverview_v0.3.1_release_validation_report_assets.tar.gz",
    "mito-overview-v0.3.1-verification.json",
    "RELEASE_NOTES_v0.3.1.md",
    "mito-overview-v0.3.1-environment.txt",
    "mito-overview-v0.3.1-environment-locks.tar.gz",
}
entries = {path.name: path for path in source.iterdir()}
if set(entries) != expected:
    raise SystemExit(
        "RELEASE_ASSET_SOURCE inventory mismatch; "
        f"missing={sorted(expected - set(entries))!r}; "
        f"unexpected={sorted(set(entries) - expected)!r}"
    )
for name, path in entries.items():
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"RELEASE_ASSET_SOURCE contains a non-regular file: {name}")
PY

CLONE_ROOT="${WORK_ROOT}/public-tag-clone"
DIST_ROOT="${WORK_ROOT}/dist"
RELEASE_ASSET_ROOT="${WORK_ROOT}/release-assets"
PACKET_SEMANTIC_ROOT="${WORK_ROOT}/release-packet-verify"
SDIST_ROOT="${WORK_ROOT}/sdist"
VENV_ROOT="${WORK_ROOT}/venv"
SDIST_VENV_ROOT="${WORK_ROOT}/sdist-venv"
PROBE_ROOT="${WORK_ROOT}/installed-probe"
SDIST_PROBE_ROOT="${WORK_ROOT}/installed-sdist-probe"
EXAMPLE_ROOT="${WORK_ROOT}/examples"
HOME_ROOT="${WORK_ROOT}/home"
TMP_ROOT="${WORK_ROOT}/tmp"
CACHE_ROOT="${WORK_ROOT}/cache"
COMMAND_ROOT="${EVIDENCE_ROOT}/commands"
LOG_ROOT="${EVIDENCE_ROOT}/logs"
CASES_PATH="${EVIDENCE_ROOT}/cases.tsv"

mkdir -p "${WORK_ROOT}" "${EVIDENCE_ROOT}" "${COMMAND_ROOT}" "${LOG_ROOT}" \
  "${DIST_ROOT}" "${RELEASE_ASSET_ROOT}" "${SDIST_ROOT}" "${PROBE_ROOT}" "${EXAMPLE_ROOT}" \
  "${SDIST_PROBE_ROOT}" \
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

"${PYTHON_BIN}" -I -S "${CLONE_ROOT}/scripts/verify_release_environment_v0.3.1.py" \
  --repo-root "${CLONE_ROOT}" \
  --expected-commit "${FINAL_SHA}" \
  --output "${EVIDENCE_ROOT}/release_environment_verification.json"
"${PYTHON_BIN}" - "${EVIDENCE_ROOT}/release_environment_verification.json" \
  "${SCIENTIFIC_PROTOCOL_VERSION}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
observed = payload.get("scientific_protocol_version")
if observed not in (None, sys.argv[2]):
    raise SystemExit("release environment scientific protocol differs")
payload["scientific_protocol_version"] = sys.argv[2]
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

write_command locked_environment <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") - <<'PY'
import platform
from importlib.metadata import version

assert platform.python_version() == "3.12.13"
expected = {
    "biopython": "1.87",
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
operating_system=$(uname -s)
architecture=$(uname -m)
python=3.12.13
samtools=1.23.1
htslib=1.23.1
minimap2=2.31-r1302
bwa=0.7.19-r1273
threads=4
scientific_protocol_version=${SCIENTIFIC_PROTOCOL_VERSION}
EOF

write_command wheel_sdist_build <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") -m build --no-isolation --outdir $(printf '%q' "${DIST_ROOT}") $(printf '%q' "${CLONE_ROOT}")
test "\$(find $(printf '%q' "${DIST_ROOT}") -maxdepth 1 -type f -name 'mito_overview-0.3.1-py3-none-any.whl' | wc -l | tr -d ' ')" = 1
test "\$(find $(printf '%q' "${DIST_ROOT}") -maxdepth 1 -type f -name 'mito_overview-0.3.1.tar.gz' | wc -l | tr -d ' ')" = 1
EOF
run_case wheel_sdist_build "wheel and source distribution built from public tag"

write_command distribution_payload_equivalence <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") \
  $(printf '%q' "${CLONE_ROOT}/scripts/verify_distribution_equivalence_v0.3.1.py") \
  $(printf '%q' "${ASSET_SOURCE_ROOT}") \
  $(printf '%q' "${DIST_ROOT}") \
  $(printf '%q' "${EVIDENCE_ROOT}/distribution_payload_equivalence.json")
EOF
run_case distribution_payload_equivalence "packet-bound distributions matched clean tag rebuild member payloads"
"${PYTHON_BIN}" - "${EVIDENCE_ROOT}/distribution_payload_equivalence.json" \
  "${SCIENTIFIC_PROTOCOL_VERSION}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
observed = payload.get("scientific_protocol_version")
if observed not in (None, sys.argv[2]):
    raise SystemExit("distribution evidence scientific protocol differs")
payload["scientific_protocol_version"] = sys.argv[2]
path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

write_command installed_cli <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") -m venv --system-site-packages $(printf '%q' "${VENV_ROOT}")
$(printf '%q' "${VENV_ROOT}/bin/python") -m pip install --no-deps --force-reinstall $(printf '%q' "${ASSET_SOURCE_ROOT}/mito_overview-0.3.1-py3-none-any.whl")
cd $(printf '%q' "${PROBE_ROOT}")
$(printf '%q' "${VENV_ROOT}/bin/python") -I -c 'from importlib.metadata import version; import mito_overview; assert version("mito-overview") == "0.3.1"; assert "site-packages" in mito_overview.__file__'
$(printf '%q' "${VENV_ROOT}/bin/python") -I -c 'import hashlib, sys; from pathlib import Path; from mito_overview.paths import annotation_resource_path; expected={"NC_012920.1.fa":"fc392cde8e63b4d2e3a870bb97cc0626dea33d46dfb8abdebffada040f42ec92","human_mt_reference.gtf":"6c8db180f5dd7999ae70bf9e3c7e5020c6c99b4cefd935d621eedcb1fc5408d9"}; root=Path(sys.prefix)/"share"/"mito-overview"/"annotations"; observed={name:annotation_resource_path(name) for name in expected}; assert observed=={name:root/name for name in expected}; assert {name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in observed.items()}==expected'
$(printf '%q' "${VENV_ROOT}/bin/python") -I -m mito_overview.cli --list-steps > installed_steps.tsv
MITO_OVERVIEW_PYTHON=$(printf '%q' "${VENV_ROOT}/bin/python") MITO_OVERVIEW_REQUIRE_INSTALLED=1 $(printf '%q' "${CLONE_ROOT}/scripts/run_mito_pipeline.sh") --list-steps > launcher_steps.tsv
diff -u installed_steps.tsv launcher_steps.tsv
EOF
run_case installed_cli "installed wheel and annotation resources resolved outside the source checkout"

write_command installed_sdist_cli <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") -m venv --system-site-packages $(printf '%q' "${SDIST_VENV_ROOT}")
$(printf '%q' "${SDIST_VENV_ROOT}/bin/python") -m pip install --no-deps --no-build-isolation --force-reinstall $(printf '%q' "${ASSET_SOURCE_ROOT}/mito_overview-0.3.1.tar.gz")
cd $(printf '%q' "${SDIST_PROBE_ROOT}")
$(printf '%q' "${SDIST_VENV_ROOT}/bin/python") -I -c 'from importlib.metadata import version; from pathlib import Path; import mito_overview; p=Path(mito_overview.__file__).resolve(); assert version("mito-overview") == "0.3.1"; assert "site-packages" in p.parts; print(p)'
$(printf '%q' "${SDIST_VENV_ROOT}/bin/python") -I -m mito_overview.cli --list-steps > installed_sdist_steps.tsv
diff -u $(printf '%q' "${PROBE_ROOT}/installed_steps.tsv") installed_sdist_steps.tsv
EOF
run_case installed_sdist_cli "installed source distribution executed from a separate environment outside the checkout"

write_command unit_tests <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") - \
  $(printf '%q' "${ASSET_SOURCE_ROOT}/mito_overview-0.3.1.tar.gz") \
  $(printf '%q' "${SDIST_ROOT}") <<'PY'
import tarfile
import sys
from pathlib import Path
archive = Path(sys.argv[1])
destination = Path(sys.argv[2])
with tarfile.open(archive, "r:gz") as handle:
    handle.extractall(destination, filter="data")
PY
cd $(printf '%q' "${SDIST_ROOT}/mito_overview-0.3.1")
$(printf '%q' "${PYTHON_BIN}") -m pytest -q tests
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
$(printf '%q' "${VENV_ROOT}/bin/python") - \
  $(printf '%q' "${CLONE_ROOT}/examples/expected_reports/TOY-001_output") \
  $(printf '%q' "${EXAMPLE_ROOT}/longread") 88 longread \
  $(printf '%q' "${CLONE_ROOT}/examples/expected_reports/TOY-SR-001_output") \
  $(printf '%q' "${EXAMPLE_ROOT}/shortread") 74 shortread <<'PY'
import hashlib
import sys
from pathlib import Path


def inventory(root: Path, label: str) -> dict[str, Path]:
    if root.is_symlink() or not root.is_dir():
        raise SystemExit(f"{label} root is not a regular directory: {root}")
    paths: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            raise SystemExit(f"{label} contains a symlink: {relative}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"{label} contains a non-regular file: {relative}")
        paths[relative] = path
    return paths


arguments = sys.argv[1:]
if len(arguments) != 8:
    raise SystemExit("internal error: expected two synthetic bundle comparison specifications")

for offset in (0, 4):
    expected_root = Path(arguments[offset]).resolve(strict=True)
    observed_root = Path(arguments[offset + 1]).resolve(strict=True)
    expected_count = int(arguments[offset + 2])
    label = arguments[offset + 3]
    expected = inventory(expected_root, f"tracked {label} bundle")
    observed = inventory(observed_root, f"generated {label} bundle")
    if len(expected) != expected_count:
        raise SystemExit(
            f"tracked {label} bundle count mismatch: expected contract={expected_count}, "
            f"observed={len(expected)}"
        )
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if missing or extra:
        raise SystemExit(
            f"generated {label} bundle inventory mismatch: "
            f"missing={missing!r}; extra={extra!r}"
        )
    changed = []
    for relative in sorted(expected):
        expected_sha256 = hashlib.sha256(expected[relative].read_bytes()).hexdigest()
        observed_sha256 = hashlib.sha256(observed[relative].read_bytes()).hexdigest()
        if observed_sha256 != expected_sha256:
            changed.append(relative)
    if changed:
        raise SystemExit(
            f"generated {label} bundle content mismatch: changed={changed!r}"
        )
    print(f"verified {label} bundle: files={expected_count}")
PY
EOF
run_case example_builders "both generated example bundles exactly matched tracked paths and content"

write_command clean_tag_checkout <<EOF
#!/usr/bin/env bash
set -euo pipefail
test "\$(git -C $(printf '%q' "${CLONE_ROOT}") rev-parse HEAD)" = $(printf '%q' "${FINAL_SHA}")
test -z "\$(git -C $(printf '%q' "${CLONE_ROOT}") status --porcelain --untracked-files=all)"
EOF
run_case clean_tag_checkout "detached public-tag checkout remained clean"

TAG_OBJECT_SHA="$(cat "${WORK_ROOT}/tag_object_sha.txt")"
write_command release_asset_semantic_identity <<EOF
#!/usr/bin/env bash
set -euo pipefail
$(printf '%q' "${PYTHON_BIN}") \
  $(printf '%q' "${CLONE_ROOT}/scripts/verify_release_asset_identity_v0.3.1.py") \
  archive-digest \
  $(printf '%q' "${ASSET_SOURCE_ROOT}/mito-overview-v0.3.1-validation.zip") \
  --release-identity \
  $(printf '%q' "${ASSET_SOURCE_ROOT}/mito-overview-v0.3.1-verification.json") \
  --repository-url $(printf '%q' "${REPOSITORY_URL}") \
  --final-sha $(printf '%q' "${FINAL_SHA}") \
  --output-json $(printf '%q' "${EVIDENCE_ROOT}/external_archive_digest.json")
$(printf '%q' "${PYTHON_BIN}") \
  $(printf '%q' "${CLONE_ROOT}/scripts/safe_extract_validation_zip.py") \
  $(printf '%q' "${ASSET_SOURCE_ROOT}/mito-overview-v0.3.1-validation.zip") \
  $(printf '%q' "${PACKET_SEMANTIC_ROOT}")
test -f $(printf '%q' "${PACKET_SEMANTIC_ROOT}/verify_bundle.sh")
test ! -L $(printf '%q' "${PACKET_SEMANTIC_ROOT}/verify_bundle.sh")
bash $(printf '%q' "${PACKET_SEMANTIC_ROOT}/verify_bundle.sh")
$(printf '%q' "${PYTHON_BIN}") \
  $(printf '%q' "${CLONE_ROOT}/scripts/verify_release_asset_identity_v0.3.1.py") \
  $(printf '%q' "${ASSET_SOURCE_ROOT}") \
  $(printf '%q' "${PACKET_SEMANTIC_ROOT}") \
  $(printf '%q' "${REPOSITORY_URL}") \
  $(printf '%q' "${FINAL_SHA}") \
  $(printf '%q' "${EVIDENCE_ROOT}/release_asset_semantic_identity.json")
EOF
run_case release_asset_semantic_identity "external ZIP digest passed before internal packet and report identity checks"

write_command trusted_release_assets <<EOF
#!/usr/bin/env bash
set -euo pipefail
test -z "\$(find $(printf '%q' "${RELEASE_ASSET_ROOT}") -mindepth 1 -maxdepth 1 -print -quit)"
for name in \
  mito_overview-0.3.1-py3-none-any.whl \
  mito_overview-0.3.1.tar.gz \
  mito-overview-v0.3.1-validation.zip \
  MitoOverview_v0.3.1_release_validation_report.md \
  MitoOverview_v0.3.1_release_validation_report.docx \
  MitoOverview_v0.3.1_release_validation_report.pdf \
  MitoOverview_v0.3.1_release_validation_report_assets.tar.gz \
  mito-overview-v0.3.1-verification.json \
  RELEASE_NOTES_v0.3.1.md \
  mito-overview-v0.3.1-environment.txt \
  mito-overview-v0.3.1-environment-locks.tar.gz; do
  test -f $(printf '%q' "${ASSET_SOURCE_ROOT}")/"\${name}"
  test ! -L $(printf '%q' "${ASSET_SOURCE_ROOT}")/"\${name}"
  cp $(printf '%q' "${ASSET_SOURCE_ROOT}")/"\${name}" $(printf '%q' "${RELEASE_ASSET_ROOT}")/"\${name}"
done
(
  cd $(printf '%q' "${RELEASE_ASSET_ROOT}")
  find . -maxdepth 1 -type f ! -name SHA256SUMS -print0 | sort -z | \
    xargs -0 shasum -a 256 | sed 's#  \./#  #' > SHA256SUMS
  shasum -a 256 -c SHA256SUMS
)
$(printf '%q' "${PYTHON_BIN}") - \
  $(printf '%q' "${RELEASE_ASSET_ROOT}") \
  $(printf '%q' "${EVIDENCE_ROOT}/trusted_release_assets.json") \
  $(printf '%q' "${REPOSITORY_URL}") \
  $(printf '%q' "${REPOSITORY_URL#https://github.com/}") \
  $(printf '%q' "${FINAL_SHA}") \
  $(printf '%q' "${TAG}") \
  $(printf '%q' "${TAG_OBJECT_SHA}") \
  $(printf '%q' "${SCIENTIFIC_PROTOCOL_VERSION}") <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

asset_root = Path(sys.argv[1])
output = Path(sys.argv[2])
expected = {
    "mito_overview-0.3.1-py3-none-any.whl",
    "mito_overview-0.3.1.tar.gz",
    "mito-overview-v0.3.1-validation.zip",
    "MitoOverview_v0.3.1_release_validation_report.md",
    "MitoOverview_v0.3.1_release_validation_report.docx",
    "MitoOverview_v0.3.1_release_validation_report.pdf",
    "MitoOverview_v0.3.1_release_validation_report_assets.tar.gz",
    "mito-overview-v0.3.1-verification.json",
    "RELEASE_NOTES_v0.3.1.md",
    "mito-overview-v0.3.1-environment.txt",
    "mito-overview-v0.3.1-environment-locks.tar.gz",
    "SHA256SUMS",
}
paths = {path.name: path for path in asset_root.iterdir()}
if set(paths) != expected:
    raise SystemExit("canonical release-asset inventory differs")
for name, path in paths.items():
    if path.is_symlink() or not path.is_file():
        raise SystemExit(f"canonical release asset is not a regular file: {name}")

checksum_pattern = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._+-]*)$")
listed = {}
checksum_bytes = paths["SHA256SUMS"].read_bytes()
for line in checksum_bytes.decode("ascii").splitlines():
    match = checksum_pattern.fullmatch(line)
    if match is None or match.group(2) in listed:
        raise SystemExit("SHA256SUMS is malformed or contains a duplicate")
    listed[match.group(2)] = match.group(1)
if set(listed) != expected - {"SHA256SUMS"}:
    raise SystemExit("SHA256SUMS inventory differs")

assets = []
for name in sorted(expected):
    path = paths[name]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if name != "SHA256SUMS" and listed[name] != digest:
        raise SystemExit(f"SHA256SUMS mismatch for {name}")
    assets.append({"name": name, "sha256": digest, "size": path.stat().st_size})

payload = {
    "schema_version": "1.0",
    "manifest_type": "trusted_release_asset_manifest",
    "validation_profile": "fresh_public_tag_validation_v2",
    "repository": sys.argv[3],
    "repository_slug": sys.argv[4],
    "release_tag": sys.argv[6],
    "scientific_protocol_version": sys.argv[8],
    "git_commit": sys.argv[5],
    "checked_out_commit": sys.argv[5],
    "tag_object_sha": sys.argv[7],
    "asset_count": len(assets),
    "sha256sums_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
    "assets": assets,
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
EOF
run_case trusted_release_assets "canonical release assets were sealed to the annotated tag and FINAL_SHA"

"${PYTHON_BIN}" - \
  "${EVIDENCE_ROOT}/tag_identity.json" "${FINAL_SHA}" "${TAG}" \
  "${TAG_OBJECT_SHA}" "${EVIDENCE_ROOT}/release_environment_verification.json" \
  "${SCIENTIFIC_PROTOCOL_VERSION}" <<'PY'
import json
import sys
from pathlib import Path

environment = json.loads(Path(sys.argv[5]).read_text(encoding="utf-8"))
if (
    environment.get("repository_commit") != sys.argv[2]
    or environment.get("repository_clean") is not True
    or environment.get("scientific_protocol_version") != sys.argv[6]
):
    raise SystemExit("release environment identity does not match the public tag")
Path(sys.argv[1]).write_text(
    json.dumps(
        {
            "annotated_tag": True,
            "checked_out_commit": sys.argv[2],
            "git_commit": sys.argv[2],
            "git_tree": environment["repository_tree"],
            "release_tag": sys.argv[3],
            "scientific_protocol_version": sys.argv[6],
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
  --replace "${ASSET_SOURCE_ROOT}=\${RELEASE_ASSET_SOURCE}" \
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
  "${EVIDENCE_ROOT}/trusted_release_assets.json" \
  "${EVIDENCE_ROOT}/release_environment_verification.json" \
  "${REPOSITORY_URL}" "${REPOSITORY_SLUG}" "${FINAL_SHA}" "${TAG}" \
  "${TAG_OBJECT_SHA}" "${SCIENTIFIC_PROTOCOL_VERSION}" <<'PY'
import csv
import hashlib
import json
import sys
from pathlib import Path

receipt = Path(sys.argv[1])
manifest = Path(sys.argv[2])
trusted_manifest = Path(sys.argv[3])
environment_path = Path(sys.argv[4])
with (receipt.parent / "cases.tsv").open(encoding="utf-8", newline="") as handle:
    rows = list(csv.DictReader(handle, delimiter="\t"))
if not rows or any(row["verdict"] != "PASS" for row in rows):
    raise SystemExit("fresh public-tag validation contains a non-PASS case")
trusted = json.loads(trusted_manifest.read_text(encoding="utf-8"))
distribution_evidence_path = receipt.parent / "distribution_payload_equivalence.json"
distribution_evidence = json.loads(
    distribution_evidence_path.read_text(encoding="utf-8")
)
if (
    distribution_evidence.get("evidence_type") != "distribution_payload_equivalence"
    or distribution_evidence.get("release_version") != "v0.3.1"
    or distribution_evidence.get("scientific_protocol_version") != sys.argv[10]
    or distribution_evidence.get("verdict") != "PASS"
    or distribution_evidence.get("verified") is not True
    or len(distribution_evidence.get("distributions", [])) != 2
    or any(
        row.get("member_payloads_identical") is not True
        for row in distribution_evidence.get("distributions", [])
    )
):
    raise SystemExit("distribution payload-equivalence evidence is invalid")
expected_trusted_identity = {
    "schema_version": "1.0",
    "manifest_type": "trusted_release_asset_manifest",
    "validation_profile": "fresh_public_tag_validation_v2",
    "repository": sys.argv[5],
    "repository_slug": sys.argv[6],
    "release_tag": sys.argv[8],
    "scientific_protocol_version": sys.argv[10],
    "git_commit": sys.argv[7],
    "checked_out_commit": sys.argv[7],
    "tag_object_sha": sys.argv[9],
}
for field, expected in expected_trusted_identity.items():
    if trusted.get(field) != expected:
        raise SystemExit(f"trusted release-asset identity mismatch for {field}")
if trusted.get("asset_count") != 12 or len(trusted.get("assets", [])) != 12:
    raise SystemExit("trusted release-asset count differs")
environment = json.loads(environment_path.read_text(encoding="utf-8"))
if (
    environment.get("repository_commit") != sys.argv[7]
    or environment.get("repository_clean") is not True
    or environment.get("scientific_protocol_version") != sys.argv[10]
):
    raise SystemExit("release environment identity differs from the public tag")

payload = {
    "schema_version": "2.0",
    "validation_profile": "fresh_public_tag_validation_v2",
    "evidence_type": "fresh_public_tag_validation",
    "repository": sys.argv[5],
    "repository_slug": sys.argv[6],
    "release_tag": sys.argv[8],
    "scientific_protocol_version": sys.argv[10],
    "git_commit": sys.argv[7],
    "checked_out_commit": sys.argv[7],
    "git_tree": environment["repository_tree"],
    "tag_object_sha": sys.argv[9],
    "public_https_clone": True,
    "detached_head": True,
    "clean_worktree": True,
    "verdict": "PASS",
    "verified": True,
    "case_count": len(rows),
    "cases_path": "cases.tsv",
    "environment_path": "environment.txt",
    "release_environment_verification_path": environment_path.name,
    "release_environment_verification_sha256": hashlib.sha256(
        environment_path.read_bytes()
    ).hexdigest(),
    "tag_identity_path": "tag_identity.json",
    "evidence_manifest_path": "evidence.sha256",
    "evidence_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    "distribution_payload_equivalence_path": distribution_evidence_path.name,
    "distribution_payload_equivalence_sha256": hashlib.sha256(
        distribution_evidence_path.read_bytes()
    ).hexdigest(),
    "trusted_asset_manifest_path": trusted_manifest.name,
    "trusted_asset_manifest_sha256": hashlib.sha256(trusted_manifest.read_bytes()).hexdigest(),
    "trusted_asset_count": trusted["asset_count"],
}
receipt.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

echo "[fresh-tag] PASS: ${EVIDENCE_ROOT}/fresh_public_tag_validation.json"
