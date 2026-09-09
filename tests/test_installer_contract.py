from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

INSTALLER = Path(__file__).parents[1] / "scripts" / "install.sh"


def test_installer_contract_is_safe_and_persistent():
    script = INSTALLER.read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in script
    assert 'cp "$ENV_EXAMPLE" "$ENV_FILE"' in script
    assert 'if [[ ! -e "$ENV_FILE" ]]' in script
    assert 'chmod 600 "$ENV_FILE"' in script
    assert "systemctl --user enable" in script
    assert "systemctl --user daemon-reload" in script
    assert "EnvironmentFile=" in script
    assert "ExecStart=:" in script
    assert '$(systemd-escape --path' not in script
    assert "systemd-analyze verify" in script
    assert "TELEGRAM_BOT_TOKEN=123456:replace_me" in script
    assert "PRIME_WORKDIR=/absolute/path/to/your/prime/workspace" in script


def test_rendered_systemd_unit_is_valid_with_special_paths(tmp_path: Path):
    systemd_analyze = shutil.which("systemd-analyze")
    if not systemd_analyze:
        pytest.skip("systemd-analyze is not installed")

    repo = tmp_path / "repo with space%q$z"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    installer = scripts / "install.sh"
    installer.write_bytes(INSTALLER.read_bytes())
    installer.chmod(0o755)

    home = tmp_path / "home with space%q$z"
    config_root = home / ".config"
    env_file = config_root / "prime-telegram-bridge" / "env"
    env_file.parent.mkdir(parents=True)
    env_file.write_text("TELEGRAM_BOT_TOKEN=x\nPRIME_WORKDIR=/tmp\n", encoding="utf-8")

    venv = tmp_path / "venv with space%q$z"
    executable = venv / "bin" / "prime-telegram-bridge"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    unit = tmp_path / "rendered.service"
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_root),
            "BRIDGE_VENV_DIR": str(venv),
            "PYTHON_BIN": sys.executable,
        }
    )
    subprocess.run(
        ["bash", str(installer), "--render-unit", str(unit)],
        check=True,
        env=env,
        text=True,
        capture_output=True,
    )

    rendered = unit.read_text(encoding="utf-8")
    assert "systemd-escape" not in rendered
    assert "EnvironmentFile=/" in rendered
    assert "WorkingDirectory=/" in rendered
    assert "ExecStart=:/" in rendered
    assert r"\x20" in rendered
    assert "%%q" in rendered

    subprocess.run(
        [systemd_analyze, "verify", str(unit)],
        check=True,
        text=True,
        capture_output=True,
    )
