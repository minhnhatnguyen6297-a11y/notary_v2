param(
    [int]$Tail = 80,
    [int]$WaitSeconds = 45,
    [switch]$ForceRestart,
    [switch]$SkipStart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runBat = Join-Path $repoRoot "run.bat"
$logsDir = Join-Path $repoRoot "logs"
$baseUrl = "http://127.0.0.1:8000"

function Get-GitLines {
    param([string]$Arguments)

    $output = & git $Arguments.Split(" ") 2>$null
    if ($LASTEXITCODE -ne 0) {
        return @()
    }
    return @($output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Normalize-ContextToken {
    param([string]$Token)

    $normalized = ""
    if ($null -ne $Token) {
        $normalized = $Token.Trim().ToLower()
    }
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        return ""
    }

    $map = @{
        "case" = "cases"
        "cases" = "cases"
        "customer" = "customers"
        "customers" = "customers"
        "property" = "properties"
        "properties" = "properties"
        "participant" = "participants"
        "participants" = "participants"
        "ocr" = "ocr"
        "qr" = "ocr"
        "mrz" = "ocr"
    }

    if ($map.ContainsKey($normalized)) {
        return $map[$normalized]
    }
    return $normalized
}

function Add-ContextScore {
    param(
        [hashtable]$Scores,
        [string]$Token,
        [int]$Weight
    )

    $key = Normalize-ContextToken -Token $Token
    if ([string]::IsNullOrWhiteSpace($key)) {
        return
    }
    if (-not $Scores.ContainsKey($key)) {
        $Scores[$key] = 0
    }
    $Scores[$key] += $Weight
}

function Get-ActiveContext {
    param(
        [string]$BranchName,
        [string[]]$ChangedPaths
    )

    $scores = @{}
    $ignoredTokens = @(
        "feature", "fix", "refactor", "chore", "bug", "hotfix", "main",
        "master", "origin", "task", "issue", "update", "first", "second"
    )

    foreach ($token in ($BranchName -split "[^a-zA-Z0-9]+")) {
        $clean = ""
        if ($null -ne $token) {
            $clean = $token.Trim().ToLower()
        }
        if ([string]::IsNullOrWhiteSpace($clean) -or $ignoredTokens -contains $clean) {
            continue
        }
        Add-ContextScore -Scores $scores -Token $clean -Weight 3
    }

    foreach ($path in $ChangedPaths) {
        $parts = $path -split "[\\/]+"
        if ($parts.Count -eq 0) {
            continue
        }

        if ($parts[0] -eq "routers" -and $parts.Count -ge 2) {
            Add-ContextScore -Scores $scores -Token ([System.IO.Path]::GetFileNameWithoutExtension($parts[1])) -Weight 4
        }
        if ($parts[0] -eq "templates" -and $parts.Count -ge 2) {
            Add-ContextScore -Scores $scores -Token $parts[1] -Weight 4
        }
        if ($parts[0] -eq "tests" -and $parts.Count -ge 2) {
            $testName = [System.IO.Path]::GetFileNameWithoutExtension($parts[1])
            $testName = $testName -replace "^test_", ""
            $testToken = ($testName -split "[^a-zA-Z0-9]+")[0]
            Add-ContextScore -Scores $scores -Token $testToken -Weight 3
        }

        Add-ContextScore -Scores $scores -Token $parts[0] -Weight 1
    }

    if ($scores.Count -eq 0) {
        return [pscustomobject]@{
            Name = "unknown"
            Scores = @{}
        }
    }

    $winner = $scores.GetEnumerator() |
        Sort-Object `
            @{ Expression = "Value"; Descending = $true }, `
            @{ Expression = "Name"; Descending = $false } |
        Select-Object -First 1

    return [pscustomobject]@{
        Name = $winner.Name
        Scores = $scores
    }
}

function Get-ChangedPaths {
    $lines = Get-GitLines -Arguments "status --porcelain"
    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($line in $lines) {
        if ($line.Length -lt 4) {
            continue
        }
        $rawPath = $line.Substring(3).Trim()
        if ([string]::IsNullOrWhiteSpace($rawPath)) {
            continue
        }
        if ($rawPath.Contains("->")) {
            $rawPath = ($rawPath -split "->")[-1].Trim()
        }
        $paths.Add($rawPath) | Out-Null
    }

    if ($paths.Count -eq 0) {
        $recent = Get-GitLines -Arguments "log -1 --name-only --pretty="
        foreach ($path in $recent) {
            $paths.Add($path.Trim()) | Out-Null
        }
    }

    return @($paths | Select-Object -Unique)
}

function Test-AppReady {
    $urls = @("$baseUrl/api/stats", "$baseUrl/")
    try {
        foreach ($url in $urls) {
            try {
                $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                    return $true
                }
            } catch {
            }
        }
        return $false
    } catch {
        return $false
    }
}

function Wait-AppReady {
    param([int]$TimeoutSeconds)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-AppReady) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Show-LogTail {
    param(
        [string]$Path,
        [string]$Title,
        [int]$TailCount
    )

    Write-Host ""
    Write-Host "===== $Title ====="
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "[missing] $Path"
        return
    }

    Get-Content -LiteralPath $Path -Tail $TailCount

    $matches = Select-String -Path $Path -Pattern "Traceback|ERROR|CRITICAL|Exception" |
        Select-Object -Last 10
    if ($matches) {
        Write-Host ""
        Write-Host "----- recent error markers -----"
        $matches | ForEach-Object {
            Write-Host ("[{0}] {1}" -f $_.LineNumber, $_.Line.Trim())
        }
    }
}

