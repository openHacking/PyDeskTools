"""Fetch and verify a pinned python-build-standalone plugin runtime."""

import argparse
import hashlib
import json
import shutil
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads((ROOT / "runtime-sources.json").read_text())
    source = config["targets"].get(args.target)
    if source is None:
        parser.error(f"unknown target: {args.target}")
    archive = ROOT / "build/runtime-downloads" / Path(source["url"]).name.replace("%2B", "+")
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
        archive.unlink(missing_ok=True)
        urllib.request.urlretrieve(source["url"], archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != source["sha256"]:
        raise RuntimeError("Downloaded plugin runtime failed SHA-256 verification")
    shutil.rmtree(args.output, ignore_errors=True)
    args.output.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(args.output, filter="data")
    runtime = args.output / "python"
    executable = runtime / source["executable"]
    if not executable.is_file():
        raise RuntimeError(f"Runtime executable missing: {executable}")
    (runtime / "BUILD").write_text(config["build"] + "\n")
    print(runtime)


if __name__ == "__main__":
    main()
