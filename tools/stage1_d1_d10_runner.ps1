param(
    [ValidateSet("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10")]
    [string]$Day,
    [switch]$All,
    [switch]$DryRun,
    [switch]$ContinueOnError,
    [double]$TargetPassRate = -1,
    [string]$RepoPath = "",
    [string]$PythonExe = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    param([string]$InputPath)
    if ($InputPath -and (Test-Path $InputPath)) {
        return (Resolve-Path $InputPath).Path
    }
    return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Resolve-Python {
    param(
        [string]$Repo,
        [string]$InputPython
    )
    if ($InputPython -and (Test-Path $InputPython)) {
        return (Resolve-Path $InputPython).Path
    }

    $venvPython = Join-Path $Repo "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return (Resolve-Path $venvPython).Path
    }

    return "python"
}

function Ensure-Branch {
    param([string]$Branch)

    $exists = $false
    git show-ref --verify --quiet ("refs/heads/{0}" -f $Branch)
    if ($LASTEXITCODE -eq 0) {
        $exists = $true
    }

    if ($exists) {
        git checkout $Branch | Out-Null
    }
    else {
        git checkout -b $Branch | Out-Null
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to checkout branch: $Branch"
    }
}

function Invoke-Step {
    param(
        [hashtable]$Step,
        [string]$LogFile,
        [switch]$DryRunMode
    )

    $name = $Step.Name
    $type = $Step.Type

    $result = [ordered]@{
        name             = $name
        type             = $type
        status           = "passed"
        exit_code        = 0
        started_at       = (Get-Date).ToString("o")
        ended_at         = ""
        duration_seconds = 0.0
        command          = ""
        message          = ""
    }

    $start = Get-Date

    try {
        if ($type -eq "branch") {
            $result.command = "git checkout -b/checkout $($Step.Branch)"
            if ($DryRunMode) {
                $result.status = "skipped"
                $result.message = "DryRun: branch step skipped"
            }
            else {
                Ensure-Branch -Branch $Step.Branch
            }
        }
        elseif ($type -eq "commit") {
            $result.command = "git add -A; git commit -m ..."
            if ($DryRunMode) {
                $result.status = "skipped"
                $result.message = "DryRun: commit step skipped"
            }
            else {
                git add -A | Out-Null
                if ($LASTEXITCODE -ne 0) {
                    throw "git add failed"
                }

                git diff --cached --quiet | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    $result.status = "skipped"
                    $result.message = "No staged changes, commit skipped"
                }
                else {
                    git commit -m $Step.Message | Out-Null
                    if ($LASTEXITCODE -ne 0) {
                        throw "git commit failed"
                    }
                }
            }
        }
        elseif ($type -eq "cmd") {
            $result.command = $Step.Command
            if ($DryRunMode) {
                $result.status = "skipped"
                $result.message = "DryRun: command step skipped"
            }
            else {
                "[STEP] $name" | Tee-Object -FilePath $LogFile -Append | Out-Null
                "[CMD ] $($Step.Command)" | Tee-Object -FilePath $LogFile -Append | Out-Null
                $previousEap = $ErrorActionPreference
                $ErrorActionPreference = "Continue"
                try {
                    & powershell -NoProfile -ExecutionPolicy Bypass -Command $Step.Command 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
                }
                finally {
                    $ErrorActionPreference = $previousEap
                }
                if ($LASTEXITCODE -ne 0) {
                    $result.status = "failed"
                    $result.exit_code = $LASTEXITCODE
                    $result.message = "Command returned non-zero exit code"
                }
            }
        }
        else {
            throw "Unknown step type: $type"
        }
    }
    catch {
        $result.status = "failed"
        $result.exit_code = if ($LASTEXITCODE) { $LASTEXITCODE } else { 1 }
        $result.message = $_.Exception.Message
    }

    $end = Get-Date
    $result.ended_at = $end.ToString("o")
    $result.duration_seconds = [math]::Round((New-TimeSpan -Start $start -End $end).TotalSeconds, 2)

    return $result
}

