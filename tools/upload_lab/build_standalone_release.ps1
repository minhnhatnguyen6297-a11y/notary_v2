param(
    [string]$DestinationRoot = ""
)

$ErrorActionPreference = "Stop"

$toolRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $DestinationRoot) {
    $DestinationRoot = Join-Path $toolRoot "_release"
}
$releaseRoot = Join-Path $DestinationRoot "upload_lab"

$filesToCopy = @(
    ".env.example",
    "__init__.py",
    "batch_scan.py",
    "bootstrap_ui.py",
    "build_standalone_release.ps1",
    "CHECKLIST_PHAT_HANH_STANDALONE.md",
    "extract_contract.py",
    "HUONG_DAN.md",
    "install_python_windows.ps1",
    "playwright_uploader.py",
    "requirements.txt",
    "run_ui.bat",
    "ui_runner.py",
    "uploader_selectors.py"
)

if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

foreach ($fileName in $filesToCopy) {
    $source = Join-Path $toolRoot $fileName
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Khong tim thay file can phat hanh: $fileName"
    }
    Copy-Item -LiteralPath $source -Destination (Join-Path $releaseRoot $fileName) -Force
}

Write-Host "[OK] Da tao ban standalone tai: $releaseRoot"
