# Plugin manager and user journeys

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## Application shell

Initial navigation has Tools, Plugins and Settings. Tools shows installed enabled commands, a search field and a result area. Plugins contains Installed and Discover tabs, with a detail panel for selected items. Settings contains language, theme, catalog sources and local data/log locations. Global launch hotkeys and tray behavior remain later integrations. Clipboard history is a default plugin with explicit opt-in recording and the background subscription lifecycle.

Use resizable layouts and PyDeskUI primitives; avoid the prototype's fixed 600x600 window. Search operates on translated labels plus stable IDs; do not filter out a tool merely because its name is in a different language.

## Primary journeys

| Journey | UI behavior | Completion condition |
|---|---|---|
| First launch offline | Provision five complete default bundles locally, then show ready tools; no sign-in prompt | All five tools work offline on an advertised supported desktop, with clipboard recording opt-in |
| Discover and install | Select version/platform, inspect publisher/source/capabilities, consent, show progress and Cancel | Verified install exists in disabled state; offer Enable now |
| Enable | Start process, handshake, activate and validate commands without freezing shell | Status ready/active and command appears |
| Execute | Render form, validate input, display progress, allow Cancel, show result/errors | One terminal task state and keyboard-accessible result |
| Disable during work | Explain that current tasks will be canceled; user confirms; enter stopping | Worker reaped, views removed and status disabled |
| Update | Show changelog/compatibility, wait for or cancel pinned jobs, install candidate | Code/data activation completed; prior version retained |
| Uninstall | Default preserve saved settings/data; separately selectable data deletion | Runtime stopped and code removed, or explicit removal_pending status |
| Broken plugin | Show failed state and concise explanation, offer log view, restart or disable | Host remains usable and no automatic restart loop occurs |

User-installed code receives a clear warning that it runs with the user's OS permissions. The confirmation concerns executing third-party code, not purchasing a product. A hash-only local bundle is shown as unverified, not secure.

## Manager detail fields

Show stable plugin ID, translated name/description, installed and available versions, publisher/catalog source, supported platform/runtime, declared host capabilities, data location and state. Trust labels distinguish official catalog, user-trusted catalog and unverified local bundle. Do not display a "sandboxed" badge.

An install job reports download, verification, dependency preparation, health check and commit phases. Errors identify the phase and preserve bounded diagnostics. Cancel before commit removes candidate state; after commit it becomes a completed installation and the UI offers uninstall rather than claiming a rollback occurred.

## Reusability boundary

PluginCard, VersionSelector, InstallProgressController, PermissionDisclosure and CatalogSourceEditor are PyDeskTools business components. They compose generic ItemList, DetailView, Form, ProgressView, Dialog and Button controls from PyDeskUI. Manifest rendering lives in the host, not the UI library.

## Recovery and accessibility

Remember input values across view refreshes where safe; invalidate result actions when their plugin/session disappears. Keep destructive buttons away from routine Enable/Run controls. Return focus after dialogs, preserve selection after list refresh and expose progress as text as well as animation. Closing the application triggers bounded shutdown and offers a clear warning for active side-effecting jobs.

The UI reports actual observed state. In particular, queued deletion on Windows is not labeled removed, and an enabled plugin awaiting lazy start is not labeled running. All state labels are translatable.
