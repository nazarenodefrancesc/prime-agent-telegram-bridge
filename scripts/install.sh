#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${BRIDGE_VENV_DIR:-$REPO_DIR/.venv}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/prime-telegram-bridge"
ENV_FILE="$CONFIG_DIR/env"
ENV_EXAMPLE="$REPO_DIR/.env.example"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/prime-telegram-bridge.service"
SERVICE_NAME="prime-telegram-bridge.service"

die() {
  echo "install: $*" >&2
  exit 1
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || die "$PYTHON_BIN not found"
command -v systemctl >/dev/null 2>&1 || die "systemctl not found; this installer requires systemd"
command -v systemd-escape >/dev/null 2>&1 || die "systemd-escape not found"

"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is required"

echo "[1/6] Creating virtualenv: $VENV_DIR"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "[2/6] Installing bridge"
"$VENV_DIR/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV_DIR/bin/python" -m pip install -e "$REPO_DIR" >/dev/null

echo "[3/6] Preparing protected configuration"
mkdir -p "$CONFIG_DIR"
if [[ ! -e "$ENV_FILE" ]]; then
  cp "$ENV_EXAMPLE" "$ENV_FILE"
fi
chmod 600 "$ENV_FILE"

echo "[4/6] Installing user service"
mkdir -p "$UNIT_DIR"
ENV_ESCAPED="$(systemd-escape --path "$ENV_FILE")"
REPO_ESCAPED="$(systemd-escape --path "$REPO_DIR")"
EXEC_ESCAPED="$(systemd-escape --path "$VENV_DIR/bin/prime-telegram-bridge")"
{
  echo "[Unit]"
  echo "Description=Prime Agent Telegram Bridge"
  echo "After=network-online.target"
  echo "Wants=network-online.target"
  echo
  echo "[Service]"
  echo "Type=simple"
  echo "EnvironmentFile=$ENV_ESCAPED"
  echo "WorkingDirectory=$REPO_ESCAPED"
  echo "ExecStart=$EXEC_ESCAPED"
  echo "Restart=on-failure"
  echo "RestartSec=3"
  echo "NoNewPrivileges=true"
  echo
  echo "[Install]"
  echo "WantedBy=default.target"
} >"$UNIT_FILE"
chmod 644 "$UNIT_FILE"

echo "[5/6] Enabling persistent user service"
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME" >/dev/null
loginctl enable-linger "$USER" >/dev/null 2>&1 || true

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
