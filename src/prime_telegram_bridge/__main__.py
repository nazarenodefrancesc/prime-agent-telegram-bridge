from __future__ import annotations

import asyncio
import logging
import signal
import sys

from .bridge import TelegramPrimeBridge
from .config import ConfigError, load_config


async def _run() -> None:
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bridge = TelegramPrimeBridge(config)
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, bridge._stopping.set)  # noqa: SLF001 - process boundary wiring
        except NotImplementedError:
            pass
    await bridge.run()


def main() -> None:
    try:
        asyncio.run(_run())
    except (ConfigError, FileNotFoundError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
