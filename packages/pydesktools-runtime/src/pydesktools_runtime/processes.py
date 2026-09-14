"""Bounded process supervision and serialized JSON-RPC requests."""

import os
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import Future
from pathlib import Path
from typing import Any

from pydesktools_sdk import PluginError
from pydesktools_sdk.protocol import encode, read, validate_progress_data


def hidden_process_kwargs(os_name=None):
    """Return native flags that keep background children out of the desktop UI."""
    if (os_name or os.name) == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def background_popen(args, **kwargs):
    """Start an internal background process without exposing platform UI."""
    kwargs.update(hidden_process_kwargs())
    return subprocess.Popen(args, **kwargs)


def terminate_process(process, *, force=False):
    """Stop a child process using the native process model."""
    if os.name == "nt":
        if process.poll() is None:
            (process.kill if force else process.terminate)()
        return
    try:
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass


class WorkerProcess:
    def __init__(self, python, manifest, root, locale, host_call, on_progress):
        self.session = uuid.uuid4().hex
        self.root = Path(root) / "sessions" / self.session
        self.root.mkdir(parents=True)
        self.import_dir = self.root / "import"
        self.export_dir = self.root / "export"
        self.import_dir.mkdir()
        self.export_dir.mkdir()
        self.manifest = manifest
        self.pending = {}
        self.pending_lock = threading.RLock()
        self.write_lock = threading.Lock()
        self._stop_lock = threading.RLock()
        self.host_call = host_call
        self.on_progress = on_progress
        self.closed = False
        self.failed = None
        self.task_id = None
        self.seen_worker_ids = set()
        self.control_slots = threading.BoundedSemaphore(8)
        self.last_progress = 0.0
        self.progress_count = 0
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PYTHON", "_PYI", "DYLD_", "LD_LIBRARY_PATH"))
        }
        env.update(PYTHONNOUSERSITE="1", PYTHONUTF8="1")
        self.process = background_popen(
            [
                str(python),
                "-I",
                "-m",
                "pydesktools_sdk.runner",
                "--entrypoint",
                manifest["entrypoint"],
                "--distribution",
                manifest["distribution"],
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=self.root,
            start_new_session=True,
            bufsize=0,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.stderr = threading.Thread(target=self._drain_stderr, daemon=True)
        self.reader.start()
        self.stderr.start()
        try:
            result = self.call(
                "initialize",
                dict(
                    session_id=self.session,
                    protocol=1,
                    plugin_id=manifest["id"],
                    version=manifest["version"],
                    locale=locale,
                    data_dir=str(Path(root) / "data"),
                    cache_dir=str(self.root),
                    import_dir=str(self.import_dir),
                    export_dir=str(self.export_dir),
                ),
                timeout=10,
            )
            if (
                result.get("plugin_id") != manifest["id"]
                or result.get("version") != manifest["version"]
                or result.get("protocol") != 1
            ):
                raise ValueError("Worker identity mismatch")
            self.call(
                "plugin.activate",
                {"settings": {}, "allowed_capabilities": manifest["capabilities"]},
                timeout=15,
            )
            self.descriptor = self.call("plugin.describe", {}, timeout=15)
        except BaseException:
            self.stop(force=True)
            raise

    def send(self, message):
        payload = encode(message)
        with self.write_lock:
            if self.closed:
                raise PluginError("not_active", "Worker is stopped", code=-32002)
            assert self.process.stdin is not None
            self.process.stdin.write(payload)
            self.process.stdin.flush()

    def call(self, method, params, *, timeout=30, token=None):
        identifier = "h-" + uuid.uuid4().hex
        future: Future[Any] = Future()
        with self.pending_lock:
            self.pending[identifier] = future
        try:
            self.send({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params})
            deadline = time.monotonic() + timeout
            cancel_at = None
            while True:
                try:
                    response = future.result(timeout=0.05)
                    break
                except TimeoutError:
                    if token and token.is_cancelled and cancel_at is None:
                        cancel_at = time.monotonic()
                        self.send(
                            {
                                "jsonrpc": "2.0",
                                "method": "task.cancel",
                                "params": {"task_id": self.task_id},
                            }
                        )
                    if time.monotonic() >= deadline or (
                        cancel_at and time.monotonic() - cancel_at > 2
                    ):
                        self.stop(force=True)
                        raise PluginError(
                            "deadline_exceeded" if cancel_at is None else "forced_stop",
                            "Worker terminated before completion was acknowledged",
                            code=-32006,
                            completion_unknown=True,
                        )
            if "error" in response:
                error = response["error"]
                data = dict(error.get("data", {}))
                kind = data.pop("kind", "worker_error")
                raise PluginError(kind, error["message"], code=error["code"], **data)
            return response["result"]
        finally:
            with self.pending_lock:
                self.pending.pop(identifier, None)

    def _fail(self, error):
        self.failed = error
        with self.pending_lock:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(
                        PluginError(
                            "worker_failed",
                            "Worker disconnected",
                            code=-32007,
                            completion_unknown=True,
                        )
                    )

    def _host_response(self, message):
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        try:
            value = self.host_call(
                self, message["params"]["capability"], message["params"].get("arguments", {})
            )
            reply["result"] = {"value": value}
        except PluginError as error:
            reply["error"] = error.wire()
        except Exception:
            reply["error"] = {
                "code": -32603,
                "message": "Host operation failed",
                "data": {"kind": "host_error"},
            }
        try:
            if not self.closed:
                self.send(reply)
        except (OSError, ValueError, PluginError):
            pass
        finally:
            self.control_slots.release()

    def _read(self):
        try:
            while not self.closed:
                message = read(self.process.stdout)
                if message.get("method") == "host.call":
                    identifier = message.get("id", "")
                    if (
                        not identifier.startswith("w-")
                        or identifier in self.seen_worker_ids
                        or len(self.seen_worker_ids) >= 100000
                    ):
                        raise ValueError("Invalid worker request ID")
                    self.seen_worker_ids.add(identifier)
                    if not self.control_slots.acquire(blocking=False):
                        raise ValueError("Host-call queue saturated")
                    threading.Thread(
                        target=self._host_response, args=(message,), daemon=True
                    ).start()
                elif message.get("method") == "task.progress":
                    params = message["params"]
                    validate_progress_data(params.get("data"))
                    fraction = params.get("fraction")
                    if fraction is not None and (
                        isinstance(fraction, bool)
                        or not isinstance(fraction, (int, float))
                        or not 0 <= fraction <= 1
                    ):
                        raise ValueError("Invalid progress fraction")
                    if (
                        not isinstance(params.get("message"), str)
                        or len(params["message"].encode()) > 4096
                    ):
                        raise ValueError("Invalid progress message")
                    if params.get("task_id") != self.task_id:
                        continue
                    now = time.monotonic()
                    if now - self.last_progress >= 1:
                        self.last_progress, self.progress_count = now, 0
                    self.progress_count += 1
                    if self.progress_count > 20:
                        raise ValueError("Progress flood")
                    self.on_progress(self, params)
                elif "method" not in message and message["id"].startswith("h-"):
                    with self.pending_lock:
                        future = self.pending.get(message["id"])
                        if future and not future.done():
                            future.set_result(message)
                else:
                    raise ValueError("Unexpected worker message")
        except (EOFError, ValueError, OSError, KeyError) as error:
            self._fail(error)
            if not self.closed:
                self.stop(force=True)

    def _drain_stderr(self):
        # Drain without persisting arbitrary plugin output or private documents.
        assert self.process.stderr is not None
        while self.process.stderr.read(4096):
            pass

    def stop(self, *, force=False):
        with self._stop_lock:
            self._stop(force=force)

    def _stop(self, *, force=False):
        if self.closed:
            return
        if not force and self.process.poll() is None:
            try:
                self.call("plugin.deactivate", {"reason": "shutdown"}, timeout=2)
                self.call("shutdown", {}, timeout=2)
            except Exception:
                pass
        self.closed = True
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            pass
        # Reap the process group even if the worker itself has already exited.
        terminate_process(self.process)
        try:
            self.process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            terminate_process(self.process, force=True)
            self.process.wait(timeout=1)
        terminate_process(self.process, force=True)
        self._fail(RuntimeError("Worker stopped"))
