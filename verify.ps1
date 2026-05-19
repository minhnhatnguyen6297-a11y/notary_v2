$ErrorActionPreference = "Continue"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot -ErrorAction Stop

$Skipped = @()
$Python = "python"
$VenvPython = Join-Path $RepoRoot "venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
}

Write-Host "Using Python: $Python"

function Get-ChangedPythonFiles {
    $ChangedFiles = @(Get-ChangedFiles)
    return @($ChangedFiles | Where-Object { $_ -like "*.py" -and (Test-Path $_) } | Select-Object -Unique)
}

function Get-ChangedFiles {
    $Tracked = @(& git diff --name-only --diff-filter=ACMRT HEAD -- "*.py")
    if ($LASTEXITCODE -ne 0) {
        return @()
    }

    $Untracked = @(& git ls-files --others --exclude-standard)
    if ($LASTEXITCODE -ne 0) {
        $Untracked = @()
    }

    return @($Tracked + $Untracked | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)
}

function Test-OcrRelevantChange {
    param([string[]]$ChangedFiles)

    $OcrRelevant = @(
        "routers/ocr_ai.py",
        "routers/ocr_local.py",
        "tasks.py",
        "tests/test_ocr_ai.py"
    )

    foreach ($File in $ChangedFiles) {
        $Normalized = $File -replace "\\", "/"
        if ($OcrRelevant -contains $Normalized) {
            return $true
        }
    }

    return $false
}

function Invoke-VerifyStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "==> $Name"
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

Invoke-VerifyStep "py_compile core Python files" {
    & $Python -m py_compile routers/ocr_ai.py routers/ocr_local.py tasks.py
}

& $Python -m ruff --version *> $null
if ($LASTEXITCODE -eq 0) {
    $ChangedPythonFiles = @(Get-ChangedPythonFiles)
    if ($ChangedPythonFiles.Count -gt 0) {
        Invoke-VerifyStep "ruff check changed Python files" {
            & $Python -m ruff check @ChangedPythonFiles
        }
    }
    else {
        $Skipped += "ruff check (no changed Python files)"
    }
}
else {
    $Skipped += "ruff check (ruff is not installed; install requirements-dev.txt)"
}

if (Test-Path "tests/test_ocr_ai.py") {
    $ChangedFiles = @(Get-ChangedFiles)
    $RunFullVerify = $env:FULL_VERIFY -eq "1"
    if ($RunFullVerify -or (Test-OcrRelevantChange -ChangedFiles $ChangedFiles)) {
        Invoke-VerifyStep "pytest tests/test_ocr_ai.py" {
            & $Python -m pytest tests/test_ocr_ai.py -q
        }
    }
    else {
        $Skipped += "pytest tests/test_ocr_ai.py (no OCR-relevant changed files; set FULL_VERIFY=1 to force)"
    }
}
else {
    $Skipped += "pytest tests/test_ocr_ai.py (file not found)"
}

if ($Skipped.Count -gt 0) {
    Write-Warning ("Skipped: " + ($Skipped -join "; "))
}

Write-Host "verify.ps1 completed"
