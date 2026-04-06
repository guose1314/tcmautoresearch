# Real Observe Smoke

This repository now includes a fixed, validated real-corpus smoke profile for the local Observe -> Analyze -> Publish path.

## Locked Profile

- Profile file: tools/diagnostics/real_observe_smoke_profile.json
- Corpus shape: 20 local text files
- Observe excerpt size: 3000 characters per file
- Literature retrieval: disabled
- Hypothesis LLM generation: disabled
- Experiment LLM protocol generation: disabled
- Required publish aliases:
  - primary_association
  - data_mining_summary
  - data_mining_methods
  - frequency_chi_square
  - association_rules

## Run The Smoke Validation

```powershell
c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe tools/diagnostics/run_real_observe_smoke.py
```

The runner exits with code 0 on success and 1 on threshold or contract failures.

## Output Artifacts

The runner writes three persistent artifacts under output/real_observe_smoke:

- latest.json: latest full execution summary and validation result
- dossier.md: human-readable smoke dossier
- timeline.jsonl: append-only execution history for repeated runs

## Contract Tests

Run the lightweight contract checks:

```powershell
c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe -m unittest tests.test_real_observe_smoke_contract
```

## Quality Gate Integration

The main repository enables this smoke profile through the quality-gate section in `config.yml`.

- `python tools/quality_gate.py` now executes the real Observe smoke gate as part of the regular quality report.
- `.github/workflows/quality-control.yml` inherits the same gate because CI runs `tools/quality_gate.py`.
- Stage runners that already invoke `tools/quality_gate.py` automatically inherit the same regression guard without adding a separate smoke command.

To execute the full real-corpus smoke test via unittest, set the opt-in flag first:

```powershell
$env:TCM_RUN_REAL_OBSERVE_SMOKE = "1"
c:/Users/hgk/tcmautoresearch/venv310/Scripts/python.exe -m unittest tests.test_real_observe_smoke_contract
```

## Current Verified Baseline

The fixed 20-file profile was re-validated locally with these results:

- processed_document_count = 20
- record_count = 16
- p_value = 0.029345
- effect_size = 0.5447
- statistical_significance = true
- kg_path_count = 50
- publish alias coverage = complete in analysis_results and research_artifact
