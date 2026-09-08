from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .config import BridgeConfig
from .state import secure_directory

logger = logging.getLogger(__name__)


class PrimeRpcError(RuntimeError):
    pass


class PrimeRpcFrameTooLarge(PrimeRpcError):
    """Raised when one JSONL frame exceeds the configured transport bound."""

    def __init__(self, max_line_bytes: int):
        self.max_line_bytes = max_line_bytes
        super().__init__(
            f"Prime RPC JSONL frame exceeded PRIME_RPC_MAX_LINE_BYTES={max_line_bytes}; "
            "the original request was not retried"
        )


@dataclass(frozen=True, slots=True)
class PrimeAgentOutcome:
    text: str | None = None
    error: str | None = None


AgentEndListener = Callable[[PrimeAgentOutcome], Awaitable[None] | None]


def _prime_subprocess_env(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Build Prime's environment without bridge-owned Telegram credentials.

    Prime provider/API credentials are intentionally preserved. This is secret
    minimization, not a security sandbox: a same-UID Prime process may still be
    able to inspect the host through other OS mechanisms.
    """
    base = os.environ if source is None else source
    return {
        key: value
        for key, value in base.items()
        if not key.startswith("TELEGRAM_") and not key.startswith("BRIDGE_")
    }


def _assistant_outcome_from_agent_end(event: dict[str, Any]) -> PrimeAgentOutcome:
    messages = event.get("messages")
    if not isinstance(messages, list):
        return PrimeAgentOutcome()

    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        error = message.get("errorMessage")
        stop_reason = message.get("stopReason")
        if error and stop_reason in {"error", "aborted"}:
            return PrimeAgentOutcome(error=str(error))

        content = message.get("content")
        if isinstance(content, list):
            text_parts = [
                str(part.get("text"))
                for part in content
                if isinstance(part, dict) and part.get("type") == "text" and part.get("text") is not None
            ]
            text = "".join(text_parts)
            if text:
                return PrimeAgentOutcome(text=text)
        return PrimeAgentOutcome(error=str(error)) if error else PrimeAgentOutcome()
    return PrimeAgentOutcome()


class PrimeRpcSession:
    """One long-lived Prime Agent RPC client mapped to one Telegram chat."""

    def __init__(self, config: BridgeConfig, *, resume_session: str | None = None, chat_id: int):
        self.config = config
        self.resume_session = resume_session
        self.chat_id = chat_id
        self.process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[
            str, tuple[asyncio.subprocess.Process, asyncio.Future[dict[str, Any]]]
        ] = {}
        self._request_id = 0
        self._agent_end_waiters: list[
            tuple[asyncio.subprocess.Process, asyncio.Future[dict[str, Any]]]
        ] = []
        self._agent_end_listeners: list[AgentEndListener] = []
        self._listener_tasks: set[asyncio.Task[Any]] = set()
        self._stderr_tail: deque[str] = deque(maxlen=100)
        self.is_streaming = False
        self._transport_closing = False
        self._start_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    @property
    def transport_alive(self) -> bool:
        return bool(
            self.process
            and self.process.returncode is None
            and not self._transport_closing
            and self._stdout_task
            and not self._stdout_task.done()
        )

    def add_agent_end_listener(self, listener: AgentEndListener) -> Callable[[], None]:
        self._agent_end_listeners.append(listener)

        def remove() -> None:
            try:
                self._agent_end_listeners.remove(listener)
            except ValueError:
                pass

        return remove

    async def start(self) -> None:
        async with self._start_lock:
            if self.transport_alive:
                return
            if self.process and self.process.returncode is None:
                stdout_task = self._stdout_task
                if (
                    self._transport_closing
                    and stdout_task
                    and stdout_task is not asyncio.current_task()
                ):
                    await asyncio.gather(stdout_task, return_exceptions=True)
                if self.process and self.process.returncode is None:
                    await self._close_process(self.process)

            secure_directory(self.config.prime_session_dir)
            args = [
                self.config.prime_agent_bin,
                "--mode",
                "rpc",
                "--session-dir",
                str(self.config.prime_session_dir),
            ]
            if self.resume_session:
                args += ["--resume", self.resume_session]
            if self.config.prime_provider:
                args += ["--provider", self.config.prime_provider]
            if self.config.prime_model:
                args += ["--model", self.config.prime_model]

            logger.info("Starting Prime RPC session for Telegram chat %s", self.chat_id)
            try:
                process = await asyncio.create_subprocess_exec(
                    *args,
                    cwd=str(self.config.prime_workdir),
                    env=_prime_subprocess_env(),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    limit=self.config.prime_rpc_max_line_bytes,
                )
            except FileNotFoundError as exc:
                raise PrimeRpcError(
                    f"Prime Agent executable not found: {self.config.prime_agent_bin!r}. "
                    "Set PRIME_AGENT_BIN if it is not on PATH."
                ) from exc

            self.process = process
            self._transport_closing = False
            assert process.stdout and process.stderr
            self._stdout_task = asyncio.create_task(
                self._read_stdout(process), name=f"prime-rpc-out-{self.chat_id}"
            )
            self._stderr_task = asyncio.create_task(
                self._read_stderr(process), name=f"prime-rpc-err-{self.chat_id}"
            )

            # Prove the client is usable instead of relying on an arbitrary sleep.
            try:
                state = await self._get_state_on_process(process, timeout=30)
                self._update_resume_from_state(state)
                if self.config.prime_thinking:
                    await self._send_on_process(
                        process,
                        {"type": "set_thinking_level", "level": self.config.prime_thinking},
                    )
            except Exception:
                await self._close_process(process)
                raise

    @staticmethod
    async def _terminate_process(process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=3)
        except TimeoutError:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.wait()

    async def _close_process(self, process: asyncio.subprocess.Process) -> None:
        if self.process is process:
            self.process = None
        await self._terminate_process(process)

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process:
            await self._close_process(process)

        tasks = [task for task in (self._stdout_task, self._stderr_task) if task]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._stdout_task = None
        self._stderr_task = None

        error = PrimeRpcError("Prime RPC session closed")
        self._fail_pending_for_process(None, error)
        self._fail_waiters_for_process(None, error)

        for task in list(self._listener_tasks):
            task.cancel()
        if self._listener_tasks:
            await asyncio.gather(*self._listener_tasks, return_exceptions=True)
        self._listener_tasks.clear()

    def _fail_pending_for_process(
        self,
        process: asyncio.subprocess.Process | None,
        error: Exception,
    ) -> None:
        doomed = [
            request_id
            for request_id, (owner, _future) in self._pending.items()
            if process is None or owner is process
        ]
        for request_id in doomed:
            _owner, future = self._pending.pop(request_id)
            if not future.done():
                future.set_exception(error)

    def _fail_waiters_for_process(
        self,
        process: asyncio.subprocess.Process | None,
        error: Exception,
    ) -> None:
        keep: list[tuple[asyncio.subprocess.Process, asyncio.Future[dict[str, Any]]]] = []
        for owner, future in self._agent_end_waiters:
            if process is None or owner is process:
                if not future.done():
                    future.set_exception(error)
            else:
                keep.append((owner, future))
        self._agent_end_waiters = keep

    async def _read_stdout(self, process: asyncio.subprocess.Process) -> None:
        assert process.stdout
        transport_error: PrimeRpcError | None = None
        try:
            while True:
                try:
                    line = await process.stdout.readline()
                except ValueError:
                    transport_error = PrimeRpcFrameTooLarge(self.config.prime_rpc_max_line_bytes)
                    logger.error(
                        "Prime RPC stdout frame exceeded %s bytes for Telegram chat %s; "
                        "closing this client without replaying work",
                        self.config.prime_rpc_max_line_bytes,
                        self.chat_id,
                    )
                    break
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8").rstrip("\r\n"))
                except Exception:
                    logger.warning("Ignoring non-JSON Prime RPC stdout line: %r", line[:500])
                    continue
                if not isinstance(payload, dict):
                    continue

                request_id = payload.get("id")
                pending = self._pending.get(str(request_id)) if request_id is not None else None
                if payload.get("type") == "response" and pending and pending[0] is process:
                    _owner, future = self._pending.pop(str(request_id))
                    if not future.done():
                        future.set_result(payload)
                    continue

                event_type = payload.get("type")
                if event_type == "agent_start":
                    if self.process is process:
                        self.is_streaming = True
                elif event_type == "agent_end":
                    if self.process is process:
                        self.is_streaming = False
                    matched: asyncio.Future[dict[str, Any]] | None = None
                    keep: list[
                        tuple[asyncio.subprocess.Process, asyncio.Future[dict[str, Any]]]
                    ] = []
                    for owner, future in self._agent_end_waiters:
                        if owner is process and matched is None:
                            matched = future
                        else:
                            keep.append((owner, future))
                    self._agent_end_waiters = keep
                    if matched is not None and not matched.done():
                        matched.set_result(payload)
                    if matched is None:
                        self._publish_autonomous_agent_end(payload)
                elif event_type in {"error", "agent_error"}:
                    logger.error("Prime RPC event error for chat %s: %s", self.chat_id, payload)
        finally:
            if self.process is process:
                self._transport_closing = True
            code = process.returncode
            err = transport_error or PrimeRpcError(
                f"Prime RPC stdout closed (exit={code}). stderr: {self.stderr_tail()}"
            )
            self._fail_pending_for_process(process, err)
            self._fail_waiters_for_process(process, err)
            if self.process is process:
                self.is_streaming = False
                # EOF is terminal for the JSONL transport. Reap the child before
                # clearing self.process so a concurrent close() cannot cancel
                # this reader while it is still terminating the subprocess.
                await self._terminate_process(process)
                if self.process is process:
                    self.process = None

    def _publish_autonomous_agent_end(self, event: dict[str, Any]) -> None:
        outcome = _assistant_outcome_from_agent_end(event)
        if not outcome.text and not outcome.error:
            return
        for listener in tuple(self._agent_end_listeners):
            try:
                result = listener(outcome)
            except Exception:
                logger.exception("Prime autonomous-output listener failed synchronously")
                continue
            if inspect.isawaitable(result):
                task = asyncio.create_task(result, name=f"prime-output-{self.chat_id}")
                self._listener_tasks.add(task)
                task.add_done_callback(self._on_listener_task_done)

    def _on_listener_task_done(self, task: asyncio.Task[Any]) -> None:
        self._listener_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logger.exception("Prime autonomous-output listener failed")

    async def _read_stderr(self, process: asyncio.subprocess.Process) -> None:
        assert process.stderr
        while True:
            try:
                line = await process.stderr.readline()
            except ValueError:
                marker = (
                    f"[Prime stderr frame exceeded {self.config.prime_rpc_max_line_bytes} "
                    "bytes; discarded]"
                )
                self._stderr_tail.append(marker)
                logger.warning("Prime[%s] %s", self.chat_id, marker)
                continue
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            self._stderr_tail.append(text)
            logger.debug("Prime[%s] %s", self.chat_id, text)

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_tail)

    async def _send_on_process(
        self,
        process: asyncio.subprocess.Process,
        command: dict[str, Any],
        *,
        timeout: float = 30,
    ) -> dict[str, Any]:
        if process.returncode is not None or not process.stdin:
            raise PrimeRpcError(f"Prime RPC process is not available (exit={process.returncode})")

        self._request_id += 1
        request_id = f"tg-{self.chat_id}-{self._request_id}"
        payload = {"id": request_id, **command}
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = (process, future)
        try:
            async with self._write_lock:
                if process.returncode is not None or not process.stdin:
                    raise PrimeRpcError(f"Prime RPC process exited before write (exit={process.returncode})")
                process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                await process.stdin.drain()
            response = await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            pending = self._pending.get(request_id)
            if pending and pending[1] is future:
                self._pending.pop(request_id, None)
            raise
        if not response.get("success", False):
            raise PrimeRpcError(str(response.get("error") or response))
        return response

    async def _send(self, command: dict[str, Any], *, timeout: float = 30) -> dict[str, Any]:
        await self.start_if_needed()
        process = self.process
        if not process:
            raise PrimeRpcError("Prime RPC process failed to start")
        return await self._send_on_process(process, command, timeout=timeout)

    async def start_if_needed(self) -> None:
        if not self.transport_alive:
            await self.start()

    @staticmethod
    def _data(response: dict[str, Any]) -> Any:
        return response.get("data")

    def _update_resume_from_state(self, state: dict[str, Any]) -> None:
        session_file = state.get("sessionFile") if isinstance(state, dict) else None
        if session_file:
            self.resume_session = str(session_file)

    async def _get_state_on_process(
        self, process: asyncio.subprocess.Process, *, timeout: float = 30
    ) -> dict[str, Any]:
        data = self._data(await self._send_on_process(process, {"type": "get_state"}, timeout=timeout))
        if not isinstance(data, dict):
            raise PrimeRpcError("Prime RPC get_state returned malformed data")
        return data

    async def get_state(self, *, timeout: float = 30) -> dict[str, Any]:
        await self.start_if_needed()
        process = self.process
        if not process:
            raise PrimeRpcError("Prime RPC process failed to start")
        state = await self._get_state_on_process(process, timeout=timeout)
        self._update_resume_from_state(state)
        return state

    async def set_thinking_level(self, level: str) -> None:
        await self._send({"type": "set_thinking_level", "level": level})

    async def set_session_name(self, name: str) -> None:
        await self._send({"type": "set_session_name", "name": name})

    async def new_session(self) -> tuple[bool, dict[str, Any]]:
        response = await self._send({"type": "new_session"})
        data = self._data(response)
        cancelled = bool(data.get("cancelled")) if isinstance(data, dict) else False
        state = await self.get_state()
        if not cancelled:
            self._update_resume_from_state(state)
        return cancelled, state

    async def abort(self) -> None:
        await self._send({"type": "abort"})

    async def steer(self, message: str) -> None:
        await self._send({"type": "steer", "message": message})

    async def follow_up(self, message: str) -> None:
        await self._send({"type": "follow_up", "message": message})

    async def compact(self, instructions: str | None = None) -> dict[str, Any]:
        command: dict[str, Any] = {"type": "compact"}
        if instructions:
            command["customInstructions"] = instructions
        data = self._data(await self._send(command, timeout=600))
        return data if isinstance(data, dict) else {}

    async def refine(self, instructions: str | None = None) -> dict[str, Any]:
        command: dict[str, Any] = {"type": "refine"}
        if instructions:
            command["instructions"] = instructions
        data = self._data(await self._send(command, timeout=900))
        return data if isinstance(data, dict) else {}

    async def get_last_assistant_text(self) -> str | None:
        data = self._data(await self._send({"type": "get_last_assistant_text"}))
        return data.get("text") if isinstance(data, dict) else None

    async def ask(
        self,
        message: str,
        images: list[dict[str, str]] | None = None,
        timeout: float = 3600,
    ) -> str:
        await self.start_if_needed()
        process = self.process
        if not process:
            raise PrimeRpcError("Prime RPC process failed to start")

        end_future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._agent_end_waiters.append((process, end_future))
        command: dict[str, Any] = {"type": "prompt", "message": message}
        if images:
            command["images"] = images
        if self.is_streaming:
            command["streamingBehavior"] = "steer"

        try:
            # Prompt acceptance is intentionally never retried across a client
            # crash: Prime may already have admitted the work in its daemon.
            await self._send_on_process(process, command)
            event = await asyncio.wait_for(end_future, timeout=timeout)
        except Exception:
            self._agent_end_waiters = [
                (owner, future)
                for owner, future in self._agent_end_waiters
                if future is not end_future
            ]
            raise

        outcome = _assistant_outcome_from_agent_end(event)
        if outcome.error:
            raise PrimeRpcError(outcome.error)
        if outcome.text:
            return outcome.text

        # Compatibility fallback for older/fake RPC emitters that omit the
        # `messages` payload on agent_end. Never used for autonomous events,
        # where falling back could resend a stale prior answer.
        return (await self.get_last_assistant_text()) or "(Prime Agent completed without a textual reply.)"