function Get-Plan {
    param(
        [string]$DayCode,
        [string]$Py
    )

    $plans = @{}

    $plans["D1"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d1-baseline" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit baseline"; Message = "stage1 D1 baseline snapshot and gate report" }
    )

    $plans["D2"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d2-config-hardening" },
        @{ Type = "cmd"; Name = "Run logic checks unit test"; Command = "& '$Py' -m unittest tests.unit.test_logic_checks" },
        @{ Type = "cmd"; Name = "Run quality gate unit test"; Command = "& '$Py' -m unittest tests.unit.test_quality_gate" },
        @{ Type = "cmd"; Name = "Run interface consistency test"; Command = "& '$Py' tests/test_interface_consistency.py" },
        @{ Type = "cmd"; Name = "Run logic checks script"; Command = "& '$Py' tools/logic_checks.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit config hardening"; Message = "stage1 D2 config hardening and validation" }
    )

    $plans["D3"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d3-preprocessor-stability" },
        @{ Type = "cmd"; Name = "Run preprocessor quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_preprocessor_output_quality" },
        @{ Type = "cmd"; Name = "Run text processing test"; Command = "& '$Py' test_text_processing.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit preprocessor stability"; Message = "stage1 D3 preprocessor stability improvements" }
    )

    $plans["D4"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d4-entity-denoise" },
        @{ Type = "cmd"; Name = "Run entity extraction test"; Command = "& '$Py' test_entity_extraction.py" },
        @{ Type = "cmd"; Name = "Run interface consistency test"; Command = "& '$Py' tests/test_interface_consistency.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit entity denoise"; Message = "stage1 D4 entity extraction denoise and conflict handling" }
    )

    $plans["D5"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d5-semantic-constraints" },
        @{ Type = "cmd"; Name = "Run semantic simple test"; Command = "& '$Py' test_semantic_simple.py" },
        @{ Type = "cmd"; Name = "Run semantic modeling test"; Command = "& '$Py' test_semantic_modeling.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit semantic constraints"; Message = "stage1 D5 semantic relationship constraints" }
    )

    $plans["D6"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d6-reasoning-refactor" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit reasoning refactor"; Message = "stage1 D6 reasoning engine evidence-chain refactor" }
    )

    $plans["D7"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d7-output-contract" },
        @{ Type = "cmd"; Name = "Run preprocessor-output quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_preprocessor_output_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit output contract"; Message = "stage1 D7 output contract and serialization safety" }
    )

    $plans["D8"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d8-observability" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run quality feedback unit test"; Command = "& '$Py' -m unittest tests.unit.test_quality_feedback" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit observability updates"; Message = "stage1 D8 pipeline observability and failure diagnostics" }
    )

    $plans["D9"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d9-stabilization" },
        @{ Type = "cmd"; Name = "Run text processing test"; Command = "& '$Py' test_text_processing.py" },
        @{ Type = "cmd"; Name = "Run entity extraction test"; Command = "& '$Py' test_entity_extraction.py" },
        @{ Type = "cmd"; Name = "Run semantic simple test"; Command = "& '$Py' test_semantic_simple.py" },
        @{ Type = "cmd"; Name = "Run semantic modeling test"; Command = "& '$Py' test_semantic_modeling.py" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit stabilization"; Message = "stage1 D9 stabilization sprint" }
    )

    $plans["D10"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d10-release" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run quality assessment"; Command = "& '$Py' tools/quality_assessment.py --gates-report output/quality-gate.json" },
        @{ Type = "cmd"; Name = "Run continuous improvement loop"; Command = "& '$Py' tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json" },
        @{ Type = "cmd"; Name = "Run quality archive"; Command = "& '$Py' tools/quality_improvement_archive.py" },
        @{ Type = "cmd"; Name = "Run quality feedback"; Command = "& '$Py' tools/quality_feedback.py" },
        @{ Type = "commit"; Name = "Commit release artifacts"; Message = "stage1 D10 release gate, assessment, archive, feedback" }
    )

    return $plans[$DayCode]
}

