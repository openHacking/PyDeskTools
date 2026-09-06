# Proposed plugin SDK

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

The `pydesktools-sdk` distribution lives in this repository and imports as `pydesktools_sdk`. Proposed baseline SDK version: 0.1.0; wire protocol major: 1. The SDK must be usable without PyDeskTools, PyDeskUI or tkinter installed.

## Plugin interface

```python
# Proposed type sketch; the interface does not yet exist.
from typing import Protocol

class Plugin(Protocol):
    def activate(self, context): ...
    def describe(self): ...       # returns Descriptor
    def invoke(self, command_id, arguments, context): ...  # returns CommandResult
    def deactivate(self): ...
    # Optional for event-subscribing plugins; ordinary command plugins omit it.
    def handle_event(self, event, context): ...
```

The manifest entrypoint is `module:factory`. `factory()` returns one Plugin instance. The runner calls activate once per process session, caches the validated descriptor, serializes invoke calls, and calls deactivate at most once on graceful shutdown. Hooks must not assume deactivate will run after a crash or forced termination. Persistent data must already be consistent after each committed operation.

| SDK type | Fields / operations | Ownership |
|---|---|---|
| `PluginContext` | `plugin_id`, `version`, `session_id`, `locale`, `data_dir`, `cache_dir`, `settings`, `logger`, `host` | Runner-provided; paths are specific to this plugin and app namespace |
| `InvocationContext` | `task_id`, `cancellation`, `host`, `report_progress(fraction, message)` | Valid for one invocation; cancellation token polled by command |
| `CancellationToken` | `is_cancelled`, `raise_if_cancelled()` | Set by control thread; cooperative, not thread termination |
| `CommandResult` | `data: dict`, `view: dict \| None = None` | JSON-compatible payload; data validated against output_schema |
| `Descriptor` | `commands: list[CommandDescriptor]` | Returned after activation; cache per installed version and locale |
| `CommandDescriptor` | `id`, `title`, `description`, `input_schema`, `output_schema`, `effects`, `retry`, `timeout_ms` | Schema and identifiers stable within a compatible plugin version |

The runner creates InvocationContext rather than exposing transport IDs to plugins. Logging goes to stderr; `report_progress` emits a notification. No callback or arbitrary Python object crosses the process boundary.

## Command semantics

Command IDs are unique lowercase names within a plugin. The host addresses a command by `(plugin_id, command_id)`, not a translated label. Input/output schemas use a documented subset of JSON Schema 2020-12: object, array, string, integer, number, boolean, null, properties, required, additionalProperties, items, enum, bounds, lengths and descriptions. Disallow remote references and executable validation. Schema size and nesting have protocol bounds.

`effects` is one of `pure`, `read`, `write`, `external`. `retry` is `safe` or `manual`. These are author declarations used for presentation and conservative orchestration, not enforced proof. Missing or unknown effects/retry are rejected rather than treated as safe. Destructive and externally visible commands normally declare manual retry. A safe declaration still requires an implementation rationale and contract test.

`timeout_ms` defaults to 30000, range 100–3600000. The host may lower a command's budget (regular expression example: 2000 ms). Deadline expiry cancels and eventually terminates the worker. Retrying is always a new task with a new ID.

## Context services

`settings.get(key, default=None)` and `settings.set(key, value)` call host-managed per-plugin JSON settings storage. Values cannot contain non-JSON objects. Changes persist independently of worker lifetime.

`host.choose_file(*, title, mode="open")` is an RPC request serviced by a main-thread native dialog. It returns a selected path or None. A separate host save dialog exports a validated artifact; plugins that directly write ordinary files still declare their side effects. Multi-file selection is opt-in and preserves the default single-file return behavior. File selection is a user interaction, not an operating-system sandbox grant.

Initial host capabilities include dialogs, screen capture, clipboard access/subscriptions and system.open_url. The full extension and artifact contracts are defined in [platform-and-artifacts.md](platform-and-artifacts.md). The manifest must declare each used capability; the host checks user consent and validates arguments. Allow only http/https for open_url. Do not offer a generic host eval/exec capability. Base settings, logs and progress are always available to an enabled plugin. Plugins have ordinary process access to their own runtime and the OS; the security document explains why this is not sandboxing.

## Declarative rendering

The host derives an initial form from input_schema and the user selects Run. A command may return a view with structured output. Detailed wire/view shapes are owned by [plugin-protocol.md](plugin-protocol.md). Python helpers may build these dictionaries, but the dictionary contract remains the wire authority. Plain schemas do not require a dependency on PyDeskUI.

## Complete example plugin

```python
# Proposed SDK example; syntactically valid but not runnable until the SDK exists.
import json
from pydesktools_sdk import CommandResult

class JsonTools:
    def activate(self, context):
        self.context = context

    def describe(self):
        return {"commands": [{
            "id": "format", "title": "Format JSON", "description": "Pretty-print JSON text",
            "input_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                             "required": ["text"], "additionalProperties": False},
            "output_schema": {"type": "object", "properties": {"text": {"type": "string"}},
                              "required": ["text"], "additionalProperties": False},
            "effects": "pure", "retry": "safe", "timeout_ms": 30000
        }]}

    def invoke(self, command_id, arguments, context):
        if command_id != "format":
            raise ValueError("Unknown command")
        context.cancellation.raise_if_cancelled()
        value = json.loads(arguments["text"])
        output = json.dumps(value, ensure_ascii=False, indent=2)
        context.report_progress(1.0, "Formatted")
        return CommandResult(data={"text": output}, view={
            "type": "detail", "title": "Formatted JSON", "body": output,
            "format": "code", "actions": []})

    def deactivate(self):
        pass

def create_plugin():
    return JsonTools()
```

Production examples translate their visible messages and map json.JSONDecodeError into a structured user input error. The transport transcript illustrates successful execution; malformed input is a required negative test.

## Compatibility and testing

Use PEP 440 for Python package and plugin version constraints. Manifest schema and protocol version are independent integers. A bundle supplies a locked SDK version satisfying its declared SDK range; the host accepts only supported protocol majors. Verify actual wheel metadata, returned plugin identity and manifest agree before admitting commands.

The SDK release includes a conformance test harness: activation/deactivation, describe validation, input/output validation, cancellation, stdout contamination, progress limits and worker crash. Test the SDK wheel in an environment without GUI packages. Entry-point discovery inside the worker uses importlib, not a metaclass global registry. [PyPA entry points specification](https://packaging.python.org/en/latest/specifications/entry-points/), accessed 2026-09-03.
