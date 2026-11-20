# A2 accuracy results and verification

This review uses the saved live A2 measurements, not regenerated predictions. The primary five-configuration comparison is [summary_reviewed_r1](../results/a2/accuracy/summary_reviewed_r1/). Its original S1 selection is recommended subject to team agreement; the separate controlled S1 rerun is diagnostic evidence. Cascade results retain post-run health warnings and must not be described as clean runs. See [the incident record](a2_accuracy_incidents.md).

## Method and frozen split

The 175-ticket golden set is partitioned by original row ID into [87 odd-row tuning tickets](../golden_set/a2/tuning%20%28odd%29.csv) and [88 even-row test tickets](../golden_set/a2/test%20%28even%29.csv). IDs are unique, disjoint and have the required parity. Only the odd rows were used to select the rule and thresholds. The even rows determine official accuracy and floors. Test-category counts are 22, 11, 15, 9, 12, 6 and 13 in the category order below, summing to 88.

The [rule](escalation_rule.md) and [prediction record](../predictions/a2_prediction_record.md) were frozen at `fafe5bfbf5b389e8e8f07cbda18a4a34cb6fe2f4`; both and the split files are unchanged relative to that commit. All six run manifests reference this freeze and live collection. The canonical even-set SHA-256 is `05967ef4b64a87efdc3b5f12e48d3564804ddeea190e41c0b158990a7be3a19c`, independently verified from sorted row/narrative/lowercase-label records. This is a canonical-data fingerprint, distinct from raw file hashes.

The [accuracy workflow](a2_accuracy_workflow.md) sends the 88 rows sequentially, once each, with a 630-second client timeout and no retries or redirects. Each saved run has 88 predictions and 176 journal events: one attempt and one response per row. Reserved warm-up IDs are -1, -2 and -3 and are excluded from scoring. Pre-run health/configuration and residency evidence, environment snapshots, model digests, deployed source, raw responses and service logs are retained. These are fresh A2 runs, not reused A1 predictions.

Every HTTP/backend failure, timeout, malformed response or invalid classification remains incorrect in the full 88-ticket denominator. The observed backend failures are HTTP 502, represented as `Failure`. `Unclassified` also counts incorrect. No failed row is dropped, replaced or retried within a scored attempt.

Llama 3.2 1B runs first in each cascade; Gemma 3 4B is the large model. S1 accepts classified Llama output at narrative length <=241 Unicode code points; S2 uses <=289. Longer narratives and `Unclassified` small-model output escalate. Length includes original whitespace. A failure before a routing decision is unknown, not an acceptance or escalation. True labels do not influence routing.

Saved environment evidence records Docker allocation of 22 logical CPUs and about 9.713 GiB. The original S1 and three single-model snapshots record 10,429,063,168 bytes; rerun S1 and S2 record 10,429,067,264 bytes, a 4,096-byte difference. Thus the saved byte totals are not exactly identical, with the intended fixed inference settings documented in [the environment record](a2_test_environment.md): context 4096, temperature 0, maximum generation 16, conditional `think=false`, keep-alive 30m and backend timeout 300 seconds. Environment copies and their recorded hashes match; this does not establish identical background load or thermal conditions. Those limitations are recorded separately.

## Reference and exact floors

Gemma 3 4B is the frozen reference, even though Mistral scores higher. Overall eligibility requires reference accuracy minus 10 percentage points; every category must also meet reference accuracy minus 15 points. Comparisons use exact rational values, not rounded display percentages. There is no substitution of the tuning floors or of Mistral as reference.

| Scope | Gemma correct/total | Exact floor (%) | Decimal floor (%) |
|---|---:|---:|---:|
| Overall | 69/88 | 1505/22 | 68.4090909090909… |
| Credit reporting | 21/22 | 885/11 | 80.4545454545454… |
| Debt collection | 9/11 | 735/11 | 66.8181818181818… |
| Mortgage | 15/15 | 85 | 85 |
| Credit card | 9/9 | 85 | 85 |
| Bank account or service | 7/12 | 130/3 | 43.3333333333333… |
| Consumer loan | 1/6 | 5/3 | 1.6666666666666… |
| Money transfer or service | 7/13 | 505/13 | 38.8461538461538… |

