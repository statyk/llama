# Releasing signed binaries

`llama` ships four PyInstaller onefile binaries per `v*` tag, built on the
self-hosted fleet by `.github/workflows/release.yml` → `packaging/build.py`.
The **macOS** and **Windows** binaries are code-signed; Linux is not (verify it
via `SHA256SUMS`). No signing secrets live in the repo or GitHub — every
credential is machine-side on the runner that uses it.

## What `build.py` does per platform

- **macOS** (`Shawns-Mac-mini`): codesign the onefile with the hardened runtime
  + `packaging/llama.entitlements`, then notarize a zip of it with
  `xcrun notarytool submit --wait`. The binary is **not stapled** — a bare
  Mach-O can't carry a stapled ticket, so Gatekeeper does an **online**
  notarization check the first time a downloaded copy runs (the machine must be
  online for that first launch). This is the accepted state of the art for a
  bare notarized CLI. The signed binary ships unchanged after submission.
- **Windows** (`ITCHY`): Authenticode-sign the onefile `.exe` with the x64
  `signtool.exe` + `Azure.CodeSigning.Dlib.dll`, driven by
  `packaging/metadata.json`, timestamped via Azure Trusted Signing.
- **Linux**: no signing.

`build.py --skip-sign` produces an unsigned build for local/dev use or a
machine without the toolchain. The release workflow never passes it. Any
signing/notarization failure fails the leg — we never silently ship unsigned.

## One-time machine setup

### Mac mini (macOS runner)

- A **Developer ID Application** certificate in the login keychain (shared with
  the litcat runner on the same box). `build.py` auto-detects the sole such
  identity; override with `LLAMA_CODESIGN_IDENTITY` or `--identity`.
- A **notarytool credential**. `build.py` defaults its profile to
  `litcat-notary`, the profile litcat already set up on this box (pinned to the
  login keychain) — so **no per-runner setup is needed**; llama reuses it as-is.
  To point elsewhere, set `LLAMA_NOTARY_PROFILE` or pass `--notary-profile`. If
  you ever want a dedicated llama profile, create one once (pin `--keychain` to
  the login keychain — notarytool otherwise stores it in the data-protection
  keychain, which a runner session can't read):

  ```bash
  xcrun notarytool store-credentials "llama-notary" \
    --apple-id you@example.com --team-id XXXXXXXXXX \
    --password <app-specific-password> \
    --keychain "$HOME/Library/Keychains/login.keychain-db"
  ```

  Headless alternatives (any one, keychain-free) via runner env:
  `LLAMA_NOTARY_KEY`/`_KEY_ID`/`_ISSUER` (App Store Connect API key) or
  `LLAMA_NOTARY_APPLE_ID`/`_PASSWORD`/`_TEAM_ID`. `LLAMA_NOTARY_KEYCHAIN`
  overrides which keychain holds the notary profile (default: the login
  keychain; set it empty to use the session's default keychain instead) —
  `build.py` honors it when pinning the `--keychain-profile` lookup.
- If the runner session can't use the login keychain's private key
  (`errSecInternalComponent`), provide the identity as a `.p12` via
  `LLAMA_SIGNING_P12` (+ `LLAMA_SIGNING_P12_PASSWORD`,
  `LLAMA_SIGNING_KEYCHAIN_PASSWORD`); `build.py` imports it into a throwaway
  keychain it manages itself. The identity string itself is still resolved
  from the keychain by default (via `security find-identity`), so if the
  Developer ID cert isn't otherwise visible to that command on this runner,
  also set `LLAMA_CODESIGN_IDENTITY` (or pass `--identity`) — the `.p12`
  supplies a session-usable key, but auto-detection still needs to see the
  cert.

### ITCHY (Windows runner)

- Install **Microsoft.Azure.ArtifactSigningClientTools** (provides
  `Azure.CodeSigning.Dlib.dll` under `%LOCALAPPDATA%`) and the Windows SDK
  Signing Tools (x64 `signtool.exe`).
- `az login` (or a service-principal credential the dlib's credential chain can
  use) so signing reaches your Azure Trusted Signing account with no CI secret.
- `packaging/metadata.json` is committed with litcat's real Azure Trusted
  Signing values (account `LitCat`, profile `bogsoft`, `eus` endpoint), which
  llama reuses — so signing works immediately on ITCHY with no edit. (llama
  binaries therefore carry LitCat's publisher identity, an accepted tradeoff.)
  `build.py` still refuses to sign if the file is ever reverted to placeholder
  values, guarding a future profile change.

## Verifying a signed build

- macOS (runnable on the Mac mini itself):

  ```bash
  codesign --verify --strict --verbose=2 dist/llama
  spctl --assess --type exec --verbose=2 dist/llama
  xcrun notarytool history --keychain-profile litcat-notary \
    --keychain "$HOME/Library/Keychains/login.keychain-db"
  ```

- Windows (on ITCHY, after a build):

  ```powershell
  signtool verify /pa /v dist\llama.exe
  ```
