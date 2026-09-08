from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import BridgeConfig
from .prime_rpc import (
    PrimeAgentOutcome,
    PrimeRpcError,
    PrimeRpcFrameTooLarge,
    PrimeRpcSession,
    _prime_subprocess_env,
)
from .state import ChatSessionRecord, StateStore, cleanup_attachment_inbox, secure_directory
from .telegram_api import IncomingMessage, TelegramClient, parse_update
from .transcript_recovery import build_recovery_capsule, parse_transcript

logger = logging.getLogger(__name__)


OutputHandler = Callable[[int, PrimeAgentOutcome], Awaitable[None]]
RecoveryHandler = Callable[[int, str], Awaitable[None]]

_FAILED_WORKER_RECLAIM_MARKER = "failed worker that could not be safely reclaimed"


def _is_failed_worker_reclaim_error(error: BaseException) -> bool:
    return _FAILED_WORKER_RECLAIM_MARKER in str(error).lower()


def _safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:160] or "attachment.bin"


class PrimeSessionManager:
    def __init__(
        self,
        config: BridgeConfig,
        *,
        output_handler: OutputHandler | None = None,
        recovery_handler: RecoveryHandler | None = None,
    ):
        self.config = config
        self.store = StateStore(config.state_dir / "state.json")
        self.sessions: dict[int, PrimeRpcSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._init_locks: dict[int, asyncio.Lock] = {}
        self._output_handler = output_handler
        self._recovery_handler = recovery_handler
        self._suppress_output_for: set[int] = set()

    def lock_for(self, chat_id: int) -> asyncio.Lock:
        return self._locks.setdefault(chat_id, asyncio.Lock())

    def _init_lock_for(self, chat_id: int) -> asyncio.Lock:
        return self._init_locks.setdefault(chat_id, asyncio.Lock())

    def _attach_output_handler(self, chat_id: int, session: PrimeRpcSession) -> None:
        if not self._output_handler:
            return

        async def on_output(outcome: PrimeAgentOutcome) -> None:
            assert self._output_handler is not None
            if chat_id in self._suppress_output_for:
                return
            await self._output_handler(chat_id, outcome)

        session.add_agent_end_listener(on_output)

    async def _start_session(
        self,
        chat_id: int,
        *,
        resume: str | None,
    ) -> PrimeRpcSession:
        session = PrimeRpcSession(self.config, resume_session=resume, chat_id=chat_id)
        self._attach_output_handler(chat_id, session)
        await session.start()
        return session

    async def _notify_recovery(self, chat_id: int, message: str) -> None:
        if not self._recovery_handler:
            return
        try:
            await self._recovery_handler(chat_id, message)
        except Exception:
            logger.exception("Failed to send Prime session recovery notice for chat %s", chat_id)

    async def _retry_failed_worker(self, session_selector: str) -> bool:
        """Ask Prime's daemon supervisor to recover the existing worker."""
        try:
            process = await asyncio.create_subprocess_exec(
                self.config.prime_agent_bin,
                "daemon",
                "retry",
                session_selector,
                cwd=str(self.config.prime_workdir),
                env=_prime_subprocess_env(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except (FileNotFoundError, OSError) as exc:
            logger.warning("Prime daemon retry could not start: %s", type(exc).__name__)
            return False
        try:
            await asyncio.wait_for(process.wait(), timeout=30)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()
            return False
        return process.returncode == 0

    async def _recover_failed_worker(
        self,
        chat_id: int,
        *,
        old: PrimeRpcSession | None,
    ) -> PrimeRpcSession:
        record = self.store.get(chat_id)
        session_file = old.resume_session if old is not None else (record.session_file if record else None)
        session_selector = record.session_id if record and record.session_id else session_file
        if not session_selector:
            raise PrimeRpcError("Cannot recover failed Prime worker without a session identifier")

        logger.warning(
            "Prime session for Telegram chat %s is bound to an unreclaimable failed worker; "
            "attempting daemon recovery before creating a fresh session",
            chat_id,
        )
        if await self._retry_failed_worker(session_selector):
            try:
                resumed = await self._start_session(chat_id, resume=session_file)
            except PrimeRpcError:
                logger.warning("Prime daemon retry completed but resume failed for chat %s", chat_id)
            else:
                await self.persist(chat_id, resumed)
                self.sessions[chat_id] = resumed
                if old is not None and old is not resumed:
                    await old.close()
                await self._notify_recovery(
                    chat_id,
                    "Prime session recovery succeeded; the previous session was restored.",
                )
                return resumed

        logger.warning(
            "Prime daemon recovery failed for Telegram chat %s; starting a fresh session "
            "without deleting the old session file",
            chat_id,
        )
        fresh = await self._start_session(chat_id, resume=None)
        await fresh.set_session_name(f"telegram-{chat_id}")
        await self.persist(chat_id, fresh)
        self.sessions[chat_id] = fresh
        if old is not None and old is not fresh:
            await old.close()
        recovered_history = False
        if self.config.transcript_recovery_enabled and session_file and Path(session_file).is_file():
            try:
                parsed = parse_transcript(
                    Path(session_file),
                    max_file_bytes=self.config.transcript_recovery_max_file_bytes,
                    max_line_bytes=self.config.transcript_recovery_max_line_bytes,
                )
                if parsed.confidence in {"high", "medium"} and parsed.turns:
                    capsule = build_recovery_capsule(
                        parsed,
                        max_turns=self.config.transcript_recovery_max_turns,
                        max_chars=self.config.transcript_recovery_max_chars,
                    )
                    self._suppress_output_for.add(chat_id)
                    try:
                        await fresh.ask(capsule, timeout=600)
                    finally:
                        self._suppress_output_for.discard(chat_id)
                    current = self.store.get(chat_id)
                    if current is not None:
                        current.recovery_mode = "transcript"
                        current.recovered_from_session_file = str(session_file)
                        current.recovery_capsule_hash = hashlib.sha256(
                            capsule.encode("utf-8")
                        ).hexdigest()
                        current.recovery_timestamp = datetime.now(UTC).isoformat()
                        self.store.set(current)
                    recovered_history = True
            except Exception:
                logger.warning("Transcript recovery failed for Telegram chat %s", chat_id, exc_info=True)
        await self._notify_recovery(
            chat_id,
            (
                "The previous Prime runtime could not be restored, but its conversation history "
                "was recovered into a new session. Runtime-only state was not recovered."
                if recovered_history
                else "The previous Prime worker could not be safely reclaimed, so the bridge started "
                "a fresh Prime session. The old session file was left untouched."
            ),
        )
        return fresh

    async def get(
        self,
        chat_id: int,
        *,
        recover_failed_worker: bool = True,
    ) -> PrimeRpcSession:
        existing = self.sessions.get(chat_id)
        if existing and getattr(existing, "transport_alive", True):
            return existing

        # Separate initialization lock avoids deadlocking callers that already
        # hold the per-chat operation lock while still preventing two first
        # messages from creating competing Prime sessions.
        async with self._init_lock_for(chat_id):
            existing = self.sessions.get(chat_id)
            if existing and getattr(existing, "transport_alive", True):
                return existing

            if isinstance(existing, PrimeRpcSession):
                try:
                    await existing.start()
                    await self.persist(chat_id, existing)
                    return existing
                except PrimeRpcError as exc:
                    if recover_failed_worker and _is_failed_worker_reclaim_error(exc):
                        return await self._recover_failed_worker(chat_id, old=existing)
                    raise

            record = self.store.get(chat_id)
            resume = record.session_file if record else None
            recovered = False

            # State stores Prime's concrete sessionFile path. If it no longer
            # exists, recovery is unambiguous: there is nothing left to resume.
            # Other startup failures (auth, provider outage, incompatible Prime)
            # are propagated instead of destroying a valid mapping. The one
            # narrowly recognized exception is Prime's unreclaimable failed-worker
            # state, where keeping the mapping only guarantees repeated failure.
            if resume and not Path(resume).exists():
                logger.warning(
                    "Stored Prime session file for Telegram chat %s is missing; starting a fresh session",
                    chat_id,
                )
                resume = None
                record = None
                recovered = True

            try:
                session = await self._start_session(chat_id, resume=resume)
            except PrimeRpcError as exc:
                if resume and recover_failed_worker and _is_failed_worker_reclaim_error(exc):
                    return await self._recover_failed_worker(chat_id, old=None)
                raise
            self.sessions[chat_id] = session
            if not record or recovered:
                await session.set_session_name(f"telegram-{chat_id}")
            await self.persist(chat_id, session)
            return session

    async def persist(self, chat_id: int, session: PrimeRpcSession) -> None:
        state = await session.get_state()
        session_file = state.get("sessionFile")
        if not session_file:
            raise PrimeRpcError("Prime RPC state did not expose sessionFile; cannot persist Telegram mapping")
        session.resume_session = str(session_file)
        self.store.set(
            ChatSessionRecord(
                chat_id=chat_id,
                session_file=str(session_file),
                session_id=state.get("sessionId"),
                session_name=state.get("sessionName"),
            )
        )

    async def new(self, chat_id: int) -> tuple[bool, dict[str, Any]]:
        session: PrimeRpcSession | None = None
        try:
            session = await self.get(chat_id, recover_failed_worker=False)
            cancelled, state = await session.new_session()
        except Exception:
            # /new is an explicit request to abandon the old conversation. If
            # a mapped session is corrupt/unresumable, prove that a fresh Prime
            # session can start before replacing the persisted map.
            if self.store.get(chat_id) is None:
                raise
            logger.warning(
                "Existing Prime session for Telegram chat %s cannot be opened; "
                "/new will recover with a fresh session",
                chat_id,
                exc_info=True,
            )
            fresh = await self._start_session(chat_id, resume=None)
            old = self.sessions.get(chat_id)
            self.sessions[chat_id] = fresh
            await fresh.set_session_name(f"telegram-{chat_id}")
            await self.persist(chat_id, fresh)
            if old is not None and old is not fresh:
                await old.close()
            return False, await fresh.get_state()

        if cancelled:
            await self.persist(chat_id, session)
            return True, state
        await session.set_session_name(f"telegram-{chat_id}")
        await self.persist(chat_id, session)
        return False, state

    async def close(self) -> None:
        await asyncio.gather(*(session.close() for session in self.sessions.values()), return_exceptions=True)
        self.sessions.clear()


class TelegramPrimeBridge:
    def __init__(self, config: BridgeConfig):
        self.config = config
        self.telegram = TelegramClient(config.telegram_bot_token)
        self.prime = PrimeSessionManager(
            config,
            output_handler=self._on_prime_output,
            recovery_handler=self._on_session_recovery,
        )
        self._stopping = asyncio.Event()
        self._update_tasks: set[asyncio.Task[Any]] = set()
        self._cleanup_task: asyncio.Task[None] | None = None

    def authorized(self, msg: IncomingMessage) -> bool:
        if msg.user_id not in self.config.telegram_allowed_user_ids:
            return False
        if self.config.telegram_allowed_chat_ids and msg.chat_id not in self.config.telegram_allowed_chat_ids:
            return False
        return True

    async def _on_prime_output(self, chat_id: int, outcome: PrimeAgentOutcome) -> None:
        """Forward Prime runs that were not synchronously awaited by a Telegram prompt.

        This is essential for RLM child -> parent messages, scheduled/follow-up
        work, and other daemon-owned continuations that start a later parent run.
        """
        if outcome.error:
            await self.telegram.send_message(chat_id, f"Prime Agent error: {outcome.error}")
        elif outcome.text:
            await self.telegram.send_message(chat_id, outcome.text)

    async def _on_session_recovery(self, chat_id: int, message: str) -> None:
        await self.telegram.send_message(chat_id, f"Prime session recovery: {message}")

    async def _cleanup_attachments_once(self) -> None:
        inbox = self.config.state_dir / "inbox"
        try:
            deleted, removed_dirs = await asyncio.to_thread(
                cleanup_attachment_inbox,
                inbox,
                self.config.telegram_attachment_retention_hours,
            )
            if deleted or removed_dirs:
                logger.info(
                    "Attachment retention cleanup removed %s file(s) and %s empty directories",
                    deleted,
                    removed_dirs,
                )
        except Exception:
            # Retention is hygiene, not a reason to take the control plane down.
            logger.exception("Attachment retention cleanup failed; bridge will continue")

    async def _attachment_cleanup_loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=3600)
                break
            except TimeoutError:
                await self._cleanup_attachments_once()

    @staticmethod
    def _poll_offset(
        in_flight: dict[int, asyncio.Task[Any]],
        max_seen: int | None,
    ) -> int | None:
        if in_flight:
            return min(in_flight)
        return max_seen + 1 if max_seen is not None else None

    async def run(self) -> None:
        secure_directory(self.config.state_dir)
        secure_directory(self.config.prime_session_dir)
        if not self.config.prime_workdir.exists():
            raise FileNotFoundError(f"PRIME_WORKDIR does not exist: {self.config.prime_workdir}")
        if self.config.bootstrap_only:
            logger.warning(
                "No TELEGRAM_ALLOWED_USER_IDS configured. Bootstrap-only mode: "
                "/id works, agent access is denied."
            )

        await self._cleanup_attachments_once()
        self._cleanup_task = asyncio.create_task(
            self._attachment_cleanup_loop(), name="attachment-retention"
        )

        in_flight: dict[int, asyncio.Task[Any]] = {}
        handled_unacked: set[int] = set()
        max_seen: int | None = None

        def mark_done(update_id: int, task: asyncio.Task[Any]) -> None:
            in_flight.pop(update_id, None)
            handled_unacked.add(update_id)
            self._update_tasks.discard(task)
            if task.cancelled():
                return
            try:
                task.result()
            except Exception:
                logger.exception("Telegram update task %s failed outside handler recovery", update_id)

        try:
            while not self._stopping.is_set():
                offset = self._poll_offset(in_flight, max_seen)
                if offset is not None:
                    handled_unacked = {update_id for update_id in handled_unacked if update_id >= offset}

                try:
                    updates = await self.telegram.get_updates(
                        offset=offset,
                        timeout=self.config.telegram_poll_timeout,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Telegram polling failed; retrying")
                    await asyncio.sleep(2)
                    continue

                scheduled_new = False
                for update in updates:
                    try:
                        update_id = int(update.get("update_id", 0))
                    except (TypeError, ValueError):
                        continue
                    max_seen = update_id if max_seen is None else max(max_seen, update_id)
                    if update_id in in_flight or update_id in handled_unacked:
                        continue

                    msg = parse_update(update)
                    if not msg:
                        handled_unacked.add(update_id)
                        continue

                    task = asyncio.create_task(self.handle_message(msg), name=f"telegram-{msg.update_id}")
                    in_flight[update_id] = task
                    self._update_tasks.add(task)
                    task.add_done_callback(lambda done, uid=update_id: mark_done(uid, done))
                    scheduled_new = True

                # While a long Prime turn is running Telegram will return its
                # unacknowledged update immediately. Avoid a hot poll loop but
                # keep polling often enough to receive /stop or /steer updates.
                if not scheduled_new and in_flight:
                    await asyncio.wait(in_flight.values(), timeout=0.5, return_when=asyncio.FIRST_COMPLETED)
        finally:
            await self.close()

    async def close(self) -> None:
        self._stopping.set()
        if self._cleanup_task:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None
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
                "Access denied. Send /id, add your user_id to TELEGRAM_ALLOWED_USER_IDS, "
                "then restart the bridge.",
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
                    "Prime Agent\n"
                    f"session={state.get('sessionId', 'unknown')}\n"
                    f"model={model.get('provider', '?')}/{model.get('id', '?')}\n"
                    f"thinking={state.get('thinkingLevel', '?')}\n"
                    f"streaming={state.get('isStreaming', False)}"
                )
                await self.telegram.send_message(msg.chat_id, text, reply_to_message_id=msg.message_id)
                return
            if command == "/new":
                async with self.prime.lock_for(msg.chat_id):
                    cancelled, _state = await self.prime.new(msg.chat_id)
                text = "Prime cancelled the session switch." if cancelled else "Started a new Prime session."
                await self.telegram.send_message(msg.chat_id, text)
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
                async with self.prime.lock_for(msg.chat_id):
                    session = await self.prime.get(msg.chat_id)
                    result = await session.compact(arg.strip() or None)
                    await self.prime.persist(msg.chat_id, session)
                summary = result.get("summary") if isinstance(result, dict) else None
                await self.telegram.send_message(msg.chat_id, summary or "Context compacted.")
                return
            if command == "/refine":
                async with self.prime.lock_for(msg.chat_id):
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
                # Lifecycle-changing request/response work is serialized per
                # chat. /stop, /steer and /followup intentionally bypass this
                # lock so they remain usable while a run is active.
                async with self.prime.lock_for(msg.chat_id):
                    session = await self.prime.get(msg.chat_id)
                    answer = await session.ask(prompt, images=images or None)
                    await self.prime.persist(msg.chat_id, session)
            finally:
                stop_typing.set()
                await asyncio.gather(typing_task, return_exceptions=True)
            await self.telegram.send_message(msg.chat_id, answer, reply_to_message_id=msg.message_id)
        except PrimeRpcFrameTooLarge as exc:
            logger.exception("Prime RPC frame too large while handling Telegram message %s", msg.message_id)
            await self.telegram.send_message(
                msg.chat_id,
                f"Prime returned an RPC frame larger than {exc.max_line_bytes} bytes. "
                "The original request was not retried. Send another message to let the bridge "
                "attempt safe session recovery, or use /new to force a fresh session.",
                reply_to_message_id=msg.message_id,
            )
        except Exception:
            logger.exception("Failed handling Telegram message %s", msg.message_id)
            await self.telegram.send_message(
                msg.chat_id,
                "Bridge error. Check bridge logs for details.",
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
        max_bytes = self.config.telegram_max_attachment_bytes

        if msg.photo_file_id:
            info = await self.telegram.get_file(msg.photo_file_id)
            file_path = info.get("file_path")
            if file_path:
                raw = await self.telegram.download_file(str(file_path), max_bytes=max_bytes)
                mime = mimetypes.guess_type(str(file_path))[0] or "image/jpeg"
                images.append(
                    {
                        "type": "image",
                        "data": base64.b64encode(raw).decode("ascii"),
                        "mimeType": mime,
                    }
                )

        if msg.document:
            declared_size = int(msg.document.get("file_size") or 0)
            if declared_size > max_bytes:
                raise ValueError("Telegram document exceeds TELEGRAM_MAX_ATTACHMENT_BYTES")
            file_id = msg.document.get("file_id")
            if file_id:
                info = await self.telegram.get_file(str(file_id))
                remote_path = info.get("file_path")
                if remote_path:
                    raw = await self.telegram.download_file(str(remote_path), max_bytes=max_bytes)
                    original = msg.document.get("file_name") or Path(str(remote_path)).name
                    filename = _safe_filename(str(original))
                    inbox = self.config.state_dir / "inbox" / str(msg.chat_id)
                    secure_directory(inbox)
                    target = inbox / f"{msg.message_id}-{filename}"
                    target.write_bytes(raw)
                    try:
                        target.chmod(0o600)
                    except OSError:
                        pass
                    notes.append(
                        "Telegram document saved locally for this task at: "
                        f"{target}. Inspect it with the available local tools if relevant."
                    )
        return images, "\n".join(notes)
