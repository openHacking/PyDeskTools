# Development guide

PyDeskTools requires Python 3.13 or newer with Tk 9. PyDeskUI 0.2 has the same
Python requirement. The shipped offline plugin bundle is narrower: its current
artifacts target CPython 3.13 on macOS arm64, so use Python 3.13 for the complete
local workflow.

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
  -e '.[dev]'
python scripts/build_bundles.py
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

Then repeat the editable install command above. Moving preserves the old files,
but the backup environment should not be run from its new path because virtual
environments are not portable.

If installation fails before completion, later scripts can report missing modules
such as `packaging`; fix the original resolver error and rerun the full install.
For example, PyDeskUI 0.2 cannot satisfy an old `pydeskui<0.2` application constraint.

On Windows PowerShell, use `py -3.13 -m venv .venv` and
`.\.venv\Scripts\Activate.ps1`; first ensure that the selected Python installation
includes Tcl/Tk 9. Linux package names vary by distribution. The packaged macOS
application already contains its GUI and plugin runtimes, so end users do not
perform this setup.

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
changing SDK or plugin sources:

```sh
python scripts/build_bundles.py
```
