# PyDeskTools design QA — 2026-09-08

## Scope and references

This revision follows the four supplied home / JSON / plugin / settings mockups
and the annotated plugin-center screenshot. PyDeskUI's gallery and its local
Card, Surface, NavigationItem, SearchEntry and ItemList implementations were
checked before changing application composition.

Home and tools retain the global search and 232 px navigation rail. Per the
user correction, plugin center and settings are standalone pages with their own
local sidebar and content, plus a Home action; the outer shell is hidden. Plugin names,
state and versions use two-line rows, while data details scroll independently of
the destructive-action footer. Home has a larger search field and an outlined
onboarding card. JSON and image workspaces use bounded PyDeskUI cards.

## Adversarial review

1. **Cards without visible boundaries on Aqua.** Card's instance defaults override
   the portable themed border. ContentCard explicitly sets the native border.
   The real macOS preview shows list, detail and editor card boundaries.
2. **Declared spacing that does not reach layout.** Surface theme padding did not
   create the intended Tk frame insets. PaddedSurface applies widget padding;
   JSON title and editor margins were checked again in a real window.
3. **Clipped names, long paths and off-screen actions.** Built-in plugin names and
   versions occupy separate lines. Detail text wraps to the viewport; the footer
   stays outside its scroll region. GUI assertions check action width and both
   window edges at the supported minimum of 1100 × 720.
4. **Stale selection or colors after route/filter/theme changes.** GUI tests
   verify standalone navigation, return-to-home actions, empty filters, restored selection and dark-theme
   list selection colors. Theme cache tests allow retained inactive variants.
5. **Empty translations leaking metadata.** An empty plugin description used to
   resolve gettext's catalog header. The fallback is a nonempty local-processing
   description, with a regression assertion. Compression-preview text is translated.

## Verification

- Full suite: 42 tests passed before the final visual spacing refinements.
- The six real-Tk GUI tests were rerun after those refinements, covering JSON
  format/copy/export, image preview/compression, route and minimum-size layout,
  theme/language switches, and native dialog cancellation.
- Ruff and mypy passed (17 configured source files).
- Real macOS previews inspected: home, settings, plugin center and JSON editor.
- Current screenshots:
  - /Users/openhacking/.codex/visualizations/2026/09/08/01a07f8d-5883-7051-9b6d-eca9ab45bb11/plugins.png
  - /Users/openhacking/.codex/visualizations/2026/09/08/01a07f8d-5883-7051-9b6d-eca9ab45bb11/json.png

## Limits

Native Aqua title bars and rectangular card borders remain platform-owned.
This is a functional composition of existing components, not a pixel-identical
rendering of the concept images. Discovery, automatic updates and other controls
without a working backend were not added. Windows and Linux visual appearance
were not inspected in this macOS session. The installed app bundle has not been
rebuilt; restart from the source checkout to see these changes.

The plugin screenshot was refreshed after the user correction. The targeted
real-Tk navigation test passed: both standalone pages hide the global shell,
retain their local sidebar, and return to the full home shell. Ruff, mypy and
git diff --check passed after this correction.

## 2026-09-08 follow-up

See [UI experience update](docs/ui-experience-update.md) for the implemented changes, adversarial review, measured timings and local screenshot/package evidence. Final unlocked focus verification and the last screenshot refresh remain pending because the desktop locked during QA.

## Current white-surface and interaction pass

