param(
    [ValidateSet("S2-1", "S2-2", "S2-3", "S2-4", "S2-5", "S2-6")]
    [string]$Stage,
    [switch]$All,
    [switch]$DryRun,
    [double]$TargetCodeHealth = 85.0,
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
    param([string]$Repo, [string]$InputPython)
    if ($InputPython -and (Test-Path $InputPython)) {
        return (Resolve-Path $InputPython).Path
    }
    $venvPython = Join-Path $Repo "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return (Resolve-Path $venvPython).Path
    }
    return "python"
}

function Ensure-LogDir {
    param([string]$Repo)
    $logDir = Join-Path $Repo "logs\stage2"
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }
    return $logDir
}

function Get-Timestamp {
    return Get-Date -Format "yyyyMMdd_HHmmss"
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

function Get-Stage2RunnerGovernanceConfig {
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
            if ($line -match '^  stage2_runner:\s*$') {
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

function Get-StageAnalysisSummary {
    param(
        [array]$Steps,
        [double]$PassRate,
        [double]$TargetCodeHealth,
        [bool]$DryRunMode
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
        pass_rate_band             = $passRateBand
        target_code_health_percent = $TargetCodeHealth
        dry_run                    = $DryRunMode
    }
}

function Get-GlobalAnalysisSummary {
    param(
        [array]$Stages,
        [bool]$DryRunMode
    )

    $stageCount = @($Stages).Count
    $failedStages = @($Stages | Where-Object { $_["failed"] }).Count
    $passRates = @($Stages | ForEach-Object { [double]($_["pass_rate_percent"]) })
    $averagePassRate = if ($passRates.Count -gt 0) {
        [math]::Round((($passRates | Measure-Object -Average).Average), 2)
    }
    else {
        0.0
    }

    return [ordered]@{
        stage_count               = $stageCount
        failed_stage_count        = $failedStages
        average_pass_rate_percent = $averagePassRate
        dry_run                   = $DryRunMode
        failed_stage_codes        = @($Stages | Where-Object { $_["failed"] } | ForEach-Object { $_["stage"] })
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

function Get-Plan {
    param([string]$StageName)

    $plans = @{
        "S2-1" = @{
            name   = "preprocessor-opt"
            branch = "stage2-s2_1-preprocessor-opt"
            steps  = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_1-preprocessor-opt' },
                @{ name = "Add type annotations"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/preprocessor/document_preprocessor.py --name source.addTypeAnnotation' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/preprocessor/document_preprocessor.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit preprocessor optimization"; type = "commit"; cmd = 'git add -A; git commit -m "S2-1: 预处理器优化 - 代码健康度提升"' }
            )
        }
        "S2-2" = @{
            name   = "extractor-refactor"
            branch = "stage2-s2_2-extractor-refactor"
            steps  = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_2-extractor-refactor' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/extractors/advanced_entity_extractor.py --name source.fixAll.pylance' },
                @{ name = "Remove unused imports"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/extractors/advanced_entity_extractor.py --name source.unusedImports' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit extractor refactor"; type = "commit"; cmd = 'git add -A; git commit -m "S2-2: 抽取器重构 - 代码质量优化"' }
            )
        }
        "S2-3" = @{
            name   = "semantic-stable"
            branch = "stage2-s2_3-semantic-stable"
            steps  = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_3-semantic-stable' },
                @{ name = "Add type annotations"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/semantic_modeling/semantic_graph_builder.py --name source.addTypeAnnotation' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/semantic_modeling/semantic_graph_builder.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit semantic stabilization"; type = "commit"; cmd = 'git add -A; git commit -m "S2-3: 语义建模稳定化 - 边界条件加固"' }
            )
        }
        "S2-4" = @{
            name   = "reasoning-opt"
            branch = "stage2-s2_4-reasoning-opt"
            steps  = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_4-reasoning-opt' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/reasoning/reasoning_engine.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit reasoning optimization"; type = "commit"; cmd = 'git add -A; git commit -m "S2-4: 推理引擎优化 - 幂等性验证"' }
            )
        }
        "S2-5" = @{
            name   = "output-strengthen"
            branch = "stage2-s2_5-output-strengthen"
            steps  = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_5-output-strengthen' },
                @{ name = "Add type annotations"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/output/output_generator.py --name source.addTypeAnnotation' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/output/output_generator.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit output generator strengthening"; type = "commit"; cmd = 'git add -A; git commit -m "S2-5: 输出生成器强化 - 契约验证完整化"' }
            )
        }
        "S2-6" = @{
            name   = "quality-integration"
            branch = "stage2-s2_6-quality-integration"
            steps  = @(
                @{ name = "Verify all branches merged"; type = "cmd"; cmd = 'git branch | find /V "*" | wc -l' },
                @{ name = "Run full quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Run quality assessment"; type = "cmd"; cmd = '& "{python}" tools/quality_assessment.py --gates-report output/quality-gate.json' },
                @{ name = "Run continuous improvement"; type = "cmd"; cmd = '& "{python}" tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json' },
                @{ name = "Archive quality metrics"; type = "cmd"; cmd = '& "{python}" tools/quality_improvement_archive.py' },
                @{ name = "Generate feedback"; type = "cmd"; cmd = '& "{python}" tools/quality_feedback.py' },
                @{ name = "Final commit"; type = "commit"; cmd = 'git add -A; git commit -m "S2-6: Stage 2 完成 - 质量评分综合提升"' }
            )
        }
    }

    if ($plans.ContainsKey($StageName)) {
        return $plans[$StageName]
    }
    throw "Unknown stage: $StageName"
}

function Invoke-Step {
    param(
        [hashtable]$Step,
        [string]$Python,
        [string]$Repo,
        [System.IO.StreamWriter]$LogWriter,
        [switch]$DryRunMode
    )

    $stepName = $Step.name
    $stepType = $Step.type
    $cmd = $Step.cmd -replace '{python}', $Python
    $result = [ordered]@{
        name             = $stepName
        type             = $stepType
        status           = "passed"
        exit_code        = 0
        started_at       = (Get-Date).ToString("o")
        ended_at         = ""
        duration_seconds = 0.0
        command          = $cmd
        message          = ""
    }
    $start = Get-Date

    Write-Host "[STEP] $stepName"
    $LogWriter.WriteLine("[STEP] $stepName")
    $LogWriter.WriteLine("[TYPE] $stepType")
    $LogWriter.WriteLine("[CMD ] $cmd")
    $LogWriter.Flush()

    try {
        if ($DryRunMode) {
            $result.status = "skipped"
            $result.message = "DryRun: $stepType step skipped"
        }
        elseif ($stepType -eq "branch") {
            if ($cmd -match 'checkout -b') {
                $branchName = ($cmd -split 'stage2-')[1]
                $branchName = "stage2-$branchName"
                Push-Location $Repo
                & git checkout -b $branchName 2>&1 | ForEach-Object { $LogWriter.WriteLine($_) }
                Pop-Location
            }
            else {
                Push-Location $Repo
                & git checkout HEAD -- . 2>&1 | ForEach-Object { $LogWriter.WriteLine($_) }
                Pop-Location
            }
        }
        elseif ($stepType -eq "commit") {
            $cmdParts = $cmd -split ';'
            Push-Location $Repo
            foreach ($part in $cmdParts) {
                $part = $part.Trim()
                if ($part) {
                    Invoke-Expression $part 2>&1 | ForEach-Object { $LogWriter.WriteLine($_) }
                }
            }
            Pop-Location
        }
        else {
            $tempOut = [System.IO.Path]::GetTempFileName()
            $tempErr = [System.IO.Path]::GetTempFileName()

            Push-Location $Repo
            $proc = Start-Process -FilePath powershell -ArgumentList @('-NoProfile', '-Command', $cmd) -RedirectStandardOutput $tempOut -RedirectStandardError $tempErr -PassThru -Wait
            Pop-Location

            Get-Content $tempOut -Encoding UTF8 2>$null | ForEach-Object { $LogWriter.WriteLine($_) }
            Get-Content $tempErr -Encoding UTF8 2>$null | ForEach-Object { $LogWriter.WriteLine("[ERR] $_") }

            Remove-Item $tempOut, $tempErr -Force -ErrorAction SilentlyContinue

            if ($proc.ExitCode -ne 0) {
                $result.status = "failed"
                $result.exit_code = $proc.ExitCode
                $result.message = "Command returned non-zero exit code"
            }
        }
    }
    catch {
        $LogWriter.WriteLine("[ERROR] $_")
        $LogWriter.Flush()
        $result.status = "failed"
        $result.exit_code = 1
        $result.message = $_.Exception.Message
    }

    $end = Get-Date
    $result.ended_at = $end.ToString("o")
    $result.duration_seconds = [math]::Round((New-TimeSpan -Start $start -End $end).TotalSeconds, 2)
    return $result
}

function Run-Stage {
    param(
        [string]$StageName,
        [string]$Repo,
        [string]$Python,
        [string]$LogDir,
        $GovernanceConfig,
        [double]$TargetCodeHealth,
        [switch]$DryRunMode
    )

    $plan = Get-Plan $StageName
    $timestamp = Get-Timestamp
    $logFile = Join-Path $LogDir "stage2_${StageName}_${timestamp}.log"
    $reportFile = Join-Path $LogDir "stage2_${StageName}_${timestamp}.json"

    Write-Host "=== Running $StageName ==="
    Write-Host "Repo   : $Repo"
    Write-Host "Python : $Python"
    Write-Host "Log    : $logFile"

    $totalSteps = $plan.steps.Count
    $passedSteps = 0
    $failedSteps = 0
    $skippedSteps = 0
    $metadata = New-RunnerMetadata
    $failedOperations = [System.Collections.ArrayList]::new()

    $logWriter = [System.IO.StreamWriter]::new($logFile, $false, [System.Text.Encoding]::UTF8)
    $logWriter.WriteLine("=== $StageName Execution ===")
    $logWriter.WriteLine("Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $logWriter.WriteLine()

    Start-RunnerPhase -Metadata $metadata -PhaseName "execute_stage2_stage"
    $stepResults = @()

    foreach ($step in $plan.steps) {
        $result = Invoke-Step -Step $step -Python $Python -Repo $Repo -LogWriter $logWriter -DryRunMode:$DryRunMode
        $stepResults += $result

        if ($result.status -eq "passed") {
            Write-Host "[PASS] $($step.name)"
            $logWriter.WriteLine("[RESULT] PASS")
            $passedSteps++
        }
        elseif ($result.status -eq "skipped") {
            Write-Host "[SKIP] $($step.name) :: $($result.message)"
            $logWriter.WriteLine("[RESULT] SKIP")
            $skippedSteps++
        }
        else {
            Write-Host "[FAIL] $($step.name) :: Command returned exit code $($result.exit_code)"
            $logWriter.WriteLine("[RESULT] FAIL (exit code: $($result.exit_code))")
            $failedSteps++
            Fail-RunnerPhase -Metadata $metadata -FailedOperations $failedOperations -PhaseName "execute_stage2_stage" -Error $result.message -Details ([ordered]@{ stage = $StageName; step = $result.name; command = $result.command; exit_code = $result.exit_code }) -DurationSeconds $result.duration_seconds
            break
        }
        $logWriter.WriteLine()
    }

    if ($metadata.final_status -ne "failed") {
        Complete-RunnerPhase -Metadata $metadata -PhaseName "execute_stage2_stage"
    }

    $passRate = if ($totalSteps -gt 0) { [math]::Round(($passedSteps / $totalSteps) * 100, 2) } else { 0 }

    $logWriter.WriteLine()
    $logWriter.WriteLine("=== Summary ===")
    $logWriter.WriteLine("Total steps: $totalSteps")
    $logWriter.WriteLine("Passed: $passedSteps")
    $logWriter.WriteLine("Failed: $failedSteps")
    $logWriter.WriteLine("Skipped: $skippedSteps")
    $logWriter.WriteLine("Pass rate: ${passRate}%")
    $logWriter.WriteLine("Ended: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $logWriter.Close()

    Start-RunnerPhase -Metadata $metadata -PhaseName "assemble_stage2_stage_summary"
    $stageSummary = [ordered]@{
        stage                      = $StageName
        started_at                 = if ($stepResults.Count -gt 0) { $stepResults[0].started_at } else { (Get-Date).ToString("o") }
        ended_at                   = (Get-Date).ToString("o")
        total_steps                = $totalSteps
        passed_steps               = $passedSteps
        skipped_steps              = $skippedSteps
        failed_steps               = $failedSteps
        pass_rate_percent          = $passRate
        target_code_health_percent = $TargetCodeHealth
        failed                     = ($failedSteps -gt 0)
        dry_run                    = [bool]$DryRunMode
        log_file                   = $logFile
        steps                      = $stepResults
        metadata                   = $metadata
        analysis_summary           = Get-StageAnalysisSummary -Steps $stepResults -PassRate $passRate -TargetCodeHealth $TargetCodeHealth -DryRunMode ([bool]$DryRunMode)
        failed_operations          = @($failedOperations)
    }
    if ($script:InventoryTrendGovernanceAlerts.Count -gt 0) {
        $stageSummary["governance_alerts"] = $script:InventoryTrendGovernanceAlerts
    }
    Complete-RunnerPhase -Metadata $metadata -PhaseName "assemble_stage2_stage_summary"

    $stageSummary = Write-Summary -ReportPath $reportFile -Summary $stageSummary -ResultSchema "stage2_stage_execution_report" -GovernanceConfig $GovernanceConfig -ExportPhaseName "export_stage2_stage_summary"
    $stageSummary["report_file"] = $reportFile

    Write-Host "Summary ${StageName}: pass_rate=${passRate}% (pass=$passedSteps, fail=$failedSteps, skip=$skippedSteps)"
    Write-Host "Report: $reportFile"
    Write-Host "Done."

    return $stageSummary
}

# Main
$repo = Resolve-RepoRoot $RepoPath
$python = Resolve-Python $repo $PythonExe
$logDir = Ensure-LogDir $repo
$configPath = Join-Path $repo "config.yml"
$governanceConfig = Get-Stage2RunnerGovernanceConfig -ConfigPath $configPath
$script:InventoryTrendGovernanceAlerts = @(Get-InventoryTrendGovernanceAlerts -Repo $repo)

if (-not $Stage -and -not $All) {
    throw "Please provide -Stage S2-1..S2-6 or -All"
}
if ($Stage -and $All) {
    throw "Use either -Stage or -All, not both"
}

$runStages = if ($All) {
    @("S2-1", "S2-2", "S2-3", "S2-4", "S2-5", "S2-6")
}
else {
    @($Stage)
}

$globalMetadata = New-RunnerMetadata
$globalFailedOperations = [System.Collections.ArrayList]::new()
$globalSummary = [ordered]@{
    started_at                 = (Get-Date).ToString("o")
    repo                       = $repo
    python                     = $python
    dry_run                    = [bool]$DryRun
    target_code_health_percent = $TargetCodeHealth
    stages                     = @()
    metadata                   = $globalMetadata
    failed_operations          = $globalFailedOperations
}

Start-RunnerPhase -Metadata $globalMetadata -PhaseName "run_stage2_stages"

foreach ($stageName in $runStages) {
    $stageSummary = Run-Stage -StageName $stageName -Repo $repo -Python $python -LogDir $logDir -GovernanceConfig $governanceConfig -TargetCodeHealth $TargetCodeHealth -DryRunMode:$DryRun
    $globalSummary.stages += $stageSummary

    if ($stageSummary.failed) {
        $globalMetadata.final_status = "failed"
        Add-FailedOperation -FailedOperations $globalFailedOperations -Operation "stage2_stage" -Error "Stage execution failed" -Details ([ordered]@{ stage = $stageSummary.stage; report_file = $stageSummary.report_file; pass_rate_percent = $stageSummary.pass_rate_percent })
    }
}

if ($globalMetadata.final_status -ne "failed") {
    Complete-RunnerPhase -Metadata $globalMetadata -PhaseName "run_stage2_stages"
}

Start-RunnerPhase -Metadata $globalMetadata -PhaseName "assemble_stage2_global_summary"
$globalSummary["ended_at"] = (Get-Date).ToString("o")
$globalSummary["analysis_summary"] = Get-GlobalAnalysisSummary -Stages $globalSummary.stages -DryRunMode ([bool]$DryRun)
$globalSummary["failed_operations"] = @($globalFailedOperations)
if ($script:InventoryTrendGovernanceAlerts.Count -gt 0) {
    $globalSummary["governance_alerts"] = $script:InventoryTrendGovernanceAlerts
}
Complete-RunnerPhase -Metadata $globalMetadata -PhaseName "assemble_stage2_global_summary"

$globalReport = Join-Path $logDir ("stage2_all_{0}.json" -f (Get-Timestamp))
$globalSummary = Write-Summary -ReportPath $globalReport -Summary $globalSummary -ResultSchema "stage2_global_execution_report" -GovernanceConfig $governanceConfig -ExportPhaseName "export_stage2_global_summary"

Write-Host ""
Write-Host "Global report: $globalReport" -ForegroundColor Cyan
