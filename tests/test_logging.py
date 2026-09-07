from __future__ import annotations

import io
import logging

import httpx
import pytest

from prime_telegram_bridge.logging_utils import configure_logging
from prime_telegram_bridge.telegram_api import TelegramApiError, TelegramClient


@pytest.fixture
def restore_logging():
    root = logging.getLogger()
    old_handlers = list(root.handlers)
    old_level = root.level
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    old_httpx_level = httpx_logger.level
    old_httpcore_level = httpcore_logger.level
    try:
        yield
    finally:
        root.handlers.clear()
        root.handlers.extend(old_handlers)
        root.setLevel(old_level)
        httpx_logger.setLevel(old_httpx_level)
        httpcore_logger.setLevel(old_httpcore_level)


def test_configure_logging_redacts_token_from_message_and_traceback(restore_logging):
    token = "12345:VERY_SECRET_TOKEN"
    stream = io.StringIO()
    configure_logging("DEBUG", telegram_bot_token=token, stream=stream)
    logger = logging.getLogger("prime_telegram_bridge.test")

    logger.info("normal secret=%s", token)
    try:
        raise RuntimeError(f"failed with {token}")
    except RuntimeError:
        logger.exception("exception path")

    rendered = stream.getvalue()
    assert token not in rendered
    assert "<redacted-secret>" in rendered


def test_configure_logging_suppresses_httpx_and_httpcore_info(restore_logging):
    configure_logging("DEBUG", telegram_bot_token="token", stream=io.StringIO())
    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


@pytest.mark.asyncio
async def test_normal_httpx_telegram_call_does_not_log_token(restore_logging):
    token = "12345:VERY_SECRET_TOKEN"
    stream = io.StringIO()
    configure_logging("DEBUG", telegram_bot_token=token, stream=stream)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": True}, request=request)

    client = TelegramClient(token)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        assert await client._call("getMe") is True
    finally:
        await client.close()

    assert token not in stream.getvalue()


@pytest.mark.asyncio
async def test_http_and_telegram_error_logs_do_not_expose_token(restore_logging):
    token = "12345:VERY_SECRET_TOKEN"
    stream = io.StringIO()
    configure_logging("DEBUG", telegram_bot_token=token, stream=stream)

    responses = iter(
        [
            httpx.Response(500, text="bad"),
            httpx.Response(
                200,
                json={"ok": False, "error_code": 400, "description": f"bad token {token}"},
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        response = next(responses)
        response.request = request
        return response

    client = TelegramClient(token)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TelegramApiError):
            await client._call("getMe")
        with pytest.raises(TelegramApiError):
            await client._call("getMe")
    finally:
        await client.close()

    rendered = stream.getvalue()
    assert token not in rendered
