# Third-party notices

Project modules and the JSON plugin use MIT. PyDeskUI is an independent MIT
library. Host dependencies: packaging (Apache-2.0/BSD-2-Clause), platformdirs (MIT),
and tkinterdnd2/TkDND (MIT-style licenses).
The Linux application additionally uses pystray 0.19.5 (LGPL-3.0), python-xlib
0.33 (LGPL-2.1-or-later), and six 1.17.0 (MIT) for system-tray integration.
The macOS application additionally uses PyObjC core/Cocoa 12.2.2 (MIT) for
nonblocking native file panels; it is not a UI-core/runtime/SDK dependency.
The JSON plugin's simplejson dependency retains MIT/Academic Free License terms
from its wheel. Its wheel includes upstream license files.

The desktop distribution embeds CPython 3.13.7 from python-build-standalone
20250918. The verified archive hashes are in runtime-sources.json. Native-library
license texts are retained in licenses/THIRD_PARTY_LICENSES.txt; this upstream set
includes licenses for libraries beyond this particular platform build. CPython,
Tcl/Tk, OpenSSL, libffi, SQLite, zlib and other bundled components retain their
original terms. The interpreter's pip and vendored components retain their licenses.

PyInstaller's bootloader uses GPL with its distribution exception; the relevant
license and exception are included in the same consolidated file. Build tools
are separately inventoried and are not all runtime dependencies. Retained texts
are copied unmodified from the verified upstream archive or installed distributions,
with identical texts included once and their original source paths listed together.

The application builder includes this inventory and license directory in the app.
Historical unrelated prototype examples/configs are retired or excluded; no new
rights-clearance claim is made for historical artwork retained in source.
