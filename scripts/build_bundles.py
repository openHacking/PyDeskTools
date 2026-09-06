"""Build the complete CPython 3.13 macOS arm64 offline JSON bundle."""

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    subprocess.run(list(map(str, args)), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--offline", action="store_true", help="Require already downloaded wheelhouse"
    )
    args = parser.parse_args()
    wheels = ROOT / "build/wheelhouse"
    wheels.mkdir(parents=True, exist_ok=True)
    for package in ("packages/pydesktools-sdk", "plugins/json-tools"):
        run(
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            wheels,
            ROOT / package,
        )
    if not args.offline:
        run(
            sys.executable,
            "-m",
            "pip",
            "download",
            "--only-binary=:all:",
            "--no-deps",
            "--dest",
            wheels,
            "simplejson==3.20.2",
        )
    selected = sorted(
        p
        for p in wheels.glob("*.whl")
        if p.name.startswith(("simplejson-", "pydesktools_sdk-", "pydesk_json_tools-"))
    )
    if len(selected) != 3:
        raise RuntimeError("Expected exactly the SDK, JSON plugin and simplejson wheels")
    manifest = """schema = 1
id = "org.pydesk.json-tools"
name = "JSON Tools"
version = "0.1.0"
distribution = "pydesk-json-tools"
entrypoint = "pydesk_json_tools:create_plugin"
requires_python = ">=3.13,<3.14"
requires_sdk = ">=0.1,<0.2"
protocol = 1
platforms = ["macos-arm64"]
languages = ["en", "zh-CN"]
capabilities = ["dialogs.open_file", "dialogs.save_file", "clipboard.write"]
"""
    payload = {"plugin.toml": manifest.encode()}
    lock = []
    for wheel in selected:
        data = wheel.read_bytes()
        name, version, _, _ = parse_wheel_filename(wheel.name)
        lock.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(data).hexdigest()}")
        payload["wheels/" + wheel.name] = data
    payload["requirements.lock"] = ("\n".join(lock) + "\n").encode()
    payload["files.json"] = json.dumps(
        {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()}, sort_keys=True
    ).encode()
    directory = ROOT / "src/pydesktools/bundles"
    directory.mkdir(exist_ok=True)
    output = directory / "json-tools.pdtplugin"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    (directory / "inventory.json").write_text(
        json.dumps({output.name: hashlib.sha256(output.read_bytes()).hexdigest()}, indent=2) + "\n"
    )
    print(output)


if __name__ == "__main__":
    main()
