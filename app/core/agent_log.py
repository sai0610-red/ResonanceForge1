"""Structured logging (JSON by default) and per-agent timers. No secrets."""

from __future__ import annotations

import json
import logging
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator, Optional

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

logger = logging.getLogger("resonanceforge.agents")

# Redact obvious secret material if it ever appears in a log message.
_REDACT_PATTERNS = (
    (re.compile(r"gsk_[A-Za-z0-9_-]+"), "gsk_[REDACTED]"),
    (
        re.compile(
            r"(?i)(api[_-]?key|demo[_-]?token|authorization|bearer)([=:\s]+)(\S+)"
        ),
        r"\1\2[REDACTED]",
    ),
)


def redact(text: str) -> str:
    out = text or ""
    for pat, repl in _REDACT_PATTERNS:
        out = pat.sub(repl, out)
    return out


def get_request_id() -> str:
    return request_id_var.get() or "-"


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
                "+00:00", "Z"
            ),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
            "request_id": getattr(record, "request_id", None) or "-",
        }
        if record.exc_info and record.exc_info[0] is not None:
            payload["error"] = record.exc_info[0].__name__
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.msg = redact(str(record.msg))
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id()
        return super().format(record)


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure the resonanceforge logger once. Does not touch the root logger."""
    lvl = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    log = logging.getLogger("resonanceforge")
    log.setLevel(lvl)
    log.propagate = False
    wanted = "json" if (fmt or "json").strip().lower() != "text" else "text"
    current = getattr(log, "_rf_format", None)
    if log.handlers and current == wanted:
        for handler in log.handlers:
            handler.setLevel(lvl)
        return
    for handler in list(log.handlers):
        log.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler()
    handler.setLevel(lvl)
    handler.addFilter(RequestIdFilter())
    if wanted == "text":
        handler.setFormatter(
            TextFormatter(
                "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
            )
        )
    else:
        handler.setFormatter(JsonFormatter())
    log.addHandler(handler)
    log._rf_format = wanted  # type: ignore[attr-defined]


@contextmanager
def agent_timer(assessment_id: Optional[str], agent: str) -> Iterator[None]:
    """Log one JSON-friendly line around an agent call."""
    started = time.perf_counter()
    ok = False
    try:
        yield
        ok = True
    finally:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "assessment_id=%s agent=%s latency_ms=%d ok=%s",
            assessment_id or "-",
            agent,
            latency_ms,
            str(ok).lower(),
        )
