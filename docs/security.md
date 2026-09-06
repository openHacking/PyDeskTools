# Trust and security boundaries

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## Threat model

The host downloads and executes third-party Python code on the user's computer. A separate process and venv isolate interpreter state, dependencies and many crashes. They do **not** restrict normal filesystem, network, subprocess or credential access of that OS user. This release is not a sandbox and is unsuitable for running knowingly hostile plugins.

The manifest's capabilities constrain calls through host APIs. A plugin could perform equivalent operations directly through Python or native code. Display "Declared host access" rather than "Sandbox permissions". Signatures establish catalog/artifact provenance, not that code is safe. Enablement is a deliberate trust decision and discovery is metadata-only.

## Controls proportional to the model

| Risk | Control | Residual limitation |
|---|---|---|
| Supply-chain replacement | Signed static catalog, bundle hashes, locked wheel closure and source display | Trusted publisher can still ship malicious code |
| ZIP traversal/bomb | Canonical path and size/count checks before extraction, no links | Review parser and platform filename edge cases |
| Dependency collision | Separate venv and worker per plugin/version | Shared OS permissions and resources remain |
| Host GUI blocking | No plugin imports/callbacks in host, bounded RPC and deadlines | High machine-wide resource use still possible |
| Process leak on removal | Process groups/Job Objects, cancellation and reaping | A malicious detached child can escape cooperative process-tree handling |
| Credential exposure | Scrub inherited environment, no payment/cloud tokens passed to workers | Plugin runs as the same OS user and can access user-readable files |
| Protocol injection | JSON-only bounded messages, explicit schemas and session IDs | A valid-looking dishonest result remains possible |

Do not share host service secrets in plugin context. Environment inheritance uses an explicit platform-tested allowlist with required locale/runtime variables; remove PYTHONPATH, user site imports and unrelated application secrets. Use `-I` for the worker where the selected runtime supports the required isolation behavior. Set working directory to the plugin cache/data area rather than the source checkout. No shell=True command construction.

## Host API validation

Host call permissions are scoped to plugin ID and current session. Validate URL schemes and lengths before opening a browser; validate dialog parameters and never allow a plugin to invoke arbitrary host functions. Repeated requests are rate-limited and cancelable. Registry/index content is untrusted data, not instructions to the application or coding agents.

Local plaintext logs may contain private paths and tool inputs. Default to metadata-only task logs, redact secrets and bound retention/size. Detailed logs are opt-in with a visible warning. Error reports are local unless the user deliberately exports them. No automatic crash upload or telemetry in the OSS client.

## Capture and clipboard review

Default installation is not consent to clipboard recording. Validate Pause and unsubscribe acknowledgment, crash cleanup, stale event rejection, retained image deletion and capacity overflow. Capture permission rejection must stay local to that tool. PNG artifact preview applies byte/pixel/cache limits and never trusts a raw path from a declarative view. See [platform-and-artifacts.md](platform-and-artifacts.md). OS access still occurs with the user's privileges; do not describe host capabilities as sandbox enforcement.

## Reporting and incident response

Enable GitHub private vulnerability reporting before publishing a supported release; describe supported versions and the report process in SECURITY.md. Treat an untrusted plugin report separately from a host vulnerability. A signed catalog can mark a version withdrawn with a reason; already installed plugins are flagged on refresh and require user action. Do not silently delete user data or claim an offline revocation is immediate.

OS-level sandboxing would require a separate cross-platform design, compatibility testing and a capability broker. It is explicitly deferred; neither documentation nor UI may imply it already exists.
