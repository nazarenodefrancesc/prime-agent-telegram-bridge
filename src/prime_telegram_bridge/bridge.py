from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import re
from pathlib import Path
from typing import Any

from .config import BridgeConfig
from .prime_rpc import PrimeRpcError, PrimeRpcSession
from .state import ChatSessionRecord, StateStore
from .telegram_api import IncomingMessage, TelegramClient, parse_update

logger = logging.getLogger(__name__)


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:160] or "attachment.bin"


class PrimeSessionManager:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.store = StateStore(config.state_dir / "state.json")
        self.sessions: dict[int, PrimeRpcSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def lock_for(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    async def get(self, chat_id: int) -> PrimeRpcSession:
        existing = self.sessions.get(chat_id)
        if existing:
            return existing
        record = self.store.get(chat_id)
        resume = record.session_file if record and record.session_file else None
        session = PrimeRpcSession(self.config, resume_session=resume, chat_id=chat_id)
        await session.start()
        self.sessions[chat_id] = session
        if not record:
            await session.set_session_name(f"telegram-{chat_id}")
        await self.persist(chat_id, session)
        return session

    async def persist(self, chat_id: int, session: PrimeRpcSession) -> None:
        state = await session.get_state()
        session_file = state.get("sessionFile")
        if not session_file:
            raise PrimeRpcError("Prime RPC state did not expose sessionFile; cannot persist Telegram mapping")
        self.store.set(
            ChatSessionRecord(
                chat_id=chat_id,
                session_file=str(session_file),
                session_id=state.get("sessionId"),
                session_name=state.get("sessionName"),
            )
        )

    async def new(self, chat_id: int) -> dict[str, Any]:
        session = await self.get(chat_id)
        state = await session.new_session()
        await session.set_session_name(f"telegram-{chat_id}")
        await self.persist(chat_id, session)
        return state

    async def close(self) -> None:
        await asyncio.gather(*(session.close() for session in self.sessions.values()), return_exceptions=True)
        self.sessions.clear()


class TelegramPrimeBridge:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.telegram = TelegramClient(config.telegram_bot_token)
        self.prime = PrimeSessionManager(config)
        self._stopping = asyncio.Event()
        self._update_tasks: set[asyncio.Task[Any]] = set()

    def authorized(self, msg: IncomingMessage) -> bool:
        if msg.user_id not in self.config.telegram_allowed_user_ids:
            return False
        if self.config.telegram_allowed_chat_ids and msg.chat_id not in self.config.telegram_allowed_chat_ids:
            return False
        return True

    async def run(self) -> None:
        self.config.state_dir.mkdir(parents=True, exist_ok=True)
        self.config.prime_session_dir.mkdir(parents=True, exist_ok=True)
        if not self.config.prime_workdir.exists():
            raise FileNotFoundError(f"PRIME_WORKDIR does not exist: {self.config.prime_workdir}")
        if self.config.bootstrap_only:
            logger.warning(
                "No TELEGRAM_ALLOWED_USER_IDS configured. Bootstrap-only mode: /id works, agent access is denied."
            )
        offset: int | None = None
        try:
            while not self._stopping.is_set():
                try:
                    updates = await self.telegram.get_updates(offset=offset, timeout=self.config.telegram_poll_timeout)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Telegram polling failed; retrying")
                    await asyncio.sleep(2)
                    continue
                for update in updates:
                    offset = max(offset or 0, int(update.get("update_id", 0)) + 1)
                    msg = parse_update(update)
                    if not msg:
                        continue
                    task = asyncio.create_task(self.handle_message(msg), name=f"telegram-{msg.update_id}")
                    self._update_tasks.add(task)
                    task.add_done_callback(self._update_tasks.discard)
        finally:
            await self.close()

    async def close(self) -> None:
        self._stopping.set()
        for task in list(self._update_tasks):
            task.cancel()
        if self._update_tasks:
            await asyncio.gather(*self._update_tasks, return_exceptions=True)
        await self.prime.close()
        await self.telegram.close()

    async def handle_message(self, msg: IncomingMessage) -> None:
        command, _, arg = msg.text.strip().partition(" ")
        command = command.split("@", 1)[0].lower()

        if command in {"/id", "/whoami"}:
            await self.telegram.send_message(
                msg.chat_id,
                f"user_id={msg.user_id}\nchat_id={msg.chat_id}",
                reply_to_message_id=msg.message_id,
            )
            return

        if not self.authorized(msg):
            await self.telegram.send_message(
                msg.chat_id,
                "Access denied. Send /id, add your user_id to TELEGRAM_ALLOWED_USER_IDS, then restart the bridge.",
                reply_to_message_id=msg.message_id,
            )
            return

        try:
            if command == "/help":
                await self._send_help(msg)
                return
            if command == "/status":
                session = await self.prime.get(msg.chat_id)
                state = await session.get_state()
                model = state.get("model") or {}
                text = (
                    f"Prime Agent\n"
                    f"session={state.get('sessionId', 'unknown')}\n"
                    f"model={model.get('provider', '?')}/{model.get('id', '?')}\n"
                    f"thinking={state.get('thinkingLevel', '?')}\n"
                    f"streaming={state.get('isStreaming', False)}"
                )
                await self.telegram.send_message(msg.chat_id, text, reply_to_message_id=msg.message_id)
                return
            if command == "/new":
                async with self.prime.lock_for(msg.chat_id):
                    await self.prime.new(msg.chat_id)
                await self.telegram.send_message(msg.chat_id, "Started a new Prime session.")
                return
            if command == "/stop":
                session = await self.prime.get(msg.chat_id)
                await session.abort()
                await self.telegram.send_message(msg.chat_id, "Abort requested.")
                return
            if command == "/steer":
                if not arg.strip():
                    await self.telegram.send_message(msg.chat_id, "Usage: /steer <instruction>")
                    return
                session = await self.prime.get(msg.chat_id)
                await session.steer(arg.strip())
                await self.telegram.send_message(msg.chat_id, "Steering instruction queued.")
                return
            if command == "/followup":
                if not arg.strip():
                    await self.telegram.send_message(msg.chat_id, "Usage: /followup <instruction>")
                    return
                session = await self.prime.get(msg.chat_id)
                await session.follow_up(arg.strip())
                await self.telegram.send_message(msg.chat_id, "Follow-up queued.")
                return
            if command == "/compact":
                session = await self.prime.get(msg.chat_id)
                result = await session.compact(arg.strip() or None)
                await self.prime.persist(msg.chat_id, session)
                summary = result.get("summary") if isinstance(result, dict) else None
                await self.telegram.send_message(msg.chat_id, summary or "Context compacted.")
                return
            if command == "/refine":
                session = await self.prime.get(msg.chat_id)
                result = await session.refine(arg.strip() or None)
                await self.prime.persist(msg.chat_id, session)
                rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
                await self.telegram.send_message(msg.chat_id, f"Refinement complete.\n{rendered[:12000]}")
                return

            images, attachment_note = await self._prepare_attachments(msg)
            prompt = msg.text.strip()
            if attachment_note:
                prompt = f"{prompt}\n\n{attachment_note}".strip()
            if not prompt:
                prompt = "Inspect the attached content and respond to the user."

            stop_typing = asyncio.Event()
            typing_task = asyncio.create_task(self.telegram.typing_loop(msg.chat_id, stop_typing))
            try:
                # Lock per chat to keep session lifecycle/persistence atomic. Prime itself still handles recursive subagents.
                async with self.prime.lock_for(msg.chat_id):
                    session = await self.prime.get(msg.chat_id)
                    answer = await session.ask(prompt, images=images or None)
                    await self.prime.persist(msg.chat_id, session)
            finally:
                stop_typing.set()
                await asyncio.gather(typing_task, return_exceptions=True)
            await self.telegram.send_message(msg.chat_id, answer, reply_to_message_id=msg.message_id)
        except Exception as exc:
            logger.exception("Failed handling Telegram message %s", msg.message_id)
            await self.telegram.send_message(
                msg.chat_id,
                f"Bridge error: {type(exc).__name__}. Check bridge logs for details.",
                reply_to_message_id=msg.message_id,
            )

    async def _send_help(self, msg: IncomingMessage) -> None:
        text = (
            "Prime Telegram Bridge\n\n"
            "/id - show Telegram IDs (works before authorization)\n"
            "/status - show Prime session/model status\n"
            "/new - start a fresh Prime session\n"
            "/stop - abort current Prime operation\n"
            "/steer <instruction> - steer a running Prime turn\n"
            "/followup <instruction> - queue work after the current run\n"
            "/compact [instructions] - compact Prime context\n"
            "/refine [instructions] - run Prime continual-harness refinement\n"
            "/help - this message\n\n"
            "Normal messages are sent to the persistent Prime session for this Telegram chat."
        )
        await self.telegram.send_message(msg.chat_id, text, reply_to_message_id=msg.message_id)

    async def _prepare_attachments(self, msg: IncomingMessage) -> tuple[list[dict[str, str]], str]:
        images: list[dict[str, str]] = []
        notes: list[str] = []

        if msg.photo_file_id:
            info = await self.telegram.get_file(msg.photo_file_id)
            file_path = info.get("file_path")
            if file_path:
                raw = await self.telegram.download_file(file_path)
                if len(raw) > self.config.telegram_max_attachment_bytes:
                    raise ValueError("Telegram photo exceeds TELEGRAM_MAX_ATTACHMENT_BYTES")
                mime = mimetypes.guess_type(file_path)[0] or "image/jpeg"
                images.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(raw).decode("ascii"),
                        "mimeType": mime,
                    }
                )

        if msg.document:
            declared_size = int(msg.document.get("file_size") or 0)
            if declared_size > self.config.telegram_max_attachment_bytes:
                raise ValueError("Telegram document exceeds TELEGRAM_MAX_ATTACHMENT_BYTES")
            file_id = msg.document.get("file_id")
            if file_id:
                info = await self.telegram.get_file(file_id)
                remote_path = info.get("file_path")
                if remote_path:
                    raw = await self.telegram.download_file(remote_path)
                    if len(raw) > self.config.telegram_max_attachment_bytes:
                        raise ValueError("Telegram document exceeds TELEGRAM_MAX_ATTACHMENT_BYTES")
                    original = msg.document.get("file_name") or Path(remote_path).name
                    filename = _safe_filename(str(original))
                    inbox = self.config.state_dir / "inbox" / str(msg.chat_id)
                    inbox.mkdir(parents=True, exist_ok=True)
                    target = inbox / f"{msg.message_id}-{filename}"
                    target.write_bytes(raw)
                    notes.append(
                        "Telegram document saved locally for this task at: "
                        f"{target}. Inspect it with the available local tools if relevant."
                    )
        return images, "\n".join(notes)
