from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from pathlib import Path
from typing import Any

from .config import BridgeConfig

logger = logging.getLogger(__name__)


class PrimeRpcError(RuntimeError):
    pass


class PrimeRpcSession:
    """One long-lived Prime Agent RPC subprocess mapped to one Telegram chat."""

    def __init__(self, config: BridgeConfig, *, resume_session: str | None = None, chat_id: int):
        self.config = config
        self.resume_session = resume_session
        self.chat_id = chat_id
        self.process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._request_id = 0
        self._agent_end_waiters: list[asyncio.Future[None]] = []
        self._stderr_tail: deque[str] = deque(maxlen=100)
        self.is_streaming = False
        self._start_lock = asyncio.Lock()

    async def start(self) -> None:
        async with self._start_lock:
            if self.process and self.process.returncode is None:
                return
            self.config.prime_session_dir.mkdir(parents=True, exist_ok=True)
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
                self.process = await asyncio.create_subprocess_exec(
                    *args,
                    cwd=str(self.config.prime_workdir),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            except FileNotFoundError as exc:
                raise PrimeRpcError(
                    f"Prime Agent executable not found: {self.config.prime_agent_bin!r}. "
                    "Set PRIME_AGENT_BIN if it is not on PATH."
                ) from exc

            assert self.process.stdout and self.process.stderr
            self._stdout_task = asyncio.create_task(self._read_stdout(), name=f"prime-rpc-out-{self.chat_id}")
            self._stderr_task = asyncio.create_task(self._read_stderr(), name=f"prime-rpc-err-{self.chat_id}")

            # Prove the process is usable instead of relying on an arbitrary sleep.
            try:
                await self.get_state(timeout=30)
                if self.config.prime_thinking:
                    await self.set_thinking_level(self.config.prime_thinking)
            except Exception:
                await self.close()
                raise

    async def close(self) -> None:
        process = self.process
        self.process = None
        if process and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=3)
            except TimeoutError:
                process.kill()
                await process.wait()
        for task in (self._stdout_task, self._stderr_task):
            if task:
                task.cancel()
        self._stdout_task = None
        self._stderr_task = None
        error = PrimeRpcError("Prime RPC session closed")
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        self._pending.clear()
        for future in self._agent_end_waiters:
            if not future.done():
                future.set_exception(error)
        self._agent_end_waiters.clear()

    async def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode("utf-8").rstrip("\r\n"))
                except Exception:
                    logger.warning("Ignoring non-JSON Prime RPC stdout line: %r", line[:500])
                    continue
                if payload.get("type") == "response" and payload.get("id") in self._pending:
                    future = self._pending.pop(payload["id"])
                    if not future.done():
                        future.set_result(payload)
                    continue
                event_type = payload.get("type")
                if event_type == "agent_start":
                    self.is_streaming = True
                elif event_type == "agent_end":
                    self.is_streaming = False
                    waiters, self._agent_end_waiters = self._agent_end_waiters, []
                    for future in waiters:
                        if not future.done():
                            future.set_result(None)
                elif event_type in {"error", "agent_error"}:
                    logger.error("Prime RPC event error for chat %s: %s", self.chat_id, payload)
        finally:
            code = self.process.returncode if self.process else None
            err = PrimeRpcError(f"Prime RPC stdout closed (exit={code}). stderr: {self.stderr_tail()}")
            for future in list(self._pending.values()):
                if not future.done():
                    future.set_exception(err)
            self._pending.clear()

    async def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        while True:
            line = await self.process.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip()
            self._stderr_tail.append(text)
            logger.debug("Prime[%s] %s", self.chat_id, text)

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr_tail)

    async def _send(self, command: dict[str, Any], *, timeout: float = 30) -> dict[str, Any]:
        await self.start_if_needed()
        assert self.process and self.process.stdin
        self._request_id += 1
        request_id = f"tg-{self.chat_id}-{self._request_id}"
        payload = {"id": request_id, **command}
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        self.process.stdin.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
        try:
            await self.process.stdin.drain()
            response = await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            self._pending.pop(request_id, None)
            raise
        if not response.get("success", False):
            raise PrimeRpcError(str(response.get("error") or response))
        return response

    async def start_if_needed(self) -> None:
        if not self.process or self.process.returncode is not None:
            await self.start()

    @staticmethod
    def _data(response: dict[str, Any]) -> Any:
        return response.get("data")

    async def get_state(self, *, timeout: float = 30) -> dict[str, Any]:
        return self._data(await self._send_no_start({"type": "get_state"}, timeout=timeout))

    async def _send_no_start(self, command: dict[str, Any], *, timeout: float = 30) -> dict[str, Any]:
        """Send assuming process already exists. Used to avoid recursion during start()."""
        assert self.process and self.process.stdin
        self._request_id += 1
        request_id = f"tg-{self.chat_id}-{self._request_id}"
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        self.process.stdin.write(
            (json.dumps({"id": request_id, **command}, ensure_ascii=False) + "\n").encode("utf-8")
        )
        await self.process.stdin.drain()
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
        except Exception:
            self._pending.pop(request_id, None)
            raise
        if not response.get("success", False):
            raise PrimeRpcError(str(response.get("error") or response))
        return response

    async def set_thinking_level(self, level: str) -> None:
        await self._send({"type": "set_thinking_level", "level": level})

    async def set_session_name(self, name: str) -> None:
        await self._send({"type": "set_session_name", "name": name})

    async def new_session(self) -> dict[str, Any]:
        await self._send({"type": "new_session"})
        return await self.get_state()

    async def abort(self) -> None:
        await self._send({"type": "abort"})

    async def compact(self, instructions: str | None = None) -> dict[str, Any]:
        command: dict[str, Any] = {"type": "compact"}
        if instructions:
            command["customInstructions"] = instructions
        return self._data(await self._send(command, timeout=600))

    async def refine(self, instructions: str | None = None) -> dict[str, Any]:
        command: dict[str, Any] = {"type": "refine"}
        if instructions:
            command["instructions"] = instructions
        return self._data(await self._send(command, timeout=900))

    async def get_last_assistant_text(self) -> str | None:
        data = self._data(await self._send({"type": "get_last_assistant_text"}))
        return data.get("text") if isinstance(data, dict) else None

    async def ask(self, message: str, images: list[dict[str, str]] | None = None, timeout: float = 3600) -> str:
        await self.start_if_needed()
        end_future = asyncio.get_running_loop().create_future()
        self._agent_end_waiters.append(end_future)
        command: dict[str, Any] = {"type": "prompt", "message": message}
        if images:
            command["images"] = images
        # A normal Telegram message received while Prime is already working is a steering message.
        if self.is_streaming:
            command["streamingBehavior"] = "steer"
        try:
            await self._send(command)
            await asyncio.wait_for(end_future, timeout=timeout)
        except Exception:
            if end_future in self._agent_end_waiters:
                self._agent_end_waiters.remove(end_future)
            raise
        return (await self.get_last_assistant_text()) or "(Prime Agent completed without a textual reply.)"
