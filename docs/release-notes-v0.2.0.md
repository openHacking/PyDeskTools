PyDeskTools 0.2.0 adds Port Manager to the experimental desktop toolbox, alongside
Image Compressor and JSON Tools. All three tools work offline.

### New in 0.2.0

- Inspect local TCP listeners and search by port, project, process, or command.
- Sort the listener table and inspect complete process details in English or Chinese.
- Stop a selected process with confirmation, identity and endpoint rechecks, and
  post-stop port verification. Force termination is a separate explicit action.
- Scanning is limited to the local machine and visible permissions. Container, WSL,
  and remote services are not inspected internally. Stopping affects all ports of
  the selected process; child processes are not stopped. On Windows, Stop service
  ends the selected process immediately.

### Included tools

- Port Manager: local TCP listener inspection and explicit single-process termination.

- Image Compressor: batch JPEG/PNG/WebP compression, previews, resizing, metadata controls, and partial-failure retries.
- JSON Tools: precision-safe formatting/minification, UTF-8 import, copy, and export.

### Downloads

- **macOS 14+ / Apple silicon:** Developer ID-signed beta DMG. This build is not
  notarized, so first launch may require **Open Anyway** in Privacy & Security.
- **Windows 10/11 x64:** unsigned beta installer. SmartScreen may warn; verify `SHA256SUMS.txt` and the GitHub attestation.
- **Linux x64:** AppImage for X11/XWayland environments compatible with Ubuntu 22.04. Native Wayland is not certified.

All processing is local and no account is required. Plugins run in separate processes,
but they are not OS-sandboxed and third-party plugins execute with the current user's
permissions. See the README and build manifests for verification instructions and exact limitations.
