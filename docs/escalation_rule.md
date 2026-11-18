# ICT3113 Assignment 2 — Team 15: Escalation rule

## 1. Configuration

Use the existing `POST /tickets` cascade with Llama 3.2 1B as the small model and Gemma 3 4B (the A1 reference) as the large model. The rule is fixed to `length` for both settings.

| Environment variable | S1 | S2 |
|---|---|---|
| MODE | cascade | cascade |
| SMALL_MODEL | llama3.2:1b | llama3.2:1b |
| LARGE_MODEL | gemma3:4b | gemma3:4b |
| RULE | length | length |
| RULE_SETTING | 241 | 289 |

Thresholds are inclusive and measured using Python `len(narrative)` on the original submitted string (Unicode code points, including whitespace), not tokens or bytes.

The benchmark configuration IDs are `cascade_s1` (S1) and `cascade_s2` (S2), matching `jmeter/a2_configs.json` and `jmeter/a2_run_load.ps1`. At this freeze, the JSON has the correct model pair but both `rule` and `rule_setting` are still `null`. The benchmark owner must populate `length` and the corresponding frozen threshold before speed testing; the runner currently warns and records the service values when these fields are null. This document does not change those files. Before official accuracy testing, verify the running service's `/health` reports the selected pair, rule and setting.

## 2. Decision logic

1. Reject an empty or whitespace-only narrative using the existing HTTP 422 behavior.
2. Classify every valid ticket with Llama using the unchanged classification prompt and category matching logic.
3. If the matched category is `Unclassified`, escalate regardless of length.
4. Otherwise, accept Llama's category if the narrative has at most the configured number of characters. Escalate if it exceeds the threshold.
5. On escalation, classify the same narrative with Gemma and use its result as final, including `Unclassified` if returned. Do not retry or substitute another classifier. A backend exception follows the existing HTTP 502 path; an error before the routing decision is not an accepted or escalated ticket.
6. On successful completion, store one final ticket and return the unchanged API response (`id`, `category`). No classification-result caching is used.

```text
small_category = classify(llama, narrative)
if small_category == Unclassified or len(narrative) > threshold:
    final_category = classify(gemma, narrative)
else:
    final_category = small_category
```

Unlike direct length-based routing, this design always pays the small-model inference cost. It uses the existing cascade implementation without service changes. The true label is never used for routing.

Category matching strips and lowercases the model output, accepts an exact category match, or uses the category mentioned earliest in the output. If no category is mentioned, it returns `Unclassified`. The seven categories are listed in the table below. A small-model backend failure stops the request with HTTP 502 without calling Gemma; a large-model failure remains a logged escalation but has no final classification or stored ticket. Do not interpret the fallback `model` field on a failed request as a successful `final_model`.

## 3. Tuning evidence and selection

The frozen golden set was split into 87 odd-row tuning tickets and 88 even-row test tickets. Only odd-row A1 predictions and their labels were used for offline rule selection. The even rows are reserved for official evaluation. The offline simulation combines historical Llama and Gemma predictions according to the rule; it is not a live cascade measurement.

On the tuning set, Llama classified 17/87 correctly (19.54%); Gemma classified 66/87 correctly (75.86%). A provisional overall floor of 65.86% and category floors of Gemma's tuning category accuracy minus 15 percentage points were used to screen settings. Official floors will instead come from Gemma's even-row accuracy.

Category-based acceptance was investigated first. Llama predicted Bank account or service 78 times, with only 13 correct; Mortgage was correct in its sole prediction. Mortgage-only acceptance escalated 86/87 tickets (98.85%), so it provided very little evidence of reliable acceptance. Length was also a weak signal: Llama's shortest quartile scored 6/22, compared with 3/22 for the longest quartile. Length-based routing nevertheless offered two differentiated settings satisfying both provisional floors without an additional routing inference.

| Tuning simulation | S1: 241 | S2: 289 |
|---|---:|---:|
| Correct / total | 65/87 | 62/87 |
| Overall accuracy | 74.71% | 71.26% |
| Accepted by Llama | 2 | 5 |
| Incorrect accepted predictions | 1 | 4 |
| Escalated to Gemma | 85 | 82 |
| Escalation fraction | 97.70% | 94.25% |
| Provisional overall and category floors | Pass | Pass |

