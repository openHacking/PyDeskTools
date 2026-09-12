import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydesktools_runtime import RuntimeConfig, create_services
from pydesktools_runtime.plugins import platform_label, venv_python
from pydesktools_runtime.processes import (
    background_popen,
    hidden_process_kwargs,
    terminate_process,
)
from pydesktools_runtime.storage import Store


class _ImmediateDialogQueue:
    def __init__(self, selected):
        self.selected = selected

    def put_nowait(self, request):
        request[-1].set_result(self.selected)


class _Artifacts:
    def __init__(self, source):
        self.source = source

    def path(self, plugin_id, artifact_id):
        assert plugin_id == "test.plugin"
        assert artifact_id == "artifact"
        return self.source


def test_platform_labels():
    assert platform_label("Darwin", "arm64") == "macos-arm64"
    assert platform_label("Windows", "AMD64") == "windows-x86_64"
    assert platform_label("Linux", "x86_64") == "linux-x86_64"
    assert platform_label("Windows", "ARM64") == "windows-arm64"


def test_unknown_platform_is_explicit():
    assert platform_label("Plan9", "MIPS64") == "unsupported-mips64"


def test_venv_python_uses_native_layout():
    root = Path("plugin/venv")
    assert venv_python(root, "Windows") == root / "Scripts/python.exe"
    assert venv_python(root, "Darwin") == root / "bin/python"
    assert venv_python(root, "Linux") == root / "bin/python"


def test_windows_plugin_processes_do_not_create_a_console(monkeypatch):
    kwargs = hidden_process_kwargs("nt")
    assert kwargs == {"creationflags": subprocess.CREATE_NO_WINDOW}
    assert hidden_process_kwargs("posix") == {}
    captured = {}

    def popen(args, **options):
        captured.update(options)
        return args

    monkeypatch.setattr("pydesktools_runtime.processes.subprocess.Popen", popen)
    assert background_popen(["worker.exe"], stdin=subprocess.PIPE) == ["worker.exe"]
    assert captured == {
        "stdin": subprocess.PIPE,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


def test_save_file_closes_temporary_before_atomic_replace(tmp_path):
    from pydesktools.platform import PlatformAdapter

    source = tmp_path / "artifact.json"
    source.write_text('{"hello":"世界"}', encoding="utf-8")
    destination = tmp_path / "export.json"
    adapter = PlatformAdapter.__new__(PlatformAdapter)
    adapter.closed = False
    adapter.requests = _ImmediateDialogQueue(str(destination))
    cancellation = SimpleNamespace(raise_if_cancelled=lambda: None)

    selected = adapter.call(
        "dialogs.save_file",
        {"artifact_id": "artifact"},
        plugin_id="test.plugin",
        cancellation=cancellation,
        artifacts=_Artifacts(source),
    )

    assert selected == str(destination)
    assert destination.read_bytes() == source.read_bytes()
    assert not list(tmp_path.glob(".pydesk-*"))


def test_open_directory_uses_native_file_manager(tmp_path, monkeypatch):
    from pydesktools.app import Application

    opened = []
    monkeypatch.setattr("subprocess.Popen", lambda arguments: opened.append(arguments))
    app = Application.__new__(Application)
    app.error = pytest.fail

    app.open_directory(tmp_path)

    if sys.platform == "darwin":
        assert opened == [["open", str(tmp_path)]]
    elif sys.platform == "win32":
        assert opened == [["explorer.exe", str(tmp_path)]]
    else:
        assert opened == [["xdg-open", str(tmp_path)]]


def test_child_process_termination_uses_native_process_model():
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    try:
        terminate_process(process, force=True)
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_profile_lock_uses_native_process_model(tmp_path):
    first = Store(tmp_path / "profile")
    try:
        with pytest.raises(RuntimeError, match="already open"):
            Store(first.root)
    finally:
        first.close()

    reopened = Store(first.root)
    reopened.close()


def test_profile_lock_precedes_runtime_resolution(tmp_path):
    first = create_services(RuntimeConfig(data_dir=tmp_path / "profile"))
    resolved = []
    try:
        with pytest.raises(RuntimeError, match="already open"):
            create_services(
                RuntimeConfig(data_dir=first.store.root),
                python_resolver=lambda: resolved.append(True),
            )
        assert not resolved
    finally:
        first.close()
