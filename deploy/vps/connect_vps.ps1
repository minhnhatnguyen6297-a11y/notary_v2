param(
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

function Log-Info {
    param([string]$Message)
    Write-Host "[VPS-Connect] $Message"
}

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

        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, [Math]::Max(0, $value.Length - 2))
        }

        $result[$key] = $value
    }
    return $result
}

function Get-ConfigValue {
    param(
        [hashtable]$Config,
        [string]$Key
    )
    if (-not $Config.ContainsKey($Key)) {
        return ""
    }
    $value = $Config[$Key]
    if ($null -eq $value) {
        return ""
    }
    return $value.ToString().Trim()
}

try {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

    if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
        $ConfigPath = Join-Path $ScriptDir "ssh_credentials.env"
    } else {
        if (-not [System.IO.Path]::IsPathRooted($ConfigPath)) {
            $ConfigPath = Join-Path (Get-Location) $ConfigPath
        }
    }

    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        throw "Khong tim thay file cau hinh: $ConfigPath`nHay tao file tu mau: deploy\vps\ssh_credentials.example"
    }

    $cfg = Read-KeyValueFile -Path $ConfigPath
    $vpsHost = Get-ConfigValue -Config $cfg -Key "VPS_HOST"
    $port = Get-ConfigValue -Config $cfg -Key "VPS_PORT"
    $user = Get-ConfigValue -Config $cfg -Key "VPS_USER"
    $password = Get-ConfigValue -Config $cfg -Key "VPS_PASSWORD"
    $hostKey = Get-ConfigValue -Config $cfg -Key "VPS_HOSTKEY"

    if ([string]::IsNullOrWhiteSpace($vpsHost)) { throw "Thieu VPS_HOST trong $ConfigPath" }
    if ([string]::IsNullOrWhiteSpace($user)) { throw "Thieu VPS_USER trong $ConfigPath" }
    if ([string]::IsNullOrWhiteSpace($password)) { throw "Thieu VPS_PASSWORD trong $ConfigPath" }
    if ([string]::IsNullOrWhiteSpace($port)) { $port = "22" }

    $binDir = Join-Path $ScriptDir "bin"
    $plinkPath = Join-Path $binDir "plink.exe"
    if (-not (Test-Path -LiteralPath $plinkPath)) {
        Log-Info "Chua co plink.exe, dang tai ve..."
        New-Item -ItemType Directory -Force -Path $binDir | Out-Null
        Invoke-WebRequest `
            -Uri "https://the.earth.li/~sgtatham/putty/latest/w64/plink.exe" `
            -OutFile $plinkPath
    }

    $sshTarget = "$user@$vpsHost"
    $remoteCommand = "cd notary_v2 && (git pull --ff-only || true) && (bash deploy/vps/one_click_install.sh || bash install_vps.sh); exec bash"
    $plinkArgs = @("-ssh", $sshTarget, "-P", $port, "-pw", $password)
    if (-not [string]::IsNullOrWhiteSpace($hostKey)) {
        $plinkArgs += @("-batch")
        $hostKeys = New-Object System.Collections.Generic.List[string]
        $hostKeys.Add($hostKey) | Out-Null
        if ($hostKey -match "(SHA256:[A-Za-z0-9+/=]+)") {
            $hostKeys.Add($Matches[1]) | Out-Null
        }
        $uniqueHostKeys = $hostKeys | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique
        foreach ($key in $uniqueHostKeys) {
            $plinkArgs += @("-hostkey", $key)
        }
    }
    $plinkArgs += @("-t", $remoteCommand)

    Log-Info "Dang ket noi ${sshTarget}:$port ..."
    & $plinkPath @plinkArgs
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "plink thoat voi ma loi $exitCode"
    }
}
catch {
    Write-Host "[VPS-Connect][ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
