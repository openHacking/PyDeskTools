"""Profile-local SQLite state and immutable artifact ownership."""

import json
import os
import shutil
import sqlite3
import threading
import uuid
from pathlib import Path

from pydesktools_sdk import PluginError


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lockfile = (self.root / "profile.lock").open("a+b")
        if os.name == "posix":
            import fcntl

            try:
                fcntl.flock(self.lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.lockfile.close()
                raise RuntimeError("This application profile is already open") from None
        else:
            self.lockfile.close()
            raise RuntimeError("This release supports POSIX process ownership only")
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.root / "state.sqlite3", check_same_thread=False)
        self.db.execute("PRAGMA foreign_keys=ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.close()
            raise RuntimeError("Profile was created by a newer application")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS plugins (
              id TEXT PRIMARY KEY, manifest TEXT NOT NULL, path TEXT NOT NULL,
              enabled INTEGER NOT NULL, decision TEXT NOT NULL, descriptor TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS journal (path TEXT PRIMARY KEY, phase TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (namespace TEXT, key TEXT, value TEXT,
              PRIMARY KEY(namespace,key));
            CREATE TABLE IF NOT EXISTS decisions (id TEXT PRIMARY KEY, value TEXT NOT NULL);
            PRAGMA user_version=1;
        """)
        self.db.commit()

    def all(self):
        with self.lock:
            return [
                dict(
                    id=r[0],
                    manifest=json.loads(r[1]),
                    path=r[2],
                    enabled=bool(r[3]),
                    decision=r[4],
                    descriptor=json.loads(r[5]),
                )
                for r in self.db.execute("SELECT * FROM plugins ORDER BY id")
            ]

    def get(self, identifier):
        return next((r for r in self.all() if r["id"] == identifier), None)

    def execute(self, sql, values=()):
        with self.lock, self.db:
            return self.db.execute(sql, values)

    def setting(self, namespace, key, default=None):
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM settings WHERE namespace=? AND key=?", (namespace, key)
            ).fetchone()
            return json.loads(row[0]) if row else default

    def set_setting(self, namespace, key, value):
        encoded = json.dumps(value, allow_nan=False)
        if len(encoded.encode()) > 65536:
            raise ValueError("Setting exceeds 64 KiB")
        self.execute("INSERT OR REPLACE INTO settings VALUES (?,?,?)", (namespace, key, encoded))

    def decision(self, identifier):
        with self.lock:
            row = self.db.execute(
                "SELECT value FROM decisions WHERE id=?", (identifier,)
            ).fetchone()
            return row[0] if row else None

    def close(self):
        if getattr(self, "db", None) and not getattr(self, "_closed", False):
            self.db.close()
            self._closed = True
        if not self.lockfile.closed:
            self.lockfile.close()


class Artifacts:
    MAX_FILE = 200 * 1024 * 1024
    MAX_CACHE = 1024 * 1024 * 1024

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.records = {}

    def import_file(self, owner, session, source, *, export_root=None):
        source = Path(source)
        if export_root is not None:
            root = Path(export_root).resolve()
            if source.is_absolute() or ".." in source.parts:
                raise PluginError("invalid_artifact", "Invalid artifact path")
            candidate = root / source
            for part in (candidate, *candidate.parents):
                if part == root:
                    break
                if part.is_symlink():
                    raise PluginError("invalid_artifact", "Symlinks are not artifacts")
            source = candidate.resolve()
            if not source.is_relative_to(root):
                raise PluginError("invalid_artifact", "Artifact outside export directory")
        if not source.is_file() or source.is_symlink():
            raise PluginError("invalid_artifact", "Expected a regular file")
        with self.lock:
            size = source.stat().st_size
            total = sum(record["size"] for record in self.records.values())
            if size > self.MAX_FILE or size + total > self.MAX_CACHE:
                raise PluginError("artifact_limit", "Artifact storage limit exceeded")
            identifier = uuid.uuid4().hex
            target = self.root / identifier
            written = 0
            try:
                with source.open("rb") as src, target.open("xb") as dst:
                    while chunk := src.read(1024 * 1024):
                        written += len(chunk)
                        if written > self.MAX_FILE or written + total > self.MAX_CACHE:
                            raise PluginError("artifact_limit", "Artifact grew beyond limit")
                        dst.write(chunk)
                self.records[identifier] = dict(
                    path=target, owner=owner, size=written, refs={session}
                )
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            return identifier

    def path(self, owner, identifier):
        with self.lock:
            record = self.records.get(identifier)
            if not record or record["owner"] != owner:
                raise PluginError("invalid_artifact", "Artifact unavailable")
            return record["path"]

    def acquire(self, owner, identifier, reference):
        with self.lock:
            self.path(owner, identifier)
            self.records[identifier]["refs"].add(reference)

    def release(self, reference, identifier=None):
        with self.lock:
            for key, record in tuple(self.records.items()):
                if identifier is None or key == identifier:
                    record["refs"].discard(reference)
                    if not record["refs"]:
                        record["path"].unlink(missing_ok=True)
                        del self.records[key]

    def read_copy(self, owner, identifier, directory):
        with self.lock:
            source = self.path(owner, identifier)
            directory = Path(directory)
            directory.mkdir(parents=True, exist_ok=True)
            destination = directory / identifier
            shutil.copyfile(source, destination)
            return str(destination)

    def close(self):
        with self.lock:
            for record in self.records.values():
                record["path"].unlink(missing_ok=True)
            self.records.clear()
