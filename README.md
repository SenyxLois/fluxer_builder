# Fluxer unsigned iOS builder

This repository automatically builds sideload-ready iOS IPAs from the latest
commit on the default branch of
[fluxerapp/flutter_client](https://github.com/fluxerapp/flutter_client).

## Fast Builds with Codemagic (8-Core M2) + GitHub Actions Progress

The GitHub Actions workflow checks upstream every six hours (and supports manual
runs via **Actions → Build unsigned iOS IPA → Run workflow**).

- **When Codemagic secrets are configured** (`CODEMAGIC_API_TOKEN` and
  `CODEMAGIC_APP_ID`), GitHub Actions triggers [`codemagic.yaml`](codemagic.yaml)
  on Codemagic's **8-core Apple M2** runner (500 free min/month on personal
  accounts), streams live step-by-step progress directly into the GitHub Actions
  log and Job Summary, downloads the verified IPAs, and publishes them to
  [GitHub Releases](https://github.com/SenyxLois/fluxer_builder/releases/latest).
- **Fallback:** If Codemagic secrets are not set (or you choose `runner: github`
  on manual dispatch), it falls back to a heavily cached GitHub-hosted macOS
  runner.

### One-Time Codemagic Setup (Only 2 GitHub Secrets Needed)

You do **not** need to add any GitHub tokens or Apple certificates inside
Codemagic — GitHub Actions handles publishing the release automatically.

1. Sign in to [Codemagic](https://codemagic.io/) with your GitHub account (free
   personal tier includes **500 min/month** on 8-core M2).
2. Click **Add application** → select `SenyxLois/fluxer_builder` → choose
   **Flutter App (via `codemagic.yaml`)**.
3. Copy your **App ID** from the Codemagic app URL:
   `https://codemagic.io/app/<CODEMAGIC_APP_ID>/...`
4. Copy your **API Token** from Codemagic:
   **User settings → Integrations → Codemagic API → Show**.
5. In this GitHub repository, go to **Settings → Secrets and variables → Actions
   → New repository secret** and add:
   - `CODEMAGIC_API_TOKEN`
   - `CODEMAGIC_APP_ID`
6. Go to **Actions → Build unsigned iOS IPA → Run workflow**, check
   **`force_rebuild: true`** for the first test run, and watch live M2 progress
   right inside GitHub Actions.

## Which IPA Should I Download?

Download directly from
[Releases](https://github.com/SenyxLois/fluxer_builder/releases/latest) (not the
zipped bundle under Actions → Artifacts):

- **`fluxer-sideload-no-plugins.ipa`** — Recommended for **SideStore** (avoids
  the 3-App-ID free Apple ID limit) and single-profile **Feather Sign**.
- **`fluxer-unsigned.ipa`** — Full bundle including `BroadcastExtension`,
  `NotificationService`, and `ShareExtension` (for paid developer certificates,
  multi-profile Feather Sign, or TrollStore).

Both IPAs are cleaned, normalized to executable (`0755`) permissions, thinned to
`arm64`, and **ad-hoc signed** (`codesign --force --sign -`) so signers like
Feather Sign (`zsign`) and SideStore can cleanly re-sign them without Mach-O
header reallocation or corruption errors.
