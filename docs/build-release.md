# macOS build and release

Validated build: macOS arm64, CPython 3.13.7 standalone build 20250918, Tk 8.6,
PyInstaller 6.22.2 and PyObjC core/Cocoa 12.2.2. `requirements-dev.lock` records the tested environment.

Prepare a verified standalone install from `runtime-source.json`. Set TCL_LIBRARY
and TK_LIBRARY to its lib/tcl8.6 and lib/tk8.6 when using that Python for GUI tests.
Build SDK/plugin wheels and the offline bundle first:

```sh
python scripts/build_bundles.py
python scripts/build_macos.py --runtime-source /path/to/verified/python
```

The default creates an **ad-hoc test app/DMG**, not a notarized public release.
The runtime is copied into a hash-addressed user-data directory before provisioning
venvs. This permits moving the app without breaking existing venv interpreter paths.
No signed app files are changed at runtime; old runtimes remain for existing installs.

For a configured Developer ID/keychain environment:

```sh
python scripts/build_macos.py --runtime-source /path/to/verified/python --identity 'Developer ID Application: Runze Liu (23RR37CJX2)' --notary-profile YOUR_EXISTING_PROFILE
```

Signing failures are errors, never fallback. No credentials belong in source.
The builder signs nested binaries, verifies the app, creates a DMG with Applications
shortcut, and optionally notarizes/staples it. Public release additionally needs
Gatekeeper testing on a clean supported machine and private signing infrastructure.

Publish UI, SDK, runtime and app/plugin artifacts in dependency order only after
reviewed tags. Use PyPI Trusted Publishing and minimum permissions; no PR releases.
CI in this milestone validates but does not publish. Build wheels/sdists with
`python -m build`, run twine check, and install them outside source checkouts.
Advertise only platform versions actually tested; macOS x86_64/Windows/Linux are
not installer targets of this milestone.

Cocoa sheets implement nonblocking file selection and task-driven dismissal.
The Tk 8.6 native dialog path was observed to block its timers on this macOS build;
the application therefore owns this platform-specific adapter.

## Repeat the frozen diagnostic

Copy the app out of the read-only DMG and use an empty disposable profile:

```sh
sandbox-exec -p '(version 1)(allow default)(deny network*)' \
  '/path/to/PyDeskTools.app/Contents/MacOS/PyDeskTools' \
  --data-dir /tmp/pydesk-disposable-profile \
  --verify-installation /tmp/pydesk-verification.json
```

The diagnostic changes that profile: it provisions, disables, removes and restores
the JSON plugin, and writes to the clipboard. Do not use your working profile.
Repeat after moving the app using the same disposable profile. Add `deny file-read*`
subpath rules for your checkouts, build interpreter and original app location to
check independence. The final delivery used both network denial and development
path denial for both passes; see `implementation-report.md`.
