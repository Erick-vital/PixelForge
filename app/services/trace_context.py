from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_TRACE_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar("pixelforge_trace_context", default=None)


def get_trace_context() -> dict[str, object]:
    """Return a copy of the request/item context for structured logging."""
    return dict(_TRACE_CONTEXT.get() or {})


@contextmanager
def log_context(**fields: object) -> Iterator[None]:
    """Bind safe correlation fields for the current async execution context."""
    current = get_trace_context()
    current.update({key: value for key, value in fields.items() if value is not None})
    token = _TRACE_CONTEXT.set(current)
    try:
        yield
    finally:
        _TRACE_CONTEXT.reset(token)


def trace_details(**fields: Any) -> dict[str, object]:
    """Drop unset values before writing bounded trace event details."""
    return {key: value for key, value in fields.items() if value is not None}
