# PyDeskTools

An offline desktop toolbox with isolated Python plugins. **0.1.0 is experimental.**
This milestone ships JSON Tools and Image Compressor as complete offline plugins.
The routed desktop shell includes a search-first home, an in-app command palette,
single-sidebar plugin management and categorized settings. No account or network is
required at runtime. Screenshot and other future tools are not implemented yet.

The macOS arm64 DMG contains the GUI, Tcl/Tk, a separate CPython 3.13 interpreter
and both complete offline plugin bundles. Drag the app to Applications. An
ad-hoc test build is not Developer ID notarized and is not a public release.

## Development

The application requires Python 3.13+ with Tk 9 and PyDeskUI 0.2. The default
offline plugin bundles currently target CPython 3.13 on macOS arm64. See the
[development guide](docs/development.md) for environment setup, editable installs,
tests, troubleshooting, and launch commands.

`pydesktools` and `python -m pydesktools` share one entrypoint. `--data-dir` selects
an isolated application profile. The first launch provisions both default tools offline.
Disabled/uninstalled defaults stay that way; Restore explicitly reinstalls the
shipped version. Installing third-party code requires consent and starts disabled.

The application owns Tk and OS dialogs/clipboard. Runtime services import no GUI;
SDK/plugin wheels can run without the toolbox. A plugin is ordinary local code
with your OS authority, not a sandboxed extension. The host never imports it.

See [implemented interfaces](docs/implemented-api.md), [release build](docs/build-release.md),
[delivery evidence](docs/implementation-report.md), [contributing](CONTRIBUTING.md),
and [architecture proposals](docs/README.md). Proposed screenshot/online/update
contracts are not claims of implemented behavior.
