# Signed macOS + Windows release binaries

**Date:** 2026-07-17
**Status:** approved

## Problem

`llama` ships four PyInstaller onefile CLI binaries per `v*` tag, built on a
self-hosted fleet (`hugo`=linux/x64, `otto`=linux/arm64, `Shawns-Mac-mini`=
macos/arm64, `ITCHY`=windows/x64) by `.github/workflows/release.yml` →
`packaging/build.py` → `packaging/llama.spec`, attached to a GitHub Release.
They are **unsigned**. macOS Gatekeeper (Sequoia) refuses to run the mac binary
("cannot be opened because Apple cannot check it for malicious software"), and
the Windows binary trips SmartScreen. The Linux legs are fine and stay
untouched.

The sibling project `litcat` (~/projects/litcat), whose runners are *second
instances on the same physical boxes*, already signs its macOS build (Developer
ID + hardened runtime + notarization) and its Windows build (Azure Trusted
Signing). Those machine-side identities and credentials are therefore already
present on `Shawns-Mac-mini` and `ITCHY`. We adopt the same, proven signing
machinery for `llama`.

## Decision

Sign the macOS and Windows legs, reusing litcat's approach, with **no signing
secrets in the repo or in GitHub** — all identities/credentials stay machine-
side on the runners, exactly as litcat does it (litcat's workflow passes zero
signing secrets). The build tool detects its platform and signs automatically;
Linux is unaffected.

Two deliberate departures from a verbatim litcat port:

1. **All signing logic lives in `packaging/build.py` (Python), not in sibling
   shell/PowerShell scripts.** llama's build is already a single cross-platform
   `build.py` orchestrator (litcat instead has per-OS `build-macos.sh` /
   `build-windows.ps1`). Keeping signing in `build.py` preserves the one-
   orchestrator structure, makes the pure decision logic unit-testable in the
   offline pytest suite (litcat's shell/PS logic is not), and — for Windows —
   sidesteps the PowerShell 5.1 "native stderr becomes a terminating
   NativeCommandError" footgun entirely, because Python `subprocess` never wraps
   stderr that way. We replicate litcat's *toolchain and pattern* (codesign /
   notarytool on mac; `signtool.exe` + `Azure.CodeSigning.Dlib` driven by
   `metadata.json` on Windows), not its language.

2. **macOS ships a bare onefile Mach-O in a `tar.gz`, not a `.app`.** So the mac
   flow is simpler than litcat's (no deep `.app` sign, no DMG, no stapling) and
   has one hard limitation, below.

### macOS: hardened runtime + notarize, but NO stapling

The mac artifact is a single Mach-O executable. The flow is:

1. Build unsigned onefile (`dist/llama`) with PyInstaller (spec unchanged;
   `codesign_identity` stays `None` — we sign explicitly afterward for full
   control over hardened runtime + entitlements).
2. `codesign --force --options runtime --entitlements packaging/llama.entitlements
   --sign "<Developer ID Application>" dist/llama` (hardened runtime).
3. Verify: `codesign --verify --strict --verbose=2 dist/llama`.
4. Zip the signed binary (`ditto -c -k`) and submit to Apple with
   `xcrun notarytool submit --wait`.
5. **No `stapler staple`** — stapling a notarization ticket is impossible for a
   bare executable (stapler only staples bundles/disk images/installers).

Accepted limitation, documented for users: because the ticket cannot be
stapled, Gatekeeper does an **online** notarization check the first time the
downloaded binary runs (the binary must have been notarized, and the machine
must be online for that first check). This is strictly better than today
(unsigned = hard refusal) and is the standard state of the art for distributing
a bare notarized CLI. The signed+notarized binary must be shipped **unchanged**
after submission — re-signing would change its cdhash and invalidate the
online-looked-up ticket.

**Identity resolution.** The Developer ID Application cert lives in the Mac
mini's login keychain (shared, already used by litcat). `build.py` resolves the
identity by precedence: `--identity` flag → `LLAMA_CODESIGN_IDENTITY` env → the
sole `"Developer ID Application: …"` match from
`security find-identity -v -p codesigning` (fail clearly if zero or ambiguous).
Auto-detection means the runner needs no machine-side identity env var.

**Headless codesign fallback.** codesign cannot always use the login keychain's
private key from a background launchd/runner session (`errSecInternalComponent`).
litcat's escape hatch is ported verbatim in behavior: when `LLAMA_SIGNING_P12`
(+ `LLAMA_SIGNING_P12_PASSWORD`, `LLAMA_SIGNING_KEYCHAIN_PASSWORD`) is set,
`build.py` imports the identity into a throwaway keychain it unlocks itself,
authorizes codesign on the key, prepends it to the search list, and tears it
down on exit. Unset → use the login keychain (fine for a foreground-registered
runner, which is how the box works for litcat today).