function Get-SelectedLogs {
    param(
        [string]$LogsPath,
        [string]$ContextName
    )

    if (-not (Test-Path -LiteralPath $LogsPath)) {
        return @()
    }

    $allLogs = @(Get-ChildItem -LiteralPath $LogsPath -File | Sort-Object LastWriteTime -Descending)
    $selected = New-Object System.Collections.Generic.List[System.IO.FileInfo]

    foreach ($name in @("web.log", "worker.log")) {
        $match = $allLogs | Where-Object { $_.Name -eq $name } | Select-Object -First 1
        if ($match) {
            $selected.Add($match) | Out-Null
        }
    }

    if ($ContextName -ne "unknown") {
        foreach ($log in $allLogs | Where-Object { $_.BaseName -like "*$ContextName*" }) {
            $selected.Add($log) | Out-Null
        }
    }

    foreach ($log in $allLogs | Select-Object -First 3) {
        $selected.Add($log) | Out-Null
    }

    return @($selected | Sort-Object FullName -Unique | Select-Object -First 5)
}

if (-not (Test-Path -LiteralPath $runBat)) {
    throw "Khong tim thay run.bat tai $runBat"
}

$branch = ((Get-GitLines -Arguments "branch --show-current") | Select-Object -First 1)
$changedPaths = Get-ChangedPaths
$context = Get-ActiveContext -BranchName $branch -ChangedPaths $changedPaths

Write-Host "===== session context ====="
Write-Host ("branch: {0}" -f ($(if ($branch) { $branch } else { "(unknown)" })))
Write-Host ("active_context: {0}" -f $context.Name)
if ($changedPaths.Count -gt 0) {
    Write-Host "changed_paths:"
    $changedPaths | Select-Object -First 12 | ForEach-Object {
        Write-Host ("- {0}" -f $_)
    }
}
if ($context.Scores.Count -gt 0) {
    Write-Host "context_scores:"
    $context.Scores.GetEnumerator() |
        Sort-Object `
            @{ Expression = "Value"; Descending = $true }, `
            @{ Expression = "Name"; Descending = $false } |
        Select-Object -First 8 |
        ForEach-Object {
            Write-Host ("- {0}: {1}" -f $_.Name, $_.Value)
        }
}

$ready = Test-AppReady
if (-not $SkipStart -and ($ForceRestart -or -not $ready)) {
    Write-Host "[session] Starting local stack via run.bat"
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c", "`"$runBat`"" `
        -WorkingDirectory $repoRoot | Out-Null

    $ready = Wait-AppReady -TimeoutSeconds $WaitSeconds
}

Write-Host ""
if ($ready) {
    Write-Host "[session] App ready at $baseUrl"
} else {
    Write-Host "[session] App not ready after waiting $WaitSeconds seconds"
}

$selectedLogs = Get-SelectedLogs -LogsPath $logsDir -ContextName $context.Name
foreach ($log in $selectedLogs) {
    Show-LogTail -Path $log.FullName -Title $log.Name -TailCount $Tail
}

if (-not $ready) {
    exit 1
}
