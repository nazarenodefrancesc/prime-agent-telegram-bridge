from pathlib import Path

import pytest

from prime_telegram_bridge.config import ConfigError, load_config


def test_load_config_parses_allowlists(tmp_path: Path):
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "TELEGRAM_ALLOWED_USER_IDS": "1, 2;3",
            "TELEGRAM_ALLOWED_CHAT_IDS": "-100,42",
            "BRIDGE_STATE_DIR": str(tmp_path / "state"),
            "PRIME_WORKDIR": str(tmp_path),
        }
    )
    assert config.telegram_allowed_user_ids == frozenset({1, 2, 3})
    assert config.telegram_allowed_chat_ids == frozenset({-100, 42})
    assert not config.bootstrap_only


def test_missing_token_is_rejected():
    with pytest.raises(ConfigError):
        load_config({})


def test_empty_allowlist_is_bootstrap_only(tmp_path: Path):
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "token",
            "BRIDGE_STATE_DIR": str(tmp_path / "state"),
            "PRIME_WORKDIR": str(tmp_path),
        }
    )
    assert config.bootstrap_only
