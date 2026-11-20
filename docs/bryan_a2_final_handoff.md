# Bryan A2 final evidence and slide handoff

Prepared: 20 November 2026  
Branch: `bryan/workload-tradeoff`

## Final recommendation supported by Bryan's evidence

Recommend **Gemma 3 4B** as the fastest configuration that satisfies both the overall and every per-category accuracy floor. Its even-row test accuracy is 78.409% and its mean of three run p50 values is 7.046 seconds. Mistral is more accurate at 86.364%, but its mean p50 is 30.433 seconds and two of three runs trigger the possible queue-growth flag. Both cascades are ineligible because they fail category floors; under the speed workload they also escalate 100% of tickets and are slower than Gemma alone.

Gemma completed 90/90 measured speed requests with no errors or unfinished requests. Its lowest achieved run rate was 200.52 tickets/hour, above the modelled 9/hour client peak on the tested host and workload. This is bounded capacity evidence, not a claim about other machines, workloads or unlimited scaling.

## Files for Yuhao

| Purpose | File |
|---|---|
| Slide 6 chart | `results/a2/summary/a2_tradeoff.png` |
| Slide 6 joined chart source | `results/a2/summary/a2_tradeoff.csv` |
| Slide 6 method and interpretation | `docs/a2_tradeoff.md` |
| Client-rate comparison | `results/a2/summary/a2_rate_comparison.csv` |
| Rate interpretation | `docs/a2_rate_comparison.md` |
| Slide 8 compact/full limitations and references | `docs/a2_slide8_limitations_references.md` |

## Slide 6 values

The chart must use even-row test accuracy on the y-axis and the mean of the three run p50 values on the x-axis.

| Configuration | Test accuracy | Mean p50 | Chart status |
|---|---:|---:|---|
| Gemma 3 4B | 78.409% | 7.046 s | Passes overall and all category floors |
| Cascade S1 | 70.455% | 10.843 s | Category-floor failure |
| Cascade S2 | 72.727% | 14.851 s | Category-floor failure |
| Mistral 7B Instruct | 86.364% | 30.433 s | Passes overall and all category floors |
| Llama 3.2 1B | 19.318% | Not measured | Accuracy failed; speed unmeasured |

Overall accuracy floor: **68.409%**. Passing this line alone does not establish eligibility.

## Live deck integration audit

Checked against Google Slides revision `WXF2LySKdDekMA` on 20 November 2026.

- **Slide 4 matches** the final reviewed accuracy totals, floors and eligibility outcomes.
- **Slide 5 matches** the final speed summary after display rounding: Gemma 7.0 s, Cascade S1 10.8 s, Cascade S2 14.9 s and Mistral 30.4 s mean p50; it also reports 100% speed-workload escalation for both cascades and the correct queue warnings.
- **Slide 6 requires replacement.** Its title says Accuracy–Latency Trade-off, but its body still contains the old golden-set labelling protocol. Replace the body with `a2_tradeoff.png`; retain the chart's legend, overall-floor line and category-failure markers.
- **Slide 7 requires reconciliation by the slide owner.** It still describes the A1 setup (one warm-up, one model loaded, 19 runs and A1 network figures). The A2 recommendation should use the wording above and the A2 environment in `docs/a2_test_environment.md`.
- **Slide 8 requires replacement.** It still contains the A1 run flow, A1 rates/search traffic and 175-row accuracy procedure. Replace it with the compact limitations and references in `docs/a2_slide8_limitations_references.md`.
- The existing references slide already lists the model, Ollama and CFPB sources; the Phase 6 document supplies the exact licence-to-model mapping and updated source wording.

## Reproducibility record

Rebuilt from the current clean branch:

| Artifact | SHA-256 after rebuild |
|---|---|
| `jmeter/feeder.tsv` (ignored/local) | `4A48B4929AFCBFCE7918EF30DEF7F3C9F22FE6CD6129C9ABA5A83662BD173FC2` |
| `results/a2/summary/a2_rate_comparison.csv` | `C0BB5615A1EB41D677354E9C6955D493F63719F15FAE360E4CA0052301EF859F` |
| `results/a2/summary/a2_tradeoff.csv` | `A18CEA21E5783A7C97B434C39AA9C335F869825BB30D2FD4CC25760C90DD11C1` |
| `results/a2/summary/a2_tradeoff.png` | `D3FCA1016D2F897336DD8C14BB27A4B41F2C0649B55812307EA4240AA0E3B187` |

All four hashes were unchanged by regeneration. The complete repository test run passes **56 tests and 15 subtests**; the only warning is a pending Starlette multipart import deprecation.

Rebuild commands:

```powershell
python scripts/make_feeder.py
python scripts/compare_a2_rates.py
python scripts/build_a2_tradeoff.py
python -m pytest -q
```

## Relevant commits

- `00a4bbd` — deterministic workload selector
- `aa94b8f` — safe non-wrapping feeder builder
- `641d383` — final 60-row measured workload freeze
- `7f97b49` — corrected workload handoff documentation
- `bec6370` — A2 versus client-peak rate comparison
- `756dd31` — accuracy-latency chart, joined source and interpretation
- `cc7db7d` — trade-off validation coverage
- `15884ea` — Slide 8 limitations, references and licences

## Privacy and tracking boundary

The private Team 15 extract, generated `jmeter/feeder.tsv`, `docsbryan/`, local databases, credentials and environment-secret files must remain outside Git. The committed row list contains IDs and selection metadata only; the final chart and summaries contain aggregated evidence rather than the private feeder narratives.
