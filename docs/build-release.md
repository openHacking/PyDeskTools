# Desktop build and release

PyDeskTools is packaged natively on each supported operating system. PyInstaller is
not a cross-compiler. The GUI needs Python 3.13+ linked to Tcl/Tk 9; plugins use the
separate CPython 3.13.7 runtimes pinned in `runtime-sources.json`.

## Release artifacts

| Target | Native builder | Output |
| --- | --- | --- |
| `macos-arm64` | macOS 14 arm64, Homebrew Python 3.13 + Tk 9 | signed/notarized DMG |
| `windows-x86_64` | Windows 2022, official Python 3.14 + Tk 9 | unsigned Inno Setup beta |
| `linux-x86_64` | Ubuntu 22.04, source-built Python 3.14 + Tk 9 | AppImage for X11/XWayland |

Every builder fails if its operating system, architecture, Python, or Tk version is
wrong. It embeds third-party notices, a hash-addressed worker runtime, and writes a
platform-specific build manifest. Plugin bundles must be rebuilt for the target before
the application is frozen.

Fetch a verified worker runtime and build bundles with:

```sh
python scripts/fetch_runtime.py --target TARGET --output build/plugin-runtime/TARGET
python scripts/build_bundles.py --target TARGET
```

### macOS

An ad-hoc local diagnostic build is explicit and never presented as a public release:

```sh
python scripts/build_macos.py \
  --runtime-source build/plugin-runtime/macos-arm64/python
```

A public build requires a Developer ID Application identity and an existing
`notarytool` keychain profile:

```sh
python scripts/build_macos.py \
  --runtime-source build/plugin-runtime/macos-arm64/python \
  --identity 'Developer ID Application: NAME (TEAM_ID)' \
  --notary-profile PROFILE
```

The builder signs nested binaries and the application, verifies the signature, creates
and signs the DMG, submits it to Apple, staples the ticket, and validates the result.
Signing or notarization failures are fatal; there is no fallback to ad-hoc signing.

### Windows

Run on Windows x64 after generating `logo.ico` with `scripts/build_brand_assets.py`:

```powershell
python scripts/build_windows.py `
  --runtime-source build/plugin-runtime/windows-x86_64/python
```

The output is deliberately named `windows-x64-unsigned.exe`. It installs per-user and
supports silent installation/uninstallation for verification. Do not remove the
unsigned/Beta disclosure until a Windows code-signing certificate is configured and
the SmartScreen experience has been tested.

### Linux

The CI bootstrap builds the pinned Tk 9 GUI interpreter; the AppImage builder receives
a separately pinned and verified `appimagetool`:

```sh
bash scripts/bootstrap_linux_gui_python.sh "$PWD/build/linux-gui"
python scripts/build_linux.py \
  --runtime-source build/plugin-runtime/linux-x86_64/python \
  --appimagetool build/appimagetool
```

The compatibility floor is Ubuntu 22.04-era glibc. Verification runs under Xvfb. X11
and XWayland are supported for 0.1.0; native Wayland behavior is not certified.

## Draft release workflow

1. Run normal CI and review the release diff.
2. Update the changelog and release notes, then create and push the annotated `v0.1.0` tag.
3. Manually run **Draft desktop release** with that existing tag.
4. The workflow validates versions, builds all three native artifacts in parallel,
   performs frozen-install diagnostics, and creates attestations.
5. Only after all jobs succeed does the final job create one Draft Pre-release with
   all artifacts, build manifests, and `SHA256SUMS.txt`.
6. Download and inspect the draft assets, then publish it manually. Enable immutable
   releases first so the published tag and assets cannot be replaced.

The macOS job requires these repository secrets:

- `APPLE_CERTIFICATE_P12`: base64-encoded Developer ID certificate and private key.
- `APPLE_CERTIFICATE_PASSWORD`: export password for the P12.
- `APPLE_SIGNING_IDENTITY`: complete Developer ID Application identity.
- `APPLE_NOTARY_KEY_P8`: App Store Connect API private key contents.
- `APPLE_NOTARY_KEY_ID` and `APPLE_NOTARY_ISSUER_ID`.

Secrets are imported into a temporary keychain and deleted in an `always()` cleanup
step. They are never available to pull-request CI. Release jobs use least-privilege
permissions and actions pinned to commit SHAs.

## Cost and retention

For a public repository, this workflow uses standard GitHub-hosted runners and does
not require paid larger runners. Intermediate Actions artifacts are retained for one
day; durable installers and manifests live on the GitHub Release. Keep the dependency
cache below GitHub's repository cache allowance. The expected GitHub-side cost is zero
under the public-repository allowance. The recurring external cost is the Apple
Developer Program membership used for Developer ID signing; Windows 0.1.0 deliberately
does not purchase or require a code-signing certificate.

## Local packaged diagnostic

Always use an empty disposable profile. The diagnostic provisions, invokes, disables,
uninstalls, and restores both built-in plugins; it also writes to the clipboard.

```sh
'/path/to/PyDeskTools' \
  --data-dir '/tmp/PyDesk Profile' \
  --verify-installation /tmp/pydesk-verification.json
```

Never run this command against a real user profile. A public platform claim requires
the diagnostic from the final installer, plus the platform-specific signature,
installation, path, process-cleanup, and uninstall checks in `release.yml`.
