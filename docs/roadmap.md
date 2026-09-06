# Roadmap, acceptance and adversarial review

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## Delivery stages

| Stage | Work | Exit criteria |
|---|---|---|
| T0: engineering foundation | Repair package imports, entrypoints, metadata; establish fixtures and basic UI shell | Wheel starts outside checkout; no obsolete global plugin registry in replacement path |
| T1: runtime feasibility | Separate interpreter, installer tooling, CPython ABI bundle, process control | Windows/macOS clean-machine plugin install/invoke/terminate evidence |
| T2: SDK and lifecycle | Manifest, protocol, schema validation, install journal, stop/remove/update | Two plugins with conflicting dependencies coexist; no host pip mutation; crash/rollback tests |
| T3: useful OSS product | Manager, static catalog, five default free plugins, en/zh-CN | End-to-end offline and online journeys with responsive UI |
| T4: international release | SDK docs/examples, packaging matrix, provenance and support docs | Signed artifacts, documented support limits, complete contributor onboarding |

Do not build catalog growth features before one plugin can be reliably installed and removed from a packaged application. The target runtimes and exact dependency resolutions are recorded by the T1 spike; an installer remains experimental if its gates fail.

## Required scenarios

| ID | Scenario | Evidence |
|---|---|---|
| AT-01 | Install a local self-contained bundle while offline | No network activity or source build; compatible wheel closure installs |
| AT-02 | Two plugins require incompatible versions of the same package | Different venvs/workers return their expected versions; host dependency inventory unchanged |
| AT-03 | Disable during a long invocation | New tasks refused, queued tasks canceled, process reaped, stale view events ignored |
| AT-04 | Plugin crashes, writes noise to stdout or floods progress | Bounded failure; GUI remains usable; no unbounded memory growth |
| AT-05 | Kill application at every install phase | Reconciliation keeps old committed pointer and removes only orphan candidates |
| AT-06 | ZIP traversal, symlink, duplicate path, invalid signature or unsupported ABI | Reject before executing plugin code |
| AT-07 | Update with data migration, then fail | Old code/data pointers remain usable; rollback after new writes requires explicit snapshot choice |
| AT-08 | Uninstall on Windows with delayed file handles | removal_pending is truthful, cleanup resumes next launch, data preserved by default |
| AT-09 | Switch language/theme with open form and active task | Values retained, focus stable; plugin restart deferred until safe |
| AT-10 | Packaged runtime on machine without Python | GUI and plugin install/invoke work, paths do not reference build machine |
| AT-11 | Minimal SDK plugin without GUI dependency | SDK wheel imports and worker runs without tkinter/PyDeskUI |
| AT-12 | Downstream application extension | Uses public composition/command facade only, separate data namespace, no host fork |

Also test duplicate requests, cancellation versus completion races, task timeouts, expired catalog metadata, user-added keys, missing Tk diagnostics, long/Unicode paths, version-pinned jobs and application shutdown. Negative fixtures must assert useful error/state outcomes, not simply exceptions.

## Additional acceptance for the revised default tools

AT-13: all five default tools install and run offline on a clean supported desktop. AT-14: uninstall/disable survives restart and app upgrade; offline Restore is explicit. AT-15: no clipboard read before opt-in or after pause/unload, including queued events; enforce pin/age/capacity rules and explicit data deletion. AT-16: denied capture permissions do not block the shell; region coordinates remain correct on mixed-DPI screens. AT-17: images use bounded artifacts, release references and preserve original compression inputs. AT-18: timestamp unit/timezone/DST errors are explicit. AT-19: headless runtime wheel imports without GUI packages or toolbox/default-plugin installation.

## Adversarial review: five highest-risk assumptions

| Risk | Design response | Residual risk / gate |
|---|---|---|
| Frozen executable cannot run a Python worker or pip | Separate redistributable interpreter and cleaned subprocess environment | T1 must prove packaging/signing/ABI behavior on clean OS installs |
| "Unload" only removes a registry entry | Stop admission, cancel, terminate/reap process tree, invalidate UI generation and release registrations | Malicious detached children are not sandboxed; AT-03/08 measure actual cleanup |
| Capabilities falsely promise a sandbox | Explicit OS-user authority disclosure and host-only permission checks | Third-party code remains trusted code; review UI wording and AT-06 boundaries |
| Downstream products drift into a fork | Public composition API and published packages, downstream contract fixture | Reject private imports and duplicated host engine; AT-12 |
| Updating code corrupts or rolls back new user data | Separate data epochs, snapshot migration and explicit restore choice | External side effects cannot be restored; AT-07 |

## Requirement traceability

Modernization and dependencies: audit/engineering. Independent UI integration and component ownership: architecture plus upstream PyDeskUI contract. Dynamic plugins and manager: SDK/protocol/lifecycle/user experience. Internationalization: storage-and-i18n. Public documentation and contribution standards: engineering. Independent downstream applications: public composition API. Commercial product strategy is outside this public repository.

## Documentation delivery

[Verification report](verification.md) records checks completed for the design artifacts. The tests above describe future product acceptance and must not be marked passed merely because JSON examples parse.
