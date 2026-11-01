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

# 2. Copy native nglif library
$NglifDll = Join-Path $Root "build\nglif\nglif.dll"
if (-not (Test-Path $NglifDll)) {
    $NglifDll = Join-Path $Root "build\nglif\Release\nglif.dll"
}
if (Test-Path $NglifDll) {
    Write-Host "Copying native nglif.dll..."
    Copy-Item $NglifDll -Destination $PublishDir -Force
} else {
    Write-Warning "nglif.dll not found in build\nglif. Simulation might require bridge fallback."
}

# 3. Provision embedded Python runtime
Write-Host "Provisioning standalone Python 3.11 runtime..."
$RuntimeDir = Join-Path $PublishDir "runtime"
python "$PSScriptRoot\download-runtime.py" `
    --platform windows `
    --output-dir $RuntimeDir `
    --repo-root $Root

# 4. Create portable ZIP archive
$ZipPath = Join-Path $OutputDir "Neurogenesis-windows-x64-portable.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Write-Host "Creating portable ZIP archive: $ZipPath..."
tar -a -c -f "$ZipPath" -C "$PublishDir" .
Write-Host "Created: $ZipPath" -ForegroundColor Green

# 5. Compile Inno Setup installer if available
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
    Write-Host "Installer created in $OutputDir" -ForegroundColor Green
} else {
    Write-Host "Inno Setup compiler (ISCC.exe) not found. Skipping .exe installer generation." -ForegroundColor Yellow
}
