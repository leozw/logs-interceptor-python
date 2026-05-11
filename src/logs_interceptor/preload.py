from __future__ import annotations

import atexit
import os
import signal
import sys

_LOGS_INTERCEPTOR_PRELOADED = False


def _write(stream: object, prefix: str, *args: object) -> None:
    message = " ".join(str(arg) for arg in args)
    text = f"{prefix} {message}\n"
    writer = getattr(stream, "write", None)
    flusher = getattr(stream, "flush", None)
    if callable(writer):
        writer(text)
    if callable(flusher):
        flusher()


def _debug(*args: object) -> None:
    if os.getenv("LOGS_DEBUG") == "true" and os.getenv("LOGS_SILENT_ERRORS") != "true":
        _write(sys.stdout, "[logs-interceptor:preload]", *args)


def _error(*args: object) -> None:
    if os.getenv("LOGS_SILENT_ERRORS") != "true":
        _write(sys.stderr, "[logs-interceptor:preload]", *args)


def _install() -> None:
    global _LOGS_INTERCEPTOR_PRELOADED
    if _LOGS_INTERCEPTOR_PRELOADED:
        return

    _LOGS_INTERCEPTOR_PRELOADED = True

    if os.getenv("LOGS_ENABLED") == "false":
        _debug("Disabled by LOGS_ENABLED=false")
        return

    try:
        os.environ["LOGS_AUTO_INIT"] = "true"
        from . import destroy, is_initialized

        if is_initialized():
            _debug("Initialized successfully via auto-init gate")
        else:
            _debug("Auto-init did not run (missing required LOGS_* variables)")

        def _graceful_shutdown(signame: str) -> None:
            _debug(f"Graceful shutdown triggered by {signame}")
            try:
                destroy()
            except Exception as exc:
                _error("Graceful shutdown failed:", exc)

        def _sigterm_handler(_sig: int, _frame: object) -> None:
            _graceful_shutdown("SIGTERM")

        def _sigint_handler(_sig: int, _frame: object) -> None:
            _graceful_shutdown("SIGINT")

        signal.signal(signal.SIGTERM, _sigterm_handler)
        signal.signal(signal.SIGINT, _sigint_handler)
        atexit.register(lambda: _graceful_shutdown("atexit"))
    except Exception as exc:
        _error("Preload failed:", exc)


_install()