Source: [floors.csv](../results/a2/accuracy/summary_reviewed_r1/floors.csv). The exact overall floor requires at least 61/88 correct; passing overall alone does not establish eligibility.

## Overall results

| Configuration | Correct | Incorrect | Accuracy | Backend failures | Overall floor | All category floors | Accuracy eligible | Speed required |
|---|---:|---:|---:|---:|---|---|---|---|
| Llama 3.2 1B | 17/88 | 71 | 19.32% | 0 | Fail | Fail | No | No |
| Gemma 3 4B | 69/88 | 19 | 78.41% | 0 | Pass | Pass | Yes | Yes |
| Mistral 7B Instruct | 76/88 | 12 | 86.36% | 0 | Pass | Pass | Yes | Yes |
| Cascade S1, original | 62/88 | 26 | 70.45% | 5 | Pass | Fail | No | Yes |
| Cascade S2 | 64/88 | 24 | 72.73% | 1 | Pass | Fail | No | Yes |

Sources: [overall.csv](../results/a2/accuracy/summary_reviewed_r1/overall.csv) and [eligibility.csv](../results/a2/accuracy/summary_reviewed_r1/eligibility.csv). The controlled S1 rerun scores 64/88 (72.73%), with 24 incorrect and one backend failure; it still fails the Debt collection floor. It is not substituted into the primary summary.

## Per-category results

Each cell is correct/total (accuracy); **F** means below that category's exact floor. All unmarked cells pass.

| Category | Llama | Gemma | Mistral | S1 original | S2 |
|---|---|---|---|---|---|
| Credit reporting | 6/22 (27.27%) **F** | 21/22 (95.45%) | 20/22 (90.91%) | 19/22 (86.36%) | 19/22 (86.36%) |
| Debt collection | 0/11 (0%) **F** | 9/11 (81.82%) | 11/11 (100%) | 7/11 (63.64%) **F** | 7/11 (63.64%) **F** |
| Mortgage | 0/15 (0%) **F** | 15/15 (100%) | 15/15 (100%) | 14/15 (93.33%) | 14/15 (93.33%) |
| Credit card | 0/9 (0%) **F** | 9/9 (100%) | 8/9 (88.89%) | 8/9 (88.89%) | 9/9 (100%) |
| Bank account or service | 11/12 (91.67%) | 7/12 (58.33%) | 10/12 (83.33%) | 7/12 (58.33%) | 7/12 (58.33%) |
| Consumer loan | 0/6 (0%) **F** | 1/6 (16.67%) | 4/6 (66.67%) | 0/6 (0%) **F** | 1/6 (16.67%) |
| Money transfer or service | 0/13 (0%) **F** | 7/13 (53.85%) | 8/13 (61.54%) | 7/13 (53.85%) | 7/13 (53.85%) |

Source: [per_category.csv](../results/a2/accuracy/summary_reviewed_r1/per_category.csv). The controlled S1 rerun has the same per-category correct counts as S2. Small denominators matter: losing Gemma's sole correct Consumer loan ticket drops original S1 below the 5/3% floor; both primary cascades lose two correct Debt collection outcomes relative to Gemma and fail that category.

**Debt collection fails independently of infrastructure errors in all three cascade attempts:** original S1, diagnostic S1 and S2 each score 7/11 (63.64%), below the exact 735/11% (66.8181818...%) floor. Each has zero backend failures in that category. Even if every failed request in the other categories were hypothetically correct, with the remaining observed predictions held fixed, all three attempts would remain accuracy-ineligible. This does not impute missing predictions or revise any saved score.

## Confusion matrices

All 315 cells in [confusion_matrices.csv](../results/a2/accuracy/summary_reviewed_r1/confusion_matrices.csv) were independently checked against the saved predictions: five matrices, each with seven true-label rows and nine prediction columns (seven categories, `Unclassified`, `Failure`). Every matrix totals 88, every row matches its test-category count, and diagonals total 17, 69, 76, 62 and 64 for Llama, Gemma, Mistral, original S1 and S2 respectively. Off-diagonal totals are 71, 19, 12, 26 and 24. Failure columns total 0, 0, 0, 5 and 1 and remain part of those totals.

