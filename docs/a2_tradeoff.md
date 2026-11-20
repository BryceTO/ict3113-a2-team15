# A2 accuracy-latency trade-off

## Method

The trade-off chart joins the reviewed even-row test accuracy with the speed-test summary by configuration ID. Its x-axis is the mean of the three per-run p50 response times; its y-axis is overall accuracy on the 88-row even test set.

The dashed line shows the overall accuracy floor of 68.409%. Passing that line alone is insufficient: a deployable configuration must also meet every per-category floor. Red diamonds identify configurations that pass the overall floor but fail at least one category floor. A configuration without a speed result remains in the joined CSV and is noted below the plot instead of being assigned an invented latency.

## Results

| Configuration | Accuracy | Mean p50 | Accuracy status | Category-floor failures |
|---|---:|---:|---|---|
| Gemma 3 4B | 78.409% | 7.046 s | Eligible | None |
| Cascade S1 | 70.455% | 10.843 s | Ineligible | Consumer loan; Debt collection |
| Cascade S2 | 72.727% | 14.851 s | Ineligible | Debt collection |
| Mistral 7B | 86.364% | 30.433 s | Eligible | None |
| Llama 3.2 1B | 19.318% | Not measured | Ineligible | Overall and multiple category floors |

Gemma is the fastest accuracy-eligible configuration. Mistral is 7.955 percentage points more accurate, but its mean p50 is about 4.3 times Gemma's. Neither cascade is eligible: both fail category floors, and the speed evidence reports a pooled escalation fraction of 1.0 for each, so they also provide no routing savings on this frozen workload. Llama failed the accuracy gate and was therefore not speed-tested.

For the final recommendation, Gemma is the strongest speed-first choice among configurations satisfying all accuracy constraints. Mistral is the accuracy-first alternative if its much higher latency and observed queue growth are acceptable.

## Reproduction and traceability

Run:

```text
python scripts/build_a2_tradeoff.py
```

Inputs:

- `results/a2/accuracy/summary_reviewed_r1/overall.csv`
- `results/a2/accuracy/summary_reviewed_r1/per_category.csv`
- `results/a2/accuracy/summary_reviewed_r1/floors.csv`
- `results/a2/accuracy/summary_reviewed_r1/eligibility.csv`
- `results/a2/summary/a2_speed_configs.csv`

Outputs:

- `results/a2/summary/a2_tradeoff.csv` — joined, auditable chart source
- `results/a2/summary/a2_tradeoff.png` — 1600 × 900 slide-ready chart

The builder validates floor consistency, pass flags, eligibility, the seven expected categories, required speed coverage, and the three-run speed aggregation before producing either output.
