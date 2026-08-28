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


def split_telegram_text(text: str, limit: int = SAFE_CHUNK) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()
    return [chunk for chunk in chunks if chunk]


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
    return IncomingMessage(
        update_id=int(update.get("update_id", 0)),
        chat_id=int(chat["id"]),
        user_id=int(sender["id"]),
        message_id=int(message["message_id"]),
        text=str(text),
        photo_file_id=photo_file_id,
        document=document,
    )


class TelegramClient:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.file_url = f"https://api.telegram.org/file/bot{token}"
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10))

    async def close(self) -> None:
        await self.client.aclose()

    async def _call(self, method: str, payload: dict[str, Any] | None = None, timeout: float = 45) -> Any:
        response = await self.client.post(f"{self.base_url}/{method}", json=payload or {}, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramApiError(f"Telegram {method} failed: {data}")
        return data.get("result")

    async def get_updates(self, *, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        return await self._call("getUpdates", payload, timeout=timeout + 15)

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
        return await self._call("getFile", {"file_id": file_id})

    async def download_file(self, file_path: str) -> bytes:
        response = await self.client.get(f"{self.file_url}/{file_path}", timeout=90)
        response.raise_for_status()
        return response.content
