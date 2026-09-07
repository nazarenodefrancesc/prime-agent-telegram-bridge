from __future__ import annotations

import httpx
import pytest

from prime_telegram_bridge.telegram_api import (
    TelegramApiError,
    TelegramClient,
    parse_update,
    split_telegram_text,
)


def utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def test_split_telegram_text_preserves_content_exactly():
    text = (" line one  \n" * 1000) + "tail  "
    chunks = split_telegram_text(text, limit=200)
    assert len(chunks) > 1
    assert all(utf16_units(chunk) <= 200 for chunk in chunks)
    assert "".join(chunks) == text


def test_split_telegram_text_counts_astral_emoji_as_two_utf16_units():
    text = "😀" * 10
    chunks = split_telegram_text(text, limit=6)
    assert chunks == ["😀😀😀", "😀😀😀", "😀😀😀", "😀"]
    assert "".join(chunks) == text


def test_parse_photo_message_uses_largest_photo():
    msg = parse_update(
        {
            "update_id": 7,
            "message": {
                "message_id": 8,
                "chat": {"id": 10},
                "from": {"id": 11},
                "caption": "hello",
                "photo": [{"file_id": "small"}, {"file_id": "large"}],
            },
        }
    )
    assert msg is not None
    assert msg.photo_file_id == "large"
    assert msg.text == "hello"


def test_parse_update_ignores_unsupported_empty_message():
    assert (
        parse_update(
            {
                "update_id": 1,
                "message": {
                    "message_id": 2,
                    "chat": {"id": 3},
                    "from": {"id": 4},
                    "sticker": {"file_id": "sticker"},
                },
            }
        )
        is None
    )


def test_parse_update_rejects_non_numeric_ids():
    assert (
        parse_update(
            {
                "update_id": "bad",
                "message": {"message_id": 2, "chat": {"id": 3}, "from": {"id": 4}, "text": "hi"},
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_telegram_api_redacts_token_from_error_description():
    token = "12345:VERY_SECRET_TOKEN"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": False, "error_code": 400, "description": f"bad token {token}"},
            request=request,
        )

    client = TelegramClient(token)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TelegramApiError) as exc_info:
            await client._call("getMe")
        assert token not in str(exc_info.value)
        assert "<redacted-telegram-token>" in str(exc_info.value)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_telegram_http_error_does_not_expose_tokenized_url():
    token = "12345:VERY_SECRET_TOKEN"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error", request=request)

    client = TelegramClient(token)
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TelegramApiError) as exc_info:
            await client._call("getMe")
        assert token not in str(exc_info.value)
        assert "HTTP 500" in str(exc_info.value)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_download_file_enforces_stream_bound():
    payload = b"x" * 101

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, request=request)

    client = TelegramClient("token")
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(ValueError, match="TELEGRAM_MAX_ATTACHMENT_BYTES"):
            await client.download_file("file.bin", max_bytes=100)
    finally:
        await client.close()
