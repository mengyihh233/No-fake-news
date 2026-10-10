"""Request-local progress: counts describe completed work, never confidence."""
from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar


STAGES = frozenset({"queued", "planning", "searching", "reading", "supplemental_search",
                    "analyzing", "checking", "repairing", "capturing", "complete"})
PROGRESS_CALLBACK: ContextVar[Callable[[dict], None] | None] = ContextVar("research_progress", default=None)


def emit_progress(stage: str, completed: int = 0, total: int | None = None) -> None:
    callback = PROGRESS_CALLBACK.get()
    if callback is None:
        return
    if stage not in STAGES or type(completed) is not int or completed < 0:
        raise ValueError("Invalid internal progress event")
    if total is not None and (type(total) is not int or total < completed):
        raise ValueError("Invalid internal progress count")
    # Only these nonsecret values cross the stream; no topic, URL, or provider text.
    callback({"stage": stage, "completed": completed, "total": total})
