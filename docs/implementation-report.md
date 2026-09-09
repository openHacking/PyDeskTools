# 0.1.0 delivery evidence

Validated on 2026-09-04, macOS 26.5 arm64, CPython 3.13.7 (standalone build
20250918), Tk 8.6. This release provides JSON Tools and offline plugin management.
It does not claim the complete planned default tool collection.

## Implemented boundary

The GUI, headless runtime, SDK and JSON plugin have separate wheels and top-level
packages. The host starts SDK workers in per-plugin environments and never imports
plugin modules. SQLite stores installed slots, user decisions, defaults and an
installation journal. Environments are created at their final paths. Installation
requires a complete hashed wheel closure and explicit authorization for local code;
local packages start disabled. Process isolation is not an OS security sandbox.

JSON formatting preserves Unicode, key order and exact decimal/integer values.
Duplicate keys and non-finite numbers are rejected with locations. Input is limited
to 20 MiB and 128 nested levels; artifacts to 200 MiB, RPC messages to 1 MiB and
previews to 64 KiB. Copy/export use the complete artifact. User JSON is excluded
from diagnostic logging. macOS file selection uses asynchronous Cocoa sheets;
export writes a temporary file then atomically replaces the confirmed destination.

English and Simplified Chinese use package-owned gettext catalogs. Shared widgets
belong to PyDeskUI; schema mapping and command/plugin state belong to PyDeskTools.

## Executed verification

- **38 tests passed in 73.67 seconds**, including seven real-Tk PyDeskUI tests.
  The suite uses actual child interpreters and offline wheel installations.
- Ruff and mypy pass. Five wheel/sdist pairs pass Twine metadata checks. PyDeskUI
  Sphinx documentation builds with warnings as errors; its Skill validates.
- Wheels installed in an isolated environment outside both checkouts import from
  that environment. PyDeskUI has zero third-party core requirements. Importing
  SDK/runtime does not load Tk or PyDeskUI; importing the host does not load JSON
  plugin code.
- Tests cover precision, Unicode, invalid syntax, duplicate locations, limits,
  large artifacts, owner/path checks, malformed protocol, real crash/stdout noise,
  timeout/cancellation, oversized pipe output, cancellation/completion races, process reaping, installation cancellation/reconciliation,
  unsafe archives, explicit consent and single-profile locking. Two fixture plugins
  use incompatible versions of the same dependency successfully.
- A real Tk application test formats, copies, exports and displays a truncated
  large result while preserving input across theme/language changes. Export path
  selection is substituted in this automated test; its disk write is real.
  A separate macOS test opens a real native panel and cancels it through the task
  token. Earlier packaged desktop checks also exercised keyboard formatting,
  clipboard and native save to a UTF-8 JSON file.
- The frozen application diagnostic runs with network access denied in a fresh
  profile, formats precise numbers, checks the clipboard and large artifacts,
  disables/reaps, uninstalls and restores the built-in plugin. It then repeats
  from a moved Unicode application path and the same user profile with access to
  both development checkouts and the development interpreter denied. Both
  runs pass using a copy taken from the final read-only DMG mount. Raw final reports accompany the generated artifacts in
  `dist/verification/`; `startup_seconds` measures application readiness, not OS
  process cold-start time. `process_wall_seconds` covers the whole diagnostic.

## Five adversarial risks and fixes

| Risk | Resolution and evidence |
| --- | --- |
| Host imports plugin code | Dedicated SDK worker entrypoint; headless import tests and frozen diagnostic report `host_imported_plugin: false`. |
| Moving a venv/app invalidates interpreter paths | Plugin venvs are created in final user slots; bundled interpreter is verified and materialized into a stable user runtime. Install subprocesses use the profile as cwd. Moved-app test denies original paths. |
| Callbacks or processes survive shutdown | Widget-owned scheduling/trace cleanup, asynchronous native-panel cancellation and serialized process-group shutdown. Real destroy, cancel, crash and reap tests pass. |
| JSON formatting loses precision | Exact decimal decoding/encoding and unbounded integers in the isolated worker; numeric round-trip and duplicate-key tests pass. Output is counted incrementally. |
| Package depends on the development machine | Bundled GUI Python/Tk plus separate fixed CPython/pip and complete offline wheels. Fresh-profile network denial and relocated frozen execution pass. |

Review also found and fixed a shutdown race that returned before process reaping,
a stale stopping flag that prevented execution after restore, and blocking Tk
native file dialogs. Archive checks bound outer and inner expansion, metadata,
member counts and dependency closure, and reject unsafe paths/symlinks/hooks.

## Artifacts and provenance

`dist/PyDeskTools-0.1.0-macos-arm64-adhoc.dmg` contains the application and an
Applications shortcut. `dist/PyDeskTools.app` is the standalone onedir bundle.
Wheel/sdist outputs live in each project's `dist` directory. The application
copies interpreter/plugin state into its user directory without modifying itself.

The standalone source, SHA-256, ABI and license inputs are recorded in
`runtime-sources.json`; build dependency versions, artifact hashes and signing mode
are in `dist/build-manifest-<platform>.json`. Runtime file hashes are embedded in `runtime.json`.
Third-party license texts are included in the application. The source release
contains the build scripts and notices; no PyPI or GitHub release was published.

## Explicit limits

- This is an **ad-hoc test build**, verified by `codesign --verify --deep --strict`.
  No valid Developer ID identity was available; notarization and Gatekeeper
  distribution approval are not claimed. Explicit formal-signing failures do not
  fall back to ad-hoc mode.
- The tests use a fresh application profile under the current macOS account, not
  a newly created OS account. Network denial is enforced for the diagnostic;
  this is not evidence of an OS-wide air-gapped test.
- Native save was manually exercised, but a full automated native overwrite-sheet
  matrix, packaged GUI RSS, prolonged load testing and accessibility/scaling
  audits remain release hardening gates. Source
  process samples were GUI RSS 133.36 MiB and worker RSS 26.25 MiB; these are not
  packaged-process memory claims. Timings and sizes are local observations.
- CI is configured with minimal permissions and pinned actions but has not run on
  hosted runners. Only this macOS arm64 environment has actual desktop evidence.
  Intel, Windows, Linux and older macOS versions are not certified.
- Screenshot/image extensions, the other four tools, online catalog, updates and
  migrations remain deferred. Unsupported service capabilities fail explicitly.

## Final artifact run

The DMG-derived fresh-profile run reached application readiness in 4.166 seconds
and completed its full diagnostic in 7.140 seconds of process wall time. The
relocated repeat reached readiness in 0.389 seconds and completed in 2.492 seconds.
Both runs had network and both development checkouts denied, and reported
`passed: true`, `clipboard_matches: true` and `host_imported_plugin: false`.

Final DMG size: 47,534,901 bytes (45.33 MiB). Application regular-file payload:
78,058,489 bytes (74.44 MiB; excludes symlink targets counted twice). DMG SHA-256:
`71548e825c9946588d77858440a7ddd3c3859cd3e69b4ded664a0cd29d889b4f`.
