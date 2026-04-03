param(
    [ValidateSet("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18", "D19", "D20", "D21", "D22", "D23", "D24", "D25", "D26", "D27", "D28", "D29", "D30", "D31", "D32", "D33", "D34", "D35", "D36", "D37", "D38", "D39", "D40", "D41", "D42", "D43", "D44", "D45", "D46", "D47", "D48", "D49", "D50", "D51", "D52", "D53", "D54", "D55", "D56")]
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

function Convert-YamlScalarValue {
    param([string]$Text)

    if ($null -eq $Text) {
        return $null
    }

    $value = $Text.Trim()
    if ($value -match '^(.*?)(\s+#.*)?$') {
        $value = $Matches[1].Trim()
    }

    if ($value.Length -ge 2) {
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            return $value.Substring(1, $value.Length - 2)
        }
    }

    if ($value -match '^(true|false)$') {
        return [System.Convert]::ToBoolean($value)
    }
    if ($value -match '^-?\d+$') {
        return [int]$value
    }
    if ($value -match '^-?\d+\.\d+$') {
        return [double]$value
    }

    return $value
}

function Get-Stage1RunnerGovernanceConfig {
    param([string]$ConfigPath)

    $config = [ordered]@{
        enable_phase_tracking     = $true
        persist_failed_operations = $true
        minimum_stable_pass_rate  = 85.0
        export_contract_version   = "d67.v1"
    }

    if (-not (Test-Path $ConfigPath)) {
        return $config
    }

    $lines = Get-Content -Path $ConfigPath -Encoding UTF8
    $inGovernance = $false
    $inSection = $false

    foreach ($line in $lines) {
        if (-not $inGovernance) {
            if ($line -match '^governance:\s*$') {
                $inGovernance = $true
            }
            continue
        }

        if (-not $inSection) {
            if ($line -match '^  stage1_runner:\s*$') {
                $inSection = $true
            }
            elseif ($line -match '^\S') {
                break
            }
            continue
        }

        if ($line -match '^  \S') {
            break
        }

        if ($line -match '^    ([A-Za-z0-9_]+):\s*(.*?)\s*$') {
            $config[$Matches[1]] = Convert-YamlScalarValue -Text $Matches[2]
        }
    }

    return $config
}

function New-RunnerMetadata {
    return [ordered]@{
        phase_history        = @()
        phase_timings        = [ordered]@{}
        completed_phases     = @()
        failed_phase         = $null
        final_status         = "completed"
        last_completed_phase = $null
    }
}

function Start-RunnerPhase {
    param(
        $Metadata,
        [string]$PhaseName
    )

    $timestamp = (Get-Date).ToString("o")
    $Metadata.phase_history += [ordered]@{
        phase     = $PhaseName
        event     = "started"
        timestamp = $timestamp
    }
    $Metadata.phase_timings[$PhaseName] = [ordered]@{
        started_at = $timestamp
    }
}

function Complete-RunnerPhase {
    param(
        $Metadata,
        [string]$PhaseName
    )

    $timestamp = (Get-Date).ToString("o")
    $Metadata.phase_history += [ordered]@{
        phase     = $PhaseName
        event     = "completed"
        timestamp = $timestamp
    }

    if (-not $Metadata.phase_timings.Contains($PhaseName)) {
        $Metadata.phase_timings[$PhaseName] = [ordered]@{}
    }

    $Metadata.phase_timings[$PhaseName]["completed_at"] = $timestamp
    $Metadata.completed_phases += $PhaseName
    $Metadata.last_completed_phase = $PhaseName
}

function Add-FailedOperation {
    param(
        [System.Collections.ArrayList]$FailedOperations,
        [string]$Operation,
        [string]$Error,
        [object]$Details,
        [double]$DurationSeconds = 0.0
    )

    if ($null -eq $FailedOperations) {
        return
    }

    [void]$FailedOperations.Add([ordered]@{
            operation        = $Operation
            error            = $Error
            details          = if ($null -ne $Details) { $Details } else { [ordered]@{} }
            timestamp        = (Get-Date).ToString("o")
            duration_seconds = [math]::Round($DurationSeconds, 2)
        })
}

function Fail-RunnerPhase {
    param(
        $Metadata,
        [System.Collections.ArrayList]$FailedOperations,
        [string]$PhaseName,
        [string]$Error,
        [object]$Details,
        [double]$DurationSeconds = 0.0
    )

    $Metadata.phase_history += [ordered]@{
        phase     = $PhaseName
        event     = "failed"
        timestamp = (Get-Date).ToString("o")
    }
    $Metadata.failed_phase = $PhaseName
    $Metadata.final_status = "failed"
    Add-FailedOperation -FailedOperations $FailedOperations -Operation $PhaseName -Error $Error -Details $Details -DurationSeconds $DurationSeconds
}

