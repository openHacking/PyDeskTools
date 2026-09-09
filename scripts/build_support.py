"""Shared, deterministic helpers for native desktop release builders."""

import hashlib
import json
import platform
import runpy
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def app_version():
    return runpy.run_path(ROOT / "src/pydesktools/_version.py")["VERSION"]


def runtime_source(target):
    config = json.loads((ROOT / "runtime-sources.json").read_text())
    return config, config["targets"][target]


def verify_builder(target):
    import tkinter

    expected = {
        "macos-arm64": ("Darwin", {"arm64", "aarch64"}),
        "windows-x86_64": ("Windows", {"AMD64", "amd64", "x86_64"}),
        "linux-x86_64": ("Linux", {"AMD64", "amd64", "x86_64"}),
    }[target]
    if platform.system() != expected[0] or platform.machine() not in expected[1]:
        raise RuntimeError(f"{target} must be built on its native {expected[0]} x64/arm64 runner")
    if tkinter.TkVersion < 9:
        raise RuntimeError(f"PyDeskTools requires Tk 9; builder provides {tkinter.TkVersion}")


def verify_runtime(source, target):
    config, entry = runtime_source(target)
    source = Path(source).resolve()
    if (source / "BUILD").read_text().strip() != config["build"]:
        raise RuntimeError(f"Expected pinned standalone build {config['build']}")
    executable = source / entry["executable"]
    version = subprocess.check_output(
        [str(executable), "-I", "-c", "import platform; print(platform.python_version())"],
        text=True,
    ).strip()
    if version != config["python"]:
        raise RuntimeError(f"Expected CPython {config['python']}; received {version}")
    return source, config, entry


def copy_legal(destination):
    destination = Path(destination)
    shutil.copytree(ROOT / "licenses", destination / "THIRD_PARTY_LICENSES", dirs_exist_ok=True)
    shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md")
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")


def copy_runtime(source, destination, target):
    source, config, entry = verify_runtime(source, target)
    destination = Path(destination)
    shutil.copytree(
        source,
        destination,
        symlinks=True,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.a", "pkgconfig"),
    )
    executable = destination / entry["executable"]
    manifest = {
        "version": config["python"],
        "abi": "cp313",
        "architecture": entry["architecture"],
        "build": config["build"],
        "source": entry["url"],
        "executable": entry["executable"],
        "sha256": sha256(executable),
    }
    manifest["files"] = {
        str(path.relative_to(destination)): sha256(path)
        for path in sorted(destination.rglob("*"))
        if path.is_file() and not path.is_symlink() and path.name != "runtime.json"
    }
    (destination / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def pyinstaller_args(target, icon):
    args = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "PyDeskTools",
        "--copy-metadata",
        "pydesktools-sdk",
        "--copy-metadata",
        "pydesktools-runtime",
        "--copy-metadata",
        "pydeskui",
        "--copy-metadata",
        "tkinterdnd2",
        "--icon",
        icon,
        "--collect-data",
        "pydesktools",
        "--collect-data",
        "pydeskui",
        "--collect-all",
        "tkinterdnd2",
        "--exclude-module",
        "pydesk_json_tools",
        "--exclude-module",
        "simplejson",
        "--distpath",
        ROOT / "dist",
        "--workpath",
        ROOT / f"build/pyinstaller-{target}",
        "--specpath",
        ROOT / "build",
        ROOT / "scripts/desktop_entry.py",
    ]
    return args


def write_build_manifest(target, artifact, runtime, **extra):
    output = ROOT / "dist" / f"build-manifest-{target}.json"
    output.write_text(
        json.dumps(
            {
                "application_version": app_version(),
                "target": target,
                "platform": platform.platform(),
                "python": platform.python_version(),
                "runtime": {key: value for key, value in runtime.items() if key != "files"},
                "artifact": Path(artifact).name,
                "artifact_sha256": sha256(artifact),
                "dependencies": {item.metadata["Name"]: item.version for item in metadata.distributions()},
                **extra,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return output
