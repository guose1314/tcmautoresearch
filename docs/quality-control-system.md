# Quality Control System

This repository uses a practical quality control baseline composed of eight gates:

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

5. Quality assessment scoring
   - Tool: `tools/quality_assessment.py`
   - Purpose: transform gate results into multi-dimension scores, grade, and recommendations for continuous quality governance.

6. Continuous improvement loop
   - Tool: `tools/continuous_improvement_loop.py`
   - Purpose: persist quality history, calculate trends, and generate next-cycle action backlog for continuous improvement.

7. Quality improvement archive
   - Tool: `tools/quality_improvement_archive.py`
   - Purpose: archive each quality cycle into a machine-readable timeline and a human-readable dossier.

8. Quality feedback mechanism
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

## Extension Rules

Add new quality gates only when they are:

1. Deterministic
2. Fast enough for CI
3. Actionable on failure
4. Testable in isolation