All 87 historical requests succeeded for both models, so there are no unknown routing decisions in these simulations. The overall preliminary floor is exactly `(66/87 * 100) - 10` percentage points (65.86% rounded); comparisons use unrounded values. Per-category checks are:

| True category | Gemma correct / total (%) | Preliminary floor (%) | S1 correct / total (%) | S2 correct / total (%) |
|---|---:|---:|---:|---:|
| Credit reporting | 14/16 (87.50) | 72.50 | 13/16 (81.25) | 13/16 (81.25) |
| Debt collection | 6/9 (66.67) | 51.67 | 6/9 (66.67) | 5/9 (55.56) |
| Mortgage | 11/12 (91.67) | 76.67 | 11/12 (91.67) | 10/12 (83.33) |
| Credit card | 13/13 (100.00) | 85.00 | 13/13 (100.00) | 13/13 (100.00) |
| Bank account or service | 10/13 (76.92) | 61.92 | 10/13 (76.92) | 10/13 (76.92) |
| Consumer loan | 2/9 (22.22) | 7.22 | 2/9 (22.22) | 2/9 (22.22) |
| Money transfer or service | 10/15 (66.67) | 51.67 | 10/15 (66.67) | 9/15 (60.00) |

These are tuning diagnostics, not official A2 accuracy results. Small category counts make the checks fragile: one ticket in a nine-ticket category changes accuracy by 11.11 percentage points.

S1 is the conservative setting; S2 accepts more small-model answers while preserving the provisional floors. A larger tested threshold of 393 characters passed the provisional overall floor but failed the debt collection category floor. These results motivate the selection; they do not guarantee official accuracy compliance or a speed improvement.

## 4. Residency and fixed conditions

The Llama–Gemma pair passed alternating-call residency verification on the original service host. Retain the evidence under `results/a2/residency/20261117-180010_llama3.2-1b__gemma3-4b/`. Before scored cascade runs, warm both models and verify both remain resident using `ollama ps`. Keep the A1 model digests, classification prompt, CPU-only hardware and inference options fixed. The documented container configuration is Ollama 0.35.0, parallelism 1, queue 512, context 4096 and keep-alive 30m; verify the effective settings before runs.

`ps_2_after_both.json` and `ps_3_after_alternating.json` list both models; `calls.csv` records three alternating rounds with no reload above the check's one-second load-duration criterion. `environment.json` records the model digests, 22 Docker CPUs, 9.713 GiB Docker memory and no extra container CPU or memory limit. This establishes residency for that check, not guaranteed residency during future runs. The service also fixes temperature at 0 and `num_predict` at 16, disables thinking where supported, and leaves thread count at the Ollama default. Preserve these settings and the existing `PROMPT` for both stages.

## 5. Official evaluation and logging

Evaluate both frozen settings on all 88 even-row tickets. Count failures and unclassified answers as incorrect. Derive overall accuracy and all seven category accuracies against the Gemma even-row reference, using the 10 and 15 percentage-point tolerances respectively. Report counts, percentages and confusion matrices.

Join requests and service logs by request ID, validating row IDs. Use the logged `routing`, `escalated`, `escalation_reason`, `final_model`, category, status and stage timings where available. Escalation fraction = escalated decisions / all reached routing decisions (including escalations whose large-model call fails). Report unknown routing separately; report correct/total for accepted and escalated groups.

Both settings must undergo fresh speed testing even if either fails accuracy. Keep rule and thresholds unchanged after the pre-test Git freeze. High escalation means both settings may be slower than Gemma alone; this is a valid outcome, not a reason to retune on test results.

## 6. Reproduction evidence

- `golden_set/a2/tuning (odd).csv` and `golden_set/a2/test (even).csv`
- `scripts/tune_cascade.py` and `scripts/tune_length.py`
- `results/a2/tuning/category_reliability.csv`, `cascade_settings.csv`, `length_reliability.csv`, `length_settings.csv`, `tuning_predictions.csv`
- `results/a2/residency/`
- Existing `service/main.py` and `docker-compose.yml`

The Git commit containing this document and the prediction record establishes the pre-measurement freeze. Do not alter the selected settings based on official test outcomes.
