# Desktop build and release

PyDeskTools is packaged natively on each supported operating system. PyInstaller is
not a cross-compiler. The GUI needs Python 3.13+ linked to Tcl/Tk 9; plugins use the
separate CPython 3.13.7 runtimes pinned in `runtime-sources.json`.

## Release artifacts

| Target | Native builder | Output |
| --- | --- | --- |
| `macos-arm64` | macOS 14 arm64, Homebrew Python 3.13 + Tk 9 | Developer ID-signed DMG (not notarized) |
| `windows-x86_64` | Windows 2022, official Python 3.14.7 + Tk 9 | unsigned Inno Setup beta |
| `linux-x86_64` | Ubuntu 22.04, source-built Python 3.14 + Tk 9 | AppImage for X11/XWayland |

Every builder fails if its operating system, architecture, Python, or Tk version is
wrong. It embeds third-party notices, a hash-addressed worker runtime, and writes a
platform-specific build manifest. Plugin bundles must be rebuilt for the target before
the application is frozen.

Fetch a verified worker runtime and build bundles with:

```sh
python scripts/fetch_runtime.py --target TARGET --output build/plugin-runtime/TARGET
python scripts/build_bundles.py --target TARGET \
  --runtime-source build/plugin-runtime/TARGET/python
```

### macOS

An ad-hoc local diagnostic build is explicit and never presented as a public release:

```sh
python scripts/build_macos.py \
  --runtime-source build/plugin-runtime/macos-arm64/python
```

A public beta build requires a Developer ID Application identity:

```sh
python scripts/build_macos.py \
  --runtime-source build/plugin-runtime/macos-arm64/python \
  --identity 'Developer ID Application: NAME (TEAM_ID)'
```

The builder signs nested binaries and the application, verifies the signature, creates
and signs the DMG, and records `notarized: false` in the build manifest. The release
workflow deliberately does not submit this beta to Apple's notary service because the
offline plugin archives currently contain native wheel binaries that are not prepared
for notarization. Users may need to approve the app with **Open Anyway** in macOS
Privacy & Security on first launch. Signing failures are fatal; there is no fallback
to ad-hoc signing.

### Windows

