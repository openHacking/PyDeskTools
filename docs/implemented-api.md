# Implemented API: 0.1.0

## Package boundaries

- `pydeskui`: generic widgets, no third-party runtime packages.
- `pydesktools_sdk`: Plugin/contexts, CommandResult, Descriptor/CommandDescriptor,
  CancellationToken, PluginError and `python -m pydesktools_sdk.runner`.
- `pydesktools_runtime`: RuntimeConfig, create_services, ServiceContainer, TaskHandle,
  CloseHandle. No tkinter, PyDeskUI or plugin import at module load.
- `pydesktools`: ApplicationConfig, ApplicationExtension, create_application, Application.
- `pydesk_json_tools`: ordinary independently installed plugin distribution.

## Services and composition

```python
from pathlib import Path
from pydesktools_runtime import RuntimeConfig, create_services

services = create_services(RuntimeConfig(data_dir=Path("profile"), python=Path("/path/to/python3.13")))
try:
    services.install(Path("tool.pdtplugin"), consent=True)
    services.enable("org.pydesk.json-tools")
    task = services.commands.submit("org.pydesk.json-tools", "format", {"text": "{}"})
    result = task.result(timeout=30)  # Never block the Tk thread here.
finally:
    services.close()
```

Use `commands.describe(plugin_id, command_id)` before submitting. `version=` may
select the installed version; other versions are rejected. `TaskHandle.id`,
`cancel()`, `future` and `result(timeout)` expose completion. `tasks.subscribe`
returns an idempotent CloseHandle. Callbacks run on service threads; GUI consumers
queue them onto their own event loop. Events: started/progress/completed/failed.
A forced stop or lost response carries `completion_unknown`, never clean success.

`disable` cancels work and waits for process reaping. `uninstall` retains saved data
unless `delete_data=True`. `set_locale` refuses active work and retires idle sessions.
`close` is idempotent; applications invoke it off the GUI thread during shutdown.
Result owners release their artifact reference with
`services.artifacts.release("result:" + task.id)` when the view is discarded.

`ApplicationConfig` supplies app_id/display_name/version/data_namespace,
extensions and optional data_dir/python. Extensions register through HostServices
commands/tasks and `views.register(id, factory)`; factories receive an explicit Tk
parent. Handles close in reverse registration order. Nonempty catalog_sources is
explicitly unsupported in this milestone.

## Protocol and images

Protocol framing, deadlines and ownership follow the design documents. SDK schema
support is the documented bounded subset; no remote references or executable
validation. Runtime interactive capabilities in 0.1 are dialogs.open_file,
dialogs.save_file and clipboard.write. No clipboard read/subscription or capture.
Artifacts contain files and are scoped by plugin ownership, with 200 MiB/file and
1 GiB/cache limits. Rendering arbitrary image views is not enabled yet.

## JSON commands

Commands: format, minify, import, copy, export. Format/minify accept exactly one
of text/artifact_id plus indent (0–8, default 2) and sort_keys (default false).
Import uses the native open dialog. Copy/export accept artifact_id from a prior
result. JSON input is capped at 20 MiB and 128 levels; output at 200 MiB.
Results include bytes, artifact_id, truncated and optional small inline text.
Previews never exceed 64 KiB. Duplicate keys/nonfinite values fail with source
positions. Decimal values are preserved numerically; whitespace/exponent spelling
may change. Files decode UTF-8 (an optional UTF-8 BOM is accepted).

## Port Manager (unreleased)

`org.pydesk.port-manager` exposes `scan` (read, safe retry) and `stop` (external,
manual retry). Scan returns services grouped by process with all visible TCP
listeners, an opaque session token, process metadata and development hints.
Stop takes `{token, force?}`; it accepts only a current scan token for an eligible
current-user process. It rechecks PID creation time, ownership and observed endpoints.
Every stop returns a fresh scan and `released_ports` / `occupied_ports` for the
original port numbers, based on the visible listeners. Neither command probes HTTP.

The first-party host supplies a searchable dedicated view and a confirmation dialog.
No generic process-execution capability is added to the SDK. The worker performs
OS operations using its existing current-user permissions; this is not a sandbox.
Windows termination is immediate. POSIX normal stop uses SIGTERM, with a separately
requested SIGKILL option. Child processes are not stopped. See the
[plugin README](../plugins/port-manager/README.md) for visibility and environment limits.
