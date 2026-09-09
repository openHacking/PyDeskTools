"""Separate-interpreter worker. stdout belongs exclusively to protocol 1."""

import argparse
import logging
import queue
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from importlib import import_module, metadata
from pathlib import Path

from . import __version__
from .api import CancellationToken, InvocationContext, PluginContext, PluginError
from .protocol import descriptor, encode, read, validate, validate_progress_data, validate_view


class HostClient:
    def __init__(self, worker):
        self.worker = worker

    def call(self, capability, **arguments):
        identifier = "w-" + uuid.uuid4().hex
        response: queue.Queue = queue.Queue(maxsize=1)
        self.worker.responses[identifier] = response
        self.worker.send(
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "method": "host.call",
                "params": {"capability": capability, "arguments": arguments},
            }
        )
        try:
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                if self.worker.token:
                    self.worker.token.raise_if_cancelled()
                try:
                    message = response.get(timeout=0.1)
                    break
                except queue.Empty:
                    continue
            else:
                raise PluginError("deadline_exceeded", "Host call timed out", code=-32006)
            if "error" in message:
                error = message["error"]
                raise PluginError(
                    error.get("data", {}).get("kind", "host_error"),
                    error["message"],
                    code=error["code"],
                )
            return message["result"]["value"]
        finally:
            self.worker.responses.pop(identifier, None)

    def choose_file(self, *, title, mode="open"):
        if mode != "open":
            raise ValueError("Use dialogs.save_file with an artifact")
        return self.call("dialogs.open_file", title=title)


class Settings:
    def __init__(self, host):
        self.host = host

    def get(self, key, default=None):
        return self.host.call("settings.get", key=key, default=default)

    def set(self, key, value):
        return self.host.call("settings.set", key=key, value=value)


