# A2 accuracy incidents

The immediate failure mechanism is confirmed: the triage service could not resolve the backend hostname `ollama`. The underlying infrastructure root cause remains unconfirmed. Memory pressure is a suspected contributing factor, not a confirmed cause. The saved failures, predictions and validation warnings are retained without changes. All failures remain incorrect predictions in the full 88-ticket denominator.

## Attempts and evidence

| Attempt | Saved run directory | Correct | Accuracy | HTTP 502 backend failures | Post-run Ollama health |
|---|---|---:|---:|---:|---|
| Original S1 | [20261119T100108Z_bcf82ced](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/) | 62/88 | 70.45% | 5 | Unhealthy |
| Controlled S1 rerun | [20261119T122549Z_e6fa148f](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/) | 64/88 | 72.73% | 1 | Unhealthy |
| S2 | [20261119T151248Z_959b77e7](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/) | 64/88 | 72.73% | 1 | Unhealthy |

Each linked directory contains `manifest.json`, `predictions.csv`, `requests.jsonl`, `complete.json`, `health_before.json`, `health_after.json` and environment evidence. The corresponding service logs are [original S1](../results/logs/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced.log), [rerun S1](../results/logs/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f.log) and [S2](../results/logs/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7.log).

All attempts completed 88 saved prediction records. Original S1 failed rows 15166, 15168, 15170, 15172 and 15174; the other two attempts failed row 15174. Each failure reconciles to HTTP 502 in the service log and `routing=not_reached`; none is an accepted or escalated result. Accuracy is 62/88 or 64/88, not accuracy over successful requests only.

All three `health_after.json` files contain `Service/Ollama not healthy`. Each `/health` response has HTTP status 200 and body `status=ok`, while separately reporting the backend as down. The [health implementation](../service/main.py) catches an exception from `/api/ps` and sets `loaded_models=[]` and `all_configured_loaded=false`. Those values mean residency could not be established through that query; they do not prove that either model was unloaded or that the Ollama process crashed. These warnings are not erased by completion markers or by later recovery. The primary [validation record](../results/a2/accuracy/summary_reviewed_r1/validation.json) remains `review_required=true`.

## Confirmed failure mechanism and residency limits

The raw response bodies in the [original S1 journal](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/requests.jsonl), [diagnostic S1 journal](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/requests.jsonl) and [S2 journal](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/requests.jsonl) identify all **seven failed requests** as `NameResolutionError`: `Failed to resolve 'ollama' ([Errno -3] Temporary failure in name resolution)` while attempting `/api/generate`. These are seven request instances across three attempts, not seven distinct test rows. Service logs record `error_stage=small` and `routing=not_reached` for each one. The failure occurred before small-model inference and the acceptance/escalation decision; it is not a model classification error. The complete response journals supply the detail truncated in the service's error field and health response.

This establishes a hostname-resolution failure on the triage-to-Ollama path, but not why resolution failed. The evidence does not isolate Docker's resolver, network endpoints, daemon, WSL or host resource pressure as the initiating cause. The repeated final-row failure at 15174 does not establish a narrative-triggered model defect, because that request did not reach inference.

All three pre-run health snapshots report both configured models loaded, and their `environment/residency.json` files record the expected model digests and context length. The maximum recorded model-load duration across successful official requests is 16.267133 ms for original S1, 7.649551 ms for diagnostic S1 and 19.712734 ms for S2. None crosses the scorer's >1-second possible-reload threshold. These observations support pre-run residency and show no logged large reload delay; they do not establish continuous residency during the failure interval. The three archived `environment/deployed_main.py` files are byte-identical.

## File-verified observations

Original S1's `docker_failure_status.txt`, `docker_failure_stats.txt` and `docker_failure_version.txt` record Docker management requests returning **HTTP 500 Internal Server Error**. These management failures are distinct from the HTTP 502 ticket predictions. Do not generalize the original Docker 500 observation to every subsequent attempt.

