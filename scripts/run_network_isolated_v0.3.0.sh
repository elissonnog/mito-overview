#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run_network_isolated_v0.3.0.sh --evidence EVIDENCE_TSV -- COMMAND [ARG ...]

Run COMMAND with operating-system network access denied. Before COMMAND starts,
the isolated child must fail to connect to a live loopback listener in the
parent network context. The wrapper writes a machine-readable evidence record
and exports its path to COMMAND.

Supported platforms:
  macOS   sandbox-exec with (deny network*)
  Linux   sudo unshare --net, followed by a UID/GID drop with setpriv
EOF
}

EVIDENCE_PATH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence)
      [[ $# -ge 2 ]] || { echo "--evidence requires a value" >&2; exit 2; }
      EVIDENCE_PATH="$2"
      shift 2
      ;;
    --)
      shift
      break
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ -n "${EVIDENCE_PATH}" ]] || { echo "--evidence is required" >&2; exit 2; }
[[ $# -gt 0 ]] || { echo "A command is required after --" >&2; exit 2; }
[[ "${EVIDENCE_PATH}" == /* ]] || {
  echo "Evidence path must be absolute: ${EVIDENCE_PATH}" >&2
  exit 2
}
[[ ! -e "${EVIDENCE_PATH}" && ! -L "${EVIDENCE_PATH}" ]] || {
  echo "Evidence path must not already exist: ${EVIDENCE_PATH}" >&2
  exit 1
}

PYTHON_REQUEST="${MITO_OVERVIEW_PYTHON:-python3}"
PYTHON_BIN="$(command -v "${PYTHON_REQUEST}" || true)"
[[ -n "${PYTHON_BIN}" ]] || {
  echo "Python interpreter not found: ${PYTHON_REQUEST}" >&2
  exit 1
}

mkdir -p "$(dirname "${EVIDENCE_PATH}")"
RUNTIME_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/mito-overview-network-isolation.XXXXXX")"
chmod 700 "${RUNTIME_ROOT}"
PORT_FILE="${RUNTIME_ROOT}/listener.port"
LISTENER_LOG="${RUNTIME_ROOT}/listener.log"
STOP_FILE="${RUNTIME_ROOT}/listener.stop"
PROBE_STATUS="${RUNTIME_ROOT}/isolated-probe.status"
ENVIRONMENT_JSON="${RUNTIME_ROOT}/environment.json"
LISTENER_PID=""
ISOLATED_PID=""

cleanup() {
  local status=$?
  touch "${STOP_FILE}" 2>/dev/null || true
  if [[ -n "${LISTENER_PID}" ]]; then
    kill "${LISTENER_PID}" 2>/dev/null || true
    wait "${LISTENER_PID}" 2>/dev/null || true
  fi
  if [[ ${status} -ne 0 && -n "${ISOLATED_PID}" ]]; then
    kill "${ISOLATED_PID}" 2>/dev/null || true
    wait "${ISOLATED_PID}" 2>/dev/null || true
  fi
  rm -rf "${RUNTIME_ROOT}"
  exit "${status}"
}
trap cleanup EXIT INT TERM HUP

"${PYTHON_BIN}" -I - "${ENVIRONMENT_JSON}" <<'PY'
import json
import os
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps(dict(os.environ), sort_keys=True),
    encoding="utf-8",
)
PY

cat > "${RUNTIME_ROOT}/listener.py" <<'PY'
import socket
import sys
import time
from pathlib import Path

port_path, log_path, stop_path = map(Path, sys.argv[1:])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(4)
    server.settimeout(0.1)
    port_path.write_text(f"{server.getsockname()[1]}\n", encoding="ascii")
    deadline = time.monotonic() + 60.0
    while not stop_path.exists() and time.monotonic() < deadline:
        try:
            connection, _ = server.accept()
        except TimeoutError:
            continue
        with connection:
            connection.settimeout(1.0)
            payload = connection.recv(512).decode("ascii", errors="replace").strip()
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
PY

cat > "${RUNTIME_ROOT}/isolated_child.py" <<'PY'
import json
import os
import socket
import sys
from pathlib import Path

(
    evidence_arg,
    status_arg,
    environment_arg,
    listener_port,
    method,
    platform_id,
    invoking_uid,
    invoking_gid,
    isolated_token,
    *command,
) = sys.argv[1:]

if command and command[0] == "--":
    command = command[1:]
if not command:
    raise SystemExit("isolated child received no command")

evidence = Path(evidence_arg)
status_path = Path(status_arg)
environment = json.loads(Path(environment_arg).read_text(encoding="utf-8"))
expected_uid = int(invoking_uid)
expected_gid = int(invoking_gid)
child_uid = os.getuid()
child_gid = os.getgid()
if child_uid != expected_uid or child_gid != expected_gid:
    status_path.write_text("identity_mismatch\n", encoding="ascii")
    raise SystemExit(
        f"isolated child identity mismatch: {child_uid}:{child_gid} != "
        f"{expected_uid}:{expected_gid}"
    )

probe_error = ""
try:
    with socket.create_connection(("127.0.0.1", int(listener_port)), timeout=2.0) as sock:
        sock.sendall((isolated_token + "\n").encode("ascii"))
except OSError as exc:
    probe_result = "blocked"
    probe_error = f"{type(exc).__name__}:{getattr(exc, 'errno', '')}"
else:
    probe_result = "reachable"
    probe_error = "connection_succeeded"

verdict = "PASS" if probe_result == "blocked" else "FAIL"
rows = [
    ("schema_version", "1.0"),
    ("platform", platform_id),
    ("isolation_method", method),
    ("isolation_scope", "process_tree"),
    ("parent_loopback_control", "reachable"),
    ("isolated_loopback_probe", probe_result),
    ("probe_target", "parent_loopback_listener"),
    ("probe_error", probe_error.replace("\t", " ").replace("\n", " ")),
    ("invoking_uid", str(expected_uid)),
    ("invoking_gid", str(expected_gid)),
    ("child_uid", str(child_uid)),
    ("child_gid", str(child_gid)),
    ("network_isolation_verdict", verdict),
]
temporary = evidence.with_name(evidence.name + ".partial")
temporary.write_text(
    "field\tvalue\n" + "".join(f"{key}\t{value}\n" for key, value in rows),
    encoding="utf-8",
)
os.replace(temporary, evidence)
status_path.write_text(probe_result + "\n", encoding="ascii")

if verdict != "PASS":
    raise SystemExit("network isolation probe unexpectedly reached the parent listener")

environment["MITO_OVERVIEW_NETWORK_ISOLATION_ACTIVE"] = "1"
environment["MITO_OVERVIEW_NETWORK_ISOLATION_EVIDENCE"] = str(evidence)
os.execvpe(command[0], command, environment)
PY

"${PYTHON_BIN}" -I "${RUNTIME_ROOT}/listener.py" \
  "${PORT_FILE}" "${LISTENER_LOG}" "${STOP_FILE}" &
LISTENER_PID=$!
for _ in $(seq 1 200); do
  [[ -s "${PORT_FILE}" ]] && break
  kill -0 "${LISTENER_PID}" 2>/dev/null || {
    echo "Parent loopback listener terminated during startup" >&2
    exit 1
  }
  sleep 0.05
done
[[ -s "${PORT_FILE}" ]] || { echo "Parent loopback listener did not start" >&2; exit 1; }
LISTENER_PORT="$(tr -d '[:space:]' < "${PORT_FILE}")"
[[ "${LISTENER_PORT}" =~ ^[0-9]+$ ]] || {
  echo "Parent loopback listener returned an invalid port" >&2
  exit 1
}

CONTROL_TOKEN="mito-overview-v0.3.0-parent-control"
ISOLATED_TOKEN="mito-overview-v0.3.0-isolated-child"
"${PYTHON_BIN}" -I - "${LISTENER_PORT}" "${CONTROL_TOKEN}" <<'PY'
import socket
import sys

with socket.create_connection(("127.0.0.1", int(sys.argv[1])), timeout=2.0) as sock:
    sock.sendall((sys.argv[2] + "\n").encode("ascii"))
PY
for _ in $(seq 1 100); do
  grep -Fxq "${CONTROL_TOKEN}" "${LISTENER_LOG}" 2>/dev/null && break
  sleep 0.05
done
grep -Fxq "${CONTROL_TOKEN}" "${LISTENER_LOG}" 2>/dev/null || {
  echo "Parent loopback control probe was not observed" >&2
  exit 1
}

INVOKING_UID="$(id -u)"
INVOKING_GID="$(id -g)"
PLATFORM_ID="$(uname -s)/$(uname -m)"
CHILD_ARGUMENTS=(
  "${RUNTIME_ROOT}/isolated_child.py"
  "${EVIDENCE_PATH}"
  "${PROBE_STATUS}"
  "${ENVIRONMENT_JSON}"
  "${LISTENER_PORT}"
)

case "${PLATFORM_ID}" in
  Darwin/x86_64|Darwin/arm64)
    command -v sandbox-exec >/dev/null 2>&1 || {
      echo "sandbox-exec is required for macOS network isolation" >&2
      exit 1
    }
    ISOLATION_METHOD="macos_sandbox_exec_deny_network"
    sandbox-exec -p '(version 1) (allow default) (deny network*)' \
      "${PYTHON_BIN}" "${CHILD_ARGUMENTS[@]}" \
      "${ISOLATION_METHOD}" "${PLATFORM_ID}" \
      "${INVOKING_UID}" "${INVOKING_GID}" "${ISOLATED_TOKEN}" -- "$@" &
    ISOLATED_PID=$!
    ;;
  Linux/x86_64)
    SUDO_BIN="$(command -v sudo || true)"
    UNSHARE_BIN="$(command -v unshare || true)"
    SETPRIV_BIN="$(command -v setpriv || true)"
    for requirement in SUDO_BIN UNSHARE_BIN SETPRIV_BIN; do
      [[ -n "${!requirement}" ]] || {
        echo "${requirement%_BIN} is required for Linux network isolation" >&2
        exit 1
      }
    done
    "${SUDO_BIN}" -n true >/dev/null 2>&1 || {
      echo "Passwordless sudo is required to create the Linux network namespace" >&2
      exit 1
    }
    ISOLATION_METHOD="linux_unshare_network_namespace"
    "${SUDO_BIN}" -n "${UNSHARE_BIN}" --net -- \
      "${SETPRIV_BIN}" --reuid="${INVOKING_UID}" --regid="${INVOKING_GID}" --clear-groups -- \
      "${PYTHON_BIN}" "${CHILD_ARGUMENTS[@]}" \
      "${ISOLATION_METHOD}" "${PLATFORM_ID}" \
      "${INVOKING_UID}" "${INVOKING_GID}" "${ISOLATED_TOKEN}" -- "$@" &
    ISOLATED_PID=$!
    ;;
  *)
    echo "Unsupported platform for OS-level network isolation: ${PLATFORM_ID}" >&2
    exit 1
    ;;
esac

for _ in $(seq 1 240); do
  [[ -s "${PROBE_STATUS}" ]] && break
  if ! kill -0 "${ISOLATED_PID}" 2>/dev/null; then
    wait "${ISOLATED_PID}" || true
    echo "Isolated child terminated before producing probe evidence" >&2
    exit 1
  fi
  sleep 0.05
done
[[ -s "${PROBE_STATUS}" ]] || {
  echo "Isolated child did not produce probe evidence" >&2
  exit 1
}
kill -0 "${LISTENER_PID}" 2>/dev/null || {
  echo "Parent loopback listener was not alive during the isolated probe" >&2
  exit 1
}
[[ "$(tr -d '[:space:]' < "${PROBE_STATUS}")" == blocked ]] || {
  echo "OS-level network isolation probe did not fail closed" >&2
  exit 1
}
if grep -Fxq "${ISOLATED_TOKEN}" "${LISTENER_LOG}" 2>/dev/null; then
  echo "Isolated child reached the parent loopback listener" >&2
  exit 1
fi

touch "${STOP_FILE}"
wait "${LISTENER_PID}" || true
LISTENER_PID=""

set +e
wait "${ISOLATED_PID}"
COMMAND_STATUS=$?
set -e
ISOLATED_PID=""
[[ ${COMMAND_STATUS} -eq 0 ]] || exit "${COMMAND_STATUS}"

grep -Fqx $'network_isolation_verdict\tPASS' "${EVIDENCE_PATH}" || {
  echo "Isolated command completed without valid PASS evidence" >&2
  exit 1
}
echo "[network-isolation] PASS method=${ISOLATION_METHOD} evidence=${EVIDENCE_PATH}"
