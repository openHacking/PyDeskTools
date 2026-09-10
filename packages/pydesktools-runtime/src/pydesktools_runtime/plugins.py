"""Validated offline bundles and final-path installation transactions."""

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import parse_tag
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version
from pydesktools_sdk import CancellationToken, PluginError
from pydesktools_sdk import __version__ as sdk_version
from pydesktools_sdk.protocol import descriptor

from .processes import WorkerProcess


def platform_label(system=None, machine=None):
    """Return the stable plugin-manifest label for a native desktop target."""
    import platform

    system = system or platform.system()
    machine = machine or platform.machine()
    operating_system = {
        "Darwin": "macos",
        "Windows": "windows",
        "Linux": "linux",
    }.get(system, "unsupported")
    architecture = {
        "AMD64": "x86_64",
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "ARM64": "arm64",
        "aarch64": "arm64",
    }.get(machine, machine.lower())
    return f"{operating_system}-{architecture}"


def venv_python(venv, system=None):
    """Return the native interpreter path created by ``python -m venv``."""
    import platform

    system = system or platform.system()
    return Path(venv) / ("Scripts/python.exe" if system == "Windows" else "bin/python")

MAX_BUNDLE = 200 * 1024 * 1024
MAX_EXPANDED = 1024 * 1024 * 1024


def safe_name(name):
    path = PurePosixPath(name)
    if (
        not name
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or ":" in name
        or any(
            part in ("", ".")
            or part.rstrip(". ") != part
            or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
            for part in path.parts
        )
    ):
        raise ValueError("Unsafe bundle path")
    return path


