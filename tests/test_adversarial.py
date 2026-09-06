import hashlib
import io
import json
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from pydesktools_runtime import RuntimeConfig, create_services
from pydesktools_runtime.plugins import inspect_bundle
from pydesktools_sdk import CancellationToken, PluginError

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "build/wheelhouse/pydesktools_sdk-0.1.0-py3-none-any.whl"


def wheel(name, version, module, source, requires=()):
    result = io.BytesIO()
    dist = name.replace("-", "_")
    info = f"{dist}-{version}.dist-info"
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr(module + "/__init__.py", source)
        archive.writestr(
            info + "/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            + "".join(f"Requires-Dist: {r}\n" for r in requires),
        )
        archive.writestr(
            info + "/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        archive.writestr(info + "/RECORD", "")
    return f"{dist}-{version}-py3-none-any.whl", result.getvalue()


PLUGIN_SOURCE = """
import os, time
from pydesktools_sdk import CommandResult
import fixturedep
class Plugin:
    def activate(self, context): pass
    def describe(self):
        return {"commands":[{"id":"run","title":"Run","description":"Fixture","effects":"pure","retry":"safe","timeout_ms":1000,
            "input_schema":{"type":"object","properties":{"mode":{"type":"string"}},"additionalProperties":False},
            "output_schema":{"type":"object","properties":{"value":{"type":"string"}},"required":["value"],"additionalProperties":False}}]}
    def invoke(self, command, arguments, context):
        mode = arguments.get("mode", "version")
        if mode == "crash": os._exit(7)
        if mode == "noise": os.write(1, b"not-rpc\\n"); time.sleep(2)
        if mode == "flood": os.write(1, b"x" * (2 * 1024 * 1024)); time.sleep(30)
        if mode in ("hang", "timeout"): time.sleep(30)
        if mode == "wait":
            while True:
                context.cancellation.raise_if_cancelled()
                time.sleep(.01)
        return CommandResult({"value":fixturedep.VERSION})
    def deactivate(self): pass
def create_plugin(): return Plugin()
"""


def bundle(tmp_path, identifier, dep_version):
    dist = identifier.replace(".", "-")
    dependencies = [f"fixturedep=={dep_version}", "pydesktools-sdk==0.1.0"]
    filename, payload = wheel(dist, "0.1.0", "fixtureplugin", PLUGIN_SOURCE, dependencies)
    depname, dep = wheel("fixturedep", dep_version, "fixturedep", f"VERSION = {dep_version!r}\n")
    files = {
        f"wheels/{filename}": payload,
        f"wheels/{depname}": dep,
        f"wheels/{SDK.name}": SDK.read_bytes(),
    }
    pins = [
        (dist, "0.1.0", payload),
        ("fixturedep", dep_version, dep),
        ("pydesktools-sdk", "0.1.0", SDK.read_bytes()),
    ]
    files["requirements.lock"] = "".join(
        f"{name}=={version} --hash=sha256:{hashlib.sha256(data).hexdigest()}\n"
        for name, version, data in pins
    ).encode()
    files["plugin.toml"] = f'''schema=1
id="{identifier}"
name="Fixture"
version="0.1.0"
distribution="{dist}"
entrypoint="fixtureplugin:create_plugin"
requires_python=">=3.13,<3.14"
requires_sdk=">=0.1,<0.2"
protocol=1
platforms=["macos-arm64"]
languages=["en"]
capabilities=[]
'''.encode()
    files["files.json"] = json.dumps(
        {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    ).encode()
    path = tmp_path / (identifier + ".pdtplugin")
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return path


@pytest.fixture
def services(tmp_path):
    service = create_services(
        RuntimeConfig(data_dir=tmp_path / "profile", python=Path(sys.executable))
    )
    yield service
    service.close()


def test_conflicting_dependencies(services, tmp_path):
    for identifier, version in [("fixture.one", "1.0"), ("fixture.two", "2.0")]:
        services.install(bundle(tmp_path, identifier, version), consent=True, official=True)
    first = services.submit("fixture.one", "run", {})
    second = services.submit("fixture.two", "run", {})
    assert first.result(10)["data"]["value"] == "1.0"
    assert second.result(10)["data"]["value"] == "2.0"
    assert "fixturedep" not in sys.modules
    assert (
        services._workers["fixture.one"].process.pid != services._workers["fixture.two"].process.pid
    )


@pytest.mark.parametrize("mode", ["wait", "hang", "crash", "noise", "flood", "timeout"])
def test_cancel_crash_and_noise(services, tmp_path, mode):
    services.install(bundle(tmp_path, "fixture.failure", "1.0"), consent=True, official=True)
    task = services.submit("fixture.failure", "run", {"mode": mode})
    if mode in ("wait", "hang"):
        time.sleep(0.3)
        task.cancel()
    with pytest.raises(PluginError) as error:
        task.result(8)
    if mode == "wait":
        assert error.value.kind == "canceled"
    elif mode in ("hang", "crash", "noise", "flood", "timeout"):
        assert error.value.details.get("completion_unknown")
    worker = services._workers["fixture.failure"]
    services.disable("fixture.failure")
    assert worker.process.poll() is not None


def test_install_cancel_and_reconcile(services, tmp_path):
    path = bundle(tmp_path, "fixture.cancel", "1.0")
    token = CancellationToken()

    def progress(phase):
        if phase == "dependencies":
            token.cancel()

    with pytest.raises(PluginError):
        services.install(path, consent=True, token=token, progress=progress)
    assert not services.store.get("fixture.cancel")
    assert not list((services.store.root / "plugins").glob("*/installs/*"))
    services.install(path, consent=True, official=True)
    record = services.store.get("fixture.cancel")
    services.store.execute("INSERT INTO journal VALUES (?,?)", (record["path"], "commit"))
    orphan = services.store.root / "plugins/fixture.cancel/installs/orphan"
    orphan.mkdir()
    services.store.execute("INSERT INTO journal VALUES (?,?)", (str(orphan), "dependencies"))
    services.installer.reconcile()
    assert Path(record["path"]).exists()
    assert not orphan.exists()


def test_unsafe_archives(tmp_path):
    for index, name in enumerate(["/absolute", "../escape", "dir/../../escape", "CON", "x\\y"]):
        path = tmp_path / f"bad{index}.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(name, b"bad")
        with pytest.raises(ValueError):
            inspect_bundle(path)


def test_consent_and_profile_lock(services, tmp_path):
    with pytest.raises(PluginError):
        services.install(bundle(tmp_path, "fixture.consent", "1.0"))
    with pytest.raises(RuntimeError, match="already open"):
        create_services(RuntimeConfig(data_dir=services.store.root))


def test_cancel_completion_race(services, tmp_path):
    services.install(bundle(tmp_path, "fixture.race", "1.0"), consent=True, official=True)
    for delay in (0, 0.001, 0.01, 0.03, 0.1):
        task = services.submit("fixture.race", "run", {})
        timer = threading.Timer(delay, task.cancel)
        timer.start()
        try:
            try:
                assert task.result(5)["data"]["value"] == "1.0"
            except PluginError as error:
                assert error.kind == "canceled" or error.details.get("completion_unknown")
        finally:
            timer.join()
        # A previous session's completion/cancellation cannot poison the next call.
        assert services.submit("fixture.race", "run", {}).result(5)["data"]["value"] == "1.0"
