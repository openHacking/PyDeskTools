"""Headless public services. The application supplies all GUI capabilities."""

import json
import logging
import re
import shutil
import sys
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from platformdirs import user_data_path
from pydesktools_sdk import CancellationToken, PluginError
from pydesktools_sdk.protocol import descriptor, validate, validate_view

from .plugins import Installer
from .processes import WorkerProcess
from .storage import Artifacts, Store


@dataclass(frozen=True)
class RuntimeConfig:
    app_id: str = "org.pydesk.tools"
    data_namespace: str = "PyDeskTools"
    data_dir: Path | None = None
    python: Path | None = None
    locale: str = "en"


class CloseHandle:
    def __init__(self, close):
        self._close = close

    def close(self):
        callback, self._close = self._close, lambda: None
        callback()


class TaskHandle:
    def __init__(self, plugin_id):
        self.id = uuid.uuid4().hex
        self.plugin_id = plugin_id
        self.cancellation = CancellationToken()
        self.future: Future[Any] = Future()

    def cancel(self):
        self.cancellation.cancel()

    def result(self, timeout=None):
        return self.future.result(timeout=timeout)


class Events:
    def __init__(self):
        self.lock = threading.RLock()
        self.callbacks = set()

    def subscribe(self, callback):
        with self.lock:
            self.callbacks.add(callback)
        return CloseHandle(lambda: self._remove(callback))

    def _remove(self, callback):
        with self.lock:
            self.callbacks.discard(callback)

    def emit(self, event):
        with self.lock:
            callbacks = tuple(self.callbacks)
        for callback in callbacks:
            callback(event)


