#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${MITO_OVERVIEW_PYTHON:-python3}"
INHERITED_PYTHONPATH="${PYTHONPATH:-}"

if [[ -n "${MITO_OVERVIEW_PYTHON:-}" ]]; then
  TOOL_BIN="$(cd "$(dirname "${MITO_OVERVIEW_PYTHON}")" && pwd)"
  export PATH="${TOOL_BIN}${PATH:+:${PATH}}"
fi

# Isolated mode excludes the current directory and PYTHONPATH, so an installed
# distribution wins even when this launcher is invoked from a source checkout.
if INSTALLED_MODULE_PATH="$(
  "${PYTHON_BIN}" -I -c \
    'from pathlib import Path; import mito_overview; print(Path(mito_overview.__file__).resolve())' \
    2>/dev/null
)"; then
  if [[ "${MITO_OVERVIEW_REQUIRE_INSTALLED:-0}" == "1" ]]; then
    case "${INSTALLED_MODULE_PATH}" in
      "${REPO_ROOT}/mito_overview"|"${REPO_ROOT}/mito_overview"/*)
        echo "Installed-package validation rejected checkout import: ${INSTALLED_MODULE_PATH}" >&2
        exit 1
        ;;
    esac
  fi
  unset PYTHONPATH
  exec "${PYTHON_BIN}" -I -m mito_overview.cli "$@"
fi

if [[ "${MITO_OVERVIEW_REQUIRE_INSTALLED:-0}" == "1" ]]; then
  echo "MITO_OVERVIEW_REQUIRE_INSTALLED=1 but mito_overview is not importable from the installed environment" >&2
  exit 1
fi

export PYTHONPATH="${REPO_ROOT}${INHERITED_PYTHONPATH:+:${INHERITED_PYTHONPATH}}"
exec "${PYTHON_BIN}" -m mito_overview.cli "$@"
