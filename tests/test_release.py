import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

import pytest
from pydesktools_runtime.plugins import inspect_bundle
from pydesktools_runtime.storage import ProfileInUseError

from pydesktools import __version__
from pydesktools import app as application_module
from pydesktools.app import ApplicationConfig, packaged_runtime_path, runtime_python

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("readme", ["README.md", "README.zh-CN.md"])
def test_readme_local_links_exist(readme):
    source = (ROOT / readme).read_text()
    missing = []
    for target in re.findall(r"!?\[[^]]*\]\(([^)]+)\)", source):
        if "://" in target or target.startswith("#"):
            continue
        path = target.split("#", 1)[0]
        if path and not (ROOT / path).exists():
            missing.append(path)
    assert not missing


def test_release_version_and_runtime_matrix():
    assert __version__ == "0.1.0"
    runtime = json.loads((ROOT / "runtime-sources.json").read_text())
    assert runtime["python"] == "3.13.7"
    assert set(runtime["targets"]) == {
        "macos-arm64",
        "windows-x86_64",
        "linux-x86_64",
    }
    assert all(len(target["sha256"]) == 64 for target in runtime["targets"].values())


def test_bundled_plugins_match_local_release_target():
    for name in ("json-tools.pdtplugin", "image-compressor.pdtplugin"):
        manifest, _ = inspect_bundle(ROOT / "src/pydesktools/bundles" / name)
        assert manifest["platforms"] == ["macos-arm64"]


def test_packaged_runtime_locations(tmp_path):
    windows = tmp_path / "windows"
    (windows / "plugin-runtime").mkdir(parents=True)
    assert packaged_runtime_path(windows / "PyDeskTools.exe") == windows / "plugin-runtime"

    macos = tmp_path / "PyDeskTools.app/Contents"
    (macos / "MacOS").mkdir(parents=True)
    (macos / "Resources/plugin-runtime").mkdir(parents=True)
    assert (
        packaged_runtime_path(macos / "MacOS/PyDeskTools")
        == macos / "Resources/plugin-runtime"
    )

    bundle = tmp_path / "bundle"
    (bundle / "plugin-runtime").mkdir(parents=True)
    assert packaged_runtime_path(tmp_path / "elsewhere/PyDeskTools", bundle) == bundle / "plugin-runtime"


def test_packaged_runtime_accepts_another_process_winning_publish_race(tmp_path, monkeypatch):
    application = tmp_path / "application"
    resource = application / "plugin-runtime"
    resource.mkdir(parents=True)
    executable = resource / "python.exe"
    executable.write_bytes(b"python")
    manifest = {
        "executable": "python.exe",
        "files": {"python.exe": hashlib.sha256(b"python").hexdigest()},
    }
    (resource / "runtime.json").write_text(json.dumps(manifest))
    profile = tmp_path / "profile"
    real_copytree = shutil.copytree

    def copytree_with_competing_winner(source, destination, **kwargs):
        result = real_copytree(source, destination, **kwargs)
        runtime_id = hashlib.sha256((resource / "runtime.json").read_bytes()).hexdigest()[:20]
        winner = profile / "runtimes" / runtime_id
        real_copytree(source, winner, symlinks=True)
        return result

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(application / "PyDeskTools.exe"))
    monkeypatch.setattr(shutil, "copytree", copytree_with_competing_winner)

    assert runtime_python(ApplicationConfig(data_dir=profile)).read_bytes() == b"python"


def test_main_treats_an_open_profile_as_an_existing_instance(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pydesktools"])

    def already_running(config):
        raise ProfileInUseError("This application profile is already open")

    monkeypatch.setattr(application_module, "create_application", already_running)
    assert application_module.main() == 0
