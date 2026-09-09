"""Build a self-contained arm64 app/DMG. Never silently downgrade signing."""

import argparse
import json
import os
import platform
import plistlib
import shutil
from importlib import metadata
from pathlib import Path

from build_support import (
    ROOT,
    app_version,
    pyinstaller_args,
    run,
    runtime_source,
    sha256,
    verify_builder,
    verify_runtime,
)

TARGET = "macos-arm64"


def main():
    version = app_version()
    runtime_config, runtime_entry = runtime_source(TARGET)
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
    verify_builder(TARGET)
    source, _, _ = verify_runtime(args.runtime_source, TARGET)
    if args.notary_profile and args.identity == "-":
        raise ValueError("Notarization requires a Developer ID identity")
    env = dict(os.environ)
    # PyDeskUI needs Tk 9 in the GUI; the pinned worker interpreter is headless.
    # Do not point PyInstaller's Tk hook at the worker runtime's Tcl/Tk 8.6.
    env.pop("TCL_LIBRARY", None)
    env.pop("TK_LIBRARY", None)
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    # The application build environment must already contain the reviewed wheels.
    installer = pyinstaller_args(TARGET, ROOT / "src/pydesktools/assets/logo.icns")
    installer[-1:-1] = [
        "--target-arch",
        "arm64",
        "--osx-bundle-identifier",
        "org.pydesk.tools",
        "--codesign-identity",
        args.identity,
    ]
    run(*installer, env=env, cwd=ROOT)
    app = ROOT / "dist/PyDeskTools.app"
    shutil.copytree(
        ROOT / "licenses", app / "Contents/Resources/THIRD_PARTY_LICENSES", dirs_exist_ok=True
    )
    shutil.copyfile(
        ROOT / "THIRD_PARTY_NOTICES.md", app / "Contents/Resources/THIRD_PARTY_NOTICES.md"
    )
    shutil.copyfile(ROOT / "LICENSE", app / "Contents/Resources/LICENSE")
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
        "version": runtime_config["python"],
        "abi": "cp313",
        "architecture": runtime_entry["architecture"],
        "build": runtime_config["build"],
        "source": runtime_entry["url"],
        "executable": runtime_entry["executable"],
        "sha256": sha256(runtime / runtime_entry["executable"]),
    }
    manifest["files"] = {
        str(p.relative_to(runtime)): sha256(p)
        for p in sorted(runtime.rglob("*"))
        if p.is_file() and not p.is_symlink()
    }
    (runtime / "runtime.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with (app / "Contents/Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    info.update(CFBundleShortVersionString=version, CFBundleVersion="1")
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
    label = "adhoc" if args.identity == "-" else "developer-id"
    suffix = "-adhoc" if args.identity == "-" else ""
    dmg = ROOT / "dist" / f"PyDeskTools-{version}-macos-arm64{suffix}.dmg"
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
    (ROOT / f"dist/build-manifest-{TARGET}.json").write_text(
        json.dumps(
            {
                "platform": platform.platform(),
                "application_version": version,
                "target": TARGET,
                "runtime": {k: v for k, v in manifest.items() if k != "files"},
                "signing": label,
                "notarized": bool(args.notary_profile),
                "dmg_sha256": sha256(dmg),
                "dependencies": inventory,
            },
            indent=2,
        )
        + "\n"
    )
    print(dmg)


if __name__ == "__main__":
    main()
