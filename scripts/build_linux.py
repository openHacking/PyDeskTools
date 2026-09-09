"""Build the Linux x86_64 AppImage on a native runner."""

import argparse
import os
import shutil
from pathlib import Path

from build_support import (
    ROOT,
    app_version,
    copy_legal,
    copy_runtime,
    pyinstaller_args,
    run,
    verify_builder,
    write_build_manifest,
)

TARGET = "linux-x86_64"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--appimagetool", type=Path, required=True)
    args = parser.parse_args()
    verify_builder(TARGET)
    shutil.rmtree(ROOT / "dist/PyDeskTools", ignore_errors=True)
    env = dict(os.environ)
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    run(*pyinstaller_args(TARGET, ROOT / "src/pydesktools/assets/logo.png"), env=env, cwd=ROOT)
    application = ROOT / "dist/PyDeskTools"
    copy_legal(application)
    runtime = copy_runtime(args.runtime_source, application / "plugin-runtime", TARGET)

    appdir = ROOT / "build/PyDeskTools.AppDir"
    shutil.rmtree(appdir, ignore_errors=True)
    (appdir / "usr/lib").mkdir(parents=True)
    shutil.copytree(application, appdir / "usr/lib/PyDeskTools", symlinks=True)
    shutil.copyfile(ROOT / "packaging/linux/AppRun", appdir / "AppRun")
    shutil.copyfile(ROOT / "packaging/linux/pydesktools.desktop", appdir / "pydesktools.desktop")
    shutil.copyfile(ROOT / "src/pydesktools/assets/logo.png", appdir / "pydesktools.png")
    (appdir / "AppRun").chmod(0o755)
    args.appimagetool.chmod(0o755)
    artifact = ROOT / "dist" / f"PyDeskTools-{app_version()}-linux-x86_64.AppImage"
    tool_env = dict(env, ARCH="x86_64", APPIMAGE_EXTRACT_AND_RUN="1")
    run(args.appimagetool, appdir, artifact, env=tool_env, cwd=ROOT)
    artifact.chmod(0o755)
    manifest = write_build_manifest(
        TARGET, artifact, runtime, signing="github-attestation", display="X11/XWayland"
    )
    print(artifact)
    print(manifest)


if __name__ == "__main__":
    main()