def inspect_bundle(path):
    path = Path(path)
    if path.stat().st_size > MAX_BUNDLE:
        raise ValueError("Bundle exceeds 200 MiB")
    with zipfile.ZipFile(path) as archive:
        infos = archive.infolist()
        if len(infos) > 10000 or sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("Expanded bundle exceeds limits")
        seen = set()
        for info in infos:
            safe_name(info.filename)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR)):
                raise ValueError("Nonregular bundle entry")
            folded = info.filename.casefold()
            if folded in seen or info.is_dir():
                raise ValueError("Duplicate or directory bundle entry")
            seen.add(folded)
        if "files.json" not in archive.namelist():
            raise ValueError("Bundle has no payload inventory")
        for name, limit in (
            ("files.json", 1024 * 1024),
            ("plugin.toml", 65536),
            ("requirements.lock", 1024 * 1024),
        ):
            if archive.getinfo(name).file_size > limit:
                raise ValueError("Bundle metadata exceeds limits")
        inventory = json.loads(archive.read("files.json"))
        if set(inventory) != set(archive.namelist()) - {"files.json"}:
            raise ValueError("Bundle contains undeclared payload")
        for name, digest in inventory.items():
            with archive.open(name) as stream:
                digest_state = hashlib.sha256()
                while chunk := stream.read(1024 * 1024):
                    digest_state.update(chunk)
                actual = digest_state.hexdigest()
            if actual != digest:
                raise ValueError("Payload hash mismatch")
        manifest = tomllib.loads(archive.read("plugin.toml").decode())
        required = {
            "schema",
            "id",
            "name",
            "version",
            "distribution",
            "entrypoint",
            "requires_python",
            "requires_sdk",
            "protocol",
            "platforms",
            "languages",
            "capabilities",
        }
        if not required <= manifest.keys() or manifest["schema"] != 1 or manifest["protocol"] != 1:
            raise ValueError("Unsupported manifest")
        if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", manifest["id"]):
            raise ValueError("Invalid plugin ID")
        if not re.fullmatch(
            r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", manifest["entrypoint"]
        ):
            raise ValueError("Invalid entrypoint")
        if not isinstance(manifest["capabilities"], list) or not all(
            isinstance(c, str) for c in manifest["capabilities"]
        ):
            raise ValueError("Invalid capabilities")
        Version(manifest["version"])
        if Version(sdk_version) not in SpecifierSet(manifest["requires_sdk"]):
            raise ValueError("SDK incompatible")
        lock = archive.read("requirements.lock").decode()
        pinned = {}
        for line in lock.splitlines():
            if not line.strip():
                continue
            match = re.fullmatch(
                r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+) --hash=sha256:([a-f0-9]{64})", line
            )
            if not match:
                raise ValueError("Lock must contain only exact versions and SHA-256 hashes")
            name, version, digest = match.groups()
            name = canonicalize_name(name)
            if name in pinned:
                raise ValueError("Duplicate lock requirement")
            pinned[name] = (Version(version), digest)
        wheel_names = [
            name for name in inventory if name.startswith("wheels/") and name.endswith(".whl")
        ]
        wheels = {}
        expanded_wheels = 0
        for name in wheel_names:
            dist, version, _, tags = parse_wheel_filename(PurePosixPath(name).name)
            if dist in wheels or dist not in pinned or pinned[dist] != (version, inventory[name]):
                raise ValueError("Wheel closure does not match lock")
            with tempfile.SpooledTemporaryFile(max_size=1024 * 1024) as temp:
                with archive.open(name) as source:
                    shutil.copyfileobj(source, temp)
                temp.seek(0)
                with zipfile.ZipFile(temp) as wheel:
                    members = wheel.infolist()
                    expanded_wheels += sum(member.file_size for member in members)
                    if len(members) > 10000 or expanded_wheels > MAX_EXPANDED:
                        raise ValueError("Expanded wheel closure exceeds limits")
                    names = set()
                    for member in members:
                        key = member.filename.casefold()
                        if key in names or stat.S_ISLNK(member.external_attr >> 16):
                            raise ValueError("Duplicate or symlink wheel member")
                        names.add(key)
                    metadata_files = [
                        n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")
                    ]
                    if len(metadata_files) != 1:
                        raise ValueError("Invalid wheel metadata")
                    for filename in wheel.namelist():
                        safe_name(filename.rstrip("/"))
                        if filename.endswith(".pth"):
                            raise ValueError("Executable .pth installation hooks are unsupported")
                    if wheel.getinfo(metadata_files[0]).file_size > 1024 * 1024:
                        raise ValueError("Wheel metadata exceeds limits")
                    metadata = BytesParser().parsebytes(wheel.read(metadata_files[0]))
                    if (
                        canonicalize_name(metadata["Name"]) != dist
                        or Version(metadata["Version"]) != version
                    ):
                        raise ValueError("Wheel identity mismatch")
                    if dist == canonicalize_name(manifest["distribution"]):
                        module = manifest["entrypoint"].split(":")[0].replace(".", "/")
                        if (
                            module + ".py" not in wheel.namelist()
                            and module + "/__init__.py" not in wheel.namelist()
                        ):
                            raise ValueError("Entrypoint is not owned by plugin distribution")
                    wheels[dist] = (tags, metadata)
        if set(wheels) != set(pinned):
            raise ValueError("Incomplete wheel closure")
        plugin_dist = canonicalize_name(manifest["distribution"])
        if (
            plugin_dist not in pinned
            or pinned[plugin_dist][0] != Version(manifest["version"])
            or "pydesktools-sdk" not in pinned
        ):
            raise ValueError("Missing plugin or SDK distribution")
        for tags, metadata in wheels.values():
            for dependency in metadata.get_all("Requires-Dist", []):
                req = Requirement(dependency)
                if req.url:
                    raise ValueError("URL dependency forbidden")
                if req.marker and not req.marker.evaluate():
                    continue
                target = pinned.get(canonicalize_name(req.name))
                if not target or target[0] not in req.specifier:
                    raise ValueError("Unsatisfied wheel dependency")
        return manifest, wheels


