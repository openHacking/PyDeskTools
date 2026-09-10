# Contributing

Source packages support Python 3.11–3.14 with Tk. Check `python --version` before
creating the environment. The current default offline plugin bundle requires
CPython 3.13/macOS arm64 for full desktop integration.
Follow the [README environment setup](README.md#source-development) first.
From the repository root, create `.venv` once with `python -m venv .venv`
and activate it with `source .venv/bin/activate` in each new macOS/Linux terminal.
If `.venv` already exists, skip creation and only activate it; do not overwrite
it using a different Python installation. The README includes interpreter checks,
environment recovery guidance and platform limitations.
Install the companion PyDeskUI 0.1 wheel or editable checkout into this same
PyDeskTools environment, then the SDK, runtime, application and JSON plugin
from their pyproject directories. Run the following with that environment active:

```sh
python -m pip install -e ../PyDeskUI -e packages/pydesktools-sdk -e packages/pydesktools-runtime -e plugins/json-tools -e '.[dev]'
python scripts/fetch_runtime.py --target macos-arm64 --output build/plugin-runtime/macos-arm64
python scripts/build_bundles.py --target macos-arm64 \
  --runtime-source build/plugin-runtime/macos-arm64/python
ruff check src packages plugins scripts tests
mypy
python -m pytest
```

Run GUI tests in a desktop session. Test dependencies/fixtures are never imported
by the application. Plugin code runs in separate interpreters; never add host-side
plugin imports to make a test easier. New capabilities require a protocol contract,
permission disclosure and lifetime tests. Never change a signed app during runtime.

Use `git commit -s` to certify provenance. Contributions remain MIT; list copied
code and assets with licenses. Maintainers review architecture, error states,
process cleanup and executed evidence. Do not commit generated runtime binaries,
private documents, keys or development-machine paths in package metadata.