function Get-RollbackTips {
    param([string]$DayCode)

    $tips = @{}
    $tips["D1"] = @(
        "git restore .",
        "git clean -fd output logs"
    )
    $tips["D2"] = @(
        "git restore config.yml run_cycle_demo.py tools/quality_gate.py",
        "& <python> tools/quality_gate.py"
    )
    $tips["D3"] = @(
        "git restore src/preprocessor/document_preprocessor.py",
        "& <python> -m unittest tests.unit.test_preprocessor_output_quality"
    )
    $tips["D4"] = @(
        "git restore src/extractors/advanced_entity_extractor.py src/data/tcm_lexicon.py",
        "& <python> test_entity_extraction.py"
    )
    $tips["D5"] = @(
        "git restore src/semantic_modeling/semantic_graph_builder.py src/semantic_modeling/tcm_relationships.py",
        "& <python> test_semantic_modeling.py"
    )
    $tips["D6"] = @(
        "git restore src/reasoning/reasoning_engine.py",
        "& <python> tests/test_full_cycle.py"
    )
    $tips["D7"] = @(
        "git restore src/output/output_generator.py run_cycle_demo.py",
        "& <python> -m unittest tests.unit.test_preprocessor_output_quality"
    )
    $tips["D8"] = @(
        "git restore run_cycle_demo.py src/cycle/iteration_cycle.py",
        "& <python> tests/test_full_cycle.py"
    )
    $tips["D9"] = @(
        "git restore src/preprocessor/document_preprocessor.py src/extractors/advanced_entity_extractor.py src/semantic_modeling/semantic_graph_builder.py src/reasoning/reasoning_engine.py src/output/output_generator.py run_cycle_demo.py",
        "& <python> tools/quality_gate.py"
    )
    $tips["D10"] = @(
        "git restore .",
        "& <python> tools/quality_gate.py"
    )

    return $tips[$DayCode]
}

function Get-StrictRollbackFlow {
    param(
        [string]$DayCode,
        [string]$Python,
        [string]$LogFile,
        [string]$ReportFile
    )

    $dayTips = Get-RollbackTips -DayCode $DayCode
    $dayTips = @($dayTips | ForEach-Object { $_ -replace "<python>", $Python })

    $strictFlow = @(
        "git status --short",
        "git stash push -u -m 'stage1-${DayCode}-failed-run'",
        "git switch -",
        ("git branch -D stage1-{0}-*  # manually keep if needed" -f ($DayCode.ToLower())),
        ("& '{0}' tools/quality_gate.py" -f $Python),
        ("Inspect log: {0}" -f $LogFile),
        ("Inspect report: {0}" -f $ReportFile)
    )

    $strictFlow += "Day-specific rollback commands:"
    $strictFlow += $dayTips
    return $strictFlow
}

function Write-Summary {
    param(
        [string]$ReportPath,
        [hashtable]$Summary
    )
    $Summary | ConvertTo-Json -Depth 8 | Set-Content -Path $ReportPath -Encoding UTF8
}

# ---- Main ----

$repo = Resolve-RepoRoot -InputPath $RepoPath
$python = Resolve-Python -Repo $repo -InputPython $PythonExe

if (-not $Day -and -not $All) {
    throw "Please provide -Day D1..D10 or -All"
}
if ($Day -and $All) {
    throw "Use either -Day or -All, not both"
}

if ($TargetPassRate -ne -1 -and ($TargetPassRate -lt 0 -or $TargetPassRate -gt 100)) {
    throw "TargetPassRate must be -1 (disabled) or between 0 and 100"
}

$targetPassRateEnabled = $TargetPassRate -ne -1

Set-Location $repo

