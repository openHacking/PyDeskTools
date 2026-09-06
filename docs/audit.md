# Current implementation audit

> Design baseline: 2026-09-03 · Source revision: `c0918e8` · Target design, not implemented behavior.

## Baseline

Observed local revision `c0918e8`, dated 2022-10-01, metadata version 0.0.1. All 24 Python files parse with Python 3.14.3. This is syntax evidence only. The environment lacks `_tkinter`, so application startup and GUI behavior were not verified.

The project currently contains two experimental plugin paths (`DeskCore` and `PluginEngine`) and a demonstration window. There is no implemented plugin marketplace, dynamic removal, dependency isolation or general plugin UI protocol. Top-level tests contain only an initializer; sample plugin tests assert `True == False` and are not meaningful coverage.

## Findings

| ID / priority | Evidence | Impact | Required change / acceptance |
|---|---|---|---|
| TOOLS-01 / P1 | [win.py](../src/pydesktools/win.py) imports `pydeskui.button.TxButton`, absent in local PyDeskUI | Main window import cannot be satisfied by the checked-out UI implementation | Consume a real released public API; clean wheel startup test |
| TOOLS-02 / P1 | [app.py](../src/pydesktools/app.py), engine/usecase modules use top-level imports such as `from engine` | Installed package depends on working directory / sys.path accidents | Package-qualified imports, `python -m pydesktools` and console/GUI entrypoints |
| TOOLS-03 / P1 | [utilities.py](../src/pydesktools/usecase/utilities.py):56–78 installs with `sys.executable -m pip` during discovery | Discovery mutates the host environment; conflicting plugin dependencies and hidden failures | Metadata-only discovery; explicit install transaction into per-plugin environments |
| TOOLS-04 / P1 | Same file:46–54 compares package names only | Existing wrong versions are treated as satisfying requirements | Resolver plus locked wheel closure, PEP 440 checks and post-install `pip check` |
| TOOLS-05 / P1 | [engine_contract.py](../src/pydesktools/engine/engine_contract.py):11 calls `super().__init__(cls)` in metaclass initialization | Signature is inconsistent with normal metaclass initialization; exact runtime failure not tested because startup imports already fail | Replace registry side effects with explicit manifest entrypoint loading in a worker |
| TOOLS-06 / P1 | [interactors.py](../src/pydesktools/usecase/interactors.py) clears registries and reuses import_module | Clearing a list does not unload modules, threads, resources or dependencies | Explicit process lifecycle; stop admission, cancel, terminate and reap |
| TOOLS-07 / P1 | [pyproject.toml](../pyproject.toml) lists only pydeskui; source also imports yaml, dacite and pkg_resources | Wheel metadata does not reproduce application requirements | Single metadata source, intentional dependency inventory and isolated install tests |
| TOOLS-08 / P2 | `PluginUtility.setup_plugin_configuration` recomputes built-in plugin path instead of using supplied directory | Custom plugin directory handling is inconsistent | Platform user-data storage with explicit roots |
| TOOLS-09 / P2 | [helpers.py](../src/pydesktools/util/helpers.py) locates config and plugins beneath installed package | User mutations target potentially read-only installation files | Separate immutable package resources and writable per-user data |
| TOOLS-10 / P2 | [app.py](../src/pydesktools/app.py) invokes plugin engine before starting GUI; metadata still mentions anime/device concepts | Startup can block; inherited domain concepts do not match a toolbox | Thin entrypoint, command model and asynchronous startup |
| TOOLS-11 / P2 | setup.py/requirements repeat incomplete metadata; sample manifests refer to `tests` while directory is `test` | Build and example drift | Unified packaging, realistic example plugin contract tests |
| TOOLS-12 / P2 | [core.py](../src/pydesktools/core.py) mutable default list; global metaclass registry and logging-class changes | Hidden global coupling complicates lifecycle testing | Explicit service ownership, scoped logging and no plugin import at discovery |

Priorities: P1 blocks reliable core behavior; P2 affects maintainability, portability or onboarding. These are design findings, not a claim that every failure was reproduced interactively.

## Dependency modernization

| Existing item | Target |
|---|---|
| pydeskui==0.0.1 | A tested compatibility range for source distribution, exact resolved version in application release lock |
| PyYAML==5.4 | Remove from new manifest/config path; TOML via tomllib and JSON/SQLite state |
| dacite==1.5.0 | Remove; explicit dataclass conversion and schema validation |
| packaging==20.4 | Retain packaging as a direct host dependency for versions and wheel compatibility; update to tested supported release |
| pkg_resources import | Remove; importlib.metadata/resources and packaging APIs |
| New platformdirs | Justified host dependency for OS data/config/cache paths |
| New jsonschema | Justified host dependency for plugin command/view validation; restrict accepted schema vocabulary |
| New cryptography | Justified host dependency for signed catalog verification; not a PyDeskUI or SDK dependency |

The SDK uses standard-library dataclasses, typing, json and logging; it does not import GUI libraries. The installer ships a pinned pip toolchain with its runtime; pip is an executable installation tool, not a Python API imported by the host. Development-only tools remain separate.

Python 3.7 is unsupported upstream. Current setuptools has removed pkg_resources, making modernization more than a formatting exercise. [Python lifecycle](https://devguide.python.org/versions/) and [setuptools history](https://setuptools.pypa.io/en/latest/history.html), accessed 2026-09-03. Dependency vulnerability status still requires an actual supported-resolution audit; no blanket CVE clearance is claimed.

## What is not established

No cross-platform installer, runtime size, startup benchmark, plugin shutdown guarantee or accessibility certification exists yet. The architecture below specifies experiments and gates to establish these facts before a release.
