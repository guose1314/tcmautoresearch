# Innovation Incentive System

This repository uses a structured innovation incentive mechanism to reward contributions that are novel, impactful, validated, reusable, and shareable.

## Goal

Turn innovation from a vague preference into a repeatable evaluation process.

## Scoring Dimensions

Each contribution profile is scored across five dimensions on a 0-5 scale:

1. Novelty
2. Impact
3. Validation
4. Reuse
5. Knowledge sharing

Weighted total:

- Novelty: 30
- Impact: 25
- Validation: 20
- Reuse: 15
- Knowledge sharing: 10

Bonus points:

- Tests: +5
- Docs: +3
- Artifact or demo: +2
- Quality gate passed: +5

## Tiers

- Pioneer: 85-100
- Catalyst: 70-84
- Explorer: 55-69
- Incubator: 0-54

## Operating Process

1. Fill the contribution profile template.
2. Run the evaluator locally.
3. Review the score, tier, reward suggestions, and improvement actions.
4. Use the result in team review, monthly innovation ranking, or follow-up prioritization.

## Adaptive Learning

The evaluator supports a feedback-driven adaptive loop:

1. Run evaluation with a human feedback score (0-5).
2. System compares predicted performance with human feedback.
3. Dimension weights are updated and persisted into state file.
4. Next evaluation uses the updated weights.

Example:

```bash
python tools/innovation_incentives.py --input docs/templates/innovation-profile.template.json --feedback 4.0
```

Default learning state output:

- `output/innovation-learning-state.json`

## Local Command

```bash
python tools/innovation_incentives.py --input docs/templates/innovation-profile.template.json
```

Default report output:

- `output/innovation-incentive-report.json`

## Governance Rule

High innovation score alone is not enough.

The preferred contribution pattern is:

1. New idea
2. Verifiable implementation
3. Reusable output
4. Shareable documentation

This prevents rewarding novelty without delivery discipline.
