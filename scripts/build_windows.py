"""Build the unsigned Windows x64 beta installer on a native runner."""

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

TARGET = "windows-x86_64"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-source", type=Path, required=True)
    parser.add_argument("--iscc", default="ISCC.exe")
    args = parser.parse_args()
    verify_builder(TARGET)
    icon = ROOT / "src/pydesktools/assets/logo.ico"
    if not icon.is_file():
        raise RuntimeError("Generate logo.ico with scripts/build_brand_assets.py first")
    shutil.rmtree(ROOT / "dist/PyDeskTools", ignore_errors=True)
    env = dict(os.environ)
    env["PYINSTALLER_CONFIG_DIR"] = str(ROOT / "build/pyinstaller-cache")
    run(*pyinstaller_args(TARGET, icon), env=env, cwd=ROOT)
    application = ROOT / "dist/PyDeskTools"
    copy_legal(application)
    runtime = copy_runtime(args.runtime_source, application / "plugin-runtime", TARGET)
    run(
        args.iscc,
        f"/DMyAppVersion={app_version()}",
        ROOT / "packaging/windows/PyDeskTools.iss",
        cwd=ROOT,
    )
    installer = ROOT / "dist" / f"PyDeskTools-{app_version()}-windows-x64-unsigned.exe"
    manifest = write_build_manifest(
        TARGET, installer, runtime, signing="unsigned", channel="beta"
    )
    print(installer)
    print(manifest)


if __name__ == "__main__":
    main()
