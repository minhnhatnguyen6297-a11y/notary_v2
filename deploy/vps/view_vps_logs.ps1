param(
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

function Read-KeyValueFile {
    param([string]$Path)
    $result = @{}
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ([string]::IsNullOrWhiteSpace($line)) { return }
        if ($line.StartsWith("#")) { return }
        $idx = $line.IndexOf("=")
        if ($idx -lt 1) { return }
        $key = $line.Substring(0, $idx).Trim().TrimStart([char]0xFEFF)
        $value = $line.Substring($idx + 1).Trim()
        $result[$key] = $value
    }
    return $result
}

function Get-ConfigValue {
    param(
        [hashtable]$Config,
        [string]$Key
    )
    if (-not $Config.ContainsKey($Key)) { return "" }
    $value = $Config[$Key]
    if ($null -eq $value) { return "" }
    return $value.ToString().Trim()
}

try {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        $ConfigPath = Join-Path $scriptDir "ssh_credentials.env"
    } elseif (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
        $ConfigPath = Join-Path (Get-Location) $ConfigPath
    }

    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Khong tim thay file cau hinh: $ConfigPath"
    }

    $cfg = Read-KeyValueFile -Path $ConfigPath
    $vpsHost = Get-ConfigValue -Config $cfg -Key "VPS_HOST"
    $vpsPort = Get-ConfigValue -Config $cfg -Key "VPS_PORT"
    $vpsUser = Get-ConfigValue -Config $cfg -Key "VPS_USER"
    $vpsPassword = Get-ConfigValue -Config $cfg -Key "VPS_PASSWORD"
    $vpsHostKey = Get-ConfigValue -Config $cfg -Key "VPS_HOSTKEY"
    $repoDir = Get-ConfigValue -Config $cfg -Key "VPS_REPO_DIR"

    if ([string]::IsNullOrWhiteSpace($vpsPort)) { $vpsPort = "22" }
    if ([string]::IsNullOrWhiteSpace($repoDir)) { $repoDir = "~/notary_v2" }
    if ([string]::IsNullOrWhiteSpace($vpsHost) -or [string]::IsNullOrWhiteSpace($vpsUser) -or [string]::IsNullOrWhiteSpace($vpsPassword)) {
        throw "Thieu VPS_HOST / VPS_USER / VPS_PASSWORD trong $ConfigPath"
    }
    if ([string]::IsNullOrWhiteSpace($vpsHostKey)) {
        throw "Thieu VPS_HOSTKEY trong $ConfigPath"
    }

    $binDir = Join-Path $scriptDir "bin"
    $plinkPath = Join-Path $binDir "plink.exe"
    if (-not (Test-Path -LiteralPath $plinkPath)) {
        New-Item -ItemType Directory -Force -Path $binDir | Out-Null
        Invoke-WebRequest -Uri "https://the.earth.li/~sgtatham/putty/latest/w64/plink.exe" -OutFile $plinkPath
    }

    $plinkArgs = @("-ssh", "$vpsUser@$vpsHost", "-P", $vpsPort, "-pw", $vpsPassword, "-batch", "-t")
    $hostKeys = New-Object System.Collections.Generic.List[string]
    $hostKeys.Add($vpsHostKey) | Out-Null
    if ($vpsHostKey -match "(SHA256:[A-Za-z0-9+/=]+)") {
        $hostKeys.Add($Matches[1]) | Out-Null
    }
    $hostKeys | Select-Object -Unique | ForEach-Object {
        if (-not [string]::IsNullOrWhiteSpace($_)) {
            $plinkArgs += @("-hostkey", $_)
        }
    }

    $remoteCommand = @"
cd $repoDir
echo '===== WEB LOG ====='
tail -n 80 -f logs/web.log logs/worker.log
"@

    & $plinkPath @plinkArgs $remoteCommand
    if ($LASTEXITCODE -ne 0) {
        throw "Khong the mo log VPS (plink exit code $LASTEXITCODE)."
    }
}
catch {
    Write-Host "[VPS-Logs][ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
