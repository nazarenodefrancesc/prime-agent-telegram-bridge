# PROGRESS-T009

**Status:** COMPLETE

- Public-repository audit reproduced the Telegram token leak through `httpx` INFO request URL logging.
- Dependency INFO logging is suppressed and formatter-level secret redaction added as defense-in-depth.
- Configurable 24-hour attachment retention added.
- Startup + hourly cleanup implemented with no symlink traversal and non-fatal failure handling.
- Security, operations, README, env example and release metadata updated.
- Regression suite expanded from 32 to 41 tests.
