#!/bin/bash
# Builds Neurogenesis.app (Intel Mac, macOS 14+; Command Line Tools are enough, no Xcode), installs it in
# ~/Applications and adds it to the Dock.
#
#   ./build.sh                      build, install, add to the Dock
#   ./build.sh --no-install         build only (build/Neurogenesis.app)
#   NG_PYTHON=/path/to/python NG_REPO=/path/to/neurogenesis-sim ./build.sh
#
# NG_PYTHON: a Python with numpy, jax and matplotlib (default: the first of conda / python3 that has them).
# NG_REPO: the neurogenesis-sim checkout whose toolbox the app imports (python -m neurogenesis.bridge with this
#          folder first on PYTHONPATH; default: the main worktree of this repository, where merged work lands).
# Both can be changed later in the app (Roadmap status → Python).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$HERE"
MAIN_WT="$(git -C "$HERE" worktree list --porcelain 2>/dev/null | sed -n '1s/^worktree //p')"
OWN="$(cd "$HERE/../.." && pwd)"
if [[ -n "$MAIN_WT" && ! -f "$MAIN_WT/neurogenesis/bridge/__main__.py" ]]; then
  MAIN_WT="$OWN"            # the main worktree has no bridge yet (not merged): use this checkout
fi
REPO="${NG_REPO:-${MAIN_WT:-$OWN}}"
ARCH="$(uname -m)"
INSTALL=1
[[ "${1:-}" == "--no-install" ]] && INSTALL=0

if [[ -z "${NG_PYTHON:-}" ]]; then
  for p in /opt/anaconda3/bin/python /opt/miniconda3/bin/python "$HOME/miniconda3/bin/python" "$HOME/anaconda3/bin/python" \
           /opt/homebrew/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
    if [[ -x "$p" ]] && "$p" -c "import numpy, jax, matplotlib" 2>/dev/null; then NG_PYTHON="$p"; break; fi
  done
fi
NG_PYTHON="${NG_PYTHON:-/usr/bin/python3}"
echo "Python:  $NG_PYTHON"
echo "Toolbox: $REPO"

APP="build/Neurogenesis.app"
mkdir -p build
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "Compiling (swiftc -O, $ARCH)…"
swiftc -O -swift-version 5 -parse-as-library -target "$ARCH-apple-macos14.0" Sources/*.swift \
  -framework Metal -framework MetalKit -o "$APP/Contents/MacOS/Neurogenesis"

echo "Icon…"
if [[ ! -f build/icon_1024.png || tools/make_icon/main.swift -nt build/icon_1024.png ]]; then
  swiftc -O -swift-version 5 tools/make_icon/main.swift -o build/make_icon
  build/make_icon build/icon_1024.png
fi
ICONSET=build/AppIcon.iconset
rm -rf "$ICONSET"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s build/icon_1024.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z $((s * 2)) $((s * 2)) build/icon_1024.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Neurogenesis</string>
  <key>CFBundleDisplayName</key><string>Neurogenesis</string>
  <key>CFBundleIdentifier</key><string>org.neurogenesis-sim.desktop</string>
  <key>CFBundleExecutable</key><string>Neurogenesis</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSApplicationCategoryType</key><string>public.app-category.education</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSPrincipalClass</key><string>NSApplication</string>
  <key>NGPython</key><string>$NG_PYTHON</string>
  <key>NGRepo</key><string>$REPO</string>
  <key>CFBundleDocumentTypes</key>
  <array><dict>
    <key>CFBundleTypeName</key><string>Neurogenesis project, plan, module or network</string>
    <key>CFBundleTypeRole</key><string>Editor</string>
    <key>LSHandlerRank</key><string>Alternate</string>
    <key>LSItemContentTypes</key><array><string>public.json</string></array>
  </dict></array>
</dict>
</plist>
PLIST
codesign --force --deep --sign - "$APP" 2>/dev/null || true
echo "Built $HERE/$APP"

if [[ $INSTALL == 1 ]]; then
  DEST="$HOME/Applications/Neurogenesis.app"
  mkdir -p "$HOME/Applications"
  rm -rf "$DEST"
  cp -R "$APP" "$DEST"
  /System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$DEST" >/dev/null 2>&1 || true
  echo "Installed $DEST"
  if ! defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Neurogenesis.app"; then
    defaults write com.apple.dock persistent-apps -array-add \
      "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file://$DEST/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>"
    killall Dock
    echo "Added to the Dock"
  else
    echo "Already in the Dock"
  fi
fi
