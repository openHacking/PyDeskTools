"""TCP listeners and explicit single-process termination, inside the SDK worker."""

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import psutil
from pydesktools_sdk import CommandResult, PluginError


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties if required is None else required),
            "additionalProperties": False}


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}
ENDPOINT = obj({"address": STR, "port": INT})
SERVICE = obj({"token": STR, "pid": INT, "name": STR, "project": STR,
               "cwd": STR, "command": STR, "username": STR, "age_seconds": INT,
               "development": BOOL, "can_stop": BOOL,
               "endpoints": {"type": "array", "items": ENDPOINT}})
OUTPUT = obj({"services": {"type": "array", "items": SERVICE},
              "warnings": {"type": "array", "items": STR}, "status": STR,
              "released_ports": {"type": "array", "items": INT},
              "occupied_ports": {"type": "array", "items": INT}})


def parse_lsof(output):
    """Parse field output, retaining IPv4/IPv6 addresses and deduplicating FDs."""
    listeners: dict[int, set[tuple[str, int]]] = {}
    pid = None
    for line in output.splitlines():
        if line.startswith("p"):
            pid = int(line[1:]) if line[1:].isdigit() else None
        elif line.startswith("n") and pid is not None:
            address, separator, port = line[1:].rpartition(":")
            if separator and port.isdigit() and 0 < int(port) <= 65535:
                listeners.setdefault(pid, set()).add((address, int(port)))
    return listeners


