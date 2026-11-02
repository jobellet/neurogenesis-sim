# PowerShell build script for Windows packaging (portable zip + Inno Setup installer)
param(
    [string]$OutputDir = ""
)

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path "$PSScriptRoot\..\..\..").Path
if (-not $OutputDir) {
    $OutputDir = Join-Path $Root "dist"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$PublishDir = Join-Path $Root "publish\win-x64"
if (Test-Path $PublishDir) {
    Remove-Item -Recurse -Force $PublishDir
}
New-Item -ItemType Directory -Force -Path $PublishDir | Out-Null

Write-Host "=== Building Neurogenesis Windows Package ===" -ForegroundColor Cyan

# 1. Publish self-contained Avalonia app
Write-Host "Publishing self-contained .NET 8 app (win-x64)..."
dotnet publish "$Root\desktop\avalonia\src\Neurogenesis.App\Neurogenesis.App.csproj" `
    -c Release -r win-x64 --self-contained true `
    -o $PublishDir
if ($LASTEXITCODE -ne 0) { throw "dotnet publish failed with exit code $LASTEXITCODE" }

# 2. Copy native nglif library (mandatory)
$NglifDll = Join-Path $Root "build\nglif\nglif.dll"
if (-not (Test-Path $NglifDll)) {
    $NglifDll = Join-Path $Root "build\nglif\Release\nglif.dll"
}
if (Test-Path $NglifDll) {
    Write-Host "Copying native nglif.dll..."
    Copy-Item $NglifDll -Destination $PublishDir -Force
} else {
    throw "Packaging error: nglif.dll was not found in build\nglif. Native simulation library is required."
}

# 3. Package UI schema files
Write-Host "Packaging UI schema..."
$SchemaCommonDir = Join-Path $PublishDir "desktop\common"
New-Item -ItemType Directory -Force -Path $SchemaCommonDir | Out-Null
Copy-Item (Join-Path $Root "desktop\common\ui_schema.example.json") -Destination $PublishDir -Force
Copy-Item (Join-Path $Root "desktop\common\ui_schema.schema.json") -Destination $PublishDir -Force
Copy-Item (Join-Path $Root "desktop\common\ui_schema.example.json") -Destination $SchemaCommonDir -Force
Copy-Item (Join-Path $Root "desktop\common\ui_schema.schema.json") -Destination $SchemaCommonDir -Force

# 4. Provision embedded Python runtime using shared script
Write-Host "Provisioning standalone Python runtime via desktop/common/runtime/build_runtime.py..."
$RuntimeScript = Join-Path $Root "desktop\common\runtime\build_runtime.py"
if (-not (Test-Path $RuntimeScript)) {
    throw "Packaging error: build_runtime.py not found at $RuntimeScript."
}

$RuntimeDir = Join-Path $PublishDir "runtime"
python "$RuntimeScript" --target windows-x86_64 --out "$RuntimeDir" --toolbox "$Root"
if ($LASTEXITCODE -ne 0) { throw "build_runtime.py failed with exit code $LASTEXITCODE" }

# Marker for packaged build
New-Item -ItemType File -Force -Path (Join-Path $PublishDir ".packaged") | Out-Null

# 5. Create portable ZIP archive
$ZipPath = Join-Path $OutputDir "Neurogenesis-windows-x64-portable.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Write-Host "Creating portable ZIP archive: $ZipPath..."
tar -a -c -f "$ZipPath" -C "$PublishDir" .
if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE" }
Write-Host "Created: $ZipPath" -ForegroundColor Green

# 6. Compile Inno Setup installer if available
$IsccCandidates = @(
    "ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles}\Inno Setup 6\ISCC.exe",
    "${env:LOCALAPPDATA}\Programs\Inno Setup 6\ISCC.exe"
)

$IsccPath = $null
foreach ($c in $IsccCandidates) {
    if (Get-Command $c -ErrorAction SilentlyContinue) {
        $IsccPath = (Get-Command $c).Source
        break
    }
    if (Test-Path $c) {
        $IsccPath = $c
        break
    }
}

if ($IsccPath) {
    Write-Host "Compiling Inno Setup installer using $IsccPath..."
    & $IsccPath "/O$OutputDir" "$PSScriptRoot\setup.iss"
    if ($LASTEXITCODE -ne 0) { throw "ISCC compilation failed with exit code $LASTEXITCODE" }
    Write-Host "Installer created in $OutputDir" -ForegroundColor Green
} else {
    Write-Host "Inno Setup compiler (ISCC.exe) not found. Skipping .exe installer generation." -ForegroundColor Yellow
}