The diagnostic S1 and S2 `docker_failure_status.txt` snapshots list both triage and Ollama containers as running. Together with the service returning HTTP 502 and HTTP 200 health responses, this rules out treating all three incidents as demonstrated container termination. It does not establish that the backend was reachable or healthy merely because its container was running.

The authoritative saved memory measurement is **8.744 GiB / 9.713 GiB (90.03%)** for Ollama in the controlled S1 rerun's [docker_failure_stats.txt](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/docker_failure_stats.txt). S2's saved stats show 2.02 GiB / 9.713 GiB. These are snapshots, not a continuous memory trace or proof of usage at the exact failure instant. The earlier **8.745 GiB / 9.713 GiB** observation was reported by the operator from PowerShell output shared in a troubleshooting conversation; no separate matching saved repository measurement was found. It must not replace the file-verified 8.744 GiB value.

Recovered original S1 container states are saved in [ollama_container_state.json](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/ollama_container_state.json) and [triage_container_state.json](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/triage_container_state.json). Both report `Status=exited`, `Running=false`, **`OOMKilled=false`** and **`ExitCode=255`**, with empty `Error`. Their recorded finish times are approximately 10:28:15 UTC, after the original run completed at 10:18:01 UTC. They are recovered states, not a contemporaneous diagnosis of each failed inference. `OOMKilled=false` does not prove absence of host/WSL memory pressure, and exit 255 is not a confirmed explanation.

The original `ollama_container_recovery.log` and `triage_container_recovery.log`, plus rerun/S2 `ollama_failure.log`, preserve available runtime output. The triage recovery log includes the five original HTTP 502 responses. These logs and snapshots do not establish a unique causal chain from memory, heat, Docker or WSL to the failed requests.

## Operator-reported recovery and cleanup

The operator supplied the following account during this documentation review, referring to terminal output shared in the troubleshooting conversation. These actions and RAM observations are **operator-reported**, not independently verified from separate repository evidence files:

- Shut down Docker Desktop and WSL2 with `wsl --shutdown`; allow the laptop to cool following excessive heat.
- Restart Docker Desktop and verify that container management commands work again.
- Stop unrelated PostgreSQL and MongoDB containers.
- Close unnecessary background applications: ChatGPT desktop, Discord, OneDrive, WhatsApp, Xbox and Notion; close Chrome before S2.
- Recover available physical RAM from 1.83 GB to 5.75 GB after application cleanup; observe 6.31 GB available after shutting down WSL following ZD's calibration.
- Preserve the original inference settings, model digests, Docker resource allocation and frozen cascade thresholds.

The repository independently retains per-run settings/digest/resource snapshots and the frozen thresholds, but these do not prove the full cleanup sequence or the reported free-RAM measurements. No new evidence file was fabricated to backfill that account. A controlled rerun denotes a separately identified troubleshooting attempt, not a claim that every environmental variable was experimentally controlled. The rerun and S2 still experienced post-run Ollama health failures despite the reported recovery measures.

## Interpretation and recommended comparison

Retain the original S1 attempt as the primary S1 comparison, **subject to team agreement**, and retain the controlled rerun as diagnostic evidence. This matches the existing `summary_reviewed_r1` provenance, preserves the first complete frozen-setting attempt and avoids selecting the more favorable score after observing failures. It is a recommendation, not evidence that team approval has already occurred or that the original run was healthy.

The diagnostic rerun improves by two correct predictions (2.27 percentage points) and reduces backend failures from five to one. It still fails the Debt collection category floor, so substituting it would not make S1 accuracy eligible. Its aggregate category and routing counts match S2, which limits claims that the threshold change explains the primary S1/S2 difference. Neither the improvement nor high memory usage proves a root cause. Memory pressure remains suspected; thermal effects and Docker/WSL instability are possible contextual factors without a confirmed attribution.

Direct prediction comparison finds only four changed outcomes between original and diagnostic S1: failed rows 15166 and 15170 become correct, while 15168 and 15172 become successful but incorrect classifications. All other final predictions are unchanged, including the failure at 15174. Diagnostic S1 and S2 have identical final predictions on all 88 rows. No predictions are substituted across runs.

