# Assignment 2 Rate Comparison

## Purpose

This analysis compares the common Assignment 2 speed-test rate and each configuration's achieved throughput with Team 15's Assignment 1 client peak of 9 tickets/hour. The 9/hour requirement is the rounded value adopted by the A1 requirement table from the modelled 8.25/hour peak.

The derived comparison is `results/a2/summary/a2_rate_comparison.csv`. Rebuild it with:

```powershell
python scripts/compare_a2_rates.py
```

The script validates the calibration record, both speed summaries, the frozen workload prefix, and the four raw evidence files for every run before writing the comparison.

## Calibration and common schedule

Source: `results/a2/calibration/a2_calibration.json`

| Item | Value |
|---|---:|
| Calibration rows | 15363, 15464, 15871 |
| Raw times | 11.506 s, 8.506 s, 6.183 s |
| Raw middle time | 8.506 s |
| Configured `S` | 8.5 s |
| Arrival interval | 17 s |
| Scheduled rate | 3.529412/min, 211.76/hour |
| Arrival window | 510 s, 8.5 min |
| Planned arrivals | 30/run |
| Response timeout | 300 s |
| Drain pause | 360 s |

The scheduled rate was common to all configurations and runs. Compared with the formal 9/hour client peak:

```text
211.76 / 9 = 23.53 times the client peak
```

## Results

Sources: `results/a2/summary/a2_speed_runs.csv` and `results/a2/summary/a2_speed_configs.csv`

| Configuration | Mean p50 | Mean achieved rate | Lowest run rate | Mean rate vs client peak | Completed | Queue-growth flags | Pooled escalation |
|---|---:|---:|---:|---:|---:|---:|---:|
| Gemma 3 4B | 7.046 s | 207.00/hour | 200.52/hour | 23.00x | 90/90 | 0/3 | n.a. |
| Cascade S1 | 10.843 s | 206.28/hour | 202.32/hour | 22.92x | 90/90 | 0/3 | 100% |
| Cascade S2 | 14.851 s | 200.52/hour | 192.60/hour | 22.28x | 90/90 | 1/3 | 100% |
| Mistral 7B Instruct | 30.433 s | 188.28/hour | 170.28/hour | 20.92x | 90/90 | 2/3 | n.a. |

All 12 runs recorded and completed 30/30 requests, with zero errors and zero unfinished requests. Every run reconciled with its service log and metadata. Even the lowest achieved per-run rate was substantially above 9/hour.

Gemma provides the cleanest capacity evidence. Its mean achieved rate was 207.00/hour, its lowest run achieved 200.52/hour, and no run triggered the queue-growth rule. This supports the claim that Gemma can handle the modelled 9/hour client peak on the tested machine, network path, and workload.

Cascade S1 also had no queue-growth flag, but both cascade settings escalated 100% of measured requests. The shortest narrative in the 30-row measured prefix was 497 characters, above the S1 and S2 length cutoffs of 241 and 289. Their small-model calls therefore added work without avoiding any large-model calls. This explains why both cascades had higher latency than Gemma alone.

Cascade S2 triggered possible queue growth in one of three runs. Mistral triggered it in two of three runs and showed the largest p50 spread. Those configurations completed every request during the drain period, but the evidence does not show that they cleanly sustained the much higher 211.76/hour A2 arrival rate.

## Interpretation limits

- The A2 benchmark did not directly run at 9/hour. It tested approximately 23.53 times that rate to compare configurations with about 30 arrivals per run.
- Exceeding 9/hour in every run supports client-peak capacity, but it does not remove the queue-growth warning at the higher A2 rate.
- Throughput is derived from completed requests over each run's measured test span. The runner's drain allowed slow requests to finish.
- Queue growth is flagged when second-half p50 exceeds 1.5 times first-half p50. It is an evidence-based warning, not proof of unbounded growth.
- Results apply to one service host, one load-generator path, one fixed workload prefix, and one common arrival rate.

## Traceability

Calibration:

- `results/a2/calibration/a2_calibration.json`
- `results/logs/a2_gemma3-4b_calibration.log`

Per-run and per-configuration summaries:

- `results/a2/summary/a2_speed_runs.csv`
- `results/a2/summary/a2_speed_configs.csv`
- `results/a2/summary/a2_rate_comparison.csv`

For each `RUN_ID` listed in the comparison:

- `results/a2/jtl/<RUN_ID>.jtl`
- `results/a2/jtl/<RUN_ID>.properties`
- `results/a2/jtl/<RUN_ID>.meta.json`
- `results/logs/<RUN_ID>.log`

Client peak sources:

- `analysis/load_scenarios.csv`
- `docs/workload_model.md`
- `docs/requirements.md`

Cascade routing explanation:

- `jmeter/a2_workload_rows.csv`
- `docs/escalation_rule.md`
