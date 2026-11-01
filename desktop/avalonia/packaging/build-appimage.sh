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
else
    echo "ERROR: libnglif.so not found in ${ROOT}/build/nglif. Native simulation library is required." >&2
    exit 1
fi

# 3. Provision embedded Python runtime using shared script
echo "Provisioning standalone Python runtime via desktop/common/runtime/build_runtime.py..."
RUNTIME_SCRIPT="${ROOT}/desktop/common/runtime/build_runtime.py"
if [ ! -f "${RUNTIME_SCRIPT}" ]; then
    echo "Checking out build_runtime.py from origin/task/H4-runtime-release..."
    git fetch origin task/H4-runtime-release
    git checkout FETCH_HEAD -- desktop/common/runtime
fi
if [ ! -f "${RUNTIME_SCRIPT}" ]; then
    echo "ERROR: build_runtime.py not found at ${RUNTIME_SCRIPT}" >&2
    exit 1
fi

python3 "${RUNTIME_SCRIPT}" \
    --target linux-x86_64 \
    --out "${APPDIR}/usr/runtime" \
    --toolbox "${ROOT}"

touch "${APPDIR}/usr/bin/.packaged"

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

# 6. Build AppImage using pinned appimagetool with SHA-256 verification
echo "Building AppImage..."
APPIMAGE_VERSION="1.9.1"
APPIMAGE_SHA256="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
APPIMAGE_TOOL="${ROOT}/build/appimagetool-x86_64.AppImage"
if [ ! -f "${APPIMAGE_TOOL}" ]; then
    mkdir -p "${ROOT}/build"
    curl -sSL -o "${APPIMAGE_TOOL}" "https://github.com/AppImage/appimagetool/releases/download/${APPIMAGE_VERSION}/appimagetool-x86_64.AppImage"
    echo "${APPIMAGE_SHA256}  ${APPIMAGE_TOOL}" | sha256sum -c -
    chmod +x "${APPIMAGE_TOOL}"
fi

export ARCH=x86_64
"${APPIMAGE_TOOL}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_DIR}/Neurogenesis-x86_64.AppImage"
echo "Created: ${OUTPUT_DIR}/Neurogenesis-x86_64.AppImage"
