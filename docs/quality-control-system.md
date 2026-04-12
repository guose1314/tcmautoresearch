# Quality Control System

This repository uses a practical quality control baseline composed of ten gates:

## Gates

1. Logic checks
   - Tool: `tools/logic_checks.py`
   - Purpose: detect hardcoded absolute `sys.path` inserts, duplicate top-level definitions, and duplicate `__all__` exports.

2. Dependency graph regeneration
   - Tool: `tools/generate_dependency_graph.py`
   - Purpose: keep internal dependency artifacts under `docs/architecture/` updated and verifiable.

3. Quality tool unit tests
   - Modules:
     - `tests.unit.test_logic_checks`
     - `tests.unit.test_dependency_graph_tool`
   - Purpose: ensure the quality-control tooling itself remains stable.

4. Code quality checks
   - Tool: `tools/code_quality_checks.py`
   - Purpose: detect syntax errors and maintainability risks (oversized functions, excessive parameters, high branching complexity, bare except).

5. Real Observe smoke validation
   - Tool: `tools/diagnostics/run_real_observe_smoke.py`
   - Purpose: validate the fixed 20-file local-corpus Observe -> Analyze -> Publish path against real metrics, significance thresholds, reasoning support, and publish alias contracts.
   - Activation: enabled in the main repository via the quality-gate section in `config.yml`; disabled by default in minimal replay harnesses unless explicitly configured.

6. Quality assessment scoring
   - Tool: `tools/quality_assessment.py`
   - Purpose: transform gate results into multi-dimension scores, grade, and recommendations for continuous quality governance.

7. Continuous improvement loop
   - Tool: `tools/continuous_improvement_loop.py`
   - Purpose: persist quality history, calculate trends, and generate next-cycle action backlog for continuous improvement.

8. Quality consumer inventory
   - Tool: `tools/quality_consumer_inventory.py`
   - Purpose: verify governance contract coverage for downstream quality consumers and surface missing-contract / root-script drift.

9. Quality improvement archive
   - Tool: `tools/quality_improvement_archive.py`
   - Purpose: archive each quality cycle into a machine-readable timeline and a human-readable dossier.

10. Quality feedback mechanism
    - Tool: `tools/quality_feedback.py`
    - Purpose: produce graded quality feedback and prioritized actions for teams and module owners.

## Unified Entry Point

Run the full quality gate locally:

```bash
python tools/quality_gate.py
```

Run code quality checks independently:

```bash
python tools/code_quality_checks.py
```

Run quality assessment independently:

```bash
python tools/quality_assessment.py --gates-report output/quality-gate.json
```

Run continuous improvement loop independently:

```bash
python tools/continuous_improvement_loop.py --assessment-report output/quality-assessment.json
```

Run quality improvement archive independently:

```bash
python tools/quality_improvement_archive.py
```

Run quality feedback independently:

```bash
python tools/quality_feedback.py
```

Outputs:

- JSON report: `output/quality-gate.json`
- Real Observe smoke latest summary: `output/real_observe_smoke/latest.json`
- Real Observe smoke dossier: `output/real_observe_smoke/dossier.md`
- Real Observe smoke timeline: `output/real_observe_smoke/timeline.jsonl`
- Quality assessment report: `output/quality-assessment.json`
- Continuous improvement report: `output/continuous-improvement.json`
- Quality history timeline: `output/quality-history.jsonl`
- Quality improvement archive timeline: `output/quality-improvement-archive.jsonl`
- Quality improvement latest snapshot: `output/quality-improvement-archive-latest.json`
- Quality improvement dossiers: `docs/quality-archive/`
- Quality feedback report: `output/quality-feedback.json`
- Quality feedback markdown: `output/quality-feedback.md`
- Dependency graph artifacts:
  - `docs/architecture/dependency-graph.json`
  - `docs/architecture/dependency-graph.mmd`
  - `docs/architecture/dependency-graph.md`

## CI Integration

The CI workflow runs the unified quality gate on pull requests and pushes to `main`.
If the gate fails, the workflow fails.
The uploaded workflow artifacts now also include the real Observe smoke outputs so failed regressions can be inspected without rerunning locally.

The same workflow now also includes two drift guards for operational entrypoints and top-level docs:

- README markdownlint: validates `README.md` and `deploy/helm/tcmautoresearch/README.md` with the repository-level `.markdownlint.json` policy.
- Helm template render: installs Helm in CI and runs `helm template tcmautoresearch ./deploy/helm/tcmautoresearch`, uploading the rendered manifest as `output/ci/helm-template.yaml` for inspection.

## Extension Rules

Add new quality gates only when they are:

1. Deterministic
2. Fast enough for CI
3. Actionable on failure
4. Testable in isolation
