# Distribution, installation and lifecycle

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## Artifact format

Proposed bundle extension: `.pdtplugin`, a ZIP container with `plugin.toml`, `requirements.lock`, `files.json`, `wheels/`, and optional translation/icon resources. It is not a source-code ZIP from GitHub. Use one bundle per target Python ABI/platform unless its entire wheel closure is portable. The first installer ABI is CPython 3.13; headless SDK/runtime source compatibility >=3.11 does not mean every plugin binary supports every Python version.

The manifest example is [plugin.toml](examples/plugin.toml). Required fields are schema=1, id, name, version, distribution, entrypoint, requires_python, requires_sdk, protocol=1, platforms, languages and capabilities. ID follows `[a-z0-9]+(?:[.-][a-z0-9]+)*` and cannot contain path separators; distribution is a normalized Python distribution name; entrypoint is `module:factory`. Catalog ownership governs ID ownership. Names/descriptions are display strings and do not participate in paths. The example platform labels are host OS/architecture identifiers, not wheel tags; independently validate each wheel against the selected interpreter's supported packaging tags and ABI before installation.

Wheel METADATA must agree with distribution/version and Python compatibility; the entry module must belong to the plugin distribution. The full dependency closure, including SDK, is pinned with hashes in requirements.lock. `files.json` maps every payload path except itself to SHA-256. Reject undeclared files. The signed catalog authenticates the complete bundle hash; files.json alone proves no publisher identity.

## Static catalog

Ship a default catalog public key and URL as release resources. Catalog envelope contains payload bytes, key ID and detached Ed25519 signature; sign exact payload bytes to avoid JSON canonicalization ambiguity. Payload has schema, monotonically increasing serial, issued_at, expires_at and plugin entries with artifact URL, SHA-256, size, platform tags, requires_python and version. Separate catalog keys from OS code-signing keys. Verify with the host cryptography dependency, never handwritten cryptography.

A user-added catalog requires explicit key fingerprint confirmation out of band. Existing key rotation is authorized by a trusted key or a new application release, not by an unsigned network response. Keep the highest accepted serial to resist rollback. Expired catalogs may be viewed from cache but cannot authorize new catalog installations until refreshed; already installed plugins continue to work offline. An explicitly selected local bundle may be installed as unverified with clear consent, without pretending a hash is a publisher signature.

Catalog and bundles are static files hosted on GitHub Pages/Releases or a user-provided equivalent. This requires no dynamic application backend, telemetry or account. An unavailable catalog does not block startup or local bundle installation. Updates are user initiated in v1; no silent plugin-code updates.

## Install transaction

1. Parse catalog metadata or a local bundle without importing plugin code. Validate size/compatibility and show source, declared capabilities and code-execution warning before consent.
2. Download to a unique cache staging file with a 30-second network inactivity timeout and cancellation. Default compressed-size limit 200 MiB and expanded limit 1 GiB; reject larger bundles with a clear unsupported-size message in v1.
3. Verify authenticity where available, bundle hash, ZIP paths, duplicates, symlinks, entry count (10000 maximum) and expanded-size limit. Reject absolute paths, traversal, case-fold collisions, device/reserved paths and writes outside staging.
4. Create an immutable installation slot `plugins/<id>/installs/<version>-<digest>/` in its final location. The directory is not active or discoverable by the command registry yet. Create its venv there; do not build a venv in a temporary directory and rename it later.
5. Run the bundled installer with isolated configuration: `pip --isolated install --no-index --find-links <wheels> --only-binary=:all: --require-hashes -r <lock>` using the slot's interpreter. Reject VCS/URL/editable requirements, unpinned items and executable installer hooks; require a self-contained closure and then `pip check`.
6. After explicit user consent, run a bounded worker activation/describe smoke check in an isolated temporary data directory. This executes plugin code and is not a security scan. The smoke-check host denies capture, clipboard subscriptions and other interactive capabilities; activation must tolerate these being unavailable. Bundled first-party checks use release trust without enabling recording. If it fails, do not activate; preserve diagnostics and delete the candidate environment when handles are closed.
7. Record a committed install row and atomically update the active-install pointer in a SQLite transaction. Ordinary user-selected installs become disabled; enabling is a separate action. Verified first-party defaults follow the enabled provisioning exception in [bundled-tools.md](bundled-tools.md); this never enables clipboard recording without opt-in. Installer UI may offer "Enable now" after success. Remove temporary extraction files after commit.

Python venv environments are not generally movable. Keeping the environment at its final path before installation preserves embedded paths. [Python venv documentation](https://docs.python.org/3/library/venv.html), accessed 2026-09-03.

A per-plugin operation lock prevents simultaneous install/update/remove. A single application-instance lock protects the database; the OS process handle is authoritative, not a stale PID file alone. Journal phases permit cleanup of uncommitted slots after a crash. Never delete a committed install merely because a temporary journal entry remains.

## Runtime state versus install state

Installed version state and process state are separate. Installation states: staging, installed, removal_pending, removed. Runtime states: disabled, starting, active, stopping, failed. A version being installed does not imply it has a running process. Store desired enabled state separately from observed state; after a crash display failed and require manual restart rather than an automatic restart loop.

Startup reads metadata and prior desired state, shows the shell, then starts enabled plugins lazily when a command/view is opened. An enabled but not-yet-started plugin is presented as ready, not failed. Disabled plugins are never imported or launched. The sole initial background exception is an installed, enabled clipboard plugin whose persisted recording consent is on: start it after the shell is ready and restore its subscription. A prior crash leaves recording paused until the user resumes it.

## Stop, unload and uninstall

First revoke all session-bound host subscriptions and cancel owned capture/dialog requests, invalidating queued events. Stop admitting new tasks, cancel queued tasks, notify the active task, and wait up to 2 seconds for cooperative completion. Allow a further 2 seconds for deactivate/shutdown. If still alive, terminate the supervised process tree and wait up to 1 second; use the platform force-kill path if needed, reap handles and record an unclean stop. Only report runtime removal after process/handle cleanup is confirmed. Windows Job Objects and POSIX process groups cover cooperating process trees; deliberately detached malicious children are outside this guarantee.

Remove command registrations, owned UI views, subscriptions and temporary resources on the GUI thread, invalidating the session generation first. File deletion waits for process handles to close. Windows sharing violations result in removal_pending and a next-start cleanup job; the UI must not claim files are already removed. No deleting shared runtime files or another plugin's environment.

Uninstall retains user settings/data by default. A separate explicit "Delete saved data" operation lists the scope, cancels use and removes only that plugin's data. Code uninstall does not revoke filesystem writes already performed by plugin code.

## Update and rollback

An update first installs and verifies the candidate without touching the active version, then asks the user to stop active work. After the old worker stops, activate the new pointer and start the candidate if the plugin was enabled. Keep the previous install for manual rollback. Jobs pin versions and prohibit replacing an in-use version; a user may cancel them before updating.

Data has a separately versioned epoch directory and recorded compatibility. Before a plugin data migration, snapshot into a new epoch, run a plugin-provided bounded migration there, and switch code/data pointers together only after validation. No migration hook means schema compatibility is required or update is blocked. Migration failure preserves the old pointers and backup.

After new-version writes, rolling back code alone may be unsafe. Offer either rollback with a compatible current epoch or explicit restore of the pre-upgrade data snapshot, warning that later writes will be lost. External side effects cannot be rolled back by restoring files. No cross-plugin dependencies in v1; tools interact through host command contracts instead of importing one another.