class Installer:
    def __init__(self, store, python, locale="en"):
        self.store, self.python, self.locale = store, Path(python).resolve(), locale
        self.root = store.root / "plugins"
        self.root.mkdir(exist_ok=True)
        self.reconcile()

    def reconcile(self):
        committed = {record["path"] for record in self.store.all()}
        with self.store.lock:
            paths = list(self.store.db.execute("SELECT path, phase FROM journal"))
        for path, phase in paths:
            candidate = Path(path)
            if phase == "removal" and candidate.is_relative_to(self.root):
                shutil.rmtree(candidate, ignore_errors=True)
                if candidate.exists():
                    continue
                self.store.execute("DELETE FROM plugins WHERE path=?", (path,))
            elif str(candidate) not in committed and candidate.is_relative_to(self.root):
                shutil.rmtree(candidate, ignore_errors=True)
            self.store.execute("DELETE FROM journal WHERE path=?", (path,))

    def _run(self, args, token, timeout=120):
        import signal
        import time

        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PYTHON", "PIP_", "_PYI", "DYLD_", "LD_LIBRARY_PATH"))
        }
        with tempfile.TemporaryFile() as log:
            process = subprocess.Popen(
                args, stdout=log, stderr=log, env=env, start_new_session=True, cwd=self.store.root
            )
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    token.raise_if_cancelled()
                    if time.monotonic() > deadline:
                        raise TimeoutError("Installer phase timed out")
                    time.sleep(0.05)
                if process.returncode:
                    raise RuntimeError("Offline dependency preparation failed")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()

    def install(
        self, bundle, *, consent=False, official=False, token=None, progress=lambda *args: None
    ):
        if not consent:
            raise PluginError(
                "permission_denied",
                "Local plugins execute with your OS permissions; consent required",
                code=-32003,
            )
        token = token or CancellationToken()
        token.raise_if_cancelled()
        progress("verification")
        manifest, wheels = inspect_bundle(bundle)
        if self.store.get(manifest["id"]):
            raise ValueError("Already installed; updates are not supported in this release")
        version = subprocess.check_output(
            [str(self.python), "-I", "-c", "import platform; print(platform.python_version())"],
            timeout=10,
            text=True,
        ).strip()
        if Version(version) not in SpecifierSet(
            manifest["requires_python"]
        ) or not version.startswith("3.13."):
            raise ValueError("Bundle requires a compatible CPython 3.13 runtime")
        import platform

        label = platform_label(platform.system(), platform.machine())
        if label not in manifest["platforms"]:
            raise ValueError("Bundle platform unsupported")
        tag_text = subprocess.check_output(
            [
                str(self.python),
                "-I",
                "-c",
                "from pip._vendor.packaging.tags import sys_tags; print(chr(10).join(map(str, sys_tags())))",
            ],
            timeout=10,
            text=True,
        )
        supported = set().union(*(parse_tag(line) for line in tag_text.splitlines()))
        for tags, metadata in wheels.values():
            if not supported.intersection(tags) or (
                metadata.get("Requires-Python")
                and Version(version) not in SpecifierSet(metadata["Requires-Python"])
            ):
                raise ValueError("Wheel incompatible with selected interpreter")
        digest = hashlib.sha256(Path(bundle).read_bytes()).hexdigest()
        slot = self.root / manifest["id"] / "installs" / (manifest["version"] + "-" + digest[:16])
        if slot.exists():
            raise ValueError("Installation slot already exists")
        self.store.execute("INSERT INTO journal VALUES (?,?)", (str(slot), "staging"))
        slot.mkdir(parents=True)
        committed = False
        try:
            with zipfile.ZipFile(bundle) as archive:
                for info in archive.infolist():
                    token.raise_if_cancelled()
                    destination = slot / "bundle" / info.filename
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as source, destination.open("xb") as target:
                        shutil.copyfileobj(source, target)
            progress("dependencies")
            self.store.execute(
                "UPDATE journal SET phase=? WHERE path=?", ("dependencies", str(slot))
            )
            self._run([str(self.python), "-I", "-m", "venv", str(slot / "venv")], token)
            python = venv_python(slot / "venv")
            self._run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "--isolated",
                    "install",
                    "--disable-pip-version-check",
                    "--no-index",
                    "--find-links",
                    str(slot / "bundle/wheels"),
                    "--only-binary=:all:",
                    "--require-hashes",
                    "-r",
                    str(slot / "bundle/requirements.lock"),
                ],
                token,
            )
            self._run([str(python), "-I", "-m", "pip", "--isolated", "check"], token)
            progress("health_check")
            self.store.execute(
                "UPDATE journal SET phase=? WHERE path=?", ("health_check", str(slot))
            )

            def deny(*args):
                raise PluginError(
                    "permission_denied",
                    "Interactive capabilities unavailable during health check",
                    code=-32003,
                )

            worker = WorkerProcess(
                python, manifest, slot / "health", self.locale, deny, lambda *args: None
            )
            try:
                descriptor(worker.descriptor)
                description = worker.descriptor
            finally:
                worker.stop()
            token.raise_if_cancelled()
            progress("commit")
            with self.store.lock, self.store.db:
                self.store.db.execute(
                    "INSERT INTO plugins VALUES (?,?,?,?,?,?)",
                    (
                        manifest["id"],
                        json.dumps(manifest),
                        str(slot),
                        int(official),
                        "enabled" if official else "disabled",
                        json.dumps(description),
                    ),
                )
                self.store.db.execute(
                    "INSERT OR REPLACE INTO decisions VALUES (?,?)",
                    (manifest["id"], "enabled" if official else "disabled"),
                )
                self.store.db.execute("DELETE FROM journal WHERE path=?", (str(slot),))
            committed = True
            shutil.rmtree(slot / "health", ignore_errors=True)
            return manifest["id"]
        finally:
            if not committed:
                shutil.rmtree(slot, ignore_errors=True)
                self.store.execute("DELETE FROM journal WHERE path=?", (str(slot),))