$runDays = if ($All) {
    @("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10")
}
else {
    @($Day)
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$logDir = Join-Path $repo "logs\stage1"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

$globalSummary = [ordered]@{
    started_at               = (Get-Date).ToString("o")
    repo                     = $repo
    python                   = $python
    dry_run                  = [bool]$DryRun
    continue_on_error        = [bool]$ContinueOnError
    target_pass_rate_percent = if ($targetPassRateEnabled) { $TargetPassRate } else { $null }
    days                     = @()
}

$abortedByThreshold = $false
$abortReason = ""

foreach ($d in $runDays) {
    $logFile = Join-Path $logDir ("stage1_{0}_{1}.log" -f $d, $stamp)
    $reportFile = Join-Path $logDir ("stage1_{0}_{1}.json" -f $d, $stamp)

    $plan = Get-Plan -DayCode $d -Py $python
    if (-not $plan) {
        throw "No plan found for $d"
    }

    $results = @()
    $failed = $false

    Write-Host ""
    Write-Host "=== Running $d ===" -ForegroundColor Cyan
    Write-Host "Repo   : $repo"
    Write-Host "Python : $python"
    Write-Host "Log    : $logFile"

    foreach ($step in $plan) {
        $r = Invoke-Step -Step $step -LogFile $logFile -DryRunMode:$DryRun
        $results += $r

        if ($r.status -eq "failed") {
            $failed = $true
            Write-Host ("[FAIL] {0} :: {1}" -f $r.name, $r.message) -ForegroundColor Red
            if (-not $ContinueOnError) {
                break
            }
        }
        elseif ($r.status -eq "passed") {
            Write-Host ("[PASS] {0}" -f $r.name) -ForegroundColor Green
        }
        else {
            Write-Host ("[SKIP] {0} :: {1}" -f $r.name, $r.message) -ForegroundColor Yellow
        }
    }

    $total = ($results | Measure-Object).Count
    $passed = ($results | Where-Object { $_.status -eq "passed" } | Measure-Object).Count
    $skipped = ($results | Where-Object { $_.status -eq "skipped" } | Measure-Object).Count
    $failedCount = ($results | Where-Object { $_.status -eq "failed" } | Measure-Object).Count
    $passRate = if ($total -gt 0) { [math]::Round(($passed * 100.0) / $total, 2) } else { 0.0 }

    $rollbackTips = Get-RollbackTips -DayCode $d
    $rollbackTips = @($rollbackTips | ForEach-Object { $_ -replace "<python>", $python })
    $thresholdBreached = $false
    if ($targetPassRateEnabled -and $passRate -lt $TargetPassRate) {
        $thresholdBreached = $true
        $failed = $true
    }

    $strictRollbackFlow = if ($thresholdBreached) {
        Get-StrictRollbackFlow -DayCode $d -Python $python -LogFile $logFile -ReportFile $reportFile
    }
    else {
        @()
    }

    $daySummary = [ordered]@{
        day                      = $d
        started_at               = ($results | Select-Object -First 1).started_at
        ended_at                 = (Get-Date).ToString("o")
        total_steps              = $total
        passed_steps             = $passed
        skipped_steps            = $skipped
        failed_steps             = $failedCount
        pass_rate_percent        = $passRate
        target_pass_rate_percent = if ($targetPassRateEnabled) { $TargetPassRate } else { $null }
        threshold_breached       = $thresholdBreached
        failed                   = $failed
        log_file                 = $logFile
        rollback_tips            = $rollbackTips
        strict_rollback_flow     = $strictRollbackFlow
        steps                    = $results
    }

    Write-Summary -ReportPath $reportFile -Summary $daySummary
    $daySummary["report_file"] = $reportFile

    $globalSummary.days += $daySummary

    Write-Host ("Summary {0}: pass_rate={1}% (pass={2}, fail={3}, skip={4})" -f $d, $passRate, $passed, $failedCount, $skipped)
    Write-Host ("Report: {0}" -f $reportFile)

    if ($thresholdBreached) {
        Write-Host ("Target pass rate breached on {0}: actual={1}% target={2}%" -f $d, $passRate, $TargetPassRate) -ForegroundColor Red
        Write-Host "Strict rollback flow:" -ForegroundColor Red
        foreach ($stepText in $strictRollbackFlow) {
            Write-Host ("  - {0}" -f $stepText) -ForegroundColor Red
        }
        $abortedByThreshold = $true
        $abortReason = "Pass rate below target on $d"
        break
    }

    if ($failed) {
        Write-Host "Rollback tips:" -ForegroundColor Yellow
        foreach ($tip in $rollbackTips) {
            Write-Host ("  - {0}" -f $tip) -ForegroundColor Yellow
        }

        if (-not $ContinueOnError -and $All) {
            Write-Host "Stop due to failure and -ContinueOnError not set." -ForegroundColor Red
            break
        }
    }
}

$globalSummary["ended_at"] = (Get-Date).ToString("o")
$globalSummary["aborted_by_threshold"] = $abortedByThreshold
$globalSummary["abort_reason"] = $abortReason
$globalReport = Join-Path $logDir ("stage1_all_{0}.json" -f $stamp)
Write-Summary -ReportPath $globalReport -Summary $globalSummary

Write-Host ""
Write-Host ("Global report: {0}" -f $globalReport) -ForegroundColor Cyan
if ($abortedByThreshold) {
    Write-Host ("Aborted: {0}" -f $abortReason) -ForegroundColor Red
    exit 2
}
Write-Host "Done."
