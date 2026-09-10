from pathlib import Path

from pydesktools_runtime.plugins import platform_label, venv_python


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
