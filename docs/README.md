# PyDeskTools design documentation

For source checkout setup, tests, and local launch commands, see the
[development guide](development.md).

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

PyDeskTools will be a local desktop toolbox for developers and technical users. It composes PyDeskUI primitives and runs user-installed Python plugins in separate processes. No account or application backend is required for the open-source client.

## Reading order

1. [Default free tools](bundled-tools.md) and [platform/artifact contracts](platform-and-artifacts.md).
2. [Current implementation audit](audit.md).
3. [Architecture and public application composition](architecture.md).
4. [Proposed plugin SDK](plugin-sdk.md).
5. [Process protocol and declarative views](plugin-protocol.md).
6. [Distribution, installation and lifecycle](plugin-lifecycle.md).
7. [Trust and security boundaries](security.md).
8. [Plugin manager and user journeys](user-experience.md).
9. [Storage and internationalization](storage-and-i18n.md).
10. [Packaging and engineering](engineering.md).
11. [Roadmap, acceptance and adversarial review](roadmap.md).
12. [ADR 0001: isolated plugin runtime](adr/0001-isolated-plugins.md).
13. [Examples](examples/README.md) and [documentation verification](verification.md).

## Authority and status

These are accepted design directions, not implemented capabilities of version 0.0.1. `plugin-sdk.md` owns command/context types, `plugin-protocol.md` owns wire/view behavior, and `plugin-lifecycle.md` owns distribution and lifecycle rules. Other projects consume these contracts rather than duplicating them.

[PyDeskUI](https://github.com/openHacking/PyDeskUI) owns generic widget contracts and can be used independently. The SDK is maintained in this repository but distributed separately from the desktop application. The SDK and UI library have no reverse dependency on the host application.

Documentation is English. Initial application translations are English and Simplified Chinese. Evidence is dated 2026-09-03 and classified as observed, proposed or unverified. Links to source files are relative to this independent repository; no private repository is required to read or build the public project.
