import json
import re
from pathlib import Path

import pytest
from pydesktools_runtime.plugins import inspect_bundle

from pydesktools import __version__
from pydesktools.app import packaged_runtime_path

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
