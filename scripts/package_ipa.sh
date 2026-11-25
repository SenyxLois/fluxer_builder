#!/usr/bin/env bash
set -euo pipefail

# Packages a Flutter-built Runner.app into two sideload-ready, ad-hoc signed IPAs:
#   1. fluxer-unsigned.ipa            (full app bundle with PlugIns)
#   2. fluxer-sideload-no-plugins.ipa (PlugIns removed for SideStore 3-App-ID limit / single-cert Feather)
#
# Why ad-hoc signing instead of completely raw --no-codesign:
#   - Requires zero Apple certificates or secrets.
#   - Ensures every Mach-O binary has a valid LC_CODE_SIGNATURE load command and
#     consistent _CodeSignature/CodeResources, preventing zsign / Feather Sign /
#     SideStore "IPA file is corrupted" & ReallocCodeSignSpace failures.
#   - Normalizes executable permissions (0755) on framework binaries (App.framework,
#     media_kit frameworks, etc.) and thins multi-arch arm64e dylibs to arm64.

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <path/to/Runner.app> <output_dir> <upstream_sha>" >&2
  exit 1
fi

APP_SRC="$1"
OUT_DIR="$2"
UPSTREAM_SHA="$3"

if [ ! -d "$APP_SRC" ]; then
  echo "::error::Expected app bundle not found: $APP_SRC" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
WORK_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/fluxer-ipa.XXXXXX")"
trap 'rm -rf "$WORK_ROOT"' EXIT

prepare_and_adhoc_sign() {
  local app_bundle="$1"

  # 1. Strip macOS extended attributes, Finder junk, and stale/partial signatures
  xattr -cr "$app_bundle" 2>/dev/null || true
  find "$app_bundle" -name "_CodeSignature" -type d -exec rm -rf {} +
  find "$app_bundle" -name "embedded.mobileprovision" -type f -delete
  find "$app_bundle" \( -name ".DS_Store" -o -name "._*" \) -type f -delete

  # 2. Fix executable permissions & thin multi-arch dylibs (e.g. arm64+arm64e) to arm64
  while IFS= read -r -d '' bin; do
    if file -b "$bin" | grep -q "Mach-O"; then
      chmod 755 "$bin"
      if file -b "$bin" | grep -q "universal binary"; then
        local archs
        archs="$(lipo -archs "$bin" 2>/dev/null || true)"
        if [[ " $archs " == *" arm64 "* ]] && [ "$(echo "$archs" | wc -w)" -gt 1 ]; then
          echo "  Thinning universal binary to arm64: ${bin#$app_bundle/}"
          lipo "$bin" -thin arm64 -output "$bin.arm64"
          mv "$bin.arm64" "$bin"
          chmod 755 "$bin"
        fi
      fi
    fi
  done < <(find "$app_bundle" -type f -print0)

  # 3. Ad-hoc sign inside-out: dylibs -> frameworks -> app extensions -> main app
  while IFS= read -r -d '' dylib; do
    /usr/bin/codesign --force --sign - --timestamp=none "$dylib"
  done < <(find "$app_bundle" -name "*.dylib" -type f -print0)

  while IFS= read -r -d '' fw; do
    /usr/bin/codesign --force --sign - --timestamp=none "$fw"
  done < <(find "$app_bundle" -name "*.framework" -type d -print0)

  if [ -d "$app_bundle/PlugIns" ]; then
    while IFS= read -r -d '' appex; do
      /usr/bin/codesign --force --sign - --timestamp=none "$appex"
    done < <(find "$app_bundle/PlugIns" -maxdepth 1 -name "*.appex" -type d -print0)
  fi

  /usr/bin/codesign --force --sign - --timestamp=none "$app_bundle"

  # 4. Verify the ad-hoc seal and ensure no real signing certificate is embedded
  /usr/bin/codesign --verify --deep --strict "$app_bundle"
  local cs_info
  cs_info="$(/usr/bin/codesign -dv "$app_bundle" 2>&1)"
  if ! echo "$cs_info" | grep -q '^Signature=adhoc$'; then
    echo "::error::Expected ad-hoc signature on $app_bundle, got:" >&2
    echo "$cs_info" >&2
    exit 1
  fi
}

pack_ipa() {
  local staging_dir="$1"
  local out_ipa="$2"

  rm -f "$out_ipa"
  (cd "$staging_dir" && /usr/bin/zip -qry -X -3 "$out_ipa" Payload)
  /usr/bin/unzip -tq "$out_ipa"
  /usr/bin/unzip -Z1 "$out_ipa" | grep -Fxq 'Payload/Runner.app/Info.plist'
  /usr/bin/unzip -Z1 "$out_ipa" | grep -Fxq 'Payload/Runner.app/_CodeSignature/CodeResources'
  echo "Created $(basename "$out_ipa") ($(du -h "$out_ipa" | awk '{print $1}'))"
}

echo "=== Packaging full IPA (with PlugIns) ==="
FULL_STAGE="$WORK_ROOT/full"
mkdir -p "$FULL_STAGE/Payload"
ditto --norsrc "$APP_SRC" "$FULL_STAGE/Payload/Runner.app"
prepare_and_adhoc_sign "$FULL_STAGE/Payload/Runner.app"
pack_ipa "$FULL_STAGE" "$OUT_DIR/fluxer-unsigned.ipa"

echo "=== Packaging sideload IPA (PlugIns removed for SideStore / single-cert Feather) ==="
LITE_STAGE="$WORK_ROOT/sideload"
mkdir -p "$LITE_STAGE/Payload"
ditto --norsrc "$APP_SRC" "$LITE_STAGE/Payload/Runner.app"
rm -rf "$LITE_STAGE/Payload/Runner.app/PlugIns"
prepare_and_adhoc_sign "$LITE_STAGE/Payload/Runner.app"
pack_ipa "$LITE_STAGE" "$OUT_DIR/fluxer-sideload-no-plugins.ipa"

echo "Built from fluxerapp/flutter_client@$UPSTREAM_SHA" > "$OUT_DIR/upstream-commit.txt"