class Worker:
    def __init__(self, entrypoint, distribution):
        self.entrypoint, self.distribution = entrypoint, distribution
        self.output = sys.stdout.buffer
        sys.stdout = sys.stderr
        self.write_lock = threading.Lock()
        self.responses = {}
        self.seen = set()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.busy = False
        self.plugin = None
        self.initialized = False
        self.activated = False
        self.deactivated = False
        self.token = None
        self.task_id = None
        self.commands = {}
        self.host = HostClient(self)
        self.last_progress = 0.0
        self.progress_lock = threading.Lock()
        self.progress_timer = None
        self.pending_progress = None
        self.stop = False

    def send(self, message):
        payload = encode(message)
        with self.write_lock:
            self.output.write(payload)
            self.output.flush()

    def progress(self, fraction, message, data=None):
        validate_progress_data(data)
        if fraction is not None and (isinstance(fraction, bool) or not 0 <= fraction <= 1):
            raise ValueError("Invalid progress fraction")
        params = {"task_id": self.task_id, "fraction": fraction,
                  "message": str(message)[:1024], **({"data": data} if data is not None else {})}
        with self.progress_lock:
            elapsed = time.monotonic() - self.last_progress
            if elapsed < 0.1:
                # Keep the latest checkpoint while a long operation runs. Dropping
                # it would hide already saved files if a later operation is stopped.
                if data is not None:
                    self.pending_progress = params
                    if self.progress_timer is None:
                        self.progress_timer = threading.Timer(0.1 - elapsed, self._flush_progress)
                        self.progress_timer.daemon = True
                        self.progress_timer.start()
                return
            if self.progress_timer is not None:
                self.progress_timer.cancel()
                self.progress_timer = None
            self.pending_progress = None
            self.last_progress = time.monotonic()
            self.send({"jsonrpc": "2.0", "method": "task.progress", "params": params})

    def _flush_progress(self):
        with self.progress_lock:
            self.progress_timer = None
            params, self.pending_progress = self.pending_progress, None
            if params and params["task_id"] == self.task_id:
                self.last_progress = time.monotonic()
                self.send({"jsonrpc": "2.0", "method": "task.progress", "params": params})

    def dispatch(self, method, params):
        if method == "initialize":
            if self.initialized or params["protocol"] != 1:
                raise PluginError("incompatible", "Unsupported initialization", code=-32001)
            version = metadata.version(self.distribution)
            if version != params["version"]:
                raise PluginError(
                    "incompatible", "Plugin distribution version mismatch", code=-32001
                )
            self.identity = params
            self.initialized = True
            return {
                "protocol": 1,
                "plugin_id": params["plugin_id"],
                "version": version,
                "sdk_version": __version__,
            }
        if not self.initialized:
            raise PluginError("not_active", "Initialize first", code=-32002)
        if method == "plugin.activate":
            if self.activated:
                raise PluginError("busy", "Already activated", code=-32004)
            module, factory = self.entrypoint.split(":")
            self.plugin = getattr(import_module(module), factory)()
            i = self.identity
            self.context = PluginContext(
                i["plugin_id"],
                i["version"],
                i["session_id"],
                i["locale"],
                Path(i["data_dir"]),
                Path(i["cache_dir"]),
                Settings(self.host),
                logging.getLogger(i["plugin_id"]),
                self.host,
            )
            self.plugin.activate(self.context)
            self.activated = True
            return {}
        if method == "plugin.describe":
            if not self.activated:
                raise PluginError("not_active", "Activate first", code=-32002)
            assert self.plugin is not None
            result = self.plugin.describe()
            if is_dataclass(result) and not isinstance(result, type):
                result = asdict(result)
            self.commands = descriptor(result)
            return result
        if method == "plugin.invoke":
            if not self.activated or params["command_id"] not in self.commands:
                raise PluginError("not_active", "Command unavailable", code=-32002)
            command = self.commands[params["command_id"]]
            validate(params["arguments"], command["input_schema"])
            assert self.plugin is not None and self.token is not None and self.task_id is not None
            result = self.plugin.invoke(
                params["command_id"],
                params["arguments"],
                InvocationContext(self.task_id, self.token, self.host, self.progress),
            )
            if not result.data.get("canceled", False):
                self.token.raise_if_cancelled()
            validate(result.data, command["output_schema"], "result")
            validate_view(result.view, self.commands)
            return asdict(result)
        if method == "plugin.deactivate":
            if self.activated and not self.deactivated:
                self.deactivated = True
                assert self.plugin is not None
                self.plugin.deactivate()
            self.activated = False
            return {}
        if method == "shutdown":
            self.stop = True
            return {}
        raise PluginError("method_not_found", "Unknown worker method", code=-32601)

    def execute(self, message):
        reply = {"jsonrpc": "2.0", "id": message["id"]}
        try:
            reply["result"] = self.dispatch(message["method"], message.get("params", {}))
            encode(reply)
        except PluginError as error:
            reply = {"jsonrpc": "2.0", "id": message["id"], "error": error.wire()}
        except Exception:
            # Exception messages may contain private document content.
            reply = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "error": {
                    "code": -32007,
                    "message": "Plugin operation failed",
                    "data": {"kind": "invalid_plugin_result"},
                },
            }
        finally:
            with self.progress_lock:
                if self.progress_timer is not None:
                    self.progress_timer.cancel()
                self.progress_timer = self.pending_progress = None
            self.task_id = None
            self.token = None
            self.busy = False
        self.send(reply)

    def run(self):
        try:
            while not self.stop:
                message = read(sys.stdin.buffer)
                if "method" not in message:
                    response = self.responses.get(message["id"])
                    if response:
                        response.put_nowait(message)
                    continue
                method, params = message["method"], message.get("params", {})
                if method == "task.cancel" and "id" not in message:
                    if self.token and params.get("task_id") == self.task_id:
                        self.token.cancel()
                    continue
                identifier = message.get("id")
                if not identifier or not identifier.startswith("h-") or identifier in self.seen:
                    raise ValueError("Unexpected or duplicate request")
                self.seen.add(identifier)
                if len(self.seen) > 100000:
                    raise ValueError("Session request limit reached")
                if self.busy:
                    self.send(
                        {
                            "jsonrpc": "2.0",
                            "id": identifier,
                            "error": {
                                "code": -32004,
                                "message": "Worker busy",
                                "data": {"kind": "busy"},
                            },
                        }
                    )
                    continue
                self.busy = True
                if method == "plugin.invoke":
                    self.task_id = params.get("task_id")
                    self.token = CancellationToken()
                self.executor.submit(self.execute, message)
        except (EOFError, ValueError, OSError):
            if self.token:
                self.token.cancel()
        finally:
            self.executor.shutdown(wait=False, cancel_futures=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--distribution", required=True)
    args = parser.parse_args()
    Worker(args.entrypoint, args.distribution).run()


if __name__ == "__main__":
    main()
