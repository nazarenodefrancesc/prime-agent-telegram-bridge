from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx

TELEGRAM_TEXT_LIMIT = 4096
SAFE_CHUNK = 3900


class TelegramApiError(RuntimeError):
    pass


@dataclass(slots=True)
class IncomingMessage:
    update_id: int
    chat_id: int
    user_id: int
    message_id: int
    text: str
    photo_file_id: str | None = None
    document: dict[str, Any] | None = None


def _utf16_units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _max_prefix_index(text: str, start: int, limit: int) -> int:
    units = 0
    index = start
    while index < len(text):
        units_for_char = 2 if ord(text[index]) > 0xFFFF else 1
        if units + units_for_char > limit:
            break
        units += units_for_char
        index += 1
    return index


def split_telegram_text(text: str, limit: int = SAFE_CHUNK) -> list[str]:
    """Split without changing content and honor Telegram's UTF-16 unit limit."""
    if not text:
        return []
    if limit < 1:
        raise ValueError("limit must be >= 1")
    if _utf16_units(text) <= limit:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        hard_end = _max_prefix_index(text, start, limit)
        if hard_end <= start:
            # Defensive only: every Unicode scalar is <= 2 UTF-16 units and
            # callers use limits far larger than 2.
            hard_end = start + 1
        if hard_end == len(text):
            chunks.append(text[start:hard_end])
            break

        # Prefer a natural boundary in the latter half of the chunk while
        # retaining the separator itself so concatenating chunks is lossless.
        window = text[start:hard_end]
        halfway = max(1, len(window) // 2)
        boundary = window.rfind("\n", halfway)
        if boundary < 0:
            boundary = window.rfind(" ", halfway)
        cut = start + boundary + 1 if boundary >= 0 else hard_end
        chunks.append(text[start:cut])
        start = cut

    return chunks


def parse_update(update: dict[str, Any]) -> IncomingMessage | None:
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    if "id" not in chat or "id" not in sender or "message_id" not in message:
        return None

    text = message.get("text") or message.get("caption") or ""
    photo_file_id = None
    photos = message.get("photo")
    if isinstance(photos, list) and photos:
        candidate = photos[-1]
        if isinstance(candidate, dict):
            photo_file_id = candidate.get("file_id")
    document = message.get("document") if isinstance(message.get("document"), dict) else None

    # Ignore stickers, service messages, locations, etc. until explicitly
    # supported. Otherwise an empty update would accidentally trigger Prime.
    if not str(text).strip() and not photo_file_id and document is None:
        return None

    try:
        return IncomingMessage(
            update_id=int(update.get("update_id", 0)),
            chat_id=int(chat["id"]),
            user_id=int(sender["id"]),
            message_id=int(message["message_id"]),
            text=str(text),
            photo_file_id=str(photo_file_id) if photo_file_id else None,
            document=document,
        )
    except (TypeError, ValueError):
        return None


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10))

    def _redact(self, text: str) -> str:
        return text.replace(self.token, "<redacted-telegram-token>")

    async def close(self) -> None:
        await self.client.aclose()

    async def _call(self, method: str, payload: dict[str, Any] | None = None, timeout: float = 45) -> Any:
        try:
            response = await self.client.post(
                f"{self.base_url}/{method}", json=payload or {}, timeout=timeout
            )
        except httpx.HTTPError as exc:
            raise TelegramApiError(f"Telegram {method} transport failed: {type(exc).__name__}") from None

        if response.is_error:
            raise TelegramApiError(f"Telegram {method} HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError:
            raise TelegramApiError(f"Telegram {method} returned malformed JSON") from None
        if not isinstance(data, dict):
            raise TelegramApiError(f"Telegram {method} returned an unexpected payload")
        if not data.get("ok"):
            description = self._redact(str(data.get("description") or "request failed"))
            error_code = data.get("error_code")
            suffix = f" ({error_code})" if error_code is not None else ""
            raise TelegramApiError(f"Telegram {method} failed{suffix}: {description}")
        return data.get("result")

    async def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload, timeout=timeout + 15)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getUpdates returned a non-list result")
        return [item for item in result if isinstance(item, dict)]

    async def send_message(self, chat_id: int, text: str, *, reply_to_message_id: int | None = None) -> None:
        for index, chunk in enumerate(split_telegram_text(text)):
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
                "link_preview_options": {"is_disabled": True},
            }
            if index == 0 and reply_to_message_id is not None:
                payload["reply_parameters"] = {"message_id": reply_to_message_id}
            await self._call("sendMessage", payload)

    async def send_typing(self, chat_id: int) -> None:
        await self._call("sendChatAction", {"chat_id": chat_id, "action": "typing"})

    async def typing_loop(self, chat_id: int, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.send_typing(chat_id)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=4)
            except TimeoutError:
                continue

    async def get_file(self, file_id: str) -> dict[str, Any]:
        result = await self._call("getFile", {"file_id": file_id})
        if not isinstance(result, dict):
            raise TelegramApiError("Telegram getFile returned an unexpected payload")
        return result

    async def download_file(self, file_path: str, *, max_bytes: int) -> bytes:
        """Stream a Telegram file and fail before buffering beyond max_bytes."""
        try:
            async with self.client.stream("GET", f"{self.file_url}/{file_path}", timeout=90) as response:
                if response.is_error:
                    raise TelegramApiError(f"Telegram file download HTTP {response.status_code}")
                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_length = int(content_length)
                    except ValueError:
                        declared_length = None
                    if declared_length is not None and declared_length > max_bytes:
                        raise ValueError("Telegram attachment exceeds TELEGRAM_MAX_ATTACHMENT_BYTES")
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError("Telegram attachment exceeds TELEGRAM_MAX_ATTACHMENT_BYTES")
                    chunks.append(chunk)
                return b"".join(chunks)
        except TelegramApiError:
            raise
        except ValueError:
            raise
        except httpx.HTTPError as exc:
            raise TelegramApiError(f"Telegram file download transport failed: {type(exc).__name__}") from None
