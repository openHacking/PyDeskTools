PyDeskTools 0.1.0 is the first experimental desktop release: two useful offline
tools, a search-first shell, and an isolated Python plugin runtime.

### Included tools

- Image Compressor: batch JPEG/PNG/WebP compression, previews, resizing, metadata controls, and partial-failure retries.
- JSON Tools: precision-safe formatting/minification, UTF-8 import, copy, and export.

### Downloads

- **macOS 14+ / Apple silicon:** signed and notarized DMG.
- **Windows 10/11 x64:** unsigned beta installer. SmartScreen may warn; verify `SHA256SUMS.txt` and the GitHub attestation.
- **Linux x64:** AppImage for X11/XWayland environments compatible with Ubuntu 22.04. Native Wayland is not certified.

All processing is local and no account is required. Plugins run in separate processes,
but they are not OS-sandboxed and third-party plugins execute with the current user's
permissions. See the README and build manifests for verification instructions and exact limitations.