Llama strongly overpredicts Bank account or service: it receives 16 Credit reporting, 12 Mortgage, 12 Money transfer or service and 10 Debt collection tickets incorrectly. Gemma and Mistral each send four Money transfer or service tickets to Bank account or service. Mistral has perfect Debt collection and Mortgage recall, but still misses five of 13 Money transfer or service tickets. S2 sends five Money transfer or service tickets to Bank account or service; original S1 sends three, with its failures also retained in the matrix. These are observed errors, not evidence that routing alone caused every difference.

## Cascade routing and accuracy

| Attempt | Known decisions | Escalated / known | Accepted correct/count | Escalated correct/count | Unknown correct/count |
|---|---:|---:|---:|---:|---:|
| S1 original | 83/88 | 77/83 (92.77%) | 1/6 (16.67%) | 61/77 (79.22%) | 0/5 (0%) |
| S1 controlled rerun | 87/88 | 81/87 (93.10%) | 1/6 (16.67%) | 63/81 (77.78%) | 0/1 (0%) |
| S2 | 87/88 | 81/87 (93.10%) | 1/6 (16.67%) | 63/81 (77.78%) | 0/1 (0%) |

Sources: [cascade_escalation.csv](../results/a2/accuracy/summary_reviewed_r1/cascade_escalation.csv), [cascade_routing.csv](../results/a2/accuracy/summary_reviewed_r1/cascade_routing.csv), and the rerun's predictions and service log linked in the incident record. Routing groups partition every attempt into 88 rows, and their correct counts sum to overall correctness.

The reported escalation fraction uses only known decisions. Confirmed escalations as a share of all tickets are 77/88 (87.50%) for original S1 and 81/88 (92.05%) for the other two attempts. Unknown decisions must not be imputed. If every unknown had escalated, the upper bound would be 82/88 (93.18%) in each attempt. All observed unknowns are matched HTTP 502 service records with `routing=not_reached`, not missing reconciliation evidence. Original S1 unknown rows are 15166, 15168, 15170, 15172 and 15174; rerun S1 and S2 have only 15174.

## Infrastructure findings and whether another accuracy run is needed

