"""Build complete CPython 3.13 macOS arm64 offline first-party bundles."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from packaging.utils import parse_wheel_filename
from packaging.version import Version

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
    for package in (
        "packages/pydesktools-sdk",
        "plugins/json-tools",
        "plugins/image-compressor",
    ):
        project = ROOT / package
        shutil.rmtree(project / "build", ignore_errors=True)
        run(
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            wheels,
            project,
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
            "Pillow==12.3.0",
        )
    manifests = {
        "json-tools.pdtplugin": """schema = 1
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
""",
        "image-compressor.pdtplugin": """schema = 1
id = "org.pydesk.image-compressor"
name = "Image Compressor"
version = "0.2.0"
distribution = "pydesk-image-compressor"
entrypoint = "pydesk_image_compressor:create_plugin"
requires_python = ">=3.13,<3.14"
requires_sdk = ">=0.1,<0.2"
protocol = 1
platforms = ["macos-arm64"]
languages = ["en", "zh-CN"]
capabilities = ["dialogs.open_files"]
""",
    }
    requirements = {
        "json-tools.pdtplugin": ("pydesktools-sdk", "pydesk-json-tools", "simplejson"),
        "image-compressor.pdtplugin": (
            "pydesktools-sdk",
            "pydesk-image-compressor",
            "pillow",
        ),
    }
    available: dict[str, tuple[Version, Path]] = {}
    for wheel in wheels.glob("*.whl"):
        name, version, _, _ = parse_wheel_filename(wheel.name)
        key = str(name)
        if key not in available or version > available[key][0]:
            available[key] = (version, wheel)
    directory = ROOT / "src/pydesktools/bundles"
    directory.mkdir(exist_ok=True)
    inventory = {}
    for filename, manifest in manifests.items():
        payload = {"plugin.toml": manifest.encode()}
        lock = []
        try:
            selected = [available[name][1] for name in requirements[filename]]
        except KeyError as error:
            raise RuntimeError(f"Missing wheel for {error.args[0]}") from None
        for wheel in selected:
            data = wheel.read_bytes()
            name, version, _, _ = parse_wheel_filename(wheel.name)
            lock.append(f"{name}=={version} --hash=sha256:{hashlib.sha256(data).hexdigest()}")
            payload["wheels/" + wheel.name] = data
        payload["requirements.lock"] = ("\n".join(lock) + "\n").encode()
        payload["files.json"] = json.dumps(
            {name: hashlib.sha256(data).hexdigest() for name, data in payload.items()},
            sort_keys=True,
        ).encode()
        output = directory / filename
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(payload.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        inventory[output.name] = hashlib.sha256(output.read_bytes()).hexdigest()
        print(output)
    (directory / "inventory.json").write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
