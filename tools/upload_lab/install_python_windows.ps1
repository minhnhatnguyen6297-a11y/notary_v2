param(
    [string]$PythonVersion = "3.14.3"
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Test-CompatiblePython {
    param([string]$PythonExe)
    if (-not (Test-Path -LiteralPath $PythonExe)) {
        return $false
    }

    try {
        $version = & $PythonExe -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>$null
        if (-not $version) {
            return $false
        }
        $parts = $version.Trim().Split(".")
        if ($parts.Length -lt 2) {
            return $false
        }
        return ([int]$parts[0] -gt 3) -or (([int]$parts[0] -eq 3) -and ([int]$parts[1] -ge 10))
    } catch {
        return $false
    }
}

function Find-InstalledPython {
    $pythonRoot = Join-Path $env:LocalAppData "Programs\Python"
    if (-not (Test-Path -LiteralPath $pythonRoot)) {
        return $null
    }

    $candidates = Get-ChildItem -LiteralPath $pythonRoot -Directory -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending
    foreach ($candidate in $candidates) {
        $pythonExe = Join-Path $candidate.FullName "python.exe"
        if (Test-CompatiblePython -PythonExe $pythonExe) {
            return $pythonExe
        }
    }
    return $null
}

$existingPython = Find-InstalledPython
if ($existingPython) {
    Write-Host "[SETUP] Da tim thay Python tai $existingPython"
    Write-Output $existingPython
    exit 0
}

$installerUrl = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-amd64.exe"
$tempDir = Join-Path $env:TEMP "upload_tool_python_bootstrap"
$installerPath = Join-Path $tempDir "python-$PythonVersion-amd64.exe"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

Write-Host "[SETUP] Dang tai Python $PythonVersion tu python.org..."
Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing

Write-Host "[SETUP] Dang cai Python cho user hien tai..."
$arguments = @(
    "/quiet",
    "InstallAllUsers=0",
    "Include_pip=1",
    "Include_tcltk=1",
    "Include_launcher=1",
    "PrependPath=0",
    "Shortcuts=0",
    "Include_test=0"
)
$process = Start-Process -FilePath $installerPath -ArgumentList $arguments -Wait -PassThru
if ($process.ExitCode -ne 0) {
    throw "Python installer that bai, exit code $($process.ExitCode)."
}

$installedPython = Find-InstalledPython
if (-not $installedPython) {
    throw "Da cai Python xong nhung khong tim thay python.exe trong %LocalAppData%\Programs\Python."
}

Write-Host "[SETUP] Cai Python thanh cong: $installedPython"
Write-Output $installedPython
