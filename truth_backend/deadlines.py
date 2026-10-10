"""Request deadline shared across queueing and staged research tasks."""
from contextvars import ContextVar


REQUEST_DEADLINE: ContextVar[float | None] = ContextVar("truth_request_deadline", default=None)
