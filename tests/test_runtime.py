import ast
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from pydesktools_runtime import RuntimeConfig, create_services
from pydesktools_runtime.plugins import inspect_bundle, venv_python
from pydesktools_sdk.protocol import read

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "src/pydesktools/bundles/json-tools.pdtplugin"
PLUGIN = "org.pydesk.json-tools"


@pytest.fixture
def services(tmp_path):
    service = create_services(RuntimeConfig(data_dir=tmp_path, python=Path(sys.executable)))
    yield service
    service.close()


def test_headless_import():
    subprocess.run(
        [
            sys.executable,
            "-c",
            'import pydesktools_runtime, pydesktools_sdk, sys; assert "tkinter" not in sys.modules; assert "pydeskui" not in sys.modules',
        ],
        check=True,
    )


def test_application_views_use_pydeskui_components():
    visible_tk_widgets = {
        "Button",
        "Canvas",
        "Entry",
        "Frame",
        "Label",
        "Listbox",
        "Text",
        "Toplevel",
    }
    violations = []
    for path in (ROOT / "src/pydesktools/app.py", ROOT / "src/pydesktools/ui.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            owner = node.func.value
            if isinstance(owner, ast.Name) and (
                owner.id == "ttk" or (owner.id == "tk" and node.func.attr in visible_tk_widgets)
            ):
                violations.append(f"{path.name}:{node.lineno}:{owner.id}.{node.func.attr}")
    assert not violations


@pytest.mark.parametrize(
    "payload",
    [
        b"[]\n",
        b'{"jsonrpc":"2.0","jsonrpc":"2.0"}\n',
        b'{"jsonrpc":"2.0","id":"h-1","result":NaN}\n',
        b"x" * (1024 * 1024 + 1),
    ],
)
def test_protocol_rejects(payload):
    with pytest.raises(ValueError):
        read(io.BytesIO(payload))


def test_locale_updates_runtime_and_installer(services):
    services.set_locale("zh-CN")
    assert services.locale == "zh-CN"
    assert services.installer.locale == "zh-CN"


def test_artifact_ownership(services, tmp_path):
    source = tmp_path / "source"
    source.write_text("private")
    identifier = services.artifacts.import_file("a", "session", source)
    with pytest.raises(Exception):
        services.artifacts.path("b", identifier)
    services.artifacts.acquire("a", identifier, "view")
    services.artifacts.release("session")
    assert services.artifacts.path("a", identifier).read_text() == "private"
    services.artifacts.release("view")
    with pytest.raises(Exception):
        services.artifacts.path("a", identifier)
    with pytest.raises(Exception):
        services.artifacts.import_file("a", "s", "../source", export_root=tmp_path)


def test_offline_lifecycle(services):
    plugin_previously_imported = "pydesk_json_tools" in sys.modules
    assert services.install(BUNDLE, consent=True) == PLUGIN
    assert not services.store.get(PLUGIN)["enabled"]
    services.enable(PLUGIN)
    result = services.submit(
        PLUGIN, "format", {"text": '{"n": 12345678901234567890.123456789}'}
    ).result(20)
    assert "12345678901234567890.123456789" in result["data"]["text"]
    worker = services._workers[PLUGIN]
    assert worker.process.pid != os.getpid()
    assert ("pydesk_json_tools" in sys.modules) == plugin_previously_imported
    assert Path(worker.process.args[0]) == venv_python(
        Path(services.store.get(PLUGIN)["path"]) / "venv"
    )
    services.disable(PLUGIN)
    assert worker.process.poll() is not None
    assert not services.store.get(PLUGIN)["enabled"]
    services.uninstall(PLUGIN)
    assert services.store.decision(PLUGIN) == "uninstalled"
    assert not services.store.get(PLUGIN)
    services.install(BUNDLE, consent=True, official=True)
    assert services.store.get(PLUGIN)["enabled"]
    assert services.submit(PLUGIN, "minify", {"text": "{}"}).result(10)["data"]["text"] == "{}"


def test_large_artifact(services):
    services.install(BUNDLE, consent=True, official=True)
    source = '{"text": "' + "世" * 30000 + '"}'
    identifier = services.import_text(PLUGIN, source)
    result = services.submit(PLUGIN, "minify", {"artifact_id": identifier}).result(20)
    assert result["data"]["truncated"]
    assert "text" not in result["data"]
    output = services.artifacts.path(PLUGIN, result["data"]["artifact_id"]).read_text()
    assert json.loads(output) == json.loads(source)
    assert len(result["view"]["body"].encode()) <= 65536


def test_malformed_bundle_rejected(tmp_path):
    bad = tmp_path / "bad.pdtplugin"
    with zipfile.ZipFile(bad, "w") as archive:
        archive.writestr("../escape", b"x")
    with pytest.raises(ValueError):
        inspect_bundle(bad)
