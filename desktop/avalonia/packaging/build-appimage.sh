#!/usr/bin/env bash
set -euo pipefail

# Build script for Linux AppImage and tar.gz
# Usage: ./build-appimage.sh [output_dir]

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
OUTPUT_DIR="${1:-${ROOT}/dist}"
APPDIR="${ROOT}/build/AppDir"

echo "=== Building Neurogenesis Linux AppImage ==="
mkdir -p "${OUTPUT_DIR}"
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin" "${APPDIR}/usr/lib" "${APPDIR}/usr/share/applications" "${APPDIR}/usr/share/icons/hicolor/256x256/apps" "${APPDIR}/usr/share/mime/packages"

# 1. Publish self-contained Avalonia app
echo "Publishing self-contained .NET 8 app (linux-x64)..."
dotnet publish "${ROOT}/desktop/avalonia/src/Neurogenesis.App/Neurogenesis.App.csproj" \
    -c Release -r linux-x64 --self-contained true \
    -o "${APPDIR}/usr/bin"

# 2. Copy native nglif library
echo "Copying native libnglif.so..."
if [ -f "${ROOT}/build/nglif/libnglif.so" ]; then
    cp "${ROOT}/build/nglif/libnglif.so" "${APPDIR}/usr/lib/"
    cp "${ROOT}/build/nglif/libnglif.so" "${APPDIR}/usr/bin/"
fi

# 3. Provision embedded Python runtime
echo "Provisioning standalone Python 3.11 runtime..."
python3 "${ROOT}/desktop/avalonia/packaging/download-runtime.py" \
    --platform linux \
    --output-dir "${APPDIR}/usr/runtime" \
    --repo-root "${ROOT}"

# 4. Desktop entry, MIME, and icon
cp "${ROOT}/desktop/avalonia/packaging/neurogenesis.desktop" "${APPDIR}/usr/share/applications/"
cp "${ROOT}/desktop/avalonia/packaging/neurogenesis.desktop" "${APPDIR}/"
cp "${ROOT}/desktop/avalonia/packaging/neurogenesis.png" "${APPDIR}/usr/share/icons/hicolor/256x256/apps/"
cp "${ROOT}/desktop/avalonia/packaging/neurogenesis.png" "${APPDIR}/"
cp "${ROOT}/desktop/avalonia/packaging/neurogenesis-mime.xml" "${APPDIR}/usr/share/mime/packages/"
cp "${ROOT}/desktop/avalonia/packaging/AppRun" "${APPDIR}/AppRun"
chmod +x "${APPDIR}/AppRun"

# 5. Build tar.gz
echo "Packaging tar.gz archive..."
TAR_OUT="${OUTPUT_DIR}/Neurogenesis-linux-x64.tar.gz"
tar -czf "${TAR_OUT}" -C "${APPDIR}" .
echo "Created: ${TAR_OUT}"

# 6. Build AppImage using appimagetool with --appimage-extract-and-run
echo "Building AppImage..."
APPIMAGE_TOOL="${ROOT}/build/appimagetool-x86_64.AppImage"
if [ ! -f "${APPIMAGE_TOOL}" ]; then
    mkdir -p "${ROOT}/build"
    curl -sSL -o "${APPIMAGE_TOOL}" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
    chmod +x "${APPIMAGE_TOOL}"
fi

export ARCH=x86_64
"${APPIMAGE_TOOL}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_DIR}/Neurogenesis-x86_64.AppImage"
echo "Created: ${OUTPUT_DIR}/Neurogenesis-x86_64.AppImage"