**Debt collection scores 7/11 (63.64%) in all three cascade attempts, below the exact 735/11% (66.8181818...%) floor, with zero backend failures in that category.** All 11 Debt collection requests completed in each attempt. Even if every infrastructure-failed request elsewhere were hypothetically correct, leaving the other observed predictions fixed, each cascade attempt would still fail this category floor and remain accuracy-ineligible. This is a bound on the recorded eligibility outcome, not a claim that a new run could never produce different predictions.

## Accuracy validity and rerun decision

The failures affected observed scores but did not invalidate the recorded end-to-end accuracy calculation: every attempt has 88 preserved records, failed requests remain incorrect, and request IDs, statuses, labels and counts reconcile. These are measurements of the system including infrastructure failures, not clean estimates of classifier-only accuracy under healthy conditions. Keep all health warnings and the summary's review-required status.

**No additional accuracy rerun is currently necessary** to validate the saved scores or determine the observed accuracy eligibility. Record integrity is established, the diagnostic rerun already exposes the failure pattern, and Debt collection fails independently of the backend failures. Repeating solely to obtain fewer failures would not resolve the unknown cause and risks selecting a more favorable attempt after seeing results.

Before future speed testing, prioritize infrastructure diagnosis and stability checks under the existing A2 constraints. Verify backend name resolution, connectivity and configured-model residency; capture timestamped Docker/network diagnostics, container events and host/WSL memory evidence before recovery if the failure recurs. Keep the same machine, CPU/RAM allocation, model digests, inference settings and frozen thresholds, and use the prescribed idle-host and restart/warm-up procedure. A further accuracy run would be justified only to evaluate a specific corrective action or meet an explicit requirement for a healthy completed run. It must be a new, separately identified attempt, never a replacement for the preserved failures. No corrective action or inference was executed in this investigation.

If the team later chooses a different primary comparison, document that decision and rationale separately and show both attempts. Never merge successful rows across attempts, drop failures, overwrite original predictions, clear validation warnings or retune the frozen rule based on the even-row results.

## Integrity and publication review

The [results verification report](a2_accuracy_results.md#verification-and-staging-limitations) records the full audit: 259 recorded hash comparisons passed, all 315 saved confusion-matrix cells matched, and all 528 official request records across six attempts reconciled. Original S1 and S2 remain the primary summary's selected cascades; the rerun is separate. Supplementary incident files are not all covered by recorded hashes, so hash coverage must not be overstated.

The earlier hostname claim was incorrect: `desktop-linux` in original S1's `docker_failure_version.txt` is a Docker context name, not a machine hostname. The targeted scan found no confirmed machine hostname, username or host-specific absolute path. Raw logs retain internal network/container identifiers, and request journals contain complaint narratives; existing redaction placeholders do not establish publication approval.

The approved 185-file package retains every attempt, run-local environment snapshot, summary component and original service log, including the four incident logs requiring targeted force-adds. The 111 byte-identical environment copies under `results/a2/environment/` remain locally without staging. Targeted `-text` evidence rules and CRLF checkout rules for the tracked runner, scorer and dataset files have been applied in `.gitattributes`; original evidence bytes, hashes, failures and validation warnings are unchanged. The contributor acknowledges public repository visibility and has revised the approval to allow the six unmodified journals if dataset terms and assignment requirements permit their public redistribution. This is individual approval, not team-wide approval. CFPB's published-data reuse statement and the remaining assignment-verification gap are recorded in the [results document](a2_accuracy_results.md#verification-and-staging-limitations). The authoritative A2 brief is unavailable in this checkout, so assignment-level publication permission remains independently unverified. The contributor subsequently explicitly authorized local staging of all 185 files, including all six request journals. This authorization permits local staging without claiming team-wide approval or permission for a later public push. No inference, prediction regeneration, commit or push has been performed.
