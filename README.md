# Fluxer unsigned iOS builder

This repository automatically builds sideload-ready iOS IPAs from the latest
commit on the default branch of
[fluxerapp/flutter_client](https://github.com/fluxerapp/flutter_client).

## Builds and updates

GitHub Actions checks upstream every six hours and also supports manual runs
from **Actions → Build unsigned iOS IPA → Run workflow** (with an optional
`force_rebuild` toggle). When upstream has a new commit, the workflow builds it
on a GitHub-hosted Apple Silicon macOS runner with incremental caching for:

- Flutter SDK & pub dependencies
- Rust toolchain & native asset build artifacts (`src/.dart_tool/hooks_runner`)
- Incremental Dart codegen (`src/.dart_tool/build`)
- Xcode `DerivedData`, Swift Package Manager (`org.swift.swiftpm`), and CocoaPods

The workflow requires no Apple signing certificates or repository secrets.

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