The [infrastructure investigation](a2_accuracy_incidents.md#confirmed-failure-mechanism-and-residency-limits) confirms the immediate failure mechanism in all seven failed request instances: the raw response journals contain `NameResolutionError` with `[Errno -3] Temporary failure in name resolution` for backend hostname `ollama` while attempting `/api/generate`. Original S1 contributes five failures, diagnostic S1 one and S2 one. Each service record has `error_stage=small` and `routing=not_reached`; the request failed before small-model inference and the routing decision. The underlying reason for the name-resolution failure remains unconfirmed. These observations do not prove an Ollama crash, a memory leak or a specific Docker/WSL defect.

All three post-run `/health` calls returned HTTP 200 and body `status=ok`, but separately reported the backend down. The service catches a failed `/api/ps` query and supplies an empty model list; therefore `loaded_models=[]` and `all_configured_loaded=false` do not establish that models were unloaded. Both models were resident before each attempt. Successful official requests have maximum recorded model-load durations below 20 ms in all three attempts, with no >1-second possible-reload indication. This is not continuous residency evidence through the failure interval.

The saved diagnostic S1 memory snapshot records 8.744 GiB / 9.713 GiB (90.03%); S2 records 2.02 GiB / 9.713 GiB. Memory pressure is suspected, not confirmed as causal: the snapshots are not continuous or synchronized to each failure, and no contemporaneous kernel OOM diagnosis is established. The earlier 8.745 GiB observation remains operator-reported. Original S1 has Docker management HTTP 500 errors and later recovered container states with `OOMKilled=false`, exit code 255 and finish times after the request failures. Diagnostic S1 and S2 status snapshots list both containers running. None of these observations establishes a common container-termination cause for all three attempts. Detailed sources and limitations remain in the incident record.

The saved scores remain valid observed end-to-end accuracy measurements with failures counted incorrect, rather than clean classifier-only accuracy estimates. Original S1 and its diagnostic rerun differ only on four previously failed rows: two become correct and two remain incorrect after successful classification. Diagnostic S1 and S2 have identical final predictions across all 88 rows. Preserve original S1 as the proposed primary comparison, subject to team agreement, and retain the rerun as diagnostic evidence; retain all health warnings and `review_required=true`.

**No additional accuracy rerun is currently necessary** to validate recorded scores or establish observed eligibility: record integrity is verified, a diagnostic rerun already exists, and Debt collection fails without backend failures in every cascade attempt. Correcting only the infrastructure-failed outcomes would not change that eligibility conclusion. First investigate infrastructure stability before speed benchmarking, preserving the A2 machine/resource allocation, model digests, inference settings and thresholds. A new separately identified accuracy attempt is justified only to test a specific corrective action or satisfy an explicit healthy-run requirement; it must not overwrite, merge or replace the existing attempts. No inference or infrastructure changes were performed in this review.

## Comparison with frozen predictions

| Frozen hypothesis | Saved outcome |
|---|---|
| S1 overall 75% | Original 70.45%, a -4.55 percentage-point deviation; diagnostic rerun 72.73%, -2.27 points |
| S2 overall 71% | 72.73%, +1.73 percentage points |
| S1 escalation 98%; S2 94% | Known-decision fractions 92.77% and 93.10%, deviations -5.23 and -0.90 points; unknown routing prevents an unconditional point estimate |
| Both cascades tentatively pass both floors | Neither primary cascade qualifies; original S1 fails Debt collection and Consumer loan, S2 fails Debt collection; rerun S1 also fails Debt collection |
| Llama fails overall; Mistral eligibility uncertain | Llama fails; Mistral passes overall and every category |
| S2 especially vulnerable in Debt collection and Mortgage, possibly Credit reporting and Money transfer | Versus Gemma, S2 loses 18.18, 6.67 and 9.09 points in Debt collection, Mortgage and Credit reporting, respectively; Money transfer is unchanged |
| S1 smaller losses than S2 | Original S1 is worse overall, with more backend failures; controlled S1 and S2 have equal aggregate accuracy. This is not an isolated causal test of thresholds |
| Gemma fastest qualifying configuration; both cascades slower; median 8.896 s each | Unresolved by accuracy runs. Requires fresh comparable speed measurements |

The frozen latency hypothesis is an A1 odd-row per-ticket proxy, not measured A2 load performance. Neither predictions nor thresholds have been revised to fit these outcomes.

## Speed benchmarking requirements

Follow [the speed-test playbook](a2_test_playbook.md): speed-test Gemma, Mistral, S1 and S2, three repeats each (12 runs). Llama does not qualify. Both cascades remain mandatory despite accuracy ineligibility. Accuracy eligibility and run-health review are separate concerns; investigate and document stability before load collection, retaining failed attempts and warnings.

Use the same service/load-generator machines and CPU/RAM allocation as A1, fixed inference settings/digests, an idle service host, and the frozen workload and network path. The committed [benchmark configuration](../jmeter/a2_configs.json) already sets `rule=length` with `rule_setting="241"` for S1 and `rule_setting="289"` for S2, matching the frozen rule; verify these settings before speed testing. Restart Ollama before each run, use the prescribed three warm-ups, verify configured models are resident and keep warm-up timings out of measured results. Interleave r1 across configurations, then r2, then r3.

Use the prescribed Gemma calibration median S, rounded to 0.1 s: arrival interval 2S seconds, rate 30/S per minute, arrival window max(S,5) minutes, timeout max(10S,300) seconds, drain timeout+60 seconds. The committed [calibration record](../results/a2/calibration/a2_calibration.json) supplies S = 8.5 s: interval 17 s, rate 3.529412 per minute, arrival window 8.5 minutes, timeout 300 s and drain 360 s. Use matched repeat seeds and a non-wrapping feeder. Report per-run successful-request p50 and its mean, standard deviation and spread across repeats; pooled p95 with sample count; throughput, errors, unfinished/cut-off requests, backlog, routing and stage timings. Reconcile JMeter records to service logs and stats. Compare the mean of the three run p50 values with the frozen 8.896-second cascade hypotheses. Sequential accuracy latencies cannot decide the speed winner.

## Verification and staging limitations

The read-only review checked all six saved attempts: 528 predictions, 1,056 journal events and 528 unique official service-log matches. The primary summary's 440 reconciliation rows and 176 routing rows agree with raw evidence. No unmatched official service records were found. The primary summary's `possible_reload_requests=0` agrees with its logged load durations under the scorer's >1-second heuristic; that is not proof of perfect runtime stability.

All 259 recorded SHA-256 comparisons passed, covering 249 distinct files: six completion records' prediction/health hashes, manifest runner hashes, both sets of environment hash lists, summary output hashes and provenance hashes for manifests, predictions, logs and scorer. All 111 run-local environment files match their corresponding environment-directory copies byte for byte. This verifies recorded hashes, not an external signature or complete hash coverage: some supplementary incident files have no recorded checksum. The canonical test fingerprint also matches. Exact floor and eligibility decisions, overall/category counts, and routing fractions were independently recalculated without executing inference or writing predictions or summaries.

The preserved [validation.json](../results/a2/accuracy/summary_reviewed_r1/validation.json) still has `review_required=true`, unhealthy post-run S1/S2 entries, zero unmatched evidence and zero possible reload requests. The S1 rerun separately retains the same health warning.

**Git byte preservation:** targeted attributes now disable text conversion for all files under `results/a2/accuracy/` and the six matching accuracy logs under `results/logs/`. Explicit `text eol=crlf` rules cover the tracked runner, scorer and both split CSVs, reproducing the working-tree bytes used by source hashes and embedded narrative lengths without changing their existing LF Git blobs. Of the 249 distinct files whose recorded hashes were checked, 239 contain CRLF and 10 are LF-only. Evidence bytes and recorded hashes must remain unchanged; do not normalize evidence or regenerate hashes. These attributes are committed on `main` with the evidence package. Future evidence changes still require staged-blob and checkout verification to preserve the recorded bytes.

**Privacy review:** the earlier hostname finding was a false positive: `desktop-linux` in original S1's `docker_failure_version.txt` is a Docker context name, not a machine hostname. The targeted scan found no confirmed machine hostname, username, host-specific absolute path, email address or credential-like value. Recovery/failure logs retain Docker-internal addresses, ports and container identifiers. Request journals contain complete complaint narratives matching the frozen test tickets, including dataset redaction placeholders; the scan does not certify that all narratives are free of personal information. The contributor acknowledges that the repository is public, has removed the earlier coursework-only access condition, and individually approves inclusion of all six unmodified journals provided dataset terms and assignment requirements permit public redistribution. No team-wide approval is claimed. [The repository source log](references.md) identifies the CFPB Consumer Complaint Database as the dataset origin. [CFPB's database page](https://www.consumerfinance.gov/data-research/consumer-complaints/) expressly makes its published complaint data available for use, analysis and building on; this supports reuse of the published dataset. The [general legal notice](https://www.consumerfinance.gov/privacy/website-privacy-policy/) distinguishes CFPB-created public-domain material from third-party material, so this review does not label all consumer-authored narratives public domain.

The repository README requires committing the golden split while keeping the full Team 15 source extract local; the speed playbook separately excludes private workload files. None of those excluded source/workload files is in the reviewed manifest. However, the authoritative A2 assignment brief is absent from this checkout, so assignment-level permission to redistribute the narratives publicly has not been independently established. The contributor previously explicitly authorized local staging of the complete 185-file package, including all six journals, without committing or pushing. This local-staging authorization does not establish assignment-level publication permission or team-wide approval.

**Committed package structure:** the reviewed manifest contains 185 files: 160 files across all six attempt directories (including run-local environment and incident evidence), 16 summary files, six original service logs, these two documents and `.gitattributes`. Preserve original S1 as the proposed primary result, subject to team agreement, and its controlled rerun as diagnostic evidence. The 111 duplicate files under `results/a2/environment/` were excluded from the committed package; the package uses their byte-identical run-local copies. Their presence in a local checkout is not required. Keep the five summary service-log copies because the summary completion record hashes them. The four incident logs ignored by the general log rule were included through targeted force-adds under the contributor's explicit local-staging authorization and are now tracked. Every documentation link resolves within this package or existing tracked files. The 185-file package was subsequently committed in `e6f38e8`, followed by the DNS investigation documentation in `053ef9f`; both are integrated into `main` through merge commit `47f9dd0` (PR #11). Integration does not establish team-wide approval or resolve the assignment-verification limitation.
