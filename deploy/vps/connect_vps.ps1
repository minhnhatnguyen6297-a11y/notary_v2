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
    $appScheme = Get-ConfigValue -Config $cfg -Key "VPS_APP_SCHEME"
    $appPort = Get-ConfigValue -Config $cfg -Key "VPS_APP_PORT"
    $appPath = Get-ConfigValue -Config $cfg -Key "VPS_APP_PATH"
    $repoDir = Get-ConfigValue -Config $cfg -Key "VPS_REPO_DIR"

    if ([string]::IsNullOrWhiteSpace($vpsHost)) { throw "Thieu VPS_HOST trong $ConfigPath" }
    if ([string]::IsNullOrWhiteSpace($user)) { throw "Thieu VPS_USER trong $ConfigPath" }
    if ([string]::IsNullOrWhiteSpace($password)) { throw "Thieu VPS_PASSWORD trong $ConfigPath" }
    if ([string]::IsNullOrWhiteSpace($hostKey)) { throw "Thieu VPS_HOSTKEY trong $ConfigPath de chay 1-click khong hoi xac nhan." }
    if ([string]::IsNullOrWhiteSpace($port)) { $port = "22" }
    if ([string]::IsNullOrWhiteSpace($appScheme)) { $appScheme = "http" }
    if ([string]::IsNullOrWhiteSpace($appPort)) { $appPort = "8000" }
    if ([string]::IsNullOrWhiteSpace($appPath)) { $appPath = "/" }
    if (-not $appPath.StartsWith("/")) { $appPath = "/$appPath" }
    if ([string]::IsNullOrWhiteSpace($repoDir)) { $repoDir = "~/notary_v2" }

    $appUrl = "{0}://{1}:{2}{3}" -f $appScheme, $vpsHost, $appPort, $appPath

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
    $remoteTemplate = @'
set -e
REPO_DIR="__REPO_DIR__"
APP_PORT="__APP_PORT__"

cd "$REPO_DIR"
(git pull --ff-only || true)

if [ -f deploy/vps/manage_services.sh ]; then
  bash deploy/vps/manage_services.sh restart >/tmp/notary_restart.log 2>&1 || true
fi

initial_code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${APP_PORT}/" || true)"
if [ "$initial_code" != "200" ]; then
  (bash deploy/vps/one_click_install.sh >/tmp/notary_install.log 2>&1 || bash install_vps.sh >/tmp/notary_install.log 2>&1)
  bash deploy/vps/manage_services.sh restart >/tmp/notary_restart.log 2>&1 || true
fi

for i in $(seq 1 60); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${APP_PORT}/" || true)"
  if [ "$code" = "200" ]; then
    echo READY
    exit 0
  fi
  sleep 1
done

echo NOT_READY
exit 1
'@
    $remoteCommand = $remoteTemplate.Replace("__REPO_DIR__", $repoDir).Replace("__APP_PORT__", $appPort)

    $plinkArgs = @("-ssh", $sshTarget, "-P", $port, "-pw", $password, "-batch")
    if (-not [string]::IsNullOrWhiteSpace($hostKey)) {
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

    Log-Info "Dang khoi dong app tren ${sshTarget}:$port ..."
    & $plinkPath @plinkArgs $remoteCommand
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        throw "Khong the khoi dong app tu xa (plink exit code $exitCode)."
    }

    Log-Info "App san sang. Dang mo trinh duyet: $appUrl"
    Start-Process $appUrl | Out-Null
}
catch {
    Write-Host "[VPS-Connect][ERROR] $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
