# Packaging, runtime and open-source engineering

> Revised design: 2026-09-04; source audit: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## Independent distributions

Publish `pydesktools`, `pydesktools-runtime` and `pydesktools-sdk` from this repository as separate wheels with separate dependency sets. The runtime exposes headless services; only the application wheel owns the toolbox shell and default-tool provisioning. The application, runtime and SDK package pyprojects are distinct authoritative build configurations, not duplicate metadata for one distribution. All use setuptools and src layouts. Publish SDK, then runtime, then application/plugin bundles in dependency order, skipping unaffected packages. PyDeskUI is a separately released dependency with a compatible range in application metadata.

Keep a checked-in developer/release lock to reproduce the application build. Dependency ranges in published package metadata must remain truthful; the installer freezes the resolved versions. The SDK has no GUI dependency. Console command `pydesktools` and `python -m pydesktools` call the same explicit main function; platform GUI launchers suppress an unnecessary console without hiding diagnostic logs.

Remove prototype setup.py metadata, YAML configs and legacy plugin engine only as replacement behavior lands. Source checkout execution from inside `src/pydesktools` is not the supported installation model.

## Two runtimes in packaged applications

Initial packaging proposal: PyInstaller onedir for the GUI, including Tcl/Tk; a separately addressable CPython 3.13 runtime for plugin venvs, sourced from a pinned redistributable build such as python-build-standalone. The plugin runtime need not include Tk. It must provide venv and a pinned pip installation toolchain. The GUI's frozen executable is not passed to `-m pip` or `-m pydesktools_sdk.runner`.

The interpreter locator reads a release-generated runtime manifest with absolute installation-relative executable path, ABI, architecture, version and hashes. Validate executable identity before running it. In pip/source mode use an explicitly validated compatible Python interpreter; when the current interpreter cannot satisfy a bundle ABI, show the mismatch and instructions rather than silently downloading another runtime.

Clean up PyInstaller-specific dynamic-library environment modifications before launching the independent runtime. Preserve required platform variables through a tested subprocess environment builder. [PyInstaller subprocess pitfalls](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html) and [redistributable Python builds](https://github.com/astral-sh/python-build-standalone), accessed 2026-09-03. This arrangement is a proposal requiring a packaging spike, not a verified installer.

## Platform rollout

| Target | First release delivery | Required runtime evidence |
|---|---|---|
| Windows 11 x64 | Signed installer containing onedir GUI and plugin runtime | Clean machine without Python; Job Object cleanup; paths with spaces/Unicode; locked-file removal |
| macOS arm64 and x86_64 | Separate Developer ID-signed application builds; notarization deferred until embedded native wheels are signed | Tcl/Tk behavior, external runtime execution and signed wheel/native code handling under platform security policies |
| Linux x86_64 | pip/source install on documented Ubuntu LTS environment | Tk system dependency, XDG paths, GUI subset under Xvfb and native desktop checks |

Concrete minimum macOS version is the stricter of the chosen Python/Tk build and the validated CI target; record it in the packaging spike before advertising support. Windows arm64, Linux arm64, additional distributions and bundled Linux packages are later gates, not implied by "cross-platform".

Do not modify a signed macOS application bundle at runtime. Plugin environments live in writable user data. Bundled runtimes update through signed application releases; retain runtimes required by existing plugin installs or rebuild those installs from their stored bundles before retiring a runtime. Old runtime cleanup checks references and running workers.

## CI matrix and tooling

Ruff, mypy and pytest are development tools. Host dependency review covers packaging, platformdirs, jsonschema and cryptography; SDK tests run with only its declared dependencies. Build wheels/sdists, `twine check`, install outside the checkout and run `pip check`.

Run headless SDK/runtime tests on Python 3.11–3.14. Run application GUI tests on
Python 3.13+ with Tk 9; the default bundle workflow uses Python 3.13. Installer CI
targets the selected runtime ABI. Test real process workers, incompatible dependency
pairs, malformed bundles/RPC, cancellation and crash recovery. A fake subprocess
mock alone cannot prove unload behavior. Test optional downstream composition
against the published host wheel.

## Governance and releases

Retain MIT and add coherent CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, CHANGELOG, issue/PR templates, maintainer/review expectations and third-party notices during implementation. Public discussion and docs use English; contributions to translations are welcome. Track licenses of plugin bundles and runtime binaries separately from the host's MIT license.

Use protected tagged releases, minimal GitHub Actions permissions, pinned actions and PyPI Trusted Publishing. Generate hashes and a dependency/license inventory for desktop artifacts; sign OS distributions and the catalog separately. Community plugin submissions require metadata/schema checks, license review, reproducible wheel closure and manual provenance review; avoid executing unreviewed code with release credentials.

Version the host and SDK independently using PEP 440-compatible semantic versions. Before 1.0, breaking changes bump minor versions. Protocol majors have explicit compatibility gates. A plugin requiring an unsupported protocol is shown as incompatible, not partially loaded.

## Performance targets to measure

No measured startup/memory claim is made. Initial acceptance targets on a recorded reference machine: shell visible within 2 seconds cold start with plugins lazily loaded; cancellation UI acknowledges within 100 ms; normal main-thread work under 50 ms. Measure GUI runtime and per-active-plugin memory separately, plus interpreter and wheel-cache disk costs. Process isolation has overhead; cap running plugins to 4 by default and queue/start on demand, shutting down idle workers after 5 minutes when no view/task/subscription needs them. A consented clipboard subscription uses the separate one-worker background lease described in the platform contract; it must not starve the four interactive slots. These defaults are tunable after measurement.

Platform capture and image clipboard adapters may require application-only native or Python dependencies. Record their OS-specific locks, licenses and missing-feature diagnostics; they must not enter PyDeskUI core, the SDK or the headless runtime. Plugin-local Pillow is separate from any host image adapter dependency.
