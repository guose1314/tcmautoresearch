# Real Observe Smoke

This repository now includes a fixed, validated real-corpus smoke profile for the local Observe -> Analyze -> Publish path.

## Locked Profile

- Profile file: tools/diagnostics/real_observe_smoke_profile.json
- Corpus shape: 20 local text files
- Observe excerpt size: 3000 characters per file
- Literature retrieval: disabled
- Hypothesis LLM generation: disabled
- Experiment protocol-design generation: disabled

Publish primary association and mining details are resolved from nested statistical_analysis and data_mining_result payloads. No publish-level mining aliases are required.

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
- publish contract uses nested statistical_analysis and data_mining_result payloads only

## 2026-04-11 Regression Note

The original historical profile was re-run after restoring the locked `data/` corpus and now passes again.

- Official recheck summary: `output/real_observe_smoke/recheck_historical_restored/latest.json`
- Official recheck dossier: `output/real_observe_smoke/recheck_historical_restored/dossier.md`

The recheck matched the locked historical baseline on the key regression metrics:

- processed_document_count = 20
- record_count = 16
- p_value = 0.029345
- effect_size = 0.5447
- kg_path_count = 50
- association_rule_count = 20
- frequency_signal_count = 15
- validation_status = passed

The offline blocker during the recheck was not missing corpus data anymore. It was the formula-similarity query path trying to initialize `SentenceTransformer` even when a persisted embedding index already existed. The current fix reuses cached vectors for exact formula-query matches, so the historical smoke profile can run offline again.

## Operational LLM Note

This smoke profile intentionally keeps Hypothesis LLM generation and Experiment protocol-design generation disabled so the baseline stays deterministic.

For normal application use, prefer the local GGUF runtime:

- `models.llm.mode = local`
- `models.llm.path = ./models/qwen1_5-7b-chat-q8_0.gguf`

Use API mode only when an explicit external deployment requires it.
