[CmdletBinding()]
param(
    [ValidateRange(1, 10000)]
    [int]$BatchSize = 200,

    # 默认空字符串 → 让 backfill_research_session_nodes.py 使用 canonical
    # ``GRAPH_SCHEMA_VERSION``（src/storage/graph_schema.py）。如需固定版本可显式传入。
    [string]$ExpectedGraphSchemaVersion = "",

    [switch]$SkipPgVersionWriteback,

    [switch]$SkipPgPhilologyArtifactWriteback,

    [switch]$ForceGraphAssetsRegen,

    [switch]$PreflightOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonExe = Join-Path $workspaceRoot "venv310\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$env:TCM_ENV = "production"

# All sensitive runtime credentials must be supplied via the caller's
# environment. We deliberately do NOT hard-code them in this script: anybody
# checking this file out should not learn the production database password.
# Set the variables in your shell or in a .env loader before invoking the
# preflight; the script aborts early if any of them is missing.
$requiredEnv = @(
    "TCM__DATABASE__HOST",
    "TCM__DATABASE__NAME",
    "TCM__DATABASE__USER",
    "TCM__DATABASE__PASSWORD",
    "TCM__NEO4J__URI",
    "TCM__NEO4J__USER",
    "TCM__NEO4J__PASSWORD"
)
$missing = @()
foreach ($name in $requiredEnv) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        $missing += $name
    }
}
if ($missing.Count -gt 0) {
    throw "Missing required environment variables: $($missing -join ', '). Refusing to run with empty credentials."
}

function Write-PreflightSummary {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Json
    )

    try {
        $report = $Json | ConvertFrom-Json
    }
    catch {
        Write-Host "[preflight-summary] WARN: failed to parse dry-run output as JSON, skipping summary"
        return
    }

    $schema = $report.graph_schema
    $backfill = $report.backfill
    $pgAssets = $report.phase_graph_assets_writeback

    Write-Host ""
    Write-Host "============================================================"
    Write-Host " production-local backfill PREFLIGHT SUMMARY (dry-run)"
    Write-Host "============================================================"
    if ($schema) {
        Write-Host (" graph schema  : expected={0} stored={1} matches={2}" -f $schema.expected_version, $schema.stored_version, $schema.matches_expected)
        if ($schema.drift_report) {
            Write-Host (" schema drift  : detected={0} detail={1}" -f $schema.drift_report.drift_detected, $schema.drift_report.detail)
        }
    }
    if ($backfill) {
        $nodesLine = " projected nodes : total={0} session={1} phase={2} artifact={3} entity={4}" -f $backfill.node_count, $backfill.session_node_count, $backfill.phase_node_count, $backfill.artifact_node_count, $backfill.observe_entity_node_count
        Write-Host $nodesLine
        $assetsLine = " projected assets: hypothesis={0} evidence={1} philology={2} exegesis_term={3} textual_chain={4} subgraphs={5}" -f $backfill.hypothesis_node_count, $backfill.evidence_node_count, $backfill.philology_node_count, $backfill.exegesis_term_node_count, $backfill.textual_evidence_chain_node_count, $backfill.graph_asset_subgraph_count
        Write-Host $assetsLine
        $edgesLine = " projected edges : total={0} has_phase={1} generated={2} captured={3} observed_witness={4} hypothesis={5} evidence={6} philology={7}" -f $backfill.edge_count, $backfill.has_phase_edge_count, $backfill.generated_edge_count, $backfill.captured_edge_count, $backfill.observed_witness_edge_count, $backfill.hypothesis_edge_count, $backfill.evidence_edge_count, $backfill.philology_edge_count
        Write-Host $edgesLine
    }
    if ($pgAssets) {
        Write-Host (" pg graph_assets : status={0} updated_phases={1} skipped={2}" -f $pgAssets.status, $pgAssets.updated_phase_count, $pgAssets.skipped_phase_count)
    }
    Write-Host "============================================================"
    Write-Host ""
}

function Invoke-ProductionLocalPreflight {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WorkspaceRoot,

        [Parameter(Mandatory = $true)]
        [string]$PythonExe,

        [Parameter(Mandatory = $false)]
        [AllowEmptyString()]
        [string]$ExpectedGraphSchemaVersion,

        [Parameter(Mandatory = $true)]
        [int]$BatchSize
    )

    $commandArgs = @(
        "tools/backfill_research_session_nodes.py",
        "--environment",
        "production",
        "--batch-size",
        $BatchSize.ToString(),
        "--dry-run"
    )
    if (-not [string]::IsNullOrWhiteSpace($ExpectedGraphSchemaVersion)) {
        $commandArgs += @("--expected-graph-schema-version", $ExpectedGraphSchemaVersion)
    }

    $tmpOut = [System.IO.Path]::GetTempFileName()
    try {
        & $PythonExe @commandArgs > $tmpOut
        $exitCode = $LASTEXITCODE
        $jsonText = Get-Content -Raw -Path $tmpOut
        if ($jsonText) {
            Write-Output $jsonText
        }
        if ($exitCode -ne 0) {
            throw "Preflight failed with exit code $exitCode"
        }
        $startIdx = $jsonText.IndexOf('{')
        if ($startIdx -ge 0) {
            Write-PreflightSummary -Json $jsonText.Substring($startIdx)
        }
    }
    finally {
        Remove-Item -Path $tmpOut -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ("Using production-local overrides: PostgreSQL {0}/{1}, Neo4j {2}" -f `
        $env:TCM__DATABASE__HOST, $env:TCM__DATABASE__NAME, $env:TCM__NEO4J__URI)

Push-Location $workspaceRoot
try {
    if ($PreflightOnly) {
        Invoke-ProductionLocalPreflight -WorkspaceRoot $workspaceRoot -PythonExe $pythonExe -ExpectedGraphSchemaVersion $ExpectedGraphSchemaVersion -BatchSize $BatchSize
        return
    }

    $commandArgs = @(
        "tools/backfill_research_session_nodes.py",
        "--environment",
        "production",
        "--batch-size",
        $BatchSize.ToString()
    )
    if (-not [string]::IsNullOrWhiteSpace($ExpectedGraphSchemaVersion)) {
        $commandArgs += @("--expected-graph-schema-version", $ExpectedGraphSchemaVersion)
    }

    if ($SkipPgVersionWriteback) {
        $commandArgs += "--skip-pg-version-writeback"
    }

    if ($SkipPgPhilologyArtifactWriteback) {
        $commandArgs += "--skip-pg-philology-artifact-writeback"
    }

    if ($ForceGraphAssetsRegen) {
        $commandArgs += "--force-pg-graph-assets-regen"
    }

    & $pythonExe @commandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Backfill failed with exit code $LASTEXITCODE"
    }
}
finally {
    Pop-Location
}