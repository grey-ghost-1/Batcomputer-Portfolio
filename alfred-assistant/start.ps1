#Requires -Version 5.1
<#
.SYNOPSIS
    Starts the Alfred Assistant service natively on Windows, loopback-only.

.DESCRIPTION
    Runs `python -m uvicorn alfred.main:app` bound to a loopback address, in
    the foreground of this terminal. Closing the terminal (or pressing
    Ctrl+C) stops the service completely.

    This script never installs a scheduled task, a registry Run key, a
    Windows service, a startup shortcut, or any other form of startup
    persistence. There is nothing left running after you close the window.

    Before a non-loopback host is ever handed to Python, this script
    validates it itself and refuses to continue if it is not a loopback
    address -- Alfred only ever serves 127.0.0.0/8, ::1, or localhost.

    Run it from anywhere; it locates its own folder first, so
    `Set-Location alfred-assistant; .\start.ps1` and `.\alfred-assistant\start.ps1`
    both work identically.

.PARAMETER BindHost
    Loopback address to bind. Defaults to $env:ALFRED_HOST, then the
    ALFRED_HOST value in .env, then 127.0.0.1.

.PARAMETER Port
    TCP port to bind. Defaults to $env:ALFRED_PORT, then the ALFRED_PORT
    value in .env, then 8020.

.EXAMPLE
    .\start.ps1

.EXAMPLE
    .\start.ps1 -Port 8111
#>

[CmdletBinding()]
param(
    [string]$BindHost,
    [int]$Port
)

$ErrorActionPreference = "Stop"

# Always operate relative to this script's own folder, regardless of the
# caller's current directory. Because this runs in the script's own scope
# (not dot-sourced), the caller's working directory is restored automatically
# once the script returns.
$ServiceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ServiceDir

$EnvExample = Join-Path $ServiceDir ".env.example"
$EnvFile = Join-Path $ServiceDir ".env"

function Get-DotEnvValue {
    <# Reads one KEY=value line from a simple .env file, ignoring comments
       and blank lines. Returns $null if the file or key is absent. #>
    param([string]$Path, [string]$Key)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $pattern = "^\s*$([regex]::Escape($Key))\s*=\s*(.+?)\s*$"
    foreach ($line in Get-Content -LiteralPath $Path) {
        if ($line -match '^\s*#' -or $line -match '^\s*$') {
            continue
        }
        if ($line -match $pattern) {
            return $Matches[1].Trim('"').Trim("'")
        }
    }
    return $null
}

function Test-LoopbackHost {
    param([string]$CandidateHost)

    $normalized = $CandidateHost.Trim().ToLowerInvariant()
    if ($normalized -eq "localhost" -or $normalized -eq "loopback") {
        return $true
    }
    try {
        $address = [System.Net.IPAddress]::Parse($normalized)
        return [System.Net.IPAddress]::IsLoopback($address)
    } catch {
        return $false
    }
}

# --- First-run convenience: copy the example env file, never overwrite. -----
if ((Test-Path -LiteralPath $EnvExample) -and (-not (Test-Path -LiteralPath $EnvFile))) {
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Created .env from .env.example (git-ignored; edit it to set ALFRED_ACTION_TOKEN)." -ForegroundColor Yellow
}

# --- Resolve the effective bind host/port: explicit parameter, then process --
# --- environment variable, then .env file, then the safe hardcoded default. -
if (-not $PSBoundParameters.ContainsKey('BindHost')) {
    if ($env:ALFRED_HOST) {
        $BindHost = $env:ALFRED_HOST
    } else {
        $fromFile = Get-DotEnvValue -Path $EnvFile -Key "ALFRED_HOST"
        if ($fromFile) { $BindHost = $fromFile } else { $BindHost = "127.0.0.1" }
    }
}
if (-not $PSBoundParameters.ContainsKey('Port')) {
    if ($env:ALFRED_PORT) {
        $Port = [int]$env:ALFRED_PORT
    } else {
        $fromFile = Get-DotEnvValue -Path $EnvFile -Key "ALFRED_PORT"
        if ($fromFile) { $Port = [int]$fromFile } else { $Port = 8020 }
    }
}

# --- Safety: refuse to bind anywhere but loopback, no exceptions. ------------
if (-not (Test-LoopbackHost -CandidateHost $BindHost)) {
    $message = "Refusing to start: '$BindHost' is not a loopback address. " +
        "Use 127.0.0.1, ::1, or localhost -- Alfred never binds to a public or LAN-reachable interface."
    Write-Error $message
    exit 1
}

# --- Resolve a Python interpreter without assuming a specific venv layout. --
$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
    $PythonCmd = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $PythonCmd) {
    $message = "Python was not found on PATH. Activate your virtual environment first, e.g.:`n" +
        "  ..\.venv\Scripts\Activate.ps1`n" +
        "See README.md for full setup steps."
    Write-Error $message
    exit 1
}
$PythonExe = $PythonCmd.Source

& $PythonExe -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
    $message = "Required packages (fastapi, uvicorn, ...) are not importable by '$PythonExe'.`n" +
        "From the repository root, run:`n  python -m pip install -r requirements.txt`nSee README.md for full setup steps."
    Write-Error $message
    exit 1
}

$tokenConfigured = [bool](Get-DotEnvValue -Path $EnvFile -Key "ALFRED_ACTION_TOKEN")
$desktopEnabled = (Get-DotEnvValue -Path $EnvFile -Key "ALFRED_DESKTOP_ACTIONS_ENABLED")

Write-Host ""
Write-Host "Alfred Assistant -- native local service" -ForegroundColor Cyan
Write-Host ("  Binding to loopback only: http://{0}:{1}" -f $BindHost, $Port) -ForegroundColor Cyan
Write-Host "  No Docker, no public deployment, no startup persistence -- this window IS the service." -ForegroundColor Cyan
Write-Host "  Every desktop action still requires its own explicit approve -> execute step." -ForegroundColor Cyan
Write-Host ("  Action token configured: {0}" -f $tokenConfigured) -ForegroundColor Cyan
Write-Host ("  Desktop actions enabled: {0}" -f ($(if ($desktopEnabled) { $desktopEnabled } else { "false" }))) -ForegroundColor Cyan
Write-Host "  Press Ctrl+C to stop." -ForegroundColor Cyan
Write-Host ""

# --- Launch in the foreground. No background job, no scheduled task, no ----
# --- service registration: closing this window stops Alfred completely. ----
& $PythonExe -m uvicorn alfred.main:app --host $BindHost --port $Port
exit $LASTEXITCODE
