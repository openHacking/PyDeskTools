# UI experience update — 2026-09-08

## Delivered behavior

- Remove the global bottom progress overlay. Busy state now guards tasks independently of presentation; batch progress and cancellation stay inside Image Compressor.
- Keep only the latest requested preview, cache at most 12 file/mtime/settings combinations, and release evicted/stale artifacts. Preserve decoded images for the active comparison; skip identical resizes and renders.
- Give the image queue 230 logical pixels, settings 250, and the preview the remaining space. Use smooth proportional preview scaling, two-line file/status rows, full-path tooltips, and scrollable settings.
- Show actual per-file save/skip/failure/cancellation results, net space saved or added, actual destinations and an output-folder action. Continue after individual failures and preserve completed files on cancellation.
- Import JSON into the input editor without transforming it. Load full result artifacts for “Use result as input”; invalidate stale copy/export references. Canceling import preserves the previous state.
- Remove repeated outlines, retain a single sidebar divider, move the settings Home/back action to the upper left, and add the source repository to About.
- Render Aqua surfaces with the native background element so icons and navigation rows match the surrounding colors. Use one-pixel focus/error outlines and explicit popup padding.
- Use a single white base surface across the light window; retain hierarchy through dividers, input borders, selection color and semantic controls rather than gray canvas blocks.
- Keep search accessories outside the editable text inset so the native cursor remains visible. Attach Popovers to the app viewport, dismiss them on outside click, and give JSON options a Done/Return path.
- Reserve a fixed image-workflow footer for idle, progress and completion feedback. Pair image-state icons with text, and switch byte counts to MB at one mebibyte.
- Replace the image compressor's noisy empty workspace with a focused drop zone plus compact settings. Once files exist, expose clear/next-batch actions and submit only pending, failed, canceled, or explicitly reconfigured items.
- Ship the blue toolbox mark as SVG, transparent PNG and ICNS, including the app/Dock icon, header, About page and README. Rebuild it with `python scripts/build_brand_assets.py`.

## Compatibility and packaging

Use the two source checkouts together. PyDeskUI is now 0.2.3; SDK/runtime are 0.1.1; the bundled JSON plugin is 0.1.1 and Image Compressor is 0.2.2. The plugin version changes ensure existing enabled or disabled installations actually receive these fixes, while preserving uninstall decisions.

PyDeskUI adds compatible `bordered` settings for Card, ScrollArea, Textarea and CodeEditor, `surface` for Icon/ScrollArea, `content_padding` for SearchEntry, and padding, a menu-matched visible boundary, toggling, initial focus and optional Return dismissal for Popover. Labels infer a semantic parent surface unless explicitly configured. CodeEditor exposes a status bar and synchronized auto-hiding scrollbars.

SDK progress accepts an optional bounded JSON object. Runtime validates it; throttled structured checkpoints are coalesced and delivered during long operations. A schema-valid canceled result may retain partial results.

The GUI builder requires Tk 9 and no longer points GUI collection at the headless worker runtime’s Tk 8.6. The host loads TkDND through `tkinterdnd2`; failure leaves the file chooser available instead of blocking startup, and frozen builds collect the Tcl scripts and native library. The worker interpreter remains the pinned CPython 3.13.7 build. No publishing or pushing was performed.

## Validation evidence

- PyDeskTools: 47 tests passed, including real Tk flows, invalid/unformatted JSON import, large full-result reuse, canceled import, navigation during completion, image batch terminal/retry/clear states, drag-path validation, stable image-footer geometry, status icons, MB formatting, stale preview rejection, 12-entry cache eviction, corrupt images, cancellation and progress checkpoints.
- PyDeskUI: 123 tests passed, including focused search-cursor clearance, accessory padding, themed bundled-icon loading, attached Popover toggling, initial focus, outside-click/Escape dismissal and optional Return dismissal.
- Ruff, mypy and whitespace checks cover both repositories. Source distribution/wheel metadata checks and packaged installation diagnostics are included in the local build artifacts.
- Local artifacts: [installation report](../dist/verification/ui-installation.json), [performance report](../dist/verification/ui-performance.json), [UI screenshots](../dist/verification/ui/), and the [macOS test DMG](../dist/PyDeskTools-0.1.0-macos-arm64-adhoc.dmg).

The earlier screenshot review covered the light image workflow, English JSON at the minimum window size, dark Home, and light About. The current batch-flow follow-up adds unlocked, side-by-side empty and completed Image Compressor comparisons at the 1280 × 840 logical viewport; `design-qa.md` records the final visual pass.

## Performance sample

Run `python scripts/benchmark_ui.py` from the repository root to repeat the disposable-profile sample.

On this Mac, Python 3.13.15 / Tk 9.0.4, the warm test recorded these median / maximum durations:

| Operation | Median | Maximum |
| --- | ---: | ---: |
| Cached image selection | 10.20 ms | 11.23 ms |
| Page navigation | 23.63 ms | 31.32 ms |
| Theme change | 34.47 ms | 46.78 ms |
| Window resize | 52.82 ms | 56.65 ms |

This is a local sample, not a cross-platform performance guarantee. The benchmark observed no callback errors. Expanding the center of cached control textures reduced excessive small-tile painting while retaining the original control dimensions.

## Adversarial review

| Likely failure | Resolution and evidence |
| --- | --- |
| An old preview replaces a newly selected image | Compare request keys before rendering; rapid-selection integration test verifies the last image’s dimensions. |
| Preview references or images accumulate | Release stale/evicted references, close decoded buffers, and cancel resize timers; 14-image integration test verifies exactly 12 cache entries / 24 retained artifacts. |
| Removing the spinner permits duplicate tasks | Keep busy/task state independent of visibility; button state tests and deferred image actions cover pending work. |
| A completed batch creates `-compressed-2` files after an accidental second click | Treat completed/skipped files as terminal, disable the action with a Completed label, and reject direct command submission when no pending paths exist. |
| Clearing a batch lets a stale preview refill the UI | Clear the active preview key, release matching artifact references and decoded image objects, and reject late preview completion against the current request key. |
| Dragged folders, corrupt files, duplicates, or paths with spaces break the whole import | Parse Tcl lists, validate every path independently, deduplicate, retain valid files, and return structured rejections for the rest. |
| Truncated output or old artifacts replace/copy the wrong JSON | Read full artifacts off the UI thread and clear invalid results; full-result, invalid-import and cancel tests cover the transitions. |
| Theme changes recreate white squares or expensive redraw loops | Native surface painting, inherited semantic backgrounds, thin outlines and unchanged-render checks; real screenshots, component tests and timing measurements provide evidence. |
