import subprocess
import sys
from pathlib import Path

import pytest
from pydesktools_runtime import RuntimeConfig, create_services
from pydesktools_runtime.plugins import platform_label, venv_python
from pydesktools_runtime.processes import (
    background_popen,
    hidden_process_kwargs,
    terminate_process,
)
from pydesktools_runtime.storage import Store


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
    # Simulate Windows constants and process creation on non-Windows test hosts.
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    kwargs = hidden_process_kwargs("nt")
    assert kwargs == {"creationflags": subprocess.CREATE_NO_WINDOW}
    assert hidden_process_kwargs("posix") == {}
    captured = {}

    def popen(args, **options):
        captured.update(options)
        return args

    monkeypatch.setattr("pydesktools_runtime.processes.subprocess.Popen", popen)
    monkeypatch.setattr("pydesktools_runtime.processes.hidden_process_kwargs", lambda: kwargs)
    assert background_popen(["worker.exe"], stdin=subprocess.PIPE) == ["worker.exe"]
    assert captured == {
        "stdin": subprocess.PIPE,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }


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