function Get-DayAnalysisSummary {
    param(
        [array]$Steps,
        [double]$PassRate,
        [int]$RollbackTipCount,
        [int]$StrictRollbackStepCount,
        [bool]$ThresholdBreached
    )

    $commandSteps = @($Steps | Where-Object { $_.type -eq "cmd" }).Count
    $branchSteps = @($Steps | Where-Object { $_.type -eq "branch" }).Count
    $commitSteps = @($Steps | Where-Object { $_.type -eq "commit" }).Count
    $failedSteps = @($Steps | Where-Object { $_.status -eq "failed" }).Count
    $passRateBand = if ($PassRate -ge 100) { "perfect" } elseif ($PassRate -ge 85) { "stable" } elseif ($PassRate -ge 60) { "watch" } else { "critical" }

    return [ordered]@{
        command_step_count         = $commandSteps
        branch_step_count          = $branchSteps
        commit_step_count          = $commitSteps
        actionable_failure_count   = $failedSteps
        rollback_tip_count         = $RollbackTipCount
        strict_rollback_step_count = $StrictRollbackStepCount
        threshold_breached         = $ThresholdBreached
        pass_rate_band             = $passRateBand
    }
}

function Get-GlobalAnalysisSummary {
    param(
        [array]$Days,
        [bool]$AbortedByThreshold
    )

    $dayCount = @($Days).Count
    $failedDays = @($Days | Where-Object { $_["failed"] }).Count
    $thresholdDays = @($Days | Where-Object { $_["threshold_breached"] }).Count
    $passRates = @($Days | ForEach-Object { [double]($_["pass_rate_percent"]) })
    $averagePassRate = if ($passRates.Count -gt 0) {
        [math]::Round((($passRates | Measure-Object -Average).Average), 2)
    }
    else {
        0.0
    }

    return [ordered]@{
        day_count                    = $dayCount
        failed_day_count             = $failedDays
        threshold_breached_day_count = $thresholdDays
        average_pass_rate_percent    = $averagePassRate
        aborted_by_threshold         = $AbortedByThreshold
        failed_day_codes             = @($Days | Where-Object { $_["failed"] } | ForEach-Object { $_["day"] })
    }
}

function New-ReportMetadata {
    param(
        $GovernanceConfig,
        $Metadata,
        [array]$FailedOperations,
        [string]$ResultSchema
    )

    return [ordered]@{
        contract_version       = $GovernanceConfig.export_contract_version
        generated_at           = (Get-Date).ToString("o")
        result_schema          = $ResultSchema
        failed_operation_count = @($FailedOperations).Count
        final_status           = $Metadata.final_status
        last_completed_phase   = $Metadata.last_completed_phase
    }
}

