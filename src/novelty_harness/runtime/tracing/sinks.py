import json
import re
from collections.abc import Mapping
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from novelty_harness.runtime.tracing.models import TraceEvent

_APPEND_LOCK = Lock()
_SENSITIVE = (
    "apikey",
    "accesstoken",
    "refreshtoken",
    "authtoken",
    "password",
    "secret",
    "authorization",
    "bearer",
)


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        return redact_mapping(cast(Mapping[str, object], value))
    if isinstance(value, list):
        return [_redact(item) for item in cast(list[object], value)]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in cast(tuple[object, ...], value))
    return value


def _is_sensitive(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(sensitive in normalized for sensitive in _SENSITIVE) or normalized.endswith("token")


def redact_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {
        key: "[REDACTED]" if _is_sensitive(key) else _redact(item) for key, item in value.items()
    }


def _snapshot(event: TraceEvent) -> TraceEvent:
    return TraceEvent.model_validate(redact_mapping(event.model_dump(mode="json")))


class TraceSink(Protocol):
    def emit(self, event: TraceEvent) -> None: ...


class JsonlTraceSink:
    def __init__(self, path: Path) -> None:
        self._path = path

    def emit(self, event: TraceEvent) -> None:
        line = json.dumps(_snapshot(event).model_dump(mode="json"), allow_nan=False)
        with _APPEND_LOCK, self._path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")


class InMemoryTraceSink:
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []
        self._lock = Lock()

    @property
    def events(self) -> tuple[TraceEvent, ...]:
        with self._lock:
            return tuple(event.model_copy(deep=True) for event in self._events)

    def emit(self, event: TraceEvent) -> None:
        snapshot = _snapshot(event)
        with self._lock:
            self._events.append(snapshot)
