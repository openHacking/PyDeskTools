# Development guide

PyDeskTools requires Python 3.13 or newer with Tk 9. PyDeskUI 0.2 has the same
Python requirement. The shipped offline plugin bundles use a separate pinned
CPython 3.13 runtime for each supported target. On macOS, use Python 3.13 for the
GUI development environment as well. On Windows, use Python 3.14.7 or newer
because earlier official Python 3.14 releases are linked to Tk 8.6.

## macOS setup

Homebrew installs the Python Tk extension separately from Python. Install both
matching formulae:

```sh
brew install python@3.13 python-tk@3.13
```

From the PyDeskTools repository root, verify the exact base interpreter before
creating a virtual environment:

```sh
"$(brew --prefix python@3.13)/bin/python3.13" -c \
  "import sys, tkinter; print(sys.executable); print(sys.version); print('Tk', tkinter.TkVersion)"
```

The final line must report Tk 9.0. A virtual environment reuses its base
interpreter's `_tkinter` extension; pip cannot add `_tkinter` to a Python that was
built without it.

Create the environment only once. Keep PyDeskUI checked out next to PyDeskTools,
then install every editable package in one resolver transaction:

```sh
"$(brew --prefix python@3.13)/bin/python3.13" -m venv .venv
source .venv/bin/activate
python -m pip install -e ../PyDeskUI \
  -e packages/pydesktools-sdk \
  -e packages/pydesktools-runtime \
  -e plugins/json-tools \
  -e plugins/image-compressor \
  -e '.[dev]'
python scripts/fetch_runtime.py --target macos-arm64 --output build/plugin-runtime/macos-arm64
python scripts/build_bundles.py --target macos-arm64 \
  --runtime-source build/plugin-runtime/macos-arm64/python
python -m pydesktools
```

The editable PyDeskUI source must be version 0.2.x. It is installed into the
PyDeskTools environment; do not activate a separate PyDeskUI environment.

For later launches:

```sh
source .venv/bin/activate
python -c "import sys, tkinter, pydeskui; print(sys.executable, tkinter.TkVersion, pydeskui.__version__)"
python -m pydesktools
```

## Windows setup

Install 64-bit Python 3.14.7 or newer from python.org. The optional Tcl/Tk and
IDLE component must be selected in the installer. In PowerShell, verify the
interpreter before creating a virtual environment:

```powershell
py -3.14 -c "import sys, tkinter; print(sys.executable); print(sys.version); print('Tk', tkinter.TkVersion)"
```

The final line must report Tk 9.0. Keep PyDeskUI checked out next to PyDeskTools,
then create the environment and install all editable packages from the
PyDeskTools repository root:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ../PyDeskUI `
  -e packages/pydesktools-sdk `
  -e packages/pydesktools-runtime `
  -e plugins/json-tools `
  -e plugins/image-compressor `
  -e '.[dev]'
python scripts/fetch_runtime.py --target windows-x86_64 --output build/plugin-runtime/windows-x86_64
python scripts/build_bundles.py --target windows-x86_64 `
  --runtime-source build/plugin-runtime/windows-x86_64/python
python -m pydesktools
```

The Python 3.14 interpreter runs the GUI and development tools. The fetched
CPython 3.13 runtime is intentionally separate and is used to build and run the
isolated plugins. Do not point the GUI virtual environment at the downloaded
plugin runtime.

For later launches:

```powershell
.\.venv\Scripts\Activate.ps1
python -c "import sys, tkinter, pydeskui; print(sys.executable, tkinter.TkVersion, pydeskui.__version__)"
python -m pydesktools
```

If PowerShell prevents `Activate.ps1` from running, follow your organization's
execution-policy guidance. Activation is optional; the equivalent commands can
be run directly with `.\.venv\Scripts\python.exe`.

## Recreating an incompatible environment

Do not run `venv` over an existing environment made by another Python. If
`python -m tkinter` raises `No module named '_tkinter'`, deactivate the environment,
move it aside for recovery, and create a new one with a Tk-enabled interpreter:

```sh
deactivate 2>/dev/null || true
mv .venv .venv.no-tk-backup
"$(brew --prefix python@3.13)/bin/python3.13" -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, move the incompatible environment aside and recreate it
with the verified Python 3.14 interpreter:

```powershell
if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
Move-Item -LiteralPath .venv -Destination .venv.no-tk-backup
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Then repeat the editable install command above. Moving preserves the old files,
but the backup environment should not be run from its new path because virtual
environments are not portable.

If installation fails before completion, later scripts can report missing modules
such as `packaging`; fix the original resolver error and rerun the full install.
For example, PyDeskUI 0.2 cannot satisfy an old `pydeskui<0.2` application constraint.

Linux developers must provide Python 3.13+ linked against Tk 9; package names
vary by distribution. Published desktop installers contain both the GUI and
plugin runtimes, so end users do not perform this setup.

## Verification

Run the static checks and test suite before submitting changes:

```sh
ruff check src packages plugins scripts tests
mypy
python -m pytest
python -m build
python -m twine check dist/*.whl dist/*.tar.gz
```

The development environment is separate from the immutable per-plugin virtual
environments provisioned by the application. Rebuild the offline bundles after
changing SDK or plugin sources, using the target for the current operating
system. For macOS arm64:

```sh
python scripts/fetch_runtime.py --target macos-arm64 --output build/plugin-runtime/macos-arm64
python scripts/build_bundles.py --target macos-arm64 \
  --runtime-source build/plugin-runtime/macos-arm64/python
```

For Windows x64:

```powershell
python scripts/fetch_runtime.py --target windows-x86_64 --output build/plugin-runtime/windows-x86_64
python scripts/build_bundles.py --target windows-x86_64 `
  --runtime-source build/plugin-runtime/windows-x86_64/python
```
