<#
.SYNOPSIS
    Keep the TCM Web API process alive and restart it on failure.
.DESCRIPTION
    1. Verify required environment variables are present (no hard-coded secrets).
    2. Start src.web.main with the inherited environment.
    3. Watch the foreground process until it exits.
    4. Wait for RestartDelaySec seconds and then restart it.
    5. Write all watchdog messages to logs\watchdog.log.

    Required environment variables (must be set BEFORE invoking this script):
        TCM__DATABASE__HOST, TCM__DATABASE__NAME, TCM__DATABASE__USER,
        TCM_DB_PASSWORD, TCM_NEO4J_URI, TCM_NEO4J_PASSWORD
    The watchdog refuses to start with any of them empty so an unconfigured
    workstation cannot accidentally talk to the production database.
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
    [int]$Port = 8765,
    [switch]$NoOutboxWorker
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $PSScriptRoot
Set-Location $ScriptDir

$LogFile = Join-Path $ScriptDir "logs\watchdog.log"
$OutboxLogFile = Join-Path $ScriptDir "logs\outbox_worker.log"
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

# ---- T6.3: Outbox worker supervision ----
$script:OutboxJob = $null
$script:OutboxJobName = "tcmar-outbox-worker-supervisor"

function Start-OutboxWorkerJob {
    param([int]$RestartDelay = 8)

    if ($NoOutboxWorker) {
        Write-Log "outbox worker supervision disabled (-NoOutboxWorker)"
        return
    }

    # Clean up any stale supervisor job from a prior run.
    Get-Job -Name $script:OutboxJobName -ErrorAction SilentlyContinue |
    ForEach-Object {
        try { Stop-Job -Job $_ -ErrorAction SilentlyContinue } catch {}
        try { Remove-Job -Job $_ -Force -ErrorAction SilentlyContinue } catch {}
    }

    $script:OutboxJob = Start-Job -Name $script:OutboxJobName -ScriptBlock {
        param($PythonExe, $RepoDir, $LogFile, $RestartDelay, $WatchdogLog)

        function _Log {
            param([string]$Msg)
            $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
            $line = "[$ts] [outbox-supervisor] $Msg"
            Add-Content -Path $WatchdogLog -Value $line -Encoding UTF8
        }

        Set-Location $RepoDir
        $restartCount = 0
        while ($true) {
            try {
                _Log "starting outbox worker (restart_count=$restartCount)"
                $proc = Start-Process -FilePath $PythonExe `
                    -ArgumentList @(
                    "tools\run_outbox_worker.py",
                    "--log-file", $LogFile
                ) `
                    -WorkingDirectory $RepoDir `
                    -NoNewWindow -PassThru `
                    -RedirectStandardOutput (Join-Path $RepoDir "logs\outbox_worker.stdout.log") `
                    -RedirectStandardError  (Join-Path $RepoDir "logs\outbox_worker.stderr.log")
                _Log "outbox worker started pid=$($proc.Id)"
                Wait-Process -Id $proc.Id -ErrorAction SilentlyContinue
                _Log "outbox worker exited pid=$($proc.Id) exit_code=$($proc.ExitCode); restarting in ${RestartDelay}s"
            }
            catch {
                _Log "outbox worker startup error: $_"
            }
            $restartCount++
            Start-Sleep -Seconds $RestartDelay
        }
    } -ArgumentList $Python, $ScriptDir, $OutboxLogFile, $RestartDelay, $LogFile

    Write-Log "outbox worker supervisor job started (job_id=$($script:OutboxJob.Id), restart_delay=${RestartDelay}s, log=$OutboxLogFile)"
}

function Stop-OutboxWorkerJob {
    if ($null -eq $script:OutboxJob) { return }
    try {
        Stop-Job -Job $script:OutboxJob -ErrorAction SilentlyContinue
        Remove-Job -Job $script:OutboxJob -Force -ErrorAction SilentlyContinue
        Write-Log "outbox worker supervisor job stopped"
    }
    catch {
        Write-Log "failed to stop outbox supervisor job: $_"
    }
    # Kill any leftover python.exe running run_outbox_worker.py.
    try {
        Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'run_outbox_worker\.py' } |
        ForEach-Object {
            Write-Log "  killing leftover outbox worker pid=$($_.ProcessId)"
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }
    catch {}
    $script:OutboxJob = $null
}

$restartCount = 0

Write-Log "=== Watchdog start (MaxRestarts=$MaxRestarts, Delay=${RestartDelaySec}s, Port=$Port, OutboxWorker=$(-not $NoOutboxWorker)) ==="

# Start outbox worker supervision once; it survives API restarts.
Start-OutboxWorkerJob -RestartDelay $RestartDelaySec

try {
    while ($true) {
        if ($MaxRestarts -gt 0 -and $restartCount -ge $MaxRestarts) {
            Write-Log "max restart count reached ($MaxRestarts), watchdog exits."
            break
        }

        Kill-OldServer

        Write-Log "starting API server (restart_count=$restartCount)"

        # Required runtime credentials must be provided via environment variables.
        # Defaults are intentionally left empty: we refuse to start with placeholder
        # secrets so an unconfigured workstation cannot accidentally talk to the
        # production database. Set the variables in a .env file or in your shell
        # profile and re-run the watchdog.
        $requiredEnv = @(
            "TCM__DATABASE__HOST",
            "TCM__DATABASE__NAME",
            "TCM__DATABASE__USER",
            "TCM_DB_PASSWORD",
            "TCM_NEO4J_URI",
            "TCM_NEO4J_PASSWORD"
        )
        $missing = @()
        foreach ($name in $requiredEnv) {
            $value = [Environment]::GetEnvironmentVariable($name, "Process")
            if ([string]::IsNullOrWhiteSpace($value)) {
                $missing += $name
            }
        }
        if ($missing.Count -gt 0) {
            Write-Log ("missing required environment variables: " + ($missing -join ", "))
            Write-Log "watchdog refuses to start the API with empty credentials. Set them and re-run."
            throw "Missing required environment variables: $($missing -join ', ')"
        }

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
}
finally {
    Stop-OutboxWorkerJob
    Write-Log "=== Watchdog stop ==="
}