class ServiceContainer:
    def __init__(self, config, *, platform_adapter=None):
        self.config = config
        self.locale = config.locale
        self.store = Store(
            config.data_dir or user_data_path(config.data_namespace, appauthor=False)
        )
        logs = self.store.root / "logs"
        logs.mkdir(exist_ok=True)
        self.logger = logging.getLogger("pydesktools." + uuid.uuid4().hex)
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(logs / "diagnostics.log", maxBytes=1024 * 1024, backupCount=3)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        self.logger.addHandler(handler)
        self.artifacts = Artifacts(self.store.root / "artifacts" / uuid.uuid4().hex)
        self.platform_adapter = platform_adapter
        self.installer = Installer(self.store, config.python or Path(sys.executable), self.locale)
        self.commands = self
        self.tasks = Events()
        self.executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="pydesk-service")
        self._locks = {}
        self._slots = {}
        self._workers = {}
        self._handles = {}
        self._last_used = {}
        self._state_lock = threading.RLock()
        self._stopping = set()
        self.closed = False
        self._maintenance_stop = threading.Event()
        self._maintenance = threading.Thread(target=self._idle, daemon=True)
        self._maintenance.start()

    def _lock(self, plugin):
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", plugin):
            raise ValueError("Invalid plugin ID")
        with self._state_lock:
            return self._locks.setdefault(plugin, threading.RLock())

    def describe(self, plugin_id, command_id):
        record = self.store.get(plugin_id)
        if not record:
            raise PluginError("not_installed", "Plugin not installed", code=-32002)
        commands = descriptor(record["descriptor"])
        if command_id not in commands:
            raise PluginError("unknown_command", "Command unavailable", code=-32601)
        return commands[command_id]

    def submit(self, plugin_id, command_id, arguments, *, version=None):
        if self.closed:
            raise RuntimeError("Services are closed")
        with self._state_lock:
            record = self.store.get(plugin_id)
            if not record or not record["enabled"] or plugin_id in self._stopping:
                raise PluginError("not_active", "Plugin is disabled or stopping", code=-32002)
            if version is not None and version != record["manifest"]["version"]:
                raise PluginError("incompatible", "Requested version is not installed", code=-32001)
            command = self.describe(plugin_id, command_id)
            validate(arguments, command["input_schema"])
            slot = self._slots.setdefault(plugin_id, threading.BoundedSemaphore(33))
            if not slot.acquire(blocking=False):
                raise PluginError("busy", "Plugin task queue is full", code=-32004)
            task = TaskHandle(plugin_id)
            self._handles[task.id] = task
            self.executor.submit(self._invoke, task, command, arguments, slot)
            return task

    def _worker(self, record):
        plugin = record["id"]
        worker = self._workers.get(plugin)
        if worker is not None and worker.closed:
            raise PluginError(
                "worker_failed", "Plugin failed; disable and enable to restart", code=-32002
            )
        if worker is None:
            with self._state_lock:
                if len([w for w in self._workers.values() if not w.closed]) >= 4:
                    idle = [p for p, w in self._workers.items() if not w.task_id]
                    if not idle:
                        raise PluginError("busy", "All worker slots are busy", code=-32004)
                    self._stop_worker(idle[0])
            worker = WorkerProcess(
                Path(record["path"]) / "venv/bin/python",
                record["manifest"],
                self.store.root / "plugin-data" / plugin,
                self.locale,
                self._host_call,
                self._progress,
            )
            self._workers[plugin] = worker
            descriptor(worker.descriptor)
            self.store.execute(
                "UPDATE plugins SET descriptor=? WHERE id=?",
                (json.dumps(worker.descriptor), plugin),
            )
        return worker

    def _invoke(self, task, command, arguments, slot):
        try:
            with self._lock(task.plugin_id):
                task.cancellation.raise_if_cancelled()
                record = self.store.get(task.plugin_id)
                if not record or not record["enabled"] or task.plugin_id in self._stopping:
                    raise PluginError("not_active", "Plugin unavailable", code=-32002)
                worker = self._worker(record)
                worker.task_id = task.id
                self.tasks.emit(
                    {"type": "started", "task_id": task.id, "session_id": worker.session}
                )
                try:
                    result = worker.call(
                        "plugin.invoke",
                        {"task_id": task.id, "command_id": command["id"], "arguments": arguments},
                        timeout=command.get("timeout_ms", 30000) / 1000,
                        token=task.cancellation,
                    )
                    validate(result["data"], command["output_schema"], "result")
                    validate_view(result.get("view"), descriptor(worker.descriptor))
                    artifact = result["data"].get("artifact_id")
                    if artifact:
                        self.artifacts.acquire(task.plugin_id, artifact, "result:" + task.id)
                        self.artifacts.release(worker.session, artifact)
                finally:
                    worker.task_id = None
                    if "artifact_id" in arguments:
                        self.artifacts.release("input:" + task.plugin_id, arguments["artifact_id"])
                    self._last_used[task.plugin_id] = time.monotonic()
                task.future.set_result(result)
                self.tasks.emit(
                    {
                        "type": "completed",
                        "task_id": task.id,
                        "session_id": worker.session,
                        "result": result,
                    }
                )
        except BaseException as error:
            self.logger.info(
                "task_failed plugin=%s task=%s kind=%s",
                task.plugin_id,
                task.id,
                error.kind if isinstance(error, PluginError) else type(error).__name__,
            )
            if not task.future.done():
                task.future.set_exception(error)
            self.tasks.emit(
                {
                    "type": "failed",
                    "task_id": task.id,
                    "error": error.wire()
                    if isinstance(error, PluginError)
                    else {"message": "Task failed", "data": {"kind": "internal_error"}},
                }
            )
        finally:
            with self._state_lock:
                self._handles.pop(task.id, None)
            slot.release()

    def _progress(self, worker, params):
        if not worker.closed and worker.task_id == params.get("task_id"):
            self.tasks.emit({"type": "progress", "session_id": worker.session, **params})

    def _host_call(self, worker, capability, arguments):
        if self.closed or worker.closed:
            raise PluginError("canceled", "Session closed", code=-32005)
        plugin = worker.manifest["id"]
        if capability == "settings.get":
            return self.store.setting(plugin, arguments["key"], arguments.get("default"))
        if capability == "settings.set":
            self.store.set_setting(plugin, arguments["key"], arguments["value"])
            return None
        if capability == "artifacts.import":
            return self.artifacts.import_file(
                plugin, worker.session, arguments["relative_path"], export_root=worker.export_dir
            )
        if capability == "artifacts.read":
            return self.artifacts.read_copy(plugin, arguments["artifact_id"], worker.import_dir)
        if capability == "artifacts.release":
            self.artifacts.release(worker.session, arguments["artifact_id"])
            return None
        if capability not in worker.manifest["capabilities"]:
            raise PluginError("permission_denied", "Capability is not declared", code=-32003)
        if self.platform_adapter is None or capability not in (
            "dialogs.open_file",
            "dialogs.save_file",
            "clipboard.write",
        ):
            raise PluginError(
                "unsupported_capability", "Capability unavailable in this release", code=-32601
            )
        if not worker.task_id:
            raise PluginError(
                "permission_denied", "Interactive capability requires an active task", code=-32003
            )
        task = self._handles.get(worker.task_id)
        if task is None:
            raise PluginError("canceled", "Task expired", code=-32005)
        return self.platform_adapter.call(
            capability,
            arguments,
            plugin_id=plugin,
            cancellation=task.cancellation,
            artifacts=self.artifacts,
        )

    def import_text(self, plugin_id, text):
        if len(text.encode("utf-8")) > 20 * 1024 * 1024:
            raise PluginError("input_too_large", "Input exceeds 20 MiB")
        import tempfile

        with tempfile.NamedTemporaryFile(dir=self.store.root, delete=False) as stream:
            source = Path(stream.name)
            stream.write(text.encode("utf-8"))
        try:
            return self.artifacts.import_file(plugin_id, "input:" + plugin_id, source)
        finally:
            source.unlink(missing_ok=True)

    def install(self, bundle, **kwargs):
        from .plugins import inspect_bundle

        manifest, _ = inspect_bundle(bundle)
        with self._lock(manifest["id"]):
            identifier = self.installer.install(bundle, **kwargs)
            self._stopping.discard(identifier)
            return identifier

    def enable(self, plugin_id):
        with self._lock(plugin_id):
            if not self.store.get(plugin_id):
                raise ValueError("Plugin not installed")
            self._stop_worker(plugin_id)
            self.store.execute(
                "UPDATE plugins SET enabled=1, decision='enabled' WHERE id=?", (plugin_id,)
            )
            self.store.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?,?)", (plugin_id, "enabled")
            )
            self._stopping.discard(plugin_id)

    def disable(self, plugin_id):
        with self._state_lock:
            self._stopping.add(plugin_id)
            for task in tuple(self._handles.values()):
                if task.plugin_id == plugin_id:
                    task.cancel()
        with self._lock(plugin_id):
            self._stop_worker(plugin_id)
            self.store.execute(
                "UPDATE plugins SET enabled=0, decision='disabled' WHERE id=?", (plugin_id,)
            )
            self.store.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?,?)", (plugin_id, "disabled")
            )

    def _stop_worker(self, plugin_id):
        worker = self._workers.pop(plugin_id, None)
        if worker:
            worker.stop()
            self.artifacts.release(worker.session)
            shutil.rmtree(worker.root, ignore_errors=True)

    def uninstall(self, plugin_id, *, delete_data=False):
        self.disable(plugin_id)
        with self._lock(plugin_id):
            record = self.store.get(plugin_id)
            if record:
                self.store.execute(
                    "INSERT OR REPLACE INTO journal VALUES (?,?)", (record["path"], "removal")
                )
                shutil.rmtree(record["path"])
                self.store.execute("DELETE FROM plugins WHERE id=?", (plugin_id,))
                self.store.execute("DELETE FROM journal WHERE path=?", (record["path"],))
            self.store.execute(
                "INSERT OR REPLACE INTO decisions VALUES (?,?)", (plugin_id, "uninstalled")
            )
            if delete_data:
                shutil.rmtree(self.store.root / "plugin-data" / plugin_id, ignore_errors=True)
                self.store.execute("DELETE FROM settings WHERE namespace=?", (plugin_id,))

    def delete_data(self, plugin_id):
        """Disable a tool and clear its own saved data, retaining installed code."""
        with self._lock(plugin_id):
            if not self.store.get(plugin_id):
                raise ValueError("Plugin not installed")
        self.disable(plugin_id)
        with self._lock(plugin_id):
            shutil.rmtree(self.store.root / "plugin-data" / plugin_id, ignore_errors=True)
            self.store.execute("DELETE FROM settings WHERE namespace=?", (plugin_id,))

    def set_locale(self, locale):
        with self._state_lock:
            if self._handles:
                raise PluginError(
                    "busy", "Wait for active tasks before changing language", code=-32004
                )
            for plugin in tuple(self._workers):
                self._stop_worker(plugin)
            self.locale = locale
            self.installer.locale = locale

    def _idle(self):
        while not self._maintenance_stop.wait(10):
            for plugin, stamp in tuple(self._last_used.items()):
                if time.monotonic() - stamp >= 300:
                    lock = self._lock(plugin)
                    if lock.acquire(blocking=False):
                        try:
                            self._stop_worker(plugin)
                            self._last_used.pop(plugin, None)
                        finally:
                            lock.release()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._maintenance_stop.set()
        for task in tuple(self._handles.values()):
            task.cancel()
        for plugin in tuple(self._workers):
            self._workers[plugin].stop(force=True)
        self.executor.shutdown(wait=True, cancel_futures=False)
        for plugin in tuple(self._workers):
            self._stop_worker(plugin)
        self.artifacts.close()
        self.store.close()
        for handler in tuple(self.logger.handlers):
            handler.close()
            self.logger.removeHandler(handler)


def create_services(config=None, *, platform_adapter=None):
    return ServiceContainer(config or RuntimeConfig(), platform_adapter=platform_adapter)