Install [Inno Setup 6](https://jrsoftware.org/isdl.php), which provides the
`ISCC.exe` compiler used to create the installer. It can be installed interactively
with Windows Package Manager:

```powershell
winget install --id JRSoftware.InnoSetup -e -s winget -i
```

After installation, open a new PowerShell window. A per-user installation normally
places the compiler under `%LOCALAPPDATA%`; a system-wide installation normally
places it under `Program Files (x86)`. Run the following complete block on Windows
x64 after generating `logo.ico` with `scripts/build_brand_assets.py`:

```powershell
$iscc = @(
  (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
  'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $iscc) { throw 'Inno Setup 6 ISCC.exe was not found' }

python scripts/build_windows.py `
  --runtime-source build/plugin-runtime/windows-x86_64/python `
  --iscc $iscc
```

If Inno Setup was installed elsewhere, pass the actual path to `ISCC.exe` instead.
Specifying `--iscc` explicitly avoids relying on the installer directory being added
to `PATH`.

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

The public installers are rebuilt by GitHub Actions from an existing annotated tag.
Do not upload a locally built DMG as a release artifact, and do not create the tag
until the exact release commit has passed CI. The workflow creates a Draft
Pre-release; publishing it is deliberately a separate manual decision.

The examples below use `v0.1.0`. Replace it consistently when preparing a later
version. Run all commands from the repository root.

### 1. Prepare and validate the release commit

Start from a clean checkout synchronized with `origin/main`:

```sh
git fetch origin --tags
git status --short --branch
test -z "$(git status --porcelain)"
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

Review the changes intended for the release. Update `CHANGELOG.md` and the matching
release-notes file, and make sure neither describes the version as unreleased. The
release workflow currently reads `docs/release-notes-v0.1.0.md`; a future release
must update both that path in `.github/workflows/release.yml` and the file itself.

Run the same fail-closed version check used by the release workflow:

```sh
python scripts/validate_release.py --tag v0.1.0
```

This checks the application version, component versions, changelog heading, and
plugin-runtime target matrix. Commit and push any corrections before continuing.

### 2. Run the full CI workflow

`CI` is a manual `workflow_dispatch` workflow. Trigger it on the exact branch and
commit that will receive the release tag:

```sh
gh workflow run ci.yml --ref main
gh run list --workflow ci.yml --branch main --event workflow_dispatch --limit 5
```

Open the newest run in GitHub Actions, or copy its numeric database ID from the list
and wait for it from the command line:

```sh
gh run watch RUN_ID --exit-status
gh run view RUN_ID --json headSha,conclusion,url
```

Do not continue unless every CI job succeeds. CI covers the supported headless Python
versions, Windows and Linux platform contracts, the macOS desktop suite, linting,
type checking, and Python distribution builds. Confirm that `headSha` is the commit
you intend to tag. If a fix is needed, push it and run CI again; the later tag must
point at the corrected commit.

### 3. Create and push the annotated tag

After CI is green, confirm `HEAD` is still the tested commit, then create an annotated
tag and push only that tag:

```sh
git status --short --branch
git tag -a v0.1.0 -m "PyDeskTools v0.1.0"
git show --no-patch --decorate v0.1.0
git push origin v0.1.0
git ls-remote --exit-code --tags origin refs/tags/v0.1.0
```

Do not move, force-push, or silently recreate a published version tag. If the tag is
wrong and no release has been published, stop and resolve it explicitly before
running the release workflow.

### 4. Build the Draft Pre-release

Trigger **Draft desktop release** with the tag that now exists on GitHub:

```sh
gh workflow run release.yml -f tag=v0.1.0
gh run list --workflow release.yml --event workflow_dispatch --limit 5
```

Alternatively, open **Actions > Draft desktop release > Run workflow**, enter
`v0.1.0`, and start the run. Copy the new run ID and wait for completion if desired:

```sh
gh run watch RUN_ID --exit-status
```

The workflow first checks out the tag and validates all release versions. It then
builds the three native targets in parallel, performs frozen-install diagnostics,
and creates GitHub artifact attestations. Only after all three jobs succeed does the
final job create one Draft Pre-release containing:

- `PyDeskTools-*-macos-arm64.dmg`
- `PyDeskTools-*-windows-x64-unsigned.exe`
- `PyDeskTools-*-linux-x86_64.AppImage`
- one `build-manifest-*.json` for each platform
- `SHA256SUMS.txt`

Intermediate Actions artifacts are retained for only one day. The Draft Release is
the durable review location. A failed platform job does not create a partial release;
if the failure is transient, rerun the unchanged tag. If correcting it requires a
source commit, stop: the existing tag no longer identifies the candidate you tested.
Explicitly resolve the unpublished tag and repeat CI/tagging, or bump the version,
rather than publishing incomplete assets or quietly moving a release tag.

### 5. Inspect the Draft and its final assets

Open **Releases**, find the `PyDeskTools 0.1.0` draft, and first check its title,
Pre-release flag, notes, tag, and complete asset list. Download the assets generated
by CI rather than inspecting a local build:

```sh
release_dir="$(mktemp -d)"
gh release download v0.1.0 --dir "$release_dir"
cd "$release_dir"
shasum -a 256 --check SHA256SUMS.txt
```

Inspect the three JSON manifests and verify the application version, target, builder
Python version, embedded runtime metadata and hashes, and each platform's applicable
signing/notarization fields. Verify the provenance attestation for each installer:

```sh
for artifact in PyDeskTools-*; do
  gh attestation verify "$artifact" --repo openHacking/PyDeskTools
done
```

Test the downloaded final installer on each platform claimed by the release whenever
possible, preferably with a clean machine or VM and an empty disposable profile.
Confirm installation or mounting, launch, the packaged diagnostic, process cleanup,
and uninstall/eject behavior. The automated jobs already exercise these paths, but
manual review catches packaging and first-launch behavior that runner diagnostics do
not reproduce.

The expected warnings are part of this beta release and must remain disclosed in the
release notes:

- The macOS DMG is Developer ID-signed but not notarized. Verify that the downloaded
  app has a valid Developer ID signature; first launch may require **Open Anyway** in
  Privacy & Security.
- The Windows installer is unsigned and may trigger SmartScreen. Its filename must
  retain `unsigned`.
- The Linux AppImage is certified for X11/XWayland on the documented compatibility
  floor, not native Wayland.

Do not publish if a checksum, attestation, manifest, signature, installation, launch,
or uninstall check fails. Do not replace a failed asset manually: correct the source
or workflow and produce a new coherent release candidate.

### 6. Enable immutable releases and publish

Before publishing the draft, open the repository **Settings**, scroll to the
**Releases** section, and select **Enable release immutability**. GitHub applies this
setting only to future published releases, so it must be enabled before clicking
Publish. See GitHub's [immutable release instructions](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes).

Return to the Draft Release and perform one final review. Keep **Set as a pre-release**
enabled for this experimental `0.1.0` release, then click **Publish release**. Once an
immutable release is published, its assets and associated tag cannot be modified or
deleted while the release exists; only metadata such as the title, notes, Pre-release
flag, and Latest flag remains editable.

Confirm the result:

```sh
gh release view v0.1.0 --json tagName,isDraft,isPrerelease,isImmutable,publishedAt,url
gh release verify v0.1.0
```

The expected state is `isDraft: false`, `isPrerelease: true`, and
`isImmutable: true`. Announce or link the release only after these checks pass.

### Stop conditions

Stop the release instead of working around any of these conditions:

- the working tree is dirty or `HEAD` differs from the reviewed remote commit;
- `validate_release.py` or any CI/release job fails;
- the remote tag is missing or points at an untested commit;
- any platform artifact, manifest, checksum, or attestation is missing;
- Apple signing fails, or an artifact's observed security state contradicts its
  release-note disclosure;
- immutable releases are not enabled before publication.

The macOS job requires these repository secrets:

- `APPLE_CERTIFICATE_P12`: base64-encoded Developer ID certificate and private key.
- `APPLE_CERTIFICATE_PASSWORD`: export password for the P12.
- `APPLE_SIGNING_IDENTITY`: complete Developer ID Application identity.

The certificate is imported into a temporary keychain and deleted in an `always()`
cleanup step. It is never available to pull-request CI. Release jobs use
least-privilege permissions and actions pinned to commit SHAs.

### Prepare the macOS signing secrets

Follow [Apple's Developer ID certificate guide](https://developer.apple.com/help/account/certificates/create-developer-id-certificates/)
if the release Mac does not already have a Developer ID Application certificate.
Creating a new Developer ID certificate normally requires the Apple Developer Program
Account Holder. Do not create or revoke a certificate when a working identity already
exists.

On the release Mac, list usable code-signing identities:

```sh
security find-identity -v -p codesigning
```

Copy the complete Developer ID Application name, including its Team ID, into the
`APPLE_SIGNING_IDENTITY` repository secret. For example:

```text
Developer ID Application: NAME (TEAM_ID)
```

Export the same identity and its private key with Keychain Access:

1. Open **Keychain Access**, select the **login** keychain, and open **My
   Certificates**.
2. Find the Developer ID Application identity and expand it. A private key must appear
   beneath the certificate. A certificate without its private key cannot sign builds
   on CI.
3. Select the identity, choose **File > Export Items**, and export it as Personal
   Information Exchange (`.p12`). See
   [Apple's Keychain export instructions](https://support.apple.com/guide/keychain-access/kyca35961/mac).
4. Set a strong, unique password when prompted. Save that password as the
   `APPLE_CERTIFICATE_PASSWORD` repository secret. This is the P12 export password;
   it is not the Apple Account password, Mac login password, or an app-specific
   password.

Convert the exported P12 binary to Base64 and copy it to the clipboard:

```sh
base64 -i DeveloperIDApplication.p12 | pbcopy
```

Save the copied value as `APPLE_CERTIFICATE_P12`. This secret contains the Base64
data, not a path to the P12 file. This follows
[GitHub's macOS signing-certificate guidance](https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications).

Create all three repository secrets under **Repository Settings > Secrets and
variables > Actions > Secrets > New repository secret**:

| Secret | Value |
| --- | --- |
| `APPLE_CERTIFICATE_P12` | Base64 text produced from the exported P12 |
| `APPLE_CERTIFICATE_PASSWORD` | Password chosen while exporting the P12 |
| `APPLE_SIGNING_IDENTITY` | Complete `Developer ID Application: NAME (TEAM_ID)` name |

GitHub documents the UI and `gh secret set` alternatives in
[Using secrets in GitHub Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

If P12 export is unavailable or disabled, first confirm that the private key is shown
beneath the certificate in **My Certificates**. The private key normally exists only
on the Mac that created the certificate signing request unless it was securely
transferred. Obtain the original identity from that Mac or ask the Account Holder to
create a replacement; do not revoke a working Developer ID certificate merely to fix
a CI setup problem.

Treat the P12 and its password as release credentials. Never commit the P12, its
Base64 representation, or the password to this repository or an `.env` file. After
the secrets are configured, keep the exported P12 only in approved encrypted storage
or remove the temporary export from the Mac.

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
