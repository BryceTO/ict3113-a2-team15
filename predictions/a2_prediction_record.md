# ICT3113 Assignment 2 — Team 15: Pre-benchmark prediction record

## 1. Scope

These are hypotheses recorded before official A2 accuracy and speed measurements, not measured A2 results. The selection uses only the 87 odd-row tuning tickets. The 88 even-row tickets are held back from rule selection. Preliminary smoke and residency checks are setup verification, not scored benchmarks.

## 2. Predicted winner

Gemma 3 4B alone is expected to be the fastest configuration satisfying both official accuracy floors. As the reference, its accuracy establishes those floors. Llama 3.2 1B is expected to fail the overall accuracy floor given its 17/87 tuning accuracy. Mistral 7B is expected to be slower than Gemma on the CPU host, regardless of whether it qualifies; its accuracy eligibility remains uncertain. Both cascade settings are expected to be slower than Gemma alone because they execute Llama on every ticket and Gemma on almost every ticket.

## 3. Numerical cascade predictions

| Predicted metric | S1 (241 characters) | S2 (289 characters) |
|---|---:|---:|
| Overall even-row accuracy | 75% | 71% |
| Escalation fraction (accuracy workload) | 98% | 94% |
| Median successful-request latency prediction (historical per-ticket proxy) | 8.896 seconds (about 8.9 s) | 8.896 seconds (about 8.9 s) |
| Expected accuracy qualification | Pass both floors (tentative) | Pass both floors (tentative, lower confidence) |

Accuracy and escalation predictions are rounded from the odd-row simulations: 65/87 correct and 85/87 escalated for S1; 62/87 correct and 82/87 escalated for S2. The speed-workload escalation fraction may differ with its length distribution; as an initial hypothesis, predict 98% and 94% under load as well.

These latency predictions replace assumed stage times with existing A1 evidence. Sources are `results/accuracy/llama3.2_1b_predictions.csv` and `results/accuracy/gemma3_4b_predictions.csv`, restricted to the 87 row IDs in `golden_set/a2/tuning (odd).csv` before analysis. Join on `row`, using the original odd-row narrative length and Llama prediction to decide acceptance. Both models have one successful HTTP 200 record without an error for every tuning row. No even-row predictions are used.

For each tuning ticket `i` and threshold `c`, calculate `T_i(c) = llama_latency_seconds_i + I(escalate_i(c)) * gemma_latency_seconds_i`, where escalation follows the rule in `docs/escalation_rule.md`, including unclassified handling. Sort the 87 simulated times and take the 44th value. The result is **8.896 s for S1 and 8.896 s for S2**. This is the median of per-ticket sums, not the sum of model medians. For context, the measured A1 odd-row single-model medians are 2.301 s for Llama and 6.736 s for Gemma; their means are 2.668 s and 7.883 s.

The simulated mean is 10.458 s for S1 and 10.324 s for S2, compared with Gemma's historical mean of 7.883 s. This calculation retains the relationship between ticket length, routing and latency instead of multiplying the escalation fraction by the unconditional Gemma mean. S2 saves some mean time but does not move the middle ticket in this sample.

The A1 `latency_seconds` field is client-observed elapsed request time from `scripts/run_accuracy.py`, not pure inference time. Summing two single-request records also counts their individual service/network overhead twice. The records were collected in separate single-model runs, not a live resident cascade. Their cache, loading and machine conditions may differ from A2; this calculation does not establish warm inference-only timings. We adopt 8.9 s as the numerical A2 median hypothesis for each setting, with low confidence in transfer to load. A2 queueing, concurrent arrivals, workload lengths, prompt-cache state and model residency can change actual latency. No queueing adjustment is claimed without evidence. These are historical latency-based predictions, **not measured A2 performance**, and cannot replace fresh A2 speed runs.

## 4. Predicted category effects

Debt collection and Mortgage are expected to be particularly vulnerable to accuracy losses with S2; Credit reporting and Money transfer or service may also lose accuracy. In the tuning simulation, Gemma scored 6/9, 11/12, 14/16 and 10/15 respectively in these categories; S2 scored 5/9, 10/12, 13/16 and 9/15. This corresponds to losses of 11.11, 8.33, 6.25 and 6.67 percentage points respectively. The other three categories showed no net loss in that simulation. Do not assume that every incorrect accepted answer represents a loss relative to Gemma.

S1 is expected to have smaller losses overall, while S2 risks failing an individual category floor because of small category counts and more incorrect accepted predictions. The exact test-set category scores and qualifying single models are not yet known.

For S1, the only observed tuning loss relative to Gemma is Credit reporting: 14/16 to 13/16 (6.25 percentage points). The complete seven-category tuning counts and preliminary floors are recorded in `docs/escalation_rule.md`. Both S1 and S2 pass those preliminary checks using unrounded values; this does not establish an official pass. The preliminary overall floor is 65.86% rounded from Gemma's 66/87 tuning accuracy minus 10 percentage points, and each preliminary category floor is Gemma's tuning accuracy minus 15 points. Official floors must instead use the even-row reference.

## 5. Evaluation and freeze

Use Gemma's measured or validly reused even-row accuracy to establish the overall and seven per-category floors. Score all three singles and both live cascade settings, with failures counted incorrect. Reuse A1 single predictions only if model digest, prompt, Ollama version, machine and classification settings are verified unchanged; otherwise run fresh accuracy tests.

Compare these frozen predictions against the official accuracy results and the mean of the three measured run p50 values for each speed-tested configuration. Speed-test both cascade settings regardless of accuracy, plus Gemma and every other qualifying single. Use fresh A2 speed measurements only.

The Git commit containing this record and `docs/escalation_rule.md` must precede official measurements. Preserve the predictions after the freeze; explain deviations in the final presentation rather than revising this record.

The frozen settings map to benchmark IDs `cascade_s1` and `cascade_s2`. Before speed testing, the benchmark owner must replace the currently null `rule` and `rule_setting` fields in `jmeter/a2_configs.json` with `length` and 241/289 respectively. Before official accuracy testing, verify `/health` against the frozen configuration and confirm both models are resident. This review does not modify benchmark configuration files or execute official tests.
