#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${BRIDGE_VENV_DIR:-$REPO_DIR/.venv}"
CONFIG_ROOT="${XDG_CONFIG_HOME:-$HOME/.config}"
CONFIG_DIR="$CONFIG_ROOT/prime-telegram-bridge"
ENV_FILE="$CONFIG_DIR/env"
ENV_EXAMPLE="$REPO_DIR/.env.example"
UNIT_DIR="$CONFIG_ROOT/systemd/user"
UNIT_FILE="$UNIT_DIR/prime-telegram-bridge.service"
SERVICE_NAME="prime-telegram-bridge.service"

die() {
  echo "install: $*" >&2
  exit 1
}

systemd_path_escape() {
  # Keep slash-separated paths intact while escaping characters that systemd
  # parses specially. `systemd-escape --path` is for unit names and therefore
  # removes path separators; it must not be used for EnvironmentFile=,
  # WorkingDirectory=, or ExecStart= values.
  "$PYTHON_BIN" - "$1" <<'PY'
import os
import sys

raw = os.fsencode(sys.argv[1])
safe = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789/._-:"
out: list[str] = []
for byte in raw:
    if byte == 0x25:  # % starts systemd specifiers even after C-unescaping.
        out.append("%%")
    elif byte in safe:
        out.append(chr(byte))
    else:
        out.append(f"\\x{byte:02x}")
print("".join(out))
PY
}

render_unit() {
  local destination="$1"
  local env_path repo_path exec_path
  env_path="$(systemd_path_escape "$ENV_FILE")"
  repo_path="$(systemd_path_escape "$REPO_DIR")"
  exec_path="$(systemd_path_escape "$VENV_DIR/bin/prime-telegram-bridge")"

  {
    echo "[Unit]"
    echo "Description=Prime Agent Telegram Bridge"
    echo "After=network-online.target"
    echo "Wants=network-online.target"
    echo
    echo "[Service]"
    echo "Type=simple"
    echo "EnvironmentFile=$env_path"
    echo "WorkingDirectory=$repo_path"
    # ':' disables systemd environment-variable expansion in the command line;
    # systemd_path_escape still preserves the real executable path.
    echo "ExecStart=:$exec_path"
    echo "Restart=on-failure"
    echo "RestartSec=3"
    echo "NoNewPrivileges=true"
    echo
    echo "[Install]"
    echo "WantedBy=default.target"
  } >"$destination"
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "$PYTHON_BIN not found"
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is required"

# Diagnostic/test hook: render exactly the unit the installer would install,
# without touching the virtualenv, configuration, or user service manager.
if [[ "${1:-}" == "--render-unit" ]]; then
  [[ $# -eq 2 ]] || die "usage: $0 --render-unit OUTPUT_PATH"
  render_unit "$2"
  exit 0
fi
[[ $# -eq 0 ]] || die "unknown argument: $1"

command -v systemctl >/dev/null 2>&1 || die "systemctl not found; this installer requires systemd"

if [[ "$CONFIG_ROOT" != /* ]]; then
  die "XDG_CONFIG_HOME must be an absolute path when set"
fi

prime_agent_path="$(command -v prime-agent 2>/dev/null || true)"
if [[ -n "$prime_agent_path" ]]; then
  echo "Prime Agent detected: $prime_agent_path"
else
  echo "WARNING: prime-agent was not found on the current PATH." >&2
  echo "Set PRIME_AGENT_BIN to an absolute executable path before starting the service." >&2
fi

echo "[1/6] Creating virtualenv: $VENV_DIR"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR" \
    || die "failed to create virtualenv; install Python venv support for $PYTHON_BIN"
fi

echo "[2/6] Installing bridge"
"$VENV_DIR/bin/python" -m pip install -e "$REPO_DIR" >/dev/null

echo "[3/6] Preparing protected configuration"
mkdir -p "$CONFIG_DIR"
if [[ ! -e "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "[4/6] Installing user service"
mkdir -p "$UNIT_DIR"
render_unit "$UNIT_FILE"
chmod 644 "$UNIT_FILE"

if command -v systemd-analyze >/dev/null 2>&1; then
  systemd-analyze verify "$UNIT_FILE" >/dev/null \
    || die "generated systemd unit failed validation: $UNIT_FILE"
fi

echo "[5/6] Enabling persistent user service"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME" >/dev/null
if command -v loginctl >/dev/null 2>&1; then
  loginctl enable-linger "$(id -un)" >/dev/null 2>&1 || true
fi

configured=true
if grep -q '^TELEGRAM_BOT_TOKEN=123456:replace_me$' "$ENV_FILE" \
  || grep -q '^TELEGRAM_BOT_TOKEN=$' "$ENV_FILE"; then
  configured=false
fi
if grep -q '^PRIME_WORKDIR=/absolute/path/to/your/prime/workspace$' "$ENV_FILE" \
  || grep -q '^PRIME_WORKDIR=$' "$ENV_FILE"; then
  configured=false
fi

if [[ "$configured" == true ]]; then
  echo "[6/6] Starting service"
  systemctl --user restart "$SERVICE_NAME"
  systemctl --user show "$SERVICE_NAME" \
    -p ActiveState -p SubState -p MainPID -p NRestarts -p ExecMainStatus
else
  echo "[6/6] Service installed but not started: configuration is incomplete"
  echo "Edit: $ENV_FILE"
  echo "Then run: systemctl --user start $SERVICE_NAME"
fi

echo
echo "Installation complete. Unit: $UNIT_FILE"
