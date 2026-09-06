# Proposed contract examples

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

These are machine-readable documentation fixtures, not installed plugins or a release catalog. Protocol/manifest version 1 and SDK 0.1.0 refer to the proposed implementation.

- [plugin.toml](plugin.toml): JSON formatter identity and compatibility.
- [descriptor.json](descriptor.json): one complete command descriptor.
- [protocol-session.json](protocol-session.json): successful initialization, activation, description, invocation, deactivation and shutdown.

The transcript wrapper is for documentation only; send each inner message as newline-delimited JSON on the actual pipe. The SDK implementation example is in [plugin-sdk.md](../plugin-sdk.md). A real bundle must add built wheels, a locked dependency closure, computed payload hashes and catalog authentication as described in [plugin-lifecycle.md](../plugin-lifecycle.md). No dummy hashes or placeholder signatures are presented as installable artifacts.

During implementation turn these fixtures into conformance inputs. Check identity/version equality, request/response pairing, command input/output schemas, view vocabulary and shutdown order. Parsing fixtures validates documentation syntax only; it does not verify process isolation or installation.

[Platform events and image view](platform-events.json) illustrates the draft clipboard/image contracts; it does not exercise OS capture or consent enforcement.
