"""Structured per-agent run logging (one line per agent run; no secrets)."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator, Optional

logger = logging.getLogger("resonanceforge.agents")


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once at LOG_LEVEL."""
    lvl = getattr(logging, str(level or "INFO").upper(), logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=lvl,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
    root.setLevel(lvl)
    logging.getLogger("resonanceforge").setLevel(lvl)


@contextmanager
def agent_timer(assessment_id: Optional[str], agent: str) -> Iterator[None]:
    """Log `assessment_id=... agent=... latency_ms=... ok=...` around an agent call."""
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
