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
    $Tracked = @(& git diff --name-only --diff-filter=ACMRT HEAD)
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

function Test-FastAuditRelevantChange {
    param([string[]]$ChangedFiles)

    $FastAuditRelevant = @(
        "services/fast_audit/__init__.py",
        "services/fast_audit/models.py",
        "services/fast_audit/scan_loader.py",
        "services/fast_audit/pdf_splitter.py",
        "services/fast_audit/ocr_runner.py",
        "services/fast_audit/doc_grouper.py",
        "services/fast_audit/word_parser.py",
        "services/fast_audit/compare_engine.py",
        "services/fast_audit/report_writer.py",
        "services/fast_audit/cache_store.py",
        "services/fast_audit/rules.py",
        "tools/run_fast_audit.py",
        "tests/test_fast_audit_scan_loader.py",
        "tests/test_fast_audit_word_parser.py",
        "tests/test_fast_audit_compare_engine.py",
        "tests/test_fast_audit_integration.py"
    )

    foreach ($File in $ChangedFiles) {
        $Normalized = $File -replace "\\", "/"
        if ($FastAuditRelevant -contains $Normalized) {
            return $true
        }
    }

    return $false
}

function Test-ZaloInboxRelevantChange {
    param([string[]]$ChangedFiles)

    foreach ($File in $ChangedFiles) {
        $Normalized = $File -replace "\\", "/"
        if (
            $Normalized -in @("models.py", "main.py", ".env.example") -or
            $Normalized -eq "routers/zalo_inbox.py" -or
            $Normalized -eq "services/zalo_inbox.py" -or
            $Normalized -eq "frontend/templates/zalo_inbox.html" -or
            $Normalized -eq "frontend/static/js/zalo_inbox.js" -or
            $Normalized -like "tests/test_zalo_inbox*.py" -or
            $Normalized -eq "tests/zalo_inbox_ui_static.test.mjs" -or
            $Normalized -like "zalo_connector/*"
        ) {
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
    if (Test-Path "services/fast_audit") {
        $FastAuditFiles = @(Get-ChildItem -Path "services/fast_audit" -Filter "*.py" | Select-Object -ExpandProperty FullName)
        if ($FastAuditFiles.Count -gt 0) {
            & $Python -m py_compile @FastAuditFiles
        }
    }
    if (Test-Path "tools/run_fast_audit.py") {
        & $Python -m py_compile tools/run_fast_audit.py
    }
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

if (Test-Path "tests/test_fast_audit_scan_loader.py") {
    $ChangedFiles = @(Get-ChangedFiles)
    $RunFullVerify = $env:FULL_VERIFY -eq "1"
    if ($RunFullVerify -or (Test-FastAuditRelevantChange -ChangedFiles $ChangedFiles)) {
        $FastAuditTests = @(Get-ChildItem -Path "tests" -Filter "test_fast_audit_*.py" | Select-Object -ExpandProperty FullName)
        Invoke-VerifyStep "pytest tests/test_fast_audit_*.py" {
            & $Python -m pytest @FastAuditTests -q
        }
    }
    else {
        $Skipped += "pytest tests/test_fast_audit_*.py (no fast-audit changed files; set FULL_VERIFY=1 to force)"
    }
}
else {
    $Skipped += "pytest tests/test_fast_audit_*.py (files not found)"
}

$ChangedFiles = @(Get-ChangedFiles)
$RunFullVerify = $env:FULL_VERIFY -eq "1"
if ($RunFullVerify -or (Test-ZaloInboxRelevantChange -ChangedFiles $ChangedFiles)) {
    Invoke-VerifyStep "pytest Zalo Inbox and OCR contract" {
        & $Python -m pytest tests/test_zalo_inbox.py tests/test_zalo_inbox_api.py tests/test_ocr_ai.py -q
    }
    Invoke-VerifyStep "node Zalo Inbox UI contract" {
        & node --test tests/zalo_inbox_ui_static.test.mjs
    }
    Invoke-VerifyStep "npm Zalo connector tests" {
        & npm --prefix zalo_connector test
    }
    Invoke-VerifyStep "npm Zalo connector syntax" {
        & npm --prefix zalo_connector run check
    }
}
else {
    $Skipped += "Zalo Inbox Python/UI/connector tests (no Zalo-relevant changed files; set FULL_VERIFY=1 to force)"
}

if ($Skipped.Count -gt 0) {
    Write-Warning ("Skipped: " + ($Skipped -join "; "))
}

Write-Host "verify.ps1 completed"