**Notarization auth.** Precedence mirrors litcat: App Store Connect API key
(`LLAMA_NOTARY_KEY`/`_KEY_ID`/`_ISSUER`) → Apple ID + app-specific password
(`LLAMA_NOTARY_APPLE_ID`/`_PASSWORD`, team id from `LLAMA_NOTARY_TEAM_ID` or
parsed from the identity's trailing `(TEAMID)`) → keychain profile
(`LLAMA_NOTARY_PROFILE`, default `llama-notary`) pinned with `--keychain` to
`~/Library/Keychains/login.keychain-db` (notarytool otherwise stores/reads the
profile in the data-protection keychain, unreadable in a runner session). A
logged-in operator uses the profile; the env-var paths exist for a truly
headless runner.

### Windows: Authenticode via Azure Trusted Signing

The Windows artifact is a single onefile `dist/llama.exe`. The flow is:

1. Build unsigned `dist/llama.exe` with PyInstaller.
2. Sign it (one `signtool sign` call) with the x64 `signtool.exe` +
   `Azure.CodeSigning.Dlib.dll` (installed per-user by
   `Microsoft.Azure.ArtifactSigningClientTools`), driven by
   `packaging/metadata.json`, timestamped at
   `http://timestamp.acs.microsoft.com`, digest SHA256 — exactly litcat's
   `sign-windows.ps1` invocation, ported to a Python `subprocess` call.
3. Verify: `signtool verify /pa /q dist/llama.exe` (best-effort; warn on
   failure, don't fail the leg on the verify step alone).

There is no bundle of DLLs to sign (onefile) and no installer, so this is much
simpler than litcat's Windows flow. Azure auth reaches `signtool` via the
dlib's credential chain (`AzureCliCredential` etc.) using the machine-side `az`
login on ITCHY — no CI secret. `build.py` heals the `az`-not-on-PATH case the
same way litcat does (prepend the standard Azure CLI `wbin` dir to `PATH` for
the sign subprocess when `az` isn't already discoverable), and refuses to sign
if `metadata.json` still holds placeholder values.

### Failure behavior and the `--skip-sign` escape hatch

- On the mac/windows legs, **any** signing or notarization failure fails the
  leg (non-zero exit, no artifact) — we never silently ship an unsigned binary
  in place of a signed one. Signing runs after the smoke test and before
  packaging, so a signing failure aborts before the archive is produced.
- `build.py --skip-sign` (ported from litcat's `--skip-sign` / `-SkipSign`)
  produces today's unsigned artifact. It is the *only* way to get an unsigned
  build, for local/dev builds and machines without the signing toolchain. The
  release workflow never passes it. On Linux, signing is not applicable and
  `--skip-sign` is a no-op.
- `build.py --dry-run` (already exists) prints the plan including the
  platform's signing steps and whether `--skip-sign` is in effect; it performs
  no signing and needs no credentials.

## Design

### Config files (committed; no secrets)

- `packaging/llama.entitlements` — plist with exactly the two keys a hardened-
  runtime PyInstaller onefile needs on macOS:
  `com.apple.security.cs.allow-unsigned-executable-memory` and
  `com.apple.security.cs.disable-library-validation`. (litcat's camera/TCC
  entitlement is dropped — llama is a headless CLI.)
- `packaging/metadata.json` — Azure Trusted Signing config
  (`Endpoint`, `CodeSigningAccountName`, `CertificateProfileName`,
  `ExcludeCredentials`), same shape as litcat's. Account/profile/endpoint values
  are **open questions** for the operator (see below); the file carries a
  placeholder-guard sentinel so an unedited template can never sign.

Neither file is a secret: the entitlements are public policy; the Azure account
and profile *names* are not credentials (litcat commits its real
`metadata.json`). Actual authentication is the machine-side `az` login.

### `packaging/build.py` additions

New pure (unit-tested) helpers:

- `resolve_codesign_identity(explicit, env, find_identity_output) -> str`
- `resolve_notary_auth(env, profile, keychain, identity) -> (list[str], str)`
- `wants_dedicated_keychain(env) -> bool` (True iff `LLAMA_SIGNING_P12` set)
- `discover_signtool(fixed_path, kits_bin_dir) -> Path`
- `signtool_sign_cmd(signtool, dlib, metadata, timestamp, digest, files) -> list[str]`
- `ensure_az_on_path(env) -> dict`
- `check_metadata_not_placeholder(text) -> None`
- `codesign_cmd(binary, identity, entitlements) -> list[str]`

New orchestration (subprocess-driven; covered on hardware, not offline):
`macos_sign(binary, opts)`, `windows_sign(binary, opts)`. `main()` calls the
right one after `smoke_test` and before `package`, unless `--skip-sign`. New
CLI options: `--skip-sign`, `--identity`, `--notary-profile`.

`packaging/llama.spec` is **unchanged** (`codesign_identity=None`,
`entitlements_file=None`): we sign explicitly in `build.py` so all signing logic
sits in one testable place.

### Workflow

`.github/workflows/release.yml` needs essentially no structural change — the
matrix already runs `python packaging/build.py --version "$VER"` on every leg,
and `build.py` now signs on mac/windows by itself using machine-side
credentials. Only the header comment ("Unsigned: … GITHUB_TOKEN only") is
corrected to state that the mac/windows legs sign via machine-side credentials
with no signing secrets in CI. `permissions` stays `contents: write`.

### Documentation

- `docs/releasing.md` (new): what gets signed, the one-time machine setup on
  each box (Developer ID in login keychain; the `llama-notary` profile or
  reusing `litcat-notary`; ITCHY's ArtifactSigningClientTools + `az` login +
  `metadata.json`), the **no-staple / online-first-run** macOS limitation,
  `--skip-sign` for local builds, and the verification commands.
- `README.md`: one line noting the mac binary is signed + notarized (Gatekeeper-
  clean; online check on first run) and the Windows binary is Authenticode-
  signed.

## Testing

Offline, per project convention (the 418-test suite stays green). New
`tests/test_packaging.py` loads `packaging/build.py` as a module and covers the
pure helpers:

- `resolve_codesign_identity`: explicit > env > sole auto-detected match;
  raises on zero and on ambiguous.
- `resolve_notary_auth`: API-key path, Apple-ID path (team from env and parsed
  from identity), profile path (with/without `--keychain`); precedence order.
- `wants_dedicated_keychain`: toggles on `LLAMA_SIGNING_P12`.
- `discover_signtool`: returns the fixed path when present; else the newest x64
  `signtool.exe` under a temp Kits tree; raises when none.
- `signtool_sign_cmd`: exact argv (`/fd`/`/tr`/`/td`/`/dlib`/`/dmdf`, files last).
- `ensure_az_on_path`: no-op when `az` present; prepends the wbin dir when a
  faked one exists.
- `check_metadata_not_placeholder`: raises on the sentinel, passes on real text.
- `codesign_cmd`: exact argv (hardened runtime + entitlements + identity).
- Config files: `llama.entitlements` parses as a plist and contains exactly the
  two required keys; `metadata.json` parses as JSON with the four expected keys.
- `--skip-sign` / dry-run: `main(--dry-run)` prints a plan (no signing); the
  signing dispatch is bypassed when `--skip-sign` is set (via monkeypatched
  `sys.platform` + injected sign stubs asserted not called).

The subprocess-driven `macos_sign` / `windows_sign` bodies cannot run offline;
they get **on-hardware verification** tasks in the plan. The dev host *is* the
macOS runner hardware, so a real signed local build + `codesign --verify
--strict` + `spctl --assess -t exec` + `notarytool log` is runnable during
implementation. Windows verification realistically needs a `workflow_dispatch`
release run on ITCHY — proposed as a documented manual verification, flagged as
residual risk.

## Open questions (operator-owned)

1. **Windows Azure Trusted Signing identity for `metadata.json`.** Which
   `CodeSigningAccountName` / `CertificateProfileName` / `Endpoint` should
   `llama` sign under? Reusing litcat's exact profile (`LitCat`/`bogsoft`) would
   stamp llama's exe with LitCat's publisher identity, which is probably not
   wanted; a llama-specific certificate profile under the same Azure account is
   the likely answer. This determines the committed `metadata.json` values and
   whether the machine-side `az` credential on ITCHY has access to that profile.
2. **macOS notarization profile.** Create a new `llama-notary` keychain profile
   on the Mac mini (one-time `xcrun notarytool store-credentials "llama-notary"
   --keychain ~/Library/Keychains/login.keychain-db …`), or reuse the existing
   `litcat-notary` profile via `LLAMA_NOTARY_PROFILE=litcat-notary` (same Apple
   ID/team works to notarize any app)? Default in code is `llama-notary`.

## Out of scope

- Signing the Linux binaries (no accepted desktop trust anchor to satisfy;
  users verify via `SHA256SUMS`).
- Any `.app`/DMG/installer packaging for macOS, or an Inno installer for
  Windows (llama ships bare onefile archives).
- Moving signing back into per-OS scripts, or introducing new GitHub secrets.
- Automated end-to-end signing tests in CI beyond the offline unit coverage +
  on-hardware verification tasks.
