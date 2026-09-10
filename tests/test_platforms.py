import subprocess
import sys
from pathlib import Path

import pytest
from pydesktools_runtime.plugins import platform_label, venv_python
from pydesktools_runtime.processes import terminate_process
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
