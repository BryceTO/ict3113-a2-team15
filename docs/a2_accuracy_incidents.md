# A2 accuracy incidents

The root cause remains unconfirmed. Memory pressure is a suspected contributing factor, not a confirmed cause. The saved failures, predictions and validation warnings are retained without changes. All failures remain incorrect predictions in the full 88-ticket denominator.

## Attempts and evidence

| Attempt | Saved run directory | Correct | Accuracy | HTTP 502 backend failures | Post-run Ollama health |
|---|---|---:|---:|---:|---|
| Original S1 | [20261119T100108Z_bcf82ced](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced/) | 62/88 | 70.45% | 5 | Unhealthy |
| Controlled S1 rerun | [20261119T122549Z_e6fa148f](../results/a2/accuracy/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f/) | 64/88 | 72.73% | 1 | Unhealthy |
| S2 | [20261119T151248Z_959b77e7](../results/a2/accuracy/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7/) | 64/88 | 72.73% | 1 | Unhealthy |

Each linked directory contains `manifest.json`, `predictions.csv`, `requests.jsonl`, `complete.json`, `health_before.json`, `health_after.json` and environment evidence. The corresponding service logs are [original S1](../results/logs/a2_cascade_s1_accuracy_20261119T100108Z_bcf82ced.log), [rerun S1](../results/logs/a2_cascade_s1_accuracy_20261119T122549Z_e6fa148f.log) and [S2](../results/logs/a2_cascade_s2_accuracy_20261119T151248Z_959b77e7.log).

All attempts completed 88 saved prediction records. Original S1 failed rows 15166, 15168, 15170, 15172 and 15174; the other two attempts failed row 15174. Each failure reconciles to HTTP 502 in the service log and `routing=not_reached`; none is an accepted or escalated result. Accuracy is 62/88 or 64/88, not accuracy over successful requests only.

All three `health_after.json` files contain `Service/Ollama not healthy`. In particular, a successful HTTP response from `/health` does not imply a healthy Ollama backend: the body records backend failure and unavailable residency. These warnings are not erased by completion markers or by the later recovery. The primary [validation record](../results/a2/accuracy/summary_reviewed_r1/validation.json) remains `review_required=true`.

## File-verified observations

Original S1's `docker_failure_status.txt`, `docker_failure_stats.txt` and `docker_failure_version.txt` record Docker management requests returning **HTTP 500 Internal Server Error**. These management failures are distinct from the HTTP 502 ticket predictions. Do not generalize the original Docker 500 observation to every subsequent attempt.

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

If the team later chooses a different primary comparison, document that decision and rationale separately and show both attempts. Never merge successful rows across attempts, drop failures, overwrite original predictions, clear validation warnings or retune the frozen rule based on the even-row results.

## Integrity and publication review

The [results verification report](a2_accuracy_results.md#verification-and-staging-limitations) records the full audit: 259 recorded hash comparisons passed, all 315 saved confusion-matrix cells matched, and all 528 official request records across six attempts reconciled. Original S1 and S2 remain the primary summary's selected cascades; the rerun is separate. Supplementary incident files are not all covered by recorded hashes, so hash coverage must not be overstated.

The earlier hostname claim was incorrect: `desktop-linux` in original S1's `docker_failure_version.txt` is a Docker context name, not a machine hostname. The targeted scan found no confirmed machine hostname, username or host-specific absolute path. Raw logs retain internal network/container identifiers, and request journals contain complaint narratives; existing redaction placeholders do not establish publication approval.

The approved 185-file package retains every attempt, run-local environment snapshot, summary component and original service log, including the four incident logs requiring targeted force-adds. The 111 byte-identical environment copies under `results/a2/environment/` remain locally without staging. Targeted `-text` evidence rules and CRLF checkout rules for the tracked runner, scorer and dataset files have been applied in `.gitattributes`; original evidence bytes, hashes, failures and validation warnings are unchanged. The contributor acknowledges public repository visibility and has revised the approval to allow the six unmodified journals if dataset terms and assignment requirements permit their public redistribution. This is individual approval, not team-wide approval. CFPB's published-data reuse statement and the remaining assignment-verification gap are recorded in the [results document](a2_accuracy_results.md#verification-and-staging-limitations). The authoritative A2 brief is unavailable in this checkout, so assignment-level publication permission remains independently unverified. The contributor subsequently explicitly authorized local staging of all 185 files, including all six request journals. This authorization permits local staging without claiming team-wide approval or permission for a later public push. No inference, prediction regeneration, commit or push has been performed.
