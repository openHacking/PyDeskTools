"""Fail closed when a tag, package versions, changelog, or runtime matrix diverges."""

import argparse
import json
import runpy
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_version(path):
    return tomllib.loads(path.read_text())["project"]["version"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    version = runpy.run_path(ROOT / "src/pydesktools/_version.py")["VERSION"]
    if args.tag != f"v{version}":
        raise SystemExit(f"tag {args.tag!r} does not match application version {version!r}")
    changelog = (ROOT / "CHANGELOG.md").read_text()
    if f"## {version}" not in changelog or f"## {version} (unreleased)" in changelog:
        raise SystemExit("CHANGELOG must contain a released version heading")
    runtime = json.loads((ROOT / "runtime-sources.json").read_text())
    expected = {"macos-arm64", "windows-x86_64", "linux-x86_64"}
    if set(runtime["targets"]) != expected:
        raise SystemExit("plugin runtime target matrix is incomplete")
    packages = {
        "sdk": project_version(ROOT / "packages/pydesktools-sdk/pyproject.toml"),
        "runtime": project_version(ROOT / "packages/pydesktools-runtime/pyproject.toml"),
        "json": project_version(ROOT / "plugins/json-tools/pyproject.toml"),
        "image": project_version(ROOT / "plugins/image-compressor/pyproject.toml"),
    }
    expected_versions = {"sdk": "0.1.1", "runtime": "0.1.1", "json": "0.1.1", "image": "0.2.2"}
    if packages != expected_versions:
        raise SystemExit(f"unexpected component versions: {packages}")
    print(json.dumps({"tag": args.tag, "application": version, "components": packages}))


if __name__ == "__main__":
    main()
