"""Build a self-contained arm64 app/DMG. Never silently downgrade signing."""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://github.com/astral-sh/python-build-standalone/releases/download/20250918/cpython-3.13.7%2B20250918-aarch64-apple-darwin-install_only_stripped.tar.gz"


def run(*args, **kwargs):
    subprocess.run(list(map(str, args)), check=True, **kwargs)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-source",
        type=Path,
        required=True,
        help="Extracted pinned Python 3.13.7 standalone install",
    )
    parser.add_argument(
        "--identity", default="-", help="Developer ID identity; '-' is an ad-hoc test build"
    )
    parser.add_argument(
        "--notary-profile", help="Existing notarytool keychain profile; requires Developer ID"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Build requires macOS arm64")
    source = args.runtime_source.resolve()
    if (source / "BUILD").read_text().strip() != "20250918":
        raise RuntimeError("Expected pinned standalone build 20250918")
    if (
        subprocess.check_output(
            [
                str(source / "bin/python3.13"),
                "-I",
                "-c",
                "import platform; print(platform.python_version())",
            ],
            text=True,
        ).strip()
        != "3.13.7"
    ):
        raise RuntimeError("Expected CPython 3.13.7")
    if args.notary_profile and args.identity == "-":
        raise ValueError("Notarization requires a Developer ID identity")
    env = dict(os.environ)
    env["TCL_LIBRARY"] = str(source / "lib/tcl8.6")
    env["TK_LIBRARY"] = str(source / "lib/tk8.6")
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    # The application build environment must already contain the reviewed wheels.
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "PyDeskTools",
        "--target-arch",
        "arm64",
        "--osx-bundle-identifier",
        "org.pydesk.tools",
        "--codesign-identity",
        args.identity,
        "--copy-metadata",
        "pydesktools-sdk",
        "--copy-metadata",
        "pydesktools-runtime",
        "--copy-metadata",
        "pydeskui",
        "--collect-data",
        "pydesktools",
        "--collect-data",
        "pydeskui",
        "--exclude-module",
        "pydesk_json_tools",
        "--exclude-module",
        "simplejson",
        "--distpath",
        ROOT / "dist",
        "--workpath",
        ROOT / "build/pyinstaller",
        "--specpath",
        ROOT / "build",
        ROOT / "scripts/desktop_entry.py",
        env=env,
        cwd=ROOT,
    )
    app = ROOT / "dist/PyDeskTools.app"
    shutil.copytree(
        ROOT / "licenses", app / "Contents/Resources/THIRD_PARTY_LICENSES", dirs_exist_ok=True
    )
    shutil.copyfile(
        ROOT / "THIRD_PARTY_NOTICES.md", app / "Contents/Resources/THIRD_PARTY_NOTICES.md"
    )
    runtime = app / "Contents/Resources/plugin-runtime"
    shutil.copytree(
        source,
        runtime,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.a", "pkgconfig"),
    )
    # Keep the worker runtime addressable. Its interpreter is never the GUI executable.
    for path in sorted(runtime.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as stream:
            magic = stream.read(4)
        if magic in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xca\xfe\xba\xbe"):
            options = ["--options", "runtime", "--timestamp"] if args.identity != "-" else []
            run("codesign", "--force", "--sign", args.identity, *options, path)
    manifest = {
        "version": "3.13.7",
        "abi": "cp313",
        "architecture": "arm64",
        "build": "20250918",
        "source": SOURCE,
        "executable": "bin/python3.13",
        "sha256": sha(runtime / "bin/python3.13"),
    }
    manifest["files"] = {
        str(p.relative_to(runtime)): sha(p)
        for p in sorted(runtime.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }
    (runtime / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (app / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    info.update(CFBundleShortVersionString="0.1.0", CFBundleVersion="1")
    with (app / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(info, stream)
    options = ["--options", "runtime", "--timestamp"] if args.identity != "-" else []
    run("codesign", "--force", "--sign", args.identity, *options, app)
    run("codesign", "--verify", "--deep", "--strict", app)
    staging = ROOT / "build/dmg"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    shutil.copytree(app, staging / app.name, symlinks=True)
    (staging / "Applications").symlink_to("/Applications")
    label = "adhoc" if args.identity == "-" else "signed"
    dmg = ROOT / "dist" / f"PyDeskTools-0.1.0-macos-arm64-{label}.dmg"
    run(
        "hdiutil",
        "create",
        "-volname",
        "PyDeskTools",
        "-srcfolder",
        staging,
        "-ov",
        "-format",
        "UDZO",
        dmg,
    )
    if args.identity != "-":
        run("codesign", "--sign", args.identity, "--timestamp", dmg)
    if args.notary_profile:
        run(
            "xcrun",
            "notarytool",
            "submit",
            dmg,
            "--keychain-profile",
            args.notary_profile,
            "--wait",
        )
        run("xcrun", "stapler", "staple", dmg)
        run("xcrun", "stapler", "validate", dmg)
    inventory = {d.metadata["Name"]: d.version for d in metadata.distributions()}
    (ROOT / "dist/build-manifest.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "runtime": {k: v for k, v in manifest.items() if k != "files"},
                "signing": label,
                "notarized": bool(args.notary_profile),
                "dmg_sha256": sha(dmg),
                "dependencies": inventory,
            },
            indent=2,
        )
        + "\n"
    )
    print(dmg)


if __name__ == "__main__":
    main()
