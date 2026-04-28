<#
.SYNOPSIS
    Keep the TCM Web API process alive and restart it on failure.
.DESCRIPTION
    1. Start src.web.main with the required environment variables.
    2. Watch the foreground process until it exits.
    3. Wait for RestartDelaySec seconds and then restart it.
    4. Write all watchdog messages to logs\watchdog.log.
.PARAMETER MaxRestarts
    Maximum restart attempts. 0 means unlimited.
.PARAMETER RestartDelaySec
    Cooldown before restart. Default is 8 seconds.
.PARAMETER Port
    API listen port. Default is 8765.
#>
param(
    [int]$MaxRestarts = 0,
    [int]$RestartDelaySec = 8,
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSScriptRoot
Set-Location $ScriptDir

$LogFile = Join-Path $ScriptDir "logs\watchdog.log"
$Python = Join-Path $ScriptDir "venv310\Scripts\python.exe"

# Ensure the log directory exists.
if (-not (Test-Path (Split-Path $LogFile))) {
    New-Item -ItemType Directory -Path (Split-Path $LogFile) -Force | Out-Null
}

function Write-Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Kill-OldServer {
    # Free the port in case an old process still holds it.
    $pids = netstat -ano 2>$null |
    Select-String ":$Port\s" |
    ForEach-Object { ($_ -split '\s+')[-1] } |
    Sort-Object -Unique |
    Where-Object { $_ -match '^\d+$' -and [int]$_ -gt 4 }
    foreach ($p in $pids) {
        try {
            Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
            Write-Log "  killed process using port $Port pid=$p"
        }
        catch {}
    }
    Start-Sleep -Seconds 2
}

$restartCount = 0

Write-Log "=== Watchdog start (MaxRestarts=$MaxRestarts, Delay=${RestartDelaySec}s, Port=$Port) ==="

while ($true) {
    if ($MaxRestarts -gt 0 -and $restartCount -ge $MaxRestarts) {
        Write-Log "max restart count reached ($MaxRestarts), watchdog exits."
        break
    }

    Kill-OldServer

    Write-Log "starting API server (restart_count=$restartCount)"

    # Set runtime environment variables.
    $env:TCM__DATABASE__HOST = "127.0.0.1"
    $env:TCM__DATABASE__NAME = "postgres"
    $env:TCM__DATABASE__USER = "postgres"
    $env:TCM_DB_PASSWORD = "yourpassword"
    $env:TCM_NEO4J_URI = "neo4j://localhost:7687"
    $env:TCM_NEO4J_PASSWORD = "Hgk1989225"

    # Start the API in the foreground so the watchdog can observe exit.
    try {
        & $Python -m src.web.main --config config.yml --environment production --port $Port
        $exitCode = $LASTEXITCODE
        Write-Log "server process exited, exit_code=$exitCode"
    }
    catch {
        Write-Log "startup exception: $_"
    }

    $restartCount++
    Write-Log "cooldown ${RestartDelaySec}s before restart"
    Start-Sleep -Seconds $RestartDelaySec
}
