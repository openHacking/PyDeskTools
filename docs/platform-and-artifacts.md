# Platform capabilities, artifacts and subscriptions

> Revised design: 2026-09-04. Proposed additions to the unreleased protocol 1 design.

These facilities support the five default tools without importing plugin code into the GUI process. They are public host capabilities and contain no commercial authorization logic. They do not create an OS sandbox.

## Responsibility boundary

The host owns OS capture/clipboard access, native dialogs, generic rectangle selection and validated artifact presentation. Plugin workers own compression, formatting, history retention, search and user-facing task logic. PyDeskUI owns only generic image preview and rectangle-selection widgets. Business data and compression/recording rules stay out of the UI library.

## Host-call additions

| Capability | Arguments | Result / lifetime |
|---|---|---|
| `screen.capture` | mode: desktop or region | `{artifact_id, width, height}` for normalized PNG; null on user cancel; permission failure is a structured error |
| `dialogs.open_file` | title; optional multiple=false | Single selection returns a path or null; multiple returns paths or an empty list on cancel. A worker reads selected files directly; to present a result, copy it into its export directory and call artifacts.import |
| `dialogs.save_file` | title, suggested_name, artifact_id | Saves through a host-owned dialog; result chosen path or null; no silent overwrite |
| `clipboard.read` | `{}` | Text or image artifact, or null for unavailable/unsupported formats |
| `clipboard.write` | text or artifact_id, exactly one | Copies content after validation; no history access implied |
| `clipboard.subscribe` | formats: text/image | subscription_id after user consent; source events carry text or image artifact |
| `clipboard.unsubscribe` | subscription_id | Idempotent release; acknowledged before UI reports recording paused |
| `artifacts.import` | relative_path under this worker's export directory | Opaque artifact_id after validation/copy; no arbitrary host path |
| `artifacts.read` | artifact_id | Readable copy path in this worker's import directory |
| `artifacts.release` | artifact_id | Releases the caller's reference, idempotently |

Open/save dialogs and capture execute through the Tk-owning thread and platform adapters; expensive copying/decoding runs outside that thread. Extend PluginContext.host helpers to call these capabilities; invocation tasks can use the same client through `InvocationContext.host`. Their lifetime remains bounded by the parent task/session. Artifact operations are base SDK services; clipboard/capture/dialog operations require declared host access and user action/consent as applicable.

## Artifact contract

Artifacts are immutable host-managed files scoped to application namespace, plugin identity and a live task/session. Protocol messages carry opaque IDs plus media metadata, not base64 image bytes. Only PNG is accepted for host image rendering; plugin-local decoders normalize other formats. Text/file artifacts may be used for JSON exceeding the inline message limit.

The runner receives host-created import/export directories at initialize. `artifacts.import` rejects absolute/traversal paths, symlinks and files outside the export root; copy into host-controlled storage before accepting the artifact. Cap a file at 200 MiB and an image at 40 million decoded pixels, validate dimensions before full decode where possible, and bound aggregate cache to 1 GiB. These are resource controls, not protection from a same-user malicious process. Do not import paths merely because a plugin's view contains a filename or URL.

Workers receive readable copies through artifacts.read and retain their own ordinary working files if needed. No consumer mutates the host's immutable artifact. Views and clipboard services acquire their own references; worker unload releases only its session references. A result view can retain a preview after worker exit, but its command actions become unavailable. Closing a view or replacing clipboard content releases the relevant host reference. Local history copies data to its persistent plugin store before releasing transient artifacts. Stale IDs fail predictably; a new session must reimport retained local content. Explicit data deletion removes history-owned image copies as well as records.

## Subscription contract

Add runner hook `handle_event(event, context)` for plugins declaring subscriptions. The control reader receives a `host.event` notification containing subscription_id, event_id and payload. The runner serializes short event handlers with ordinary command hooks through a bounded queue; no concurrent mutations of the plugin instance. Cancellation/control reading remain independently responsive. Event handler budget is 100 ms; expensive work must be scheduled as a task rather than blocking the reader.

Subscriptions hold an active-worker lease, so clipboard recording is not killed by the ordinary five-minute idle timeout. Track them separately from the interactive worker admission count; v1 permits one background-subscribed worker per profile. Starting another background subscriber returns a visible capacity error until the existing lease is released. Enabling this lease requires consent; it is not granted merely by a manifest field.

Disable/uninstall/crash closes the host subscription before process cleanup and increments its generation. Discard queued or late events after unsubscribe; stop the OS listener when no subscriptions remain. Restart recording only if the user's persisted setting was enabled and the plugin was neither disabled nor removed. Unexpected worker crashes mark recording paused/failed and do not enter an automatic restart loop. User requests Resume to recover.

Queue capacity is 256 notifications per subscriber. Overflow pauses that subscription with a visible gap indicator; do not imply complete clipboard history after dropping events. Persistent history remains usable while recording is paused. Events and content are not written to host logs.

## Declarative image view

Add view type `image` with required `type`, `title`, `artifact_id`; optional `actions` uses the existing same-plugin command action contract. The renderer acquires an artifact reference and uses PyDeskUI ImageView. An optional `metadata` object can contain original/output byte counts for compression comparisons. It must not contain executable callbacks, raw file paths or remote URLs. Screen region selection occurs inside screen.capture through a generic host dialog, not through arbitrary user plugin Tk widgets.

Validate image views, artifact ownership, expiry, resource limits and cleanup with fixtures. Keep the existing 1 MiB RPC frame limit. Protocol 1 is not yet released, so these additions update its draft rather than pretending a deployed compatibility promise has changed.
