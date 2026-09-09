"""Public SDK data types; no transport or GUI objects cross the boundary."""

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable, Protocol


class PluginError(Exception):
    def __init__(self, kind: str, message: str, *, code: int = -32602, **details):
        super().__init__(message)
        self.kind, self.code, self.details = kind, code, details

    def wire(self):
        return {
            "code": self.code,
            "message": str(self),
            "data": {"kind": self.kind, **self.details},
        }


class CancellationToken:
    def __init__(self):
        self._event = Event()

    @property
    def is_cancelled(self):
        return self._event.is_set()

    def cancel(self):
        self._event.set()

    def raise_if_cancelled(self):
        if self.is_cancelled:
            raise PluginError("canceled", "Task canceled", code=-32005)


@dataclass
class CommandResult:
    data: dict
    view: dict | None = None


@dataclass
class PluginContext:
    plugin_id: str
    version: str
    session_id: str
    locale: str
    data_dir: Path
    cache_dir: Path
    settings: Any
    logger: Any
    host: Any


@dataclass
class InvocationContext:
    task_id: str
    cancellation: CancellationToken
    host: Any
    report_progress: Callable[..., None]


@dataclass(frozen=True)
class CommandDescriptor:
    id: str
    title: str
    description: str
    input_schema: dict
    output_schema: dict
    effects: str
    retry: str
    timeout_ms: int = 30000


@dataclass(frozen=True)
class Descriptor:
    commands: list[CommandDescriptor]


class Plugin(Protocol):
    def activate(self, context: PluginContext) -> None: ...
    def describe(self) -> dict | Descriptor: ...
    def invoke(
        self, command_id: str, arguments: dict, context: InvocationContext
    ) -> CommandResult: ...
    def deactivate(self) -> None: ...
