# A2 evidence index

Evidence reviewed on 23 November 2026 against [main at c59826f](https://github.com/BryceTO/ict3113-a2-team15/commit/c59826f09b83ca7a90c6c715fbddaf300d2bbf24). Use this index to trace the figures in `Group15_A2.pptx` during deck integration.

Final file review on 25 November 2026 checked the same main snapshot. All evidence checks passed with seven recorded warnings. All 134 local source links resolved. Temporary-copy checks confirmed that missing required runs and altered source values cause failures.

## Run the evidence check

From the repository root, using Python 3.10 or newer:

```powershell
python -B scripts/check_a2_evidence.py
```

The checker uses Python’s standard library and reuses the repository’s accuracy scorer, speed summarizer and rate comparison. It checks split membership and labels, reruns the comparisons on saved records, checks required speed repeats, and verifies the chart data and the PNG checksum. Speed timelines are rebuilt in a temporary directory for comparison. Exit code `0` means the evidence checks passed, with any warnings printed separately. Exit code `1` means evidence is missing or differs from its source.

Speed checks also match warm-up request IDs to service logs, validate logged model and routing settings, and recompute stored-ticket totals from the before/after stats snapshots. Post-run health issues are printed as warnings. Split narrative comparisons allow LF/CRLF conversion, while the accuracy runner verifies the frozen even-row fingerprint using the preserved test-file content.

The review reconciled **440 primary accuracy requests**, **88 diagnostic accuracy requests**, and **360 speed samples across 12 runs**. The slide mappings below identify source figures for integration. Check the final slide text and figure labels against these sources after exporting the deck.

## Split, settings and freeze

| Item | Evidence |
|---|---|
| Frozen labels and held-out rows | [Golden set](../golden_set/golden_set.csv) · [87 odd tuning rows](../golden_set/a2/tuning%20%28odd%29.csv) · [88 even test rows](../golden_set/a2/test%20%28even%29.csv) |
| Experiment settings | [Configuration IDs and thresholds](../jmeter/a2_configs.json) · [written escalation rule](escalation_rule.md) · [prediction record](../predictions/a2_prediction_record.md) |
| Git history | [Split commit `1d27a6c`](https://github.com/BryceTO/ict3113-a2-team15/commit/1d27a6c) precedes [rule and prediction freeze `fafe5bf`](https://github.com/BryceTO/ict3113-a2-team15/commit/fafe5bf). The freeze precedes the primary accuracy runs. The split, rule and prediction files match the freeze on the reviewed main. |
| Speed workload | [Frozen row list](../jmeter/a2_workload_rows.csv) · [workload freeze `641d383`](https://github.com/BryceTO/ict3113-a2-team15/commit/641d383) · [selection method](a2_workload_selection.md). Each scored run used the same first 30 of 60 measured IDs. The workload is disjoint from all 175 golden IDs. |
| Calibration and pre-run checks | [Calibration record](../results/a2/calibration/a2_calibration.json) · [calibration log](../results/logs/a2_gemma3-4b_calibration.log) · [environment](a2_test_environment.md) · [JMeter playbook](a2_test_playbook.md) |
| Resident model pair | [Llama 1B + Gemma 4B residency check](../results/a2/residency/20261117-180010_llama3.2-1b__gemma3-4b/summary.md). For each speed run, use the metadata’s `health_before_run` snapshot for the loaded models. |

## Slide evidence

| Slide | What to show | Source |
|---|---|---|
| 1 · Cover and accuracy limits | Gemma A1 **134/175 (76.57%)**. Gemma A2 reference **69/88 (78.41%)**, overall floor **68.41%** and seven category floors. | [A1 requirements comparison](model_requirement_comparison.md) · [A2 floors and reference counts](../results/a2/accuracy/summary_reviewed_r1/floors.csv) |
| 2 · Cascade design | Llama first, then Gemma if Unclassified or length exceeds the threshold. S1 **241**, S2 **289** characters. Both models fit in the recorded residency check. | [Rule and rationale](escalation_rule.md) · [tuning settings](../results/a2/tuning/length_settings.csv) · [loaded model snapshot after alternation](../results/a2/residency/20261117-180010_llama3.2-1b__gemma3-4b/ps_3_after_alternating.json) |
| 3 · Test method | Calibration rows **15363, 15464, 15871** took **11.506, 8.506, 6.183 s**. Configured S **8.5 s**, **3.529412/min**, **510 s** arrival window, **300 s** timeout and **360 s** drain. | [Calibration record](../results/a2/calibration/a2_calibration.json) · [environment](a2_test_environment.md) · [workload rows](../jmeter/a2_workload_rows.csv) |
| 4 · Accuracy | Five configurations on 88 even rows, all category counts, floors and confusion matrices. S1 escalated **77/83** decided requests and S2 **81/87**. Both accepted groups scored **1/6**. | [Overall](../results/a2/accuracy/summary_reviewed_r1/overall.csv) · [categories](../results/a2/accuracy/summary_reviewed_r1/per_category.csv) · [eligibility](../results/a2/accuracy/summary_reviewed_r1/eligibility.csv) · [confusion matrices](../results/a2/accuracy/summary_reviewed_r1/confusion_matrices.csv) · [routing groups](../results/a2/accuracy/summary_reviewed_r1/cascade_escalation.csv) · [request reconciliation](../results/a2/accuracy/summary_reviewed_r1/service_reconciliation.csv) |
| 5 · Speed | Three p50s, mean and spread, pooled p95 and sample size, throughput, errors, counts and escalation. All 12 runs completed **30/30**, with zero errors and zero unfinished. Each cascade escalated **90/90**. | [Per-run summary](../results/a2/summary/a2_speed_runs.csv) · [configuration summary](../results/a2/summary/a2_speed_configs.csv) · raw speed files below |
| 6 · Accuracy and latency | Mean of three run p50s versus even-row accuracy. Mark both cascade category-floor failures. Label Llama as accuracy-failed and speed unmeasured. | [Chart](../results/a2/summary/a2_tradeoff.png) · [joined CSV](../results/a2/summary/a2_tradeoff.csv) · [chart method](a2_tradeoff.md) |
| 7 · Prediction and recommendation | Gemma **7.046 s** mean p50 and **78.41%** accuracy is the fastest qualifying option. Mistral **30.433 s** and **86.36%** offers **7.95 points** more accuracy. Both cascades were slower and failed category floors. | [Frozen predictions](../predictions/a2_prediction_record.md) · [category results](../results/a2/accuracy/summary_reviewed_r1/per_category.csv) · [speed results](../results/a2/summary/a2_speed_configs.csv) · [stage timings](../results/a2/summary/a2_speed_runs.csv) |
| 8 · Limitations, citations and AI use | Small category samples, workload and hardware limits, run caveats, **211.76/hour** scheduled versus the **9/hour** A1 peak, and the team's actual AI use. | [Rate comparison](../results/a2/summary/a2_rate_comparison.csv) · [limitations and licences](a2_slide8_limitations_references.md) · [accuracy incidents](a2_accuracy_incidents.md) |

## Accuracy runs

The [reviewed provenance](../results/a2/accuracy/summary_reviewed_r1/provenance.json) identifies the five primary runs. Use the original S1 **62/88** for the deck. Keep the diagnostic S1 **64/88** separate.

| Configuration | Accuracy run files | Service evidence |
|---|---|---|
| Gemma 4B | [Predictions](../results/a2/accuracy/a2_gemma3-4b_accuracy_20261119T085515Z/predictions.csv) · [Manifest](../results/a2/accuracy/a2_gemma3-4b_accuracy_20261119T085515Z/manifest.json) · [Journal](../results/a2/accuracy/a2_gemma3-4b_accuracy_20261119T085515Z/requests.jsonl) | [Log](../results/logs/a2_gemma3-4b_accuracy_20261119T085515Z.log) |
| Llama 1B | [Predictions](../results/a2/accuracy/a2_llama3.2-1b_accuracy_20261119T092405Z_e545b8fe/predictions.csv) · [Manifest](../results/a2/accuracy/a2_llama3.2-1b_accuracy_20261119T092405Z_e545b8fe/manifest.json) · [Journal](../results/a2/accuracy/a2_llama3.2-1b_accuracy_20261119T092405Z_e545b8fe/requests.jsonl) | [Log](../results/logs/a2_llama3.2-1b_accuracy_20261119T092405Z_e545b8fe.log) |
| Mistral 7B | [Predictions](../results/a2/accuracy/a2_mistral-7b-instruct_accuracy_20261119T093145Z_800e6ea1/predictions.csv) · [Manifest](../results/a2/accuracy/a2_mistral-7b-instruct_accuracy_20261119T093145Z_800e6ea1/manifest.json) · [Journal](../results/a2/accuracy/a2_mistral-7b-instruct_accuracy_20261119T093145Z_800e6ea1/requests.jsonl) | [Log](../results/logs/a2_mistral-7b-instruct_accuracy_20261119T093145Z_800e6ea1.log) |
| Cascade S1, primary | [Predictions](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/predictions.csv) · [Manifest](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/manifest.json) · [Journal](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/requests.jsonl) | [Log](../results/logs/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced.log) |
| Cascade S2 | [Predictions](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/predictions.csv) · [Manifest](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/manifest.json) · [Journal](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/requests.jsonl) | [Log](../results/logs/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7.log) |
| Cascade S1, diagnostic | [Predictions](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/predictions.csv) · [Manifest](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/manifest.json) · [Journal](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/requests.jsonl) | [Log](../results/logs/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f.log) |

## Speed runs

| Configuration and repeat | JMeter evidence | Service evidence |
|---|---|---|
| Gemma 4B r1 | [JTL](../results/a2/jtl/a2_gemma3-4b_speed_r1.jtl) · [Properties](../results/a2/jtl/a2_gemma3-4b_speed_r1.properties) · [Metadata](../results/a2/jtl/a2_gemma3-4b_speed_r1.meta.json) | [Log](../results/logs/a2_gemma3-4b_speed_r1.log) · [Timeline](../results/a2/summary/timeline/a2_gemma3-4b_speed_r1.csv) |
| Gemma 4B r2 | [JTL](../results/a2/jtl/a2_gemma3-4b_speed_r2.jtl) · [Properties](../results/a2/jtl/a2_gemma3-4b_speed_r2.properties) · [Metadata](../results/a2/jtl/a2_gemma3-4b_speed_r2.meta.json) | [Log](../results/logs/a2_gemma3-4b_speed_r2.log) · [Timeline](../results/a2/summary/timeline/a2_gemma3-4b_speed_r2.csv) |
| Gemma 4B r3 | [JTL](../results/a2/jtl/a2_gemma3-4b_speed_r3.jtl) · [Properties](../results/a2/jtl/a2_gemma3-4b_speed_r3.properties) · [Metadata](../results/a2/jtl/a2_gemma3-4b_speed_r3.meta.json) | [Log](../results/logs/a2_gemma3-4b_speed_r3.log) · [Timeline](../results/a2/summary/timeline/a2_gemma3-4b_speed_r3.csv) |
| Mistral 7B r1 | [JTL](../results/a2/jtl/a2_mistral-7b-instruct_speed_r1.jtl) · [Properties](../results/a2/jtl/a2_mistral-7b-instruct_speed_r1.properties) · [Metadata](../results/a2/jtl/a2_mistral-7b-instruct_speed_r1.meta.json) | [Log](../results/logs/a2_mistral-7b-instruct_speed_r1.log) · [Timeline](../results/a2/summary/timeline/a2_mistral-7b-instruct_speed_r1.csv) |
| Mistral 7B r2 | [JTL](../results/a2/jtl/a2_mistral-7b-instruct_speed_r2.jtl) · [Properties](../results/a2/jtl/a2_mistral-7b-instruct_speed_r2.properties) · [Metadata](../results/a2/jtl/a2_mistral-7b-instruct_speed_r2.meta.json) | [Log](../results/logs/a2_mistral-7b-instruct_speed_r2.log) · [Timeline](../results/a2/summary/timeline/a2_mistral-7b-instruct_speed_r2.csv) |
| Mistral 7B r3 | [JTL](../results/a2/jtl/a2_mistral-7b-instruct_speed_r3.jtl) · [Properties](../results/a2/jtl/a2_mistral-7b-instruct_speed_r3.properties) · [Metadata](../results/a2/jtl/a2_mistral-7b-instruct_speed_r3.meta.json) | [Log](../results/logs/a2_mistral-7b-instruct_speed_r3.log) · [Timeline](../results/a2/summary/timeline/a2_mistral-7b-instruct_speed_r3.csv) |
| Cascade S1 r1 | [JTL](../results/a2/jtl/a2_cascade_s1_speed_r1.jtl) · [Properties](../results/a2/jtl/a2_cascade_s1_speed_r1.properties) · [Metadata](../results/a2/jtl/a2_cascade_s1_speed_r1.meta.json) | [Log](../results/logs/a2_cascade_s1_speed_r1.log) · [Timeline](../results/a2/summary/timeline/a2_cascade_s1_speed_r1.csv) |
| Cascade S1 r2 | [JTL](../results/a2/jtl/a2_cascade_s1_speed_r2.jtl) · [Properties](../results/a2/jtl/a2_cascade_s1_speed_r2.properties) · [Metadata](../results/a2/jtl/a2_cascade_s1_speed_r2.meta.json) | [Log](../results/logs/a2_cascade_s1_speed_r2.log) · [Timeline](../results/a2/summary/timeline/a2_cascade_s1_speed_r2.csv) |
| Cascade S1 r3 | [JTL](../results/a2/jtl/a2_cascade_s1_speed_r3.jtl) · [Properties](../results/a2/jtl/a2_cascade_s1_speed_r3.properties) · [Metadata](../results/a2/jtl/a2_cascade_s1_speed_r3.meta.json) | [Log](../results/logs/a2_cascade_s1_speed_r3.log) · [Timeline](../results/a2/summary/timeline/a2_cascade_s1_speed_r3.csv) |
| Cascade S2 r1 | [JTL](../results/a2/jtl/a2_cascade_s2_speed_r1.jtl) · [Properties](../results/a2/jtl/a2_cascade_s2_speed_r1.properties) · [Metadata](../results/a2/jtl/a2_cascade_s2_speed_r1.meta.json) | [Log](../results/logs/a2_cascade_s2_speed_r1.log) · [Timeline](../results/a2/summary/timeline/a2_cascade_s2_speed_r1.csv) |
| Cascade S2 r2 | [JTL](../results/a2/jtl/a2_cascade_s2_speed_r2.jtl) · [Properties](../results/a2/jtl/a2_cascade_s2_speed_r2.properties) · [Metadata](../results/a2/jtl/a2_cascade_s2_speed_r2.meta.json) | [Log](../results/logs/a2_cascade_s2_speed_r2.log) · [Timeline](../results/a2/summary/timeline/a2_cascade_s2_speed_r2.csv) |
| Cascade S2 r3 | [JTL](../results/a2/jtl/a2_cascade_s2_speed_r3.jtl) · [Properties](../results/a2/jtl/a2_cascade_s2_speed_r3.properties) · [Metadata](../results/a2/jtl/a2_cascade_s2_speed_r3.meta.json) | [Log](../results/logs/a2_cascade_s2_speed_r3.log) · [Timeline](../results/a2/summary/timeline/a2_cascade_s2_speed_r3.csv) |

## Findings to retain in the deck

- **Cascade accuracy health.** Original S1, diagnostic S1 and S2 had five, one and one HTTP 502 failures respectively. The failed rows remain incorrect and their pre-routing failures remain unknown for escalation. Both primary cascades scored **7/11 (63.64%)** in Debt collection versus its **66.82%** floor, with zero backend failures in that category. [Validation flags](../results/a2/accuracy/summary_reviewed_r1/validation.json) · [incident record](a2_accuracy_incidents.md)
- **Calibration timing.** On 19 November, Gemma calibration was recorded at **20:08 SGT**, before the final primary accuracy run finished at **23:28 SGT**. All 12 scored speed runs started after accuracy finished. State the calibration timing as recorded, since the playbook places calibration after accuracy testing. [Calibration record](../results/a2/calibration/a2_calibration.json) · [S2 completion record](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/complete.json)
- **Queue growth.** Keep the possible queue-growth flags for S2 r2 and Mistral r1–r2. Gemma finished **90/90** with no queue-growth flags and a lowest achieved rate of **200.52/hour**. The capacity claim applies to the tested workload and environment. [Per-run summary](../results/a2/summary/a2_speed_runs.csv) · [rate interpretation](a2_rate_comparison.md)
- **Prediction comparison.** Gemma was predicted to be fastest among qualifying configurations. S1/S2 were predicted at **75%/71%** accuracy, **98%/94%** escalation and **8.896 s** median latency each. Recorded accuracy was **70.45%/72.73%**, and accuracy-set escalation among known decisions was **92.77%/93.10%**. Under load both escalated **100%** and their mean run p50s were **10.843 s/14.851 s**. The measured prefix’s shortest ticket had **497 characters**, above both thresholds. The prediction latency is a historical proxy for comparison. [Prediction record](../predictions/a2_prediction_record.md) · [accuracy results](a2_accuracy_results.md) · [speed summary](../results/a2/summary/a2_speed_configs.csv) · [workload rows](../jmeter/a2_workload_rows.csv)
