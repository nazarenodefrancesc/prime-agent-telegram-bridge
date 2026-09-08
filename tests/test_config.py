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


def test_explicit_empty_mapping_does_not_fall_back_to_os_environ(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "host-secret")
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


def test_prime_thinking_is_normalized_and_validated(tmp_path: Path):
    base = {
        "TELEGRAM_BOT_TOKEN": "token",
        "BRIDGE_STATE_DIR": str(tmp_path / "state"),
        "PRIME_WORKDIR": str(tmp_path),
    }
    assert load_config({**base, "PRIME_THINKING": " HIGH "}).prime_thinking == "high"
    with pytest.raises(ConfigError, match="PRIME_THINKING"):
        load_config({**base, "PRIME_THINKING": "turbo"})


def test_attachment_retention_defaults_to_24_hours_and_is_validated(tmp_path: Path):
    base = {
        "TELEGRAM_BOT_TOKEN": "token",
        "BRIDGE_STATE_DIR": str(tmp_path / "state"),
        "PRIME_WORKDIR": str(tmp_path),
    }
    assert load_config(base).telegram_attachment_retention_hours == 24
    assert (
        load_config({**base, "TELEGRAM_ATTACHMENT_RETENTION_HOURS": "72"})
        .telegram_attachment_retention_hours
        == 72
    )
    with pytest.raises(ConfigError, match="TELEGRAM_ATTACHMENT_RETENTION_HOURS"):
        load_config({**base, "TELEGRAM_ATTACHMENT_RETENTION_HOURS": "0"})


def test_prime_rpc_max_line_bytes_defaults_to_16_mib_and_is_bounded(tmp_path: Path):
    base = {
        "TELEGRAM_BOT_TOKEN": "token",
        "BRIDGE_STATE_DIR": str(tmp_path / "state"),
        "PRIME_WORKDIR": str(tmp_path),
    }
    assert load_config(base).prime_rpc_max_line_bytes == 16 * 1024 * 1024
    assert (
        load_config({**base, "PRIME_RPC_MAX_LINE_BYTES": "1048576"}).prime_rpc_max_line_bytes
        == 1048576
    )
    with pytest.raises(ConfigError, match="PRIME_RPC_MAX_LINE_BYTES"):
        load_config({**base, "PRIME_RPC_MAX_LINE_BYTES": "65535"})
