[CmdletBinding()]
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $projectRoot "build\pyinstaller"
$distRoot = Join-Path $projectRoot "dist"
$launcher = Join-Path $PSScriptRoot "launcher.py"
$bundleRoot = Join-Path $distRoot "Aero-Analytica"
$pythonRoot = Split-Path -Parent (Resolve-Path -LiteralPath $Python)
$runtimeBin = Join-Path $pythonRoot "Library\bin"
$archivePath = Join-Path $distRoot "Aero-Analytica-windows-x64.zip"
$checksumPath = Join-Path $distRoot "Aero-Analytica-windows-x64.sha256"

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name "Aero-Analytica" `
    --distpath $distRoot `
    --workpath $buildRoot `
    --specpath $buildRoot `
    --add-data "$projectRoot\app.py;." `
    --add-data "$projectRoot\src;src" `
    --add-binary "$runtimeBin\ffi.dll;." `
    --add-binary "$runtimeBin\liblzma.dll;." `
    --add-binary "$runtimeBin\libbz2.dll;." `
    --add-binary "$runtimeBin\libcrypto-3-x64.dll;." `
    --add-binary "$runtimeBin\libssl-3-x64.dll;." `
    --add-binary "$runtimeBin\expat.dll;." `
    --add-binary "$runtimeBin\libexpat.dll;." `
    --collect-all streamlit `
    --collect-all pandas `
    --collect-all numpy `
    --collect-all plotly `
    --collect-all pymavlink `
    --collect-all pyulog `
    --collect-all httpx `
    --collect-all watchdog `
    $launcher

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed with exit code $LASTEXITCODE."
}

Copy-Item -LiteralPath (Join-Path $projectRoot "README.md") -Destination $bundleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "README_EN.md") -Destination $bundleRoot -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $bundleRoot -Force

Compress-Archive -LiteralPath $bundleRoot -DestinationPath $archivePath -Force
$hash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash.ToLowerInvariant()
Set-Content -LiteralPath $checksumPath -Value "$hash  $(Split-Path -Leaf $archivePath)" -Encoding ascii

Write-Output "Portable bundle created at: $bundleRoot"
Write-Output "Archive created at: $archivePath"
Write-Output "Run: $bundleRoot\Aero-Analytica.exe"
