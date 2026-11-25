# Fluxer unsigned iOS builder

This repository automatically builds an **unsigned IPA** from the latest
`main` commit of [fluxerapp/flutter_client](https://github.com/fluxerapp/flutter_client).

## Builds and updates

GitHub Actions checks upstream every six hours and also supports a manual run
from the **Actions → Build unsigned iOS IPA → Run workflow** page. When upstream
has a new commit, the workflow builds it on a GitHub-hosted macOS runner and
publishes a GitHub release. The latest build is available at
[Releases](https://github.com/SenyxLois/fluxer_builder/releases/latest), with
the asset named `fluxer-unsigned.ipa`. Each workflow run also provides a
downloadable artifact for 14 days.

The workflow follows the upstream iOS build setup: Flutter 3.50, the iOS store
build profile, and Rust native assets. It does not require Apple signing
certificates or repository secrets.

## Installing

The IPA is intentionally unsigned and cannot be installed directly. Sign it
with your own Apple developer certificate or a compatible sideloading tool
before installing. It is built from upstream's `main` branch, not an official
App Store release.