function Get-InventoryTrendGovernanceAlerts {
    param([string]$Repo)

    $archiveLatest = Join-Path $Repo "output\quality-improvement-archive-latest.json"
    if (-not (Test-Path $archiveLatest)) {
        return @()
    }

    try {
        $payload = Get-Content -Path $archiveLatest -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        return @()
    }

    if ($null -eq $payload -or $null -eq $payload.inventory_trend) {
        return @()
    }

    $inventoryTrend = $payload.inventory_trend
    if ($inventoryTrend.status -ne "regressing") {
        return @()
    }

    $inventorySummary = if ($null -ne $payload.inventory_summary) { $payload.inventory_summary } else { $null }
    return @(
        [ordered]@{
            alert_type                      = "inventory_trend_regressing"
            severity                        = "warning"
            source_report                   = $archiveLatest
            message                         = "Inventory trend is regressing; expose governance follow-up in runner summary."
            inventory_trend_status          = $inventoryTrend.status
            history_points                  = $inventoryTrend.history_points
            missing_contract_delta          = $inventoryTrend.missing_contract_delta
            uncategorized_root_script_delta = $inventoryTrend.uncategorized_root_script_delta
            recommended_next_target         = if ($null -ne $inventorySummary) { $inventorySummary.recommended_next_target } else { $null }
        }
    )
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
                Invoke-Expression $Step.Command 2>&1 | Tee-Object -FilePath $LogFile -Append | Out-Null
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
        @{ Type = "cmd"; Name = "Run validation tests"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
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

    $plans["D11"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d11-validation" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run validation tests"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit validation"; Message = "stage1 D11 validation" }
    )

    $plans["D12"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d12-optimization" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run optimization regression tests"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit optimization"; Message = "stage1 D12 optimization" }
    )

    $plans["D13"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d13-system-insights" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run system insight regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit system insights"; Message = "stage1 D13 system insights" }
    )

    $plans["D14"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d14-orchestration" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run orchestration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit orchestration"; Message = "stage1 D14 orchestration" }
    )

    $plans["D15"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d15-export-contract" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run export contract regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit export contract"; Message = "stage1 D15 export contract" }
    )

    $plans["D16"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d16-module-alignment" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run module alignment regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit module alignment"; Message = "stage1 D16 module alignment" }
    )

    $plans["D17"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d17-test-iteration" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run test iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit test iteration"; Message = "stage1 D17 test iteration" }
    )

    $plans["D18"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d18-fixing-stage" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run fixing stage classification unit test"; Command = "& '$Py' -m unittest tests.unit.test_fixing_stage_classification" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run fixing stage regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit fixing stage alignment"; Message = "stage1 D18 fixing stage alignment" }
    )

    $plans["D19"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d19-research-pipeline" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap" },
        @{ Type = "cmd"; Name = "Run cycle quality unit test"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run research pipeline regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit research pipeline alignment"; Message = "stage1 D19 research pipeline alignment" }
    )

    $plans["D20"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d20-theoretical-framework" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run theoretical framework regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit theoretical framework alignment"; Message = "stage1 D20 theoretical framework alignment" }
    )

    $plans["D21"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d21-algorithm-optimizer" },
        @{ Type = "cmd"; Name = "Run optimization feature tests"; Command = "& '$Py' -m unittest tests.unit.test_learning_optimization_features" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run algorithm optimizer regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit algorithm optimizer alignment"; Message = "stage1 D21 algorithm optimizer alignment" }
    )

    $plans["D22"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d22-system-architecture" },
        @{ Type = "cmd"; Name = "Run architecture cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run optimization feature tests"; Command = "& '$Py' -m unittest tests.unit.test_learning_optimization_features" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run system architecture regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit system architecture alignment"; Message = "stage1 D22 system architecture alignment" }
    )

    $plans["D23"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d23-automated-tester" },
        @{ Type = "cmd"; Name = "Run automated tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_automated_tester_quality" },
        @{ Type = "cmd"; Name = "Run architecture cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run optimization feature tests"; Command = "& '$Py' -m unittest tests.unit.test_learning_optimization_features" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run automated tester regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit automated tester alignment"; Message = "stage1 D23 automated tester alignment" }
    )

    $plans["D24"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d24-integration-tester" },
        @{ Type = "cmd"; Name = "Run integration tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_integration_tester_quality" },
        @{ Type = "cmd"; Name = "Run automated tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_automated_tester_quality" },
        @{ Type = "cmd"; Name = "Run architecture cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run optimization feature tests"; Command = "& '$Py' -m unittest tests.unit.test_learning_optimization_features" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run integration tester regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit integration tester alignment"; Message = "stage1 D24 integration tester alignment" }
    )

    $plans["D25"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d25-algorithm-optimizer-refresh" },
        @{ Type = "cmd"; Name = "Run optimization feature tests"; Command = "& '$Py' -m unittest tests.unit.test_learning_optimization_features" },
        @{ Type = "cmd"; Name = "Run integration tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_integration_tester_quality" },
        @{ Type = "cmd"; Name = "Run automated tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_automated_tester_quality" },
        @{ Type = "cmd"; Name = "Run architecture cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run cycle system unittest"; Command = "& '$Py' -m unittest tests.test_cycle_system" },
        @{ Type = "cmd"; Name = "Run full cycle test"; Command = "& '$Py' tests/test_full_cycle.py" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run optimizer regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit algorithm optimizer refresh"; Message = "stage1 D25 algorithm optimizer refresh" }
    )

    $plans["D26"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d26-research-pipeline-refresh" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline observe tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_observe" },
        @{ Type = "cmd"; Name = "Run research pipeline ingestion tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_ingestion" },
        @{ Type = "cmd"; Name = "Run research pipeline literature tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_literature" },
        @{ Type = "cmd"; Name = "Run research pipeline clinical gap tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_clinical_gap" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run pipeline regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit research pipeline refresh"; Message = "stage1 D26 research pipeline refresh" }
    )

    $plans["D27"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d27-theoretical-framework-refresh" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run theoretical framework regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit theoretical framework refresh"; Message = "stage1 D27 theoretical framework refresh" }
    )

    $plans["D28"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d28-system-iteration-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run system iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit system iteration refresh"; Message = "stage1 D28 system iteration refresh" }
    )

    $plans["D29"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d29-iteration-cycle-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run iteration cycle regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit iteration cycle refresh"; Message = "stage1 D29 iteration cycle refresh" }
    )

    $plans["D30"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d30-fixing-stage-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality tests.unit.test_fixing_stage_classification" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run fixing stage regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit fixing stage refresh"; Message = "stage1 D30 fixing stage refresh" }
    )

    $plans["D31"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d31-module-iteration-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run module iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit module iteration refresh"; Message = "stage1 D31 module iteration refresh" }
    )

    $plans["D32"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d32-system-iteration-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run system iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit system iteration refresh"; Message = "stage1 D32 system iteration refresh" }
    )

    $plans["D33"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d33-test-driven-iteration-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run test-driven iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit test-driven iteration refresh"; Message = "stage1 D33 test-driven iteration refresh" }
    )

    $plans["D34"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d34-system-architecture-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run architecture regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings" },
        @{ Type = "commit"; Name = "Commit system architecture refresh"; Message = "stage1 D34 system architecture refresh" }
    )

    $plans["D35"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d35-automated-tester-refresh" },
        @{ Type = "cmd"; Name = "Run automated tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_automated_tester_quality" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run automated tester regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_automated_tester_quality.py" },
        @{ Type = "commit"; Name = "Commit automated tester refresh"; Message = "stage1 D35 automated tester refresh" }
    )

    $plans["D36"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d36-integration-tester-refresh" },
        @{ Type = "cmd"; Name = "Run integration tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_integration_tester_quality" },
        @{ Type = "cmd"; Name = "Run automated tester quality tests"; Command = "& '$Py' -m unittest tests.unit.test_automated_tester_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run integration tester regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_integration_tester_quality.py" },
        @{ Type = "commit"; Name = "Commit integration tester refresh"; Message = "stage1 D36 integration tester refresh" }
    )

    $plans["D37"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d37-theoretical-framework-refresh" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run theoretical framework regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/test_theoretical_framework_quality.py" },
        @{ Type = "commit"; Name = "Commit theoretical framework refresh"; Message = "stage1 D37 theoretical framework refresh" }
    )

    $plans["D38"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d38-algorithm-optimizer-refresh" },
        @{ Type = "cmd"; Name = "Run optimization quality tests"; Command = "& '$Py' -m unittest tests.unit.test_learning_optimization_features" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run optimizer regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_learning_optimization_features.py" },
        @{ Type = "commit"; Name = "Commit algorithm optimizer refresh"; Message = "stage1 D38 algorithm optimizer refresh" }
    )

    $plans["D39"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d39-research-pipeline-refresh" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap" },
        @{ Type = "cmd"; Name = "Run theoretical framework quality tests"; Command = "& '$Py' -m unittest tests.test_theoretical_framework_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run research pipeline regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/test_research_pipeline_quality.py" },
        @{ Type = "commit"; Name = "Commit research pipeline refresh"; Message = "stage1 D39 research pipeline refresh" }
    )

    $plans["D40"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d40-iteration-cycle-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run iteration cycle regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py" },
        @{ Type = "commit"; Name = "Commit iteration cycle D40 refresh"; Message = "stage1 D40 iteration cycle refresh" }
    )

    $plans["D41"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d41-fixing-stage-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality tests.unit.test_fixing_stage_classification" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run fixing stage regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py tests/unit/test_fixing_stage_classification.py" },
        @{ Type = "commit"; Name = "Commit fixing stage D41 refresh"; Message = "stage1 D41 fixing stage refresh" }
    )

    $plans["D42"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d42-system-iteration-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run system iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py" },
        @{ Type = "commit"; Name = "Commit system iteration D42 refresh"; Message = "stage1 D42 system iteration refresh" }
    )

    $plans["D43"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d43-module-iteration-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run module iteration regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py" },
        @{ Type = "commit"; Name = "Commit module iteration D43 refresh"; Message = "stage1 D43 module iteration refresh" }
    )

    $plans["D44"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d44-research-pipeline-refresh" },
        @{ Type = "cmd"; Name = "Run research pipeline quality tests"; Command = "& '$Py' -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run research pipeline regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/test_research_pipeline_quality.py" },
        @{ Type = "commit"; Name = "Commit research pipeline D44 refresh"; Message = "stage1 D44 research pipeline refresh" }
    )

    $plans["D45"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d45-system-architecture-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run architecture regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py" },
        @{ Type = "commit"; Name = "Commit system architecture D45 refresh"; Message = "stage1 D45 system architecture refresh" }
    )

    $plans["D46"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d46-module-base-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run module base regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py" },
        @{ Type = "commit"; Name = "Commit module base D46 refresh"; Message = "stage1 D46 module base refresh" }
    )

    $plans["D47"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d47-module-interface-refresh" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run module interface regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_architecture_cycle_quality.py" },
        @{ Type = "commit"; Name = "Commit module interface D47 refresh"; Message = "stage1 D47 module interface refresh" }
    )

    $plans["D48"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d48-interface-consistency-refresh" },
        @{ Type = "cmd"; Name = "Run interface consistency tests"; Command = "& '$Py' -m unittest tests.test_interface_consistency" },
        @{ Type = "cmd"; Name = "Run architecture and cycle quality tests"; Command = "& '$Py' -m unittest tests.unit.test_architecture_cycle_quality" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run interface consistency regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/test_interface_consistency.py" },
        @{ Type = "commit"; Name = "Commit interface consistency D48 refresh"; Message = "stage1 D48 interface consistency refresh" }
    )

    $plans["D49"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d49-quality-assessment-refresh" },
        @{ Type = "cmd"; Name = "Run quality assessment unit tests"; Command = "& '$Py' -m unittest tests.unit.test_quality_assessment tests.unit.test_quality_gate" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run quality assessment regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_quality_assessment.py tests/unit/test_quality_gate.py" },
        @{ Type = "commit"; Name = "Commit quality assessment D49 refresh"; Message = "stage1 D49 quality assessment refresh" }
    )

    $plans["D50"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d50-continuous-improvement-refresh" },
        @{ Type = "cmd"; Name = "Run continuous improvement unit tests"; Command = "& '$Py' -m unittest tests.unit.test_continuous_improvement_loop tests.unit.test_quality_gate" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run continuous improvement regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_continuous_improvement_loop.py tests/unit/test_quality_gate.py" },
        @{ Type = "commit"; Name = "Commit continuous improvement D50 refresh"; Message = "stage1 D50 continuous improvement refresh" }
    )

    $plans["D51"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d51-quality-archive-refresh" },
        @{ Type = "cmd"; Name = "Run quality archive unit tests"; Command = "& '$Py' -m unittest tests.unit.test_quality_improvement_archive tests.unit.test_quality_gate" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run quality archive regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_quality_improvement_archive.py tests/unit/test_quality_gate.py" },
        @{ Type = "commit"; Name = "Commit quality archive D51 refresh"; Message = "stage1 D51 quality archive refresh" }
    )

    $plans["D52"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d52-quality-feedback-refresh" },
        @{ Type = "cmd"; Name = "Run quality feedback unit tests"; Command = "& '$Py' -m unittest tests.unit.test_quality_feedback tests.unit.test_quality_gate" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "cmd"; Name = "Run quality feedback regressions"; Command = "& '$Py' -m pytest --maxfail=5 --disable-warnings tests/unit/test_quality_feedback.py tests/unit/test_quality_gate.py" },
        @{ Type = "commit"; Name = "Commit quality feedback D52 refresh"; Message = "stage1 D52 quality feedback refresh" }
    )

    $plans["D53"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d53-quality-chain-doc-refresh" },
        @{ Type = "cmd"; Name = "Review governance chain doc"; Command = ('& ''{0}'' -c "from pathlib import Path; print(Path(''''docs/quality-governance/refactor-quality-templates.md'''').read_text(encoding=''''utf-8'''')[:2000])"' -f $Py) },
        @{ Type = "commit"; Name = "Commit quality chain D53 refresh"; Message = "stage1 D53 quality chain doc refresh" }
    )

    $plans["D54"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d54-quality-consumer-inventory" },
        @{ Type = "cmd"; Name = "Run quality consumer inventory unit tests"; Command = "& '$Py' -m unittest tests.unit.test_quality_consumer_inventory" },
        @{ Type = "cmd"; Name = "Run quality consumer inventory"; Command = "& '$Py' tools/quality_consumer_inventory.py --root . --config config.yml" },
        @{ Type = "cmd"; Name = "Run integrated research test"; Command = "& '$Py' test_integrated_research.py" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit quality consumer inventory D54 refresh"; Message = "stage1 D54 quality consumer inventory refresh" }
    )

    $plans["D55"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d55-stage1-runner-contract" },
        @{ Type = "cmd"; Name = "Run stage1 runner contract unit tests"; Command = "& '$Py' -m unittest tests.unit.test_stage1_runner_contract" },
        @{ Type = "cmd"; Name = "Run stage1 runner dry-run contract smoke"; Command = "powershell -NoProfile -ExecutionPolicy Bypass -File tools/stage1_d1_d10_runner.ps1 -Day D1 -DryRun -PythonExe '$Py'" },
        @{ Type = "cmd"; Name = "Run quality consumer inventory"; Command = "& '$Py' tools/quality_consumer_inventory.py --root . --config config.yml" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit stage1 runner D55 refresh"; Message = "stage1 D55 stage1 runner contract refresh" }
    )

    $plans["D56"] = @(
        @{ Type = "branch"; Name = "Create or switch branch"; Branch = "stage1-d56-stage2-runner-contract" },
        @{ Type = "cmd"; Name = "Run stage2 runner contract unit tests"; Command = "& '$Py' -m unittest tests.unit.test_stage2_runner_contract" },
        @{ Type = "cmd"; Name = "Run stage2 runner dry-run contract smoke"; Command = "powershell -NoProfile -ExecutionPolicy Bypass -File tools/stage2_s2_1_s2_6_runner.ps1 -Stage S2-1 -DryRun -PythonExe '$Py'" },
        @{ Type = "cmd"; Name = "Run quality consumer inventory"; Command = "& '$Py' tools/quality_consumer_inventory.py --root . --config config.yml" },
        @{ Type = "cmd"; Name = "Run quality gate"; Command = "& '$Py' tools/quality_gate.py" },
        @{ Type = "commit"; Name = "Commit stage2 runner D56 refresh"; Message = "stage1 D56 stage2 runner contract refresh" }
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
    $tips["D11"] = @(
        "git restore .",
        "& <python> tools/quality_gate.py"
    )
    $tips["D12"] = @(
        "git restore src/cycle/iteration_cycle.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D13"] = @(
        "git restore src/cycle/system_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D14"] = @(
        "git restore src/cycle/iteration_cycle.py src/cycle/system_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D15"] = @(
        "git restore src/cycle/iteration_cycle.py src/cycle/system_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D16"] = @(
        "git restore src/cycle/module_iteration.py src/cycle/iteration_cycle.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D17"] = @(
        "git restore src/cycle/test_driven_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D18"] = @(
        "git restore src/cycle/fixing_stage.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py tests/unit/test_fixing_stage_classification.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality tests.unit.test_fixing_stage_classification"
    )
    $tips["D19"] = @(
        "git restore src/research/research_pipeline.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_research_pipeline_quality.py",
        "& <python> -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap"
    )
    $tips["D20"] = @(
        "git restore src/research/theoretical_framework.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_theoretical_framework_quality.py",
        "& <python> -m unittest tests.test_theoretical_framework_quality"
    )
    $tips["D21"] = @(
        "git restore src/core/algorithm_optimizer.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_learning_optimization_features.py",
        "& <python> -m unittest tests.unit.test_learning_optimization_features"
    )
    $tips["D22"] = @(
        "git restore src/core/architecture.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D23"] = @(
        "git restore src/test/automated_tester.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_automated_tester_quality.py",
        "& <python> -m unittest tests.unit.test_automated_tester_quality"
    )
    $tips["D24"] = @(
        "git restore src/test/integration_tester.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_integration_tester_quality.py",
        "& <python> -m unittest tests.unit.test_integration_tester_quality"
    )
    $tips["D25"] = @(
        "git restore src/core/algorithm_optimizer.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_learning_optimization_features.py",
        "& <python> -m unittest tests.unit.test_learning_optimization_features"
    )
    $tips["D26"] = @(
        "git restore src/research/research_pipeline.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_research_pipeline_quality.py",
        "& <python> -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap"
    )
    $tips["D27"] = @(
        "git restore src/research/theoretical_framework.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_theoretical_framework_quality.py",
        "& <python> -m unittest tests.test_theoretical_framework_quality"
    )
    $tips["D28"] = @(
        "git restore src/cycle/system_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D29"] = @(
        "git restore src/cycle/iteration_cycle.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D30"] = @(
        "git restore src/cycle/fixing_stage.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality tests.unit.test_fixing_stage_classification"
    )
    $tips["D31"] = @(
        "git restore src/cycle/module_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D32"] = @(
        "git restore src/cycle/system_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D33"] = @(
        "git restore src/cycle/test_driven_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D34"] = @(
        "git restore src/core/architecture.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D35"] = @(
        "git restore src/test/automated_tester.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_automated_tester_quality.py",
        "& <python> -m unittest tests.unit.test_automated_tester_quality"
    )
    $tips["D36"] = @(
        "git restore src/test/integration_tester.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_integration_tester_quality.py",
        "& <python> -m unittest tests.unit.test_integration_tester_quality"
    )
    $tips["D37"] = @(
        "git restore src/research/theoretical_framework.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_theoretical_framework_quality.py",
        "& <python> -m unittest tests.test_theoretical_framework_quality"
    )
    $tips["D38"] = @(
        "git restore src/core/algorithm_optimizer.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_learning_optimization_features.py",
        "& <python> -m unittest tests.unit.test_learning_optimization_features"
    )
    $tips["D39"] = @(
        "git restore src/research/research_pipeline.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_research_pipeline_quality.py",
        "& <python> -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap"
    )

    $tips["D40"] = @(
        "git restore src/cycle/iteration_cycle.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )

    $tips["D41"] = @(
        "git restore src/cycle/fixing_stage.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py tests/unit/test_fixing_stage_classification.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality tests.unit.test_fixing_stage_classification"
    )
    $tips["D42"] = @(
        "git restore src/cycle/system_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D43"] = @(
        "git restore src/cycle/module_iteration.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D44"] = @(
        "git restore src/research/research_pipeline.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/test_research_pipeline_quality.py",
        "& <python> -m unittest tests.test_research_pipeline_quality tests.test_research_pipeline_observe tests.test_research_pipeline_ingestion tests.test_research_pipeline_literature tests.test_research_pipeline_clinical_gap"
    )
    $tips["D45"] = @(
        "git restore src/core/architecture.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D46"] = @(
        "git restore src/core/module_base.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D47"] = @(
        "git restore src/core/module_interface.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md tests/unit/test_architecture_cycle_quality.py",
        "& <python> -m unittest tests.unit.test_architecture_cycle_quality"
    )
    $tips["D48"] = @(
        "git restore tests/test_interface_consistency.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.test_interface_consistency"
    )
    $tips["D49"] = @(
        "git restore tools/quality_assessment.py tools/quality_gate.py tests/unit/test_quality_assessment.py tests/unit/test_quality_gate.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_quality_assessment tests.unit.test_quality_gate"
    )
    $tips["D50"] = @(
        "git restore tools/continuous_improvement_loop.py tools/quality_gate.py tests/unit/test_continuous_improvement_loop.py tests/unit/test_quality_gate.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_continuous_improvement_loop tests.unit.test_quality_gate"
    )
    $tips["D51"] = @(
        "git restore tools/quality_improvement_archive.py tools/quality_gate.py tests/unit/test_quality_improvement_archive.py tests/unit/test_quality_gate.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_quality_improvement_archive tests.unit.test_quality_gate"
    )
    $tips["D52"] = @(
        "git restore tools/quality_feedback.py tools/quality_gate.py tests/unit/test_quality_feedback.py tests/unit/test_quality_gate.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_quality_feedback tests.unit.test_quality_gate"
    )
    $tips["D53"] = @(
        "git restore docs/quality-governance/refactor-quality-templates.md tools/stage1_d1_d10_runner.ps1",
        "git diff -- docs/quality-governance/refactor-quality-templates.md"
    )
    $tips["D54"] = @(
        "git restore tools/quality_consumer_inventory.py tests/unit/test_quality_consumer_inventory.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_quality_consumer_inventory"
    )
    $tips["D55"] = @(
        "git restore tools/stage1_d1_d10_runner.ps1 tests/unit/test_stage1_runner_contract.py config.yml docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_stage1_runner_contract"
    )
    $tips["D56"] = @(
        "git restore tools/stage2_s2_1_s2_6_runner.ps1 tests/unit/test_stage2_runner_contract.py config.yml tools/stage1_d1_d10_runner.ps1 docs/quality-governance/refactor-quality-templates.md",
        "& <python> -m unittest tests.unit.test_stage2_runner_contract"
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
        $Summary,
        [string]$ResultSchema,
        $GovernanceConfig,
        [string]$ExportPhaseName
    )

    Start-RunnerPhase -Metadata $Summary.metadata -PhaseName $ExportPhaseName
    Complete-RunnerPhase -Metadata $Summary.metadata -PhaseName $ExportPhaseName
    $Summary.report_metadata = New-ReportMetadata -GovernanceConfig $GovernanceConfig -Metadata $Summary.metadata -FailedOperations $Summary.failed_operations -ResultSchema $ResultSchema
    $Summary | ConvertTo-Json -Depth 12 | Set-Content -Path $ReportPath -Encoding UTF8
    return $Summary
}

# ---- Main ----

$repo = Resolve-RepoRoot -InputPath $RepoPath
$python = Resolve-Python -Repo $repo -InputPython $PythonExe
$configPath = Join-Path $repo "config.yml"
$runnerGovernanceConfig = Get-Stage1RunnerGovernanceConfig -ConfigPath $configPath
$inventoryTrendGovernanceAlerts = @(Get-InventoryTrendGovernanceAlerts -Repo $repo)

if (-not $Day -and -not $All) {
    throw "Please provide -Day D1..D56 or -All"
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
    @("D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10", "D11", "D12", "D13", "D14", "D15", "D16", "D17", "D18", "D19", "D20", "D21", "D22", "D23", "D24", "D25", "D26", "D27", "D28", "D29", "D30", "D31", "D32", "D33", "D34", "D35", "D36", "D37", "D38", "D39", "D40", "D41", "D42", "D43", "D44", "D45", "D46", "D47", "D48", "D49", "D50", "D51", "D52", "D53", "D54", "D55", "D56")
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
    metadata                 = New-RunnerMetadata
    failed_operations        = [System.Collections.ArrayList]::new()
}

Start-RunnerPhase -Metadata $globalSummary.metadata -PhaseName "run_stage1_days"

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
    $dayMetadata = New-RunnerMetadata
    $dayFailedOperations = [System.Collections.ArrayList]::new()

    Start-RunnerPhase -Metadata $dayMetadata -PhaseName "execute_stage1_day"

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
            Fail-RunnerPhase -Metadata $dayMetadata -FailedOperations $dayFailedOperations -PhaseName "execute_stage1_day" -Error $r.message -Details ([ordered]@{ day = $d; step = $r.name; command = $r.command; exit_code = $r.exit_code }) -DurationSeconds $r.duration_seconds
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
        Fail-RunnerPhase -Metadata $dayMetadata -FailedOperations $dayFailedOperations -PhaseName "execute_stage1_day" -Error "Pass rate below target" -Details ([ordered]@{ day = $d; actual_pass_rate = $passRate; target_pass_rate = $TargetPassRate })
    }

    if ($dayMetadata.final_status -ne "failed") {
        Complete-RunnerPhase -Metadata $dayMetadata -PhaseName "execute_stage1_day"
    }

    $strictRollbackFlow = if ($thresholdBreached) {
        Get-StrictRollbackFlow -DayCode $d -Python $python -LogFile $logFile -ReportFile $reportFile
    }
    else {
        @()
    }

    Start-RunnerPhase -Metadata $dayMetadata -PhaseName "assemble_stage1_day_summary"
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
        metadata                 = $dayMetadata
        analysis_summary         = Get-DayAnalysisSummary -Steps $results -PassRate $passRate -RollbackTipCount @($rollbackTips).Count -StrictRollbackStepCount @($strictRollbackFlow).Count -ThresholdBreached $thresholdBreached
        failed_operations        = @($dayFailedOperations)
    }
    if ($inventoryTrendGovernanceAlerts.Count -gt 0) {
        $daySummary["governance_alerts"] = $inventoryTrendGovernanceAlerts
    }

    if ($failed -and $dayMetadata.final_status -ne "failed") {
        $dayMetadata.final_status = "failed"
    }
    Complete-RunnerPhase -Metadata $dayMetadata -PhaseName "assemble_stage1_day_summary"

    $daySummary = Write-Summary -ReportPath $reportFile -Summary $daySummary -ResultSchema "stage1_day_execution_report" -GovernanceConfig $runnerGovernanceConfig -ExportPhaseName "export_stage1_day_summary"
    $daySummary["report_file"] = $reportFile

    $globalSummary.days += $daySummary

    if ($failed) {
        Add-FailedOperation -FailedOperations $globalSummary.failed_operations -Operation "stage1_day" -Error "Day execution failed" -Details ([ordered]@{ day = $d; report_file = $reportFile; pass_rate_percent = $passRate; threshold_breached = $thresholdBreached })
        $globalSummary.metadata.final_status = "failed"
    }

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

Complete-RunnerPhase -Metadata $globalSummary.metadata -PhaseName "run_stage1_days"

Start-RunnerPhase -Metadata $globalSummary.metadata -PhaseName "assemble_stage1_global_summary"

$globalSummary["ended_at"] = (Get-Date).ToString("o")
$globalSummary["aborted_by_threshold"] = $abortedByThreshold
$globalSummary["abort_reason"] = $abortReason
$globalSummary["analysis_summary"] = Get-GlobalAnalysisSummary -Days $globalSummary.days -AbortedByThreshold $abortedByThreshold
$globalSummary["failed_operations"] = @($globalSummary.failed_operations)
if ($inventoryTrendGovernanceAlerts.Count -gt 0) {
    $globalSummary["governance_alerts"] = $inventoryTrendGovernanceAlerts
}
if (-not $globalSummary.metadata.last_completed_phase) {
    $globalSummary.metadata.final_status = "completed"
}
Complete-RunnerPhase -Metadata $globalSummary.metadata -PhaseName "assemble_stage1_global_summary"
$globalReport = Join-Path $logDir ("stage1_all_{0}.json" -f $stamp)
$globalSummary = Write-Summary -ReportPath $globalReport -Summary $globalSummary -ResultSchema "stage1_global_execution_report" -GovernanceConfig $runnerGovernanceConfig -ExportPhaseName "export_stage1_global_summary"

Write-Host ""
Write-Host ("Global report: {0}" -f $globalReport) -ForegroundColor Cyan
if ($abortedByThreshold) {
    Write-Host ("Aborted: {0}" -f $abortReason) -ForegroundColor Red
    exit 2
}
Write-Host "Done."
