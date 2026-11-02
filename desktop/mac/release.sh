#!/bin/bash
# Release build of the Mac app: embedded Python runtime, signature, disk image. No Python or Xcode needed by users.
#
#   ./release.sh                                   build/Neurogenesis-<version>-macos-<arch>.dmg for this Mac's arch
#   NG_RUNTIME=build/runtime-macos-arm64 ./release.sh      reuse a runtime built by build_runtime.py
#
# Signing (optional; otherwise ad hoc, and users open the app with right-click -> Open the first time):
#   MACOS_SIGN_IDENTITY   "Developer ID Application: Name (TEAMID)", in the keychain
#   APPLE_ID, APPLE_TEAM_ID, APPLE_APP_PASSWORD     notarize and staple the disk image as well
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
ARCH="$(uname -m)"
TARGET="macos-$([[ "$ARCH" == "arm64" ]] && echo arm64 || echo x86_64)"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' ../../pyproject.toml | head -1)"
PY="${NG_BUILD_PYTHON:-$(command -v python3)}"
RUNTIME="${NG_RUNTIME:-build/runtime-$TARGET}"

if [[ ! -x "$RUNTIME/python/bin/python3" ]]; then
  echo "Building the Python runtime ($TARGET) with $PY…"
  "$PY" ../common/runtime/build_runtime.py --target "$TARGET" --out "$RUNTIME"
fi

NG_REPO="" ./build.sh --no-install --runtime "$RUNTIME"     # a release never imports a checkout: the runtime has the toolbox
APP="build/Neurogenesis.app"
if [[ -n "$(/usr/libexec/PlistBuddy -c 'Print :NGRepo' "$APP/Contents/Info.plist" 2>/dev/null)" ]] ||
   [[ "$(/usr/libexec/PlistBuddy -c 'Print :NGPython' "$APP/Contents/Info.plist")" != "@bundled" ]]; then
  echo "release build must use the embedded runtime and no toolbox checkout"; exit 1
fi

if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
  echo "Signing with $MACOS_SIGN_IDENTITY (hardened runtime)…"
  # every Mach-O inside first (Python, extension modules, dylibs), then the app
  find "$APP/Contents/Resources/python" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) -print0 |
    while IFS= read -r -d '' f; do
      if file -b "$f" | grep -q "Mach-O"; then
        codesign --force --timestamp --options runtime --entitlements entitlements.plist --sign "$MACOS_SIGN_IDENTITY" "$f"
      fi
    done
  codesign --force --timestamp --options runtime --entitlements entitlements.plist --sign "$MACOS_SIGN_IDENTITY" "$APP"
  codesign --verify --deep --strict "$APP"
else
  echo "No MACOS_SIGN_IDENTITY: ad-hoc signature (first launch: right-click -> Open)."
fi

tools/check_bundle.sh "$APP"        # runs on a clean Mac: nothing linked outside macOS or the bundle

DMG="build/Neurogenesis-$VERSION-$TARGET.dmg"
STAGE="$(mktemp -d)"
ditto "$APP" "$STAGE/Neurogenesis.app"
ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -quiet -volname "Neurogenesis $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE"

if [[ -n "${MACOS_SIGN_IDENTITY:-}" ]]; then
  codesign --force --timestamp --sign "$MACOS_SIGN_IDENTITY" "$DMG"
  if [[ -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" && -n "${APPLE_APP_PASSWORD:-}" ]]; then
    echo "Notarizing…"
    xcrun notarytool submit "$DMG" --apple-id "$APPLE_ID" --team-id "$APPLE_TEAM_ID" --password "$APPLE_APP_PASSWORD" --wait
    xcrun stapler staple "$DMG"
  fi
fi
shasum -a 256 "$DMG" | tee "$DMG.sha256"
echo "Release: $HERE/$DMG ($(du -h "$DMG" | cut -f1))"
