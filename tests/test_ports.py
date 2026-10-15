"""Adversarial identity checks and real disposable listener termination."""

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import psutil
import pytest
from pydesk_port_manager import PortManager, listeners, parse_lsof
from pydesktools_sdk import CancellationToken, PluginError


@pytest.fixture
def plugin():
    manager = PortManager()
    manager.activate(SimpleNamespace())
    return manager


@pytest.fixture
def context():
    return SimpleNamespace(cancellation=CancellationToken())


@pytest.fixture
def server():
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", "import socket,time; "
         "a=socket.socket(); a.bind(('127.0.0.1',0)); a.listen(); "
         "b=socket.socket(); b.bind(('127.0.0.1',0)); b.listen(); "
         "print(a.getsockname()[1],b.getsockname()[1],flush=True); time.sleep(120)"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        ports = list(map(int, process.stdout.readline().split()))
        assert len(ports) == 2
        yield process, ports
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()


def test_lsof_ipv6_duplicates_and_missing_pid():
    assert parse_lsof("n*:80\np12\nf1\nn127.0.0.1:3000\nf2\nn127.0.0.1:3000\n"
                      "n[::1]:3000\np13\nn*:5173\nninvalid\n") == {
        12: {("127.0.0.1", 3000), ("[::1]", 3000)}, 13: {("*", 5173)}}


@pytest.mark.parametrize("force", [False, True])
def test_real_scan_and_stop_releases_all_ports_only_of_selected_process(plugin, context, server, force):
    import socket

    process, ports = server
    unrelated = socket.socket()
    unrelated.bind(("127.0.0.1", 0))
    unrelated.listen()
    try:
        data = plugin.invoke("scan", {}, context).data
        service = next(s for s in data["services"] if s["pid"] == process.pid)
        assert set(e["port"] for e in service["endpoints"]) == set(ports)
        assert service["can_stop"]
        assert not next(s for s in data["services"] if s["pid"] == os.getpid())["can_stop"]
        result = plugin.invoke("stop", {"token": service["token"], "force": force}, context).data
        assert process.poll() is not None
        assert result["released_ports"] == sorted(ports)
        assert result["occupied_ports"] == []
        assert all(s["pid"] != process.pid for s in result["services"])
        assert any(e["port"] == unrelated.getsockname()[1]
                   for s in result["services"] for e in s["endpoints"])
        for port in ports:
            with socket.socket() as check:
                check.bind(("127.0.0.1", port))
    finally:
        unrelated.close()


def test_refresh_invalidates_previous_selection(plugin, context, server):
    process, _ = server
    data = plugin.invoke("scan", {}, context).data
    service = next(s for s in data["services"] if s["pid"] == process.pid)
    plugin.invoke("scan", {}, context)
    with pytest.raises(PluginError, match="Refresh"):
        plugin.invoke("stop", {"token": service["token"]}, context)
    assert process.poll() is None


def test_pid_reuse_never_signals_new_process(plugin, context, monkeypatch):
    plugin.snapshots["selected"] = (42, 100.0, {("127.0.0.1", 3000)})
    replacement = Mock()
    replacement.create_time.return_value = 101.0
    monkeypatch.setattr(psutil, "Process", lambda pid: replacement)
    with pytest.raises(PluginError, match="identity changed"):
        plugin.stop({"token": "selected"}, context)
    replacement.terminate.assert_not_called()
    replacement.kill.assert_not_called()


def test_changed_ports_never_signals_process(plugin, context, server, monkeypatch):
    process, _ = server
    data = plugin.scan(context)
    service = next(s for s in data["services"] if s["pid"] == process.pid)
    monkeypatch.setattr("pydesk_port_manager.listeners", lambda: {})
    with pytest.raises(PluginError, match="ports changed"):
        plugin.stop({"token": service["token"]}, context)
    assert process.poll() is None


def test_same_user_and_ancestors_rechecked_before_stop(plugin, context, monkeypatch):
    plugin.snapshots["selected"] = (42, 100.0, {("127.0.0.1", 3000)})
    target, own = Mock(), Mock()
    target.create_time.return_value = 100.0
    target.username.return_value = "other"
    own.pid = os.getpid()
    own.username.return_value = "me"
    own.parents.return_value = []
    monkeypatch.setattr(psutil, "Process", lambda pid: target if pid == 42 else own)
    with pytest.raises(PluginError, match="cannot be stopped"):
        plugin.stop({"token": "selected"}, context)
    target.terminate.assert_not_called()
    plugin.snapshots["selected"] = (42, 100.0, {("127.0.0.1", 3000)})
    target.username.return_value = "me"
    own.parents.return_value = [SimpleNamespace(pid=42)]
    with pytest.raises(PluginError, match="cannot be stopped"):
        plugin.stop({"token": "selected"}, context)
    target.terminate.assert_not_called()


def test_tcp_only_fallback_and_access_denied(monkeypatch):
    monkeypatch.setattr("pydesk_port_manager.sys.platform", "linux")
    query = Mock(return_value=[
        SimpleNamespace(status="LISTEN", pid=12, laddr=SimpleNamespace(ip="::1", port=8000)),
        SimpleNamespace(status="ESTABLISHED", pid=13),
        SimpleNamespace(status="LISTEN", pid=None, laddr=SimpleNamespace(ip="0.0.0.0", port=9000)),
    ])
    monkeypatch.setattr(psutil, "net_connections", query)
    assert listeners() == {12: {("::1", 8000)}, 0: {("0.0.0.0", 9000)}}
    query.assert_called_once_with(kind="tcp")
    query.side_effect = psutil.AccessDenied()
    with pytest.raises(PluginError, match="Permission denied"):
        listeners()


def test_lsof_failure_is_not_empty_success(monkeypatch):
    monkeypatch.setattr("pydesk_port_manager.sys.platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(returncode=1, stdout="", stderr="query failed"))
    with pytest.raises(PluginError, match="query failed"):
        listeners()


def test_scan_cancellation(plugin, context):
    context.cancellation.cancel()
    with pytest.raises(PluginError):
        plugin.scan(context)


@pytest.mark.skipif(os.name == "nt", reason="Windows terminate is immediate")
def test_sigterm_timeout_does_not_automatically_force_stop(plugin, context):
    process = subprocess.Popen(
        [sys.executable, "-u", "-c", "import signal,socket,time; "
         "signal.signal(signal.SIGTERM,signal.SIG_IGN); s=socket.socket(); "
         "s.bind(('127.0.0.1',0)); s.listen(); print(s.getsockname()[1],flush=True); time.sleep(120)"],
        stdout=subprocess.PIPE, text=True,
    )
    try:
        port = int(process.stdout.readline())
        service = next(s for s in plugin.scan(context)["services"] if s["pid"] == process.pid)
        result = plugin.stop({"token": service["token"]}, context)
        assert process.poll() is None
        assert "still running" in result["status"]
        assert result["occupied_ports"] == [port]
        refreshed = next(s for s in result["services"] if s["pid"] == process.pid)
        forced = plugin.stop({"token": refreshed["token"], "force": True}, context)
        assert process.poll() is not None
        assert forced["released_ports"] == [port]
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stdout.close()


def test_unknown_owner_listener_stays_visible_and_cannot_be_stopped(plugin, context, monkeypatch):
    monkeypatch.setattr("pydesk_port_manager.listeners", lambda: {0: {("0.0.0.0", 9000)}})
    data = plugin.scan(context)
    assert len(data["services"]) == 1
    assert data["services"][0]["endpoints"] == [{"address": "0.0.0.0", "port": 9000}]
    assert not data["services"][0]["can_stop"]
