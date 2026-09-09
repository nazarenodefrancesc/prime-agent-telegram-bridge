from pathlib import Path

INSTALLER = Path(__file__).parents[1] / "scripts" / "install.sh"


def test_installer_contract_is_safe_and_persistent():
    script = INSTALLER.read_text(encoding="utf-8")

    assert "set -Eeuo pipefail" in script
    assert "cp \"$ENV_EXAMPLE\" \"$ENV_FILE\"" in script
    assert "if [[ ! -e \"$ENV_FILE\" ]]" in script
    assert "chmod 600 \"$ENV_FILE\"" in script
    assert "systemctl --user enable" in script
    assert "systemctl --user daemon-reload" in script
    assert "EnvironmentFile=" in script
    assert "ExecStart=" in script
    assert "TELEGRAM_BOT_TOKEN=123456:replace_me" in script
    assert "PRIME_WORKDIR=/absolute/path/to/your/prime/workspace" in script
