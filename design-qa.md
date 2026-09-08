# PyDeskTools design QA

## Comparison target

- Source visual truth:
  - PyDeskUI gallery: `/Volumes/github/private/PyDeskUI/docs/images/studio-light.jpg`
  - Home annotations: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-59e56252-e0a6-426b-aedd-8366750a450b.png` (1287 × 876)
  - Plugin-center annotations: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-7eeb5d44-2565-465d-aa15-e490c1dfead9.png` (1280 × 875)
  - Image-compressor empty and populated annotations: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-eec57723-0580-424a-a619-62b28ea19e16.png` and `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-f8aeed3f-5882-497b-89d0-ca26b0acdfc8.png` (1089 × 823 populated)
  - JSON annotations: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-1830d15a-0aca-4e01-a834-003d9952385e.png` (1260 × 813)
- Rendered implementation:
  - `/Users/openhacking/.codex/visualizations/2026/09/07/01a07a81-37c2-7110-b12d-aac661d4f71f/pydesktools-home-final.png`
  - `/Users/openhacking/.codex/visualizations/2026/09/07/01a07a81-37c2-7110-b12d-aac661d4f71f/pydesktools-plugins-final.png`
  - `/Users/openhacking/.codex/visualizations/2026/09/07/01a07a81-37c2-7110-b12d-aac661d4f71f/pydesktools-json-final.png`
  - `/Users/openhacking/.codex/visualizations/2026/09/07/01a07a81-37c2-7110-b12d-aac661d4f71f/pydesktools-image-final.png`
- Viewport: 1280 × 840 Tk logical pixels; each application-window capture is 1280 × 868 physical pixels at 1× density, including the 28-pixel native title bar.
- State: light theme; home with one recent command; enabled Image Compressor selected in plugin center; JSON waiting state; image compressor with one PNG and completed automatic preview.
- Density normalization: source captures vary in size, so comparisons used the same visible desktop state and normalized persistent-region proportions. The final implementation captures share one viewport and density.

## Findings

No actionable P0, P1, or P2 differences remain against the requested annotations.

- Fonts and typography: section, title, body, muted metadata, and monospaced code now have clear hierarchy. JSON code uses the application text scale with 12-pixel horizontal and 10-pixel vertical inset.
- Spacing and layout rhythm: the 188-pixel navigation rail follows the gallery rhythm; only the selected route has a contrasting tile. Home shortcut dividers and decorative icon boxes are gone. Plugin filters have six-pixel gaps. JSON input/output headers and status rows align.
- Colors and visual tokens: the neutral canvas, white selected/working surfaces, blue primary actions, muted metadata, and destructive red are semantic. Destructive button icons now use the same foreground token as their text.
- Image quality and asset fidelity: the compressor contains the complete selected image without cropping. The single Original/Compressed preview avoids the former squeezed double image. No custom or placeholder icon assets were introduced.
- Copy and content: plugin data is grouped under “Plugin details” and “Data and permissions”; the compressor states that outputs are saved beside originals. The English QA capture is an intentional locale state; the Chinese catalog was compiled and locale switching passed the real-Tk regression.
- Interaction: file addition selects the first image and automatically requests a preview; selecting another image or changing settings refreshes it. Compress writes non-overwriting `-compressed` files beside each source and never asks for an output folder.
- Accessibility: controls remain native Tk/PyDeskUI widgets with keyboard focus and visible selected/disabled states. Screen-reader announcements remain a platform runtime concern rather than a screenshot claim.

Focused region comparison was required and performed for the annotated hero icon, sidebar navigation tiles, plugin filter/action rows, plugin metadata hierarchy, JSON first line and bottom status, and the image preview/settings boundary. The final captures keep each region readable at original detail.

## Comparison history

1. Initial implementation pass improved the compressor but missed several literal screenshot annotations. Result remained blocked.
2. Home post-fix comparison found that PyDeskUI `Icon` canvases still exposed rectangular backgrounds and unselected navigation rows still looked like cards. Icons were given the native window background and the sidebar/navigation surface was aligned with the gallery; the post-fix capture shows only the selected route tile.
3. Plugin-center comparison found the old installed 0.1.0 bundle still exposed `dialogs.choose_directory`. The image plugin was bumped to 0.2.0, first-party startup provisioning gained version-aware upgrades, and the persisted QA profile upgraded in place. The final plugin capture shows version 0.2.0 and only `dialogs.open_files`.
4. JSON comparison found duplicated/misaligned status rows and undersized edge-hugging code. Input and output now use matching code surfaces with a single aligned status row and larger padded monospaced text.
5. Image comparison found the preview switcher too close to the settings heading. It was moved to its own row. The final capture shows a complete automatically generated preview with no overlap and no manual Preview action.

## Verification

- Ruff passed across PyDeskTools and the changed PyDeskUI files.
- Mypy passed all 17 configured PyDeskTools source files.
- 36 non-GUI image, JSON, runtime, and adversarial tests passed.
- Real-Tk regressions passed individually for the complete JSON/theme/language flow, route/sidebar/plugin layout, automatic image preview/compression, and the changed PyDeskUI navigation/segmented controls.
- The rebuilt installed image bundle was queried from the persisted SQLite profile: version `0.2.0`, capabilities `["dialogs.open_files"]`.
- Primary interactions checked: route selection, plugin filtering and selection, JSON editing/format flow, image queue selection, automatic preview, Original/Compressed switching, setting refresh, and compression. No Tk callback errors appeared during captures.

## Follow-up polish

- P3: macOS title-bar chrome and font rasterization remain platform-owned.
- P3: Tk integer image subsampling prioritizes guaranteed full-image containment over browser-grade interpolation.

final result: passed
