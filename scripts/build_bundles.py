"""Build native offline first-party bundles for the pinned CPython 3.13 worker."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from build_support import verify_builder, verify_runtime
from packaging.tags import parse_tag
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
    parser.add_argument(
        "--target",
        choices=("macos-arm64", "windows-x86_64", "linux-x86_64"),
        default="macos-arm64",
        help="Platform label embedded in the first-party plugin manifests",
    )
    parser.add_argument(
        "--runtime-source",
        type=Path,
        help="Extracted pinned plugin runtime; defaults to build/plugin-runtime/TARGET/python",
    )
    args = parser.parse_args()
    verify_builder(args.target)
    runtime_source = (
        args.runtime_source or ROOT / "build/plugin-runtime" / args.target / "python"
    )
    runtime, _, runtime_entry = verify_runtime(runtime_source, args.target)
    runtime_python = runtime / runtime_entry["executable"]
    wheels = ROOT / "build/wheelhouse" / args.target
    wheels.mkdir(parents=True, exist_ok=True)
    if not args.offline:
        for stale_wheel in wheels.glob("*.whl"):
            stale_wheel.unlink()
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
            runtime_python,
            "-I",
            "-m",
            "pip",
            "--isolated",
            "download",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--no-deps",
            "--dest",
            wheels,
            "simplejson==3.20.2",
            "Pillow==12.3.0",
        )
    manifests = {
        "json-tools.pdtplugin": f"""schema = 1
id = "org.pydesk.json-tools"
name = "JSON Tools"
version = "0.1.1"
distribution = "pydesk-json-tools"
entrypoint = "pydesk_json_tools:create_plugin"
requires_python = ">=3.13,<3.14"
requires_sdk = ">=0.1.1,<0.2"
protocol = 1
platforms = ["{args.target}"]
languages = ["en", "zh-CN"]
capabilities = ["dialogs.open_file", "dialogs.save_file", "clipboard.write"]
""",
        "image-compressor.pdtplugin": f"""schema = 1
id = "org.pydesk.image-compressor"
name = "Image Compressor"
version = "0.2.2"
distribution = "pydesk-image-compressor"
entrypoint = "pydesk_image_compressor:create_plugin"
requires_python = ">=3.13,<3.14"
requires_sdk = ">=0.1.1,<0.2"
protocol = 1
platforms = ["{args.target}"]
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
    tag_text = subprocess.check_output(
        [
            str(runtime_python),
            "-I",
            "-c",
            "from pip._vendor.packaging.tags import sys_tags; print(chr(10).join(map(str, sys_tags())))",
        ],
        text=True,
    )
    compatible_tags = set().union(*(parse_tag(line) for line in tag_text.splitlines()))
    available: dict[str, tuple[Version, Path]] = {}
    for wheel in wheels.glob("*.whl"):
        name, version, _, tags = parse_wheel_filename(wheel.name)
        if not tags.intersection(compatible_tags):
            raise RuntimeError(
                f"Wheel {wheel.name} is incompatible with the native {args.target} builder"
            )
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
