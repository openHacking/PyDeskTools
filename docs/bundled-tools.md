# Default free tools

> Revised design: 2026-09-04. Proposed behavior; no plugin implementation is delivered here.

## Product contract

A fresh PyDeskTools installation provides five usable free tools: Screenshot, JSON Formatter, Image Compressor, Timestamp Converter and Clipboard History. All five are first-party open-source plugins using the ordinary SDK and lifecycle. No account, license, use counter, added output watermark or online model is required. Watermark removal is outside the current scope. Regex and file-hash examples remain SDK fixtures rather than default product tiles.

| Stable plugin ID | Free baseline | Deliberate boundary |
|---|---|---|
| `org.pydesk.screenshot` | Full desktop or rectangular region capture; preview, copy and save PNG | No scrolling capture, OCR or complex annotation in the first version |
| `org.pydesk.json-tools` | Format/minify JSON, locate syntax errors, import/export UTF-8 files and copy | JSON stays local; large inputs use file artifacts rather than oversized RPC strings |
| `org.pydesk.image-compressor` | JPEG/PNG/WebP input and output, quality/size controls, preview and before/after bytes | No original overwrite by default; no claim every setting makes every file smaller |
| `org.pydesk.timestamp` | Explicit seconds/milliseconds, dates, current time, timezone selection and copy | Do not silently infer ambiguous units or daylight-saving times |
| `org.pydesk.clipboard` | Local text/image history, text search, pin, delete, clear and pause/resume | Image search means metadata only, not OCR; recording starts only after opt-in |

The installer includes compatible complete bundles and runtime dependencies. Provision them into final-path environments on first setup without network access, with visible per-tool progress and recoverable failures. Setup completes before advertising all tools ready. Ordinary third-party installs remain disabled until enabled; the verified first-party default set is provisioned enabled, with lazy worker start. Recording is a separate setting and is initially off.

## Installation and removal choices

Persist `default_provisioning_completed` per application profile and a per-plugin user decision (untouched/enabled/disabled/uninstalled). An app upgrade preserves these decisions. It must not reinstall a removed tool, re-enable a disabled tool or turn recording back on. New defaults introduced in later releases require an explicit offer to existing profiles. A reset-to-defaults action lists changes before applying them.

Uninstall uses the same stop/reap/remove lifecycle as other plugins. Keep saved data by default and offer separate deletion. Immutable bundled ZIP resources inside a signed app may remain for offline reinstall; distinguish retained recovery-resource size from removable installed-environment size. Never mutate a signed application bundle to remove one plugin. Offline Restore installs the shipped compatible bundle; it does not silently retrieve the latest release.

## Tool-specific correctness

Screenshot acquisition and OS consent belong to the host platform adapter; the screenshot plugin owns the task and result actions. Hide transient capture UI before acquisition. Capture one desktop image first, let the user choose a rectangular region against that image, and map preview coordinates back to physical pixels. Escape cancels without saving. Verify negative monitor coordinates and mixed DPI; unsupported capture environments produce a clear tool-local error. Global hotkeys and tray launching are not required for the first release.

Image compression uses a plugin-local Pillow dependency. Run one selected file or a selected set sequentially without an arbitrary commercial count limit; show per-file outcomes. Preserve originals, normalize EXIF orientation, preserve alpha when the chosen format supports it and require an explicit background when converting transparency to JPEG. Offer metadata preservation/removal explicitly. Preserve ICC profiles when supported; disclose conversion limitations. Animated images are unsupported in v1 rather than silently flattened. Write a temporary output and replace the destination only after success and collision confirmation. If output is larger, show the result and let the user keep it or choose different settings. Bound decoded pixels and memory; cancellation must not leave a corrupt final file.

Timestamp conversion uses datetime/zoneinfo and bundles tzdata in that plugin where needed for consistent offline IANA zones. Date input is ISO 8601; an explicit UTC offset takes precedence only when consistent with a supplied named zone, otherwise report a conflict. Require a choice for ambiguous local times and reject nonexistent local times; never guess at daylight-saving boundaries. Seconds/milliseconds are explicit input modes. [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html), accessed 2026-09-04.

Clipboard History begins recording only after the user enables it. Default limits: 500 entries, 30 days for unpinned entries, 100 MiB of stored content, and 20 MiB per image. Pinned entries are exempt from age eviction but still count toward capacity; if pinned data alone fills capacity, pause capture with an explanation rather than silently deleting it. De-duplicate consecutive equal content. Store text and normalized image artifacts in the plugin's local data, never in diagnostics. Expose remaining capacity, retention settings and Pause/Clear controls. Clearing history also removes unreferenced image files; copying an old entry should not produce a duplicate loop. There is no guarantee that every password or sensitive item can be detected and excluded.

## Platform release gates

A supported default-tool distribution must demonstrate all five tools on its advertised OS. Windows/macOS complete installer targets remain first. Linux source/pip support must publish a separate capability matrix for the tested desktop session: X11 and Wayland capture/clipboard behavior cannot be assumed interchangeable. A missing portal/helper or denied permission is an explicit limitation, not a passing screenshot test. Pillow's capture support varies by platform; one import is not a cross-platform implementation. [Pillow ImageGrab](https://pillow.readthedocs.io/en/stable/reference/ImageGrab.html), accessed 2026-09-04.

## Acceptance

Fresh offline install; no developer Python needed for desktop installers; all five tiles work after setup. Remove/disable a default, restart and upgrade without undoing that choice. Restore a removed default offline. Deny screenshot permission while other tools remain usable. Test pixel-correct region selection on mixed-DPI monitors. Compress transparent/oriented/corrupt/oversized images without modifying originals. Test timestamp units, negative epochs and DST ambiguity. Verify no clipboard reads before opt-in, no events after pause/unload, bounded history and complete explicit data deletion.
