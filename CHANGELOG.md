# Changelog

## 0.1.0

- Separate GUI, headless runtime and SDK packages; retire the prototype registry.
- Add bounded protocol 1 workers, offline wheel bundles, lifecycle and immutable artifacts.
- Add JSON formatting/minification with exact decimals, UTF-8 import, copy and export.
- Add English/Chinese shell, generic command forms and scoped PyDeskUI components.
- Add macOS arm64 app/DMG build with a relocatable, separately addressable interpreter.
- Unify the light application chrome on white, expose focused search cursors, and make JSON options dismissible by click, Escape, Return or an explicit Done action.
- Keep image compression feedback in a fixed footer, format MiB-scale results as MB, and pair per-image status icons with readable labels.
- Present a completed image batch as a readable status badge with a green check instead of a faded disabled action.
- Turn image compression into an explicit batch workflow with a focused drop zone, drag-and-drop import, clear/next-batch actions, pending-only retries, and a disabled completed state until settings change.
- Add native release builders for macOS arm64, Windows x64 beta, and Linux x64,
  with pinned plugin runtimes, build manifests, checksums, and provenance.
- Keep window-close actions in the system tray on Windows, macOS, and supported
  Linux desktops, with explicit tray and keyboard quit actions.
- Initial delivery includes two complete tools. Online catalogs, screenshot tools,
  and additional CPU architectures remain future work.