- Source visual truth: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-bf52f7a6-04a4-4ba0-ae00-9643f5c88f4d.png` and `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-dd9373c9-ca0c-4fbf-8bec-7f05ce9291bd.png`.
- Source dimensions: 1271 × 871 and 1255 × 847 physical pixels.
- Intended implementation viewport: 1280 × 840 Tk logical pixels at the current macOS display density.
- States required: light Home with focused search; light Image Compressor after a completed batch; JSON Options open and dismissed through Return/outside click.
- Implementation screenshot: unavailable because the Mac remained locked during both Computer Use capture attempts.
- Full-view and focused-region comparison: blocked before capture; no fidelity claim is made from tests or source inspection alone.
- Interaction evidence: PyDeskUI 123 tests and PyDeskTools 46 tests passed, including insertion-cursor clearance, attached Popover dismissal/focus, stable image-workspace geometry, status imagery and MB formatting.
- Comparison history: implementation completed and automated checks passed; no visual iteration could begin while the desktop was locked.

historical result: blocked

## Image Compressor batch-flow pass — 2026-09-08

- Source visual truth: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-bbaedbaf-de15-4d89-90d0-ed93588c2ae2.png` (empty) and `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-99f8ca48-368d-4bed-b113-ec95cb437c09.png` (completed).
- Implementation captures: `dist/verification/ui/image-compressor-empty-20260908-window.png` and `dist/verification/ui/image-compressor-completed-20260908-window.png`.
- Side-by-side inputs inspected: `dist/verification/ui/image-compressor-empty-comparison-20260908.jpg` and `dist/verification/ui/image-compressor-completed-comparison-20260908.jpg`.
- Viewport: 1280 × 840 Tk logical pixels, light mode, Simplified Chinese, macOS Aqua.
- Layout: the empty list, preview, footer, and disabled action are removed from the initial state. A single large import target now owns the left workspace while the compact settings column remains stable. The active state restores three bounded columns without overlap or clipping.
- Hierarchy and copy: the import icon, drag instruction, supported formats, primary chooser, and local-processing reassurance form one scan path. The completed state exposes pending count, clear action, disabled Completed action, next-batch action, and output-folder action without duplicating the empty guidance.
- Typography, color, icons, and imagery: existing PyDeskUI font/token/icon assets are retained; no substitute SVG, CSS drawing, or placeholder image was introduced. Disabled and semantic status states remain distinguishable by icon plus text.
- Interaction and accessibility: chooser remains available when TkDND is unavailable; drop paths use Tcl list parsing; controls are disabled during compression; button labels describe Completed, Recompress, and Retry states. Real Tk tests cover 1100 × 720 minimum layout, Chinese/English, light/dark changes, keyboard-invokable buttons, stale-preview cleanup, and state transitions.
- Adversarial fixes made during QA: compiled new strings into the packaged locale rather than the source-only catalog; registered visible drop-target descendants so child labels and the queue Treeview cannot mask card targets; changed the toolbar count from total-only to pending plus total; rejected direct compression submission with no pending paths.
- Verification: 47 tests passed; Ruff, mypy, and `git diff --check` passed. The rebuilt frozen app loaded Tk 9.0.4 and TkDND 2.10.2, its disposable installation diagnostic passed, deep code-sign verification passed, and the DMG checksum verified.

final result: passed

## JSON Options Popover boundary pass — 2026-09-09

- Source visual truth: `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-c2cd6064-0983-48c6-ae1b-8d0658c3858b.png` (301 × 307) and the menu-style reference `/var/folders/t4/5jpgr2kj5ygcf_9jq59b0ykm0000gn/T/codex-clipboard-6bffd897-96d6-406b-a390-d53a9de2f31e.png` (519 × 371).
- Implementation screenshot: `/private/tmp/pydesktools-popover-after.png` (1280 × 840 physical pixels), native Tk viewport 1280 × 840, light mode, Simplified Chinese, macOS Aqua, JSON Options open.
- Focused side-by-side evidence: `/private/tmp/pydesktools-popover-comparison.png`. The comparison uses the supplied problem crop, the supplied DropdownMenu treatment, and a 301 × 307 crop of the updated application at matching output density. Full-view evidence is the implementation screenshot; focused evidence is decisive because the scope is only the popup boundary.
- Comparison history: the initial PyDeskUI reproduction (`/private/tmp/pydeskui-popover-before.png`) had no visible edge. After moving the menu inset into the shared attached-popup surface, `/private/tmp/pydeskui-popover-after.png` and the application capture show a continuous rounded one-pixel boundary without changing internal layout.
- Fonts, copy, controls, icons, and semantic colors remain unchanged. Existing `popover`/`border` tokens provide light/dark compatibility; no new asset or fixed color was added.
- Interaction evidence: PyDeskTools' real-Tk regression opens Options, checks the shared surface inset and initial field focus, then dismisses with Return. PyDeskUI's full overlay tests cover outside click, Escape, toggling, viewport bounds, menu keyboard navigation, and theme refresh.
- Findings: no actionable P0, P1, or P2 mismatch remains. Windows/Linux visual capture is a P3 follow-up only.

final result: passed
