# Releasing signed binaries

`llama` ships four PyInstaller onefile binaries per `v*` tag, built on
**GitHub-hosted runners** by `.github/workflows/release.yml` →
`packaging/build.py`. The **macOS** and **Windows** binaries are code-signed;
Linux is not (verify it via `SHA256SUMS`). Signing credentials live in
**GitHub Actions secrets** (repo → Settings → Secrets and variables → Actions),
decoded into the job at runtime and never written to the repo.

## Cutting a release

1. Land everything on `main` and push.
2. Tag and push:

   ```bash
   git tag -a v0.7.0 -m "llama 0.7.0" && git push origin v0.7.0
   ```

   The tag's version drives the build (`v0.7.0` → `0.7.0`); `pyproject.toml`'s
   static `version` is not the source of truth. The `prep` job validates the
   version against a strict allowlist regex before anything runs.
3. The workflow builds all four targets, signs macOS + Windows, and the
   `release` job attaches the archives + `SHA256SUMS` to a GitHub Release.

**Dry runs / rehearsals** (`workflow_dispatch`):

- `dry_run=true` — plan only; `build.py --dry-run` prints what it would do,
  runs no PyInstaller and no signing, publishes nothing.
- `skip_release=true` — full builds **and real signing** on every leg, artifacts
  uploaded, but the `release` job is skipped. This is the true pre-tag rehearsal
  (a `dry_run` exercises no signing code):

  ```bash
  gh workflow run release --field version=0.7.0 --field skip_release=true
  ```

## Runners

All jobs run on GitHub-hosted runners — `ubuntu-latest`, `ubuntu-24.04-arm`
(free for public repos; **public repos only** — it fails on a private repo),
`macos-latest` (arm64), and `windows-latest`. PyInstaller can't cross-compile,
so each binary is built on native hardware. There are **no self-hosted
runners**; the earlier self-hosted fleet was decommissioned once
`ubuntu-24.04-arm` made hosted Linux-arm64 available.

## What `build.py` does per platform

- **macOS** (`macos-latest`): codesign the onefile with the hardened runtime +
  `packaging/llama.entitlements`, then notarize a zip of it with
  `xcrun notarytool submit --wait`. The binary is **not stapled** — a bare
  Mach-O can't carry a stapled ticket, so Gatekeeper does an **online**
  notarization check the first time a downloaded copy runs (the machine must be
  online for that first launch). This is the accepted state of the art for a
  bare notarized CLI. The signed binary ships unchanged after submission.
- **Windows** (`windows-latest`): Authenticode-sign the onefile `.exe` with the
  x64 `signtool.exe` + `Azure.CodeSigning.Dlib.dll`, driven by
  `packaging/metadata.json`, timestamped via Azure Trusted Signing.
- **Linux**: no signing.

`build.py --skip-sign` produces an unsigned build for local/dev use or a
machine without the toolchain. The release workflow never passes it. Any
signing/notarization failure — including a non-zero `signtool verify` — fails
the leg; we never silently ship unsigned.

## GitHub Actions secrets

Set these once on the repo (they never expire on their own, but rotate as your
Apple/Azure credentials rotate):

### macOS signing

| Secret | Value |
|---|---|
| `LLAMA_CODESIGN_IDENTITY` | full `Developer ID Application: … (TEAMID)` string — **keep the `(TEAMID)` suffix**; `build.py` derives the notary team from it |
| `LLAMA_SIGNING_P12_BASE64` | `base64 -i developer-id.p12` of a Developer ID cert **+ private key** export |
| `LLAMA_SIGNING_P12_PASSWORD` | the password chosen at `.p12` export |
| `LLAMA_NOTARY_APPLE_ID` | Apple ID for notarytool |
| `LLAMA_NOTARY_PASSWORD` | app-specific password for that Apple ID |

The workflow decodes `LLAMA_SIGNING_P12_BASE64` to a temp file, generates a
throwaway `LLAMA_SIGNING_KEYCHAIN_PASSWORD` per run (`openssl rand -hex 24`),
and passes the identity/notary values as env to the mac Build step. `build.py`
imports the `.p12` into an ephemeral keychain it creates and tears down itself,
so nothing persists on the runner. App Store Connect API-key auth
(`LLAMA_NOTARY_KEY`/`_KEY_ID`/`_ISSUER`) is an alternative to the Apple-ID pair
if you prefer a revocable key.

> The `.p12` must contain the **cert and its private key together**. Export it
> from Keychain Access → My Certificates → select the "Developer ID
> Application" cert **and** its key → Export 2 items → `.p12`. (This is the only
> irreplaceable signing material — Apple never re-issues a private key; keep an
> offsite copy of the `.p12` + its password.)

### Windows signing

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | service principal app id |
| `AZURE_TENANT_ID` | tenant id |
| `AZURE_CLIENT_SECRET` | service principal secret |

`Azure.CodeSigning.Dlib.dll` uses `DefaultAzureCredential`; with these three in
the job env, `EnvironmentCredential` authenticates non-interactively (no
`az login`). The service principal needs the **Trusted Signing Certificate
Profile Signer** role on the signing account/profile. The windows Build step
first fetches the Trusted Signing client package by downloading its `.nupkg`
directly and extracting `bin/x64/` into the location `build.py` expects
(`%LOCALAPPDATA%\Microsoft\MicrosoftArtifactSigningClientTools\`) — a direct
download because `nuget install` intermittently fails to resolve the package on
`windows-latest`.

`packaging/metadata.json` is committed with the Azure Trusted Signing account
values (account `LitCat`, profile `bogsoft`, `eus` endpoint), so signing works
with no per-run edit; llama binaries carry that publisher identity, an accepted
tradeoff. `build.py` refuses to sign if the file is ever reverted to
placeholder values, guarding a future profile change.

## Verifying a signed build

Verify **from the workflow run logs**, not from an interactive shell — a green
job is not proof the artifact was signed. In the `Build` step logs, expect:

- macOS: `Current status: Accepted` and `signed + notarized`.
- Windows: `Number of files successfully Signed: 1` and `signed + verified`.

To spot-check a downloaded artifact locally:

```bash
# macOS
codesign --verify --strict --verbose=2 ./llama
spctl --assess --type exec --verbose=2 ./llama   # "rejected … not an app" is expected for a bare CLI

# Windows (PowerShell)
signtool verify /pa /v .\llama.exe
```