def listeners():
    if sys.platform == "darwin":
        # psutil's system-wide connection query requires root on macOS.
        try:
            result = subprocess.run(
                ["/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fpn"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise PluginError("scan_failed", "Could not query local TCP listeners") from error
        if result.returncode not in (0, 1) or (result.returncode == 1 and result.stderr):
            raise PluginError("scan_failed", "The system TCP listener query failed")
        return parse_lsof(result.stdout)
    try:
        connections = psutil.net_connections(kind="tcp")
    except psutil.AccessDenied as error:
        raise PluginError("access_denied", "Permission denied while querying TCP listeners") from error
    found: dict[int, set[tuple[str, int]]] = {}
    for connection in connections:
        if connection.status == psutil.CONN_LISTEN:
            found.setdefault(connection.pid or 0, set()).add(
                (connection.laddr.ip, connection.laddr.port))
    return found


def development(name, command):
    # Hints only: a runtime is not proof that the listener is a development server.
    executable = name.casefold().removesuffix(".exe")
    return executable in {"node", "bun", "deno", "java", "ruby", "php", "go"} or (
        executable.startswith("python") or any(
            word in command.casefold() for word in ("vite", "next dev", "uvicorn", "webpack", "nodemon")
        ))


class PortManager:
    def activate(self, context):
        self.context = context
        self.snapshots = {}

    def describe(self):
        return {"commands": [
            {"id": "scan", "title": "Scan ports", "description": "Inspect local TCP listeners",
             "effects": "read", "retry": "safe", "timeout_ms": 60000,
             "input_schema": obj({}), "output_schema": OUTPUT},
            {"id": "stop", "title": "Stop service", "description": "Stop one inspected process",
             "effects": "external", "retry": "manual", "timeout_ms": 60000,
             "input_schema": obj({"token": STR, "force": BOOL}, ("token",)),
             "output_schema": OUTPUT},
        ]}

    def scan(self, context, status=""):
        context.cancellation.raise_if_cancelled()
        # Capture process identities before enumeration, to reject PID reuse during a scan.
        identities = {}
        for process in psutil.process_iter():
            context.cancellation.raise_if_cancelled()
            try:
                identities[process.pid] = process.create_time()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        found = listeners()
        own = psutil.Process(os.getpid())
        protected = {own.pid, *(p.pid for p in own.parents())}
        username = own.username()
        services, snapshots = [], {}
        warnings = ["Local machine only. Permissions may hide listeners or process details; "
                    "Docker, WSL and remote services are not inspected internally."]
        for pid, endpoints in sorted(found.items()):
            context.cancellation.raise_if_cancelled()
            try:
                if pid == 0:
                    raise psutil.AccessDenied(pid)
                process = psutil.Process(pid)
                birth = process.create_time()
                if identities.get(pid) != birth:
                    warnings.append(f"PID {pid} changed during scanning; refresh to inspect it.")
                    continue
                name = process.name()
                owner = process.username()
                try:
                    cwd, command = process.cwd(), " ".join(process.cmdline())
                except psutil.AccessDenied:
                    cwd, command = "", ""
                token = uuid.uuid4().hex
                can_stop = owner == username and pid > 1 and pid not in protected
                if can_stop:
                    snapshots[token] = (pid, birth, set(endpoints))
                services.append({"token": token, "pid": pid, "name": name,
                                 "project": Path(cwd).name if cwd else "",
                                 "cwd": cwd, "command": command, "username": owner,
                                 "age_seconds": max(0, int(time.time() - birth)),
                                 "development": development(name, command), "can_stop": can_stop,
                                 "endpoints": [{"address": a, "port": p} for a, p in sorted(endpoints)]})
            except psutil.NoSuchProcess:
                continue
            except psutil.AccessDenied:
                warnings.append(f"PID {pid}: process details unavailable.")
                services.append({"token": "", "pid": pid, "name": "", "project": "",
                                 "cwd": "", "command": "", "username": "", "age_seconds": 0,
                                 "development": False, "can_stop": False,
                                 "endpoints": [{"address": a, "port": p} for a, p in sorted(endpoints)]})
        self.snapshots = snapshots
        return {"services": services, "warnings": warnings, "status": status,
                "released_ports": [], "occupied_ports": []}

    def stop(self, arguments, context):
        snapshot = self.snapshots.pop(arguments["token"], None)
        if snapshot is None:
            raise PluginError("stale_selection", "Refresh the list and select the service again")
        pid, birth, expected = snapshot
        context.cancellation.raise_if_cancelled()
        try:
            process = psutil.Process(pid)
            if process.create_time() != birth:
                raise PluginError("stale_selection", "The process identity changed; refresh the list")
            own = psutil.Process(os.getpid())
            if (pid <= 1 or pid in {own.pid, *(p.pid for p in own.parents())}
                    or process.username() != own.username()):
                raise PluginError("protected_process", "This process cannot be stopped by this tool")
            if listeners().get(pid, set()) != expected:
                raise PluginError("stale_selection", "The listening ports changed; refresh the list")
            context.cancellation.raise_if_cancelled()
            # psutil checks PID reuse again inside terminate/kill. No group or ancestor signals.
            (process.kill if arguments.get("force", False) else process.terminate)()
            try:
                process.wait(timeout=3)
                status = "Process exited. Check the refreshed list for released or reassigned ports."
            except psutil.TimeoutExpired:
                if process.status() == psutil.STATUS_ZOMBIE or not process.is_running():
                    # A non-child can have exited but await reaping by its real parent.
                    status = "Process exited. Check the refreshed list for released or reassigned ports."
                else:
                    status = "Process is still running. Select it again to force termination if needed."
        except psutil.NoSuchProcess:
            status = "Process already exited. The list has been refreshed."
        except psutil.AccessDenied as error:
            raise PluginError("access_denied", "Permission denied while stopping this process") from error
        result = self.scan(context, status)
        expected_ports = {port for _, port in expected}
        observed_ports = {endpoint["port"] for service in result["services"]
                          for endpoint in service["endpoints"]}
        result["released_ports"] = sorted(expected_ports - observed_ports)
        result["occupied_ports"] = sorted(expected_ports & observed_ports)
        return result

    def invoke(self, command_id, arguments, context):
        if command_id == "scan":
            return CommandResult(self.scan(context))
        if command_id == "stop":
            return CommandResult(self.stop(arguments, context))
        raise PluginError("unknown_command", "Unknown port manager command")

    def deactivate(self):
        self.snapshots.clear()


def create_plugin():
    return PortManager()
