param(
    [ValidateSet("S2-1", "S2-2", "S2-3", "S2-4", "S2-5", "S2-6")]
    [string]$Stage,
    [switch]$All,
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
        return $venvPython
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

function Get-Plan {
    param([string]$StageName)
    
    $plans = @{
        "S2-1" = @{
            name = "preprocessor-opt"
            branch = "stage2-s2_1-preprocessor-opt"
            steps = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_1-preprocessor-opt' },
                @{ name = "Add type annotations"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/preprocessor/document_preprocessor.py --name source.addTypeAnnotation' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/preprocessor/document_preprocessor.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit preprocessor optimization"; type = "commit"; cmd = 'git add -A; git commit -m "S2-1: 预处理器优化 - 代码健康度提升"' }
            )
        };
        "S2-2" = @{
            name = "extractor-refactor"
            branch = "stage2-s2_2-extractor-refactor"
            steps = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_2-extractor-refactor' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/extractors/advanced_entity_extractor.py --name source.fixAll.pylance' },
                @{ name = "Remove unused imports"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/extractors/advanced_entity_extractor.py --name source.unusedImports' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit extractor refactor"; type = "commit"; cmd = 'git add -A; git commit -m "S2-2: 抽取器重构 - 代码质量优化"' }
            )
        };
        "S2-3" = @{
            name = "semantic-stable"
            branch = "stage2-s2_3-semantic-stable"
            steps = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_3-semantic-stable' },
                @{ name = "Add type annotations"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/semantic_modeling/semantic_graph_builder.py --name source.addTypeAnnotation' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/semantic_modeling/semantic_graph_builder.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit semantic stabilization"; type = "commit"; cmd = 'git add -A; git commit -m "S2-3: 语义建模稳定化 - 边界条件加固"' }
            )
        };
        "S2-4" = @{
            name = "reasoning-opt"
            branch = "stage2-s2_4-reasoning-opt"
            steps = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_4-reasoning-opt' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/reasoning/reasoning_engine.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit reasoning optimization"; type = "commit"; cmd = 'git add -A; git commit -m "S2-4: 推理引擎优化 - 幂等性验证"' }
            )
        };
        "S2-5" = @{
            name = "output-strengthen"
            branch = "stage2-s2_5-output-strengthen"
            steps = @(
                @{ name = "Create or switch branch"; type = "branch"; cmd = 'git checkout -b/checkout stage2-s2_5-output-strengthen' },
                @{ name = "Add type annotations"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/output/output_generator.py --name source.addTypeAnnotation' },
                @{ name = "Apply pylance fixes"; type = "cmd"; cmd = '& "{python}" -m pylance mcp_s_pylanceInvokeRefactoring --file src/output/output_generator.py --name source.fixAll.pylance' },
                @{ name = "Run quality gate"; type = "cmd"; cmd = '& "{python}" tools/quality_gate.py' },
                @{ name = "Commit output generator strengthening"; type = "commit"; cmd = 'git add -A; git commit -m "S2-5: 输出生成器强化 - 契约验证完整化"' }
            )
        };
        "S2-6" = @{
            name = "quality-integration"
            branch = "stage2-s2_6-quality-integration"
            steps = @(
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
        [System.IO.StreamWriter]$LogWriter
    )
    
    $stepName = $Step.name
    $stepType = $Step.type
    $cmd = $Step.cmd -replace '{python}', $Python
    
    Write-Host "[STEP] $stepName"
    $LogWriter.WriteLine("[STEP] $stepName")
    $LogWriter.WriteLine("[TYPE] $stepType")
    $LogWriter.WriteLine("[CMD ] $cmd")
    $LogWriter.Flush()
    
    try {
        if ($stepType -eq "branch") {
            if ($cmd -match 'checkout -b') {
                $branchName = ($cmd -split 'stage2-')[1]
                $branchName = "stage2-$branchName"
                Push-Location $Repo
                & git checkout -b $branchName 2>&1 | ForEach-Object { $LogWriter.WriteLine($_) }
                Pop-Location
            } else {
                Push-Location $Repo
                & git checkout HEAD -- . 2>&1 | ForEach-Object { $LogWriter.WriteLine($_) }
                Pop-Location
            }
            return @{ passed = $true; exitCode = 0 }
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
            return @{ passed = $true; exitCode = 0 }
        } 
        else {
            $tempOut =  [System.IO.Path]::GetTempFileName()
            $tempErr = [System.IO.Path]::GetTempFileName()
            
            Push-Location $Repo
            $proc = Start-Process -FilePath powershell -ArgumentList @('-NoProfile', '-Command', $cmd) -RedirectStandardOutput $tempOut -RedirectStandardError $tempErr -PassThru -Wait
            Pop-Location
            
            Get-Content $tempOut -Encoding UTF8 2>$null | ForEach-Object { $LogWriter.WriteLine($_) }
            Get-Content $tempErr -Encoding UTF8 2>$null | ForEach-Object { $LogWriter.WriteLine("[ERR] $_") }
            
            Remove-Item $tempOut, $tempErr -Force -ErrorAction SilentlyContinue
            
            return @{ passed = $proc.ExitCode -eq 0; exitCode = $proc.ExitCode }
        }
    } 
    catch {
        $LogWriter.WriteLine("[ERROR] $_")
        $LogWriter.Flush()
        return @{ passed = $false; exitCode = 1 }
    }
}

function Run-Stage {
    param(
        [string]$StageName,
        [string]$Repo,
        [string]$Python,
        [string]$LogDir
    )
    
    $plan = Get-Plan $StageName
    $timestamp = Get-Timestamp
    $logFile = Join-Path $LogDir "stage2_${StageName}_${timestamp}.log"
    
    Write-Host "=== Running $StageName ==="
    Write-Host "Repo   : $Repo"
    Write-Host "Python : $Python"
    Write-Host "Log    : $logFile"
    
    $totalSteps = $plan.steps.Count
    $passedSteps = 0
    $failedSteps = 0
    
    $logWriter = [System.IO.StreamWriter]::new($logFile, $false, [System.Text.Encoding]::UTF8)
    $logWriter.WriteLine("=== $StageName Execution ===")
    $logWriter.WriteLine("Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $logWriter.WriteLine()
    
    foreach ($step in $plan.steps) {
        $result = Invoke-Step $step $Python $Repo $logWriter
        
        if ($result.passed) {
            Write-Host "[PASS] $($step.name)"
            $logWriter.WriteLine("[RESULT] PASS")
            $passedSteps++
        } else {
            Write-Host "[FAIL] $($step.name) :: Command returned exit code $($result.exitCode)"
            $logWriter.WriteLine("[RESULT] FAIL (exit code: $($result.exitCode))")
            $failedSteps++
            break
        }
        $logWriter.WriteLine()
    }
    
    $passRate = if ($totalSteps -gt 0) { [math]::Round(($passedSteps / $totalSteps) * 100, 2) } else { 0 }
    
    $logWriter.WriteLine()
    $logWriter.WriteLine("=== Summary ===")
    $logWriter.WriteLine("Total steps: $totalSteps")
    $logWriter.WriteLine("Passed: $passedSteps")
    $logWriter.WriteLine("Failed: $failedSteps")
    $logWriter.WriteLine("Pass rate: ${passRate}%")
    $logWriter.WriteLine("Ended: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
    $logWriter.Close()
    
    Write-Host "Summary ${StageName}: pass_rate=${passRate}% (pass=$passedSteps, fail=$failedSteps, skip=0)"
    Write-Host "Report: $logFile"
    Write-Host "Done."
}

# Main
$repo = Resolve-RepoRoot $RepoPath
$python = Resolve-Python $repo $PythonExe
$logDir = Ensure-LogDir $repo

if ($All) {
    @("S2-1", "S2-2", "S2-3", "S2-4", "S2-5", "S2-6") | ForEach-Object {
        Run-Stage $_ $repo $python $logDir
    }
} else {
    Run-Stage $Stage $repo $python $logDir
}
