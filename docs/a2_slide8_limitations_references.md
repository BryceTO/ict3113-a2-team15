# A2 Slide 8: Limitations and references

This document supplies slide-ready wording and a traceable reference list.

## Slide-ready limitations

- **Limited accuracy sample.** Accuracy uses 88 even-row tickets. Per-category denominators are only 22, 11, 15, 9, 12, 6 and 13, so one ticket can materially change a category result.
- **Not a fully unseen benchmark.** A1 evaluated the same complete 175-ticket golden set. A2 made fresh model calls and used only the 87 odd rows for cascade tuning, but the 88-row even test split comes from data whose earlier A1 outcomes were already available to the team.
- **One environment and workload.** Results cover one CPU-only service laptop (22 Docker CPUs, 9.713 GiB available to Docker), one separate load generator, one direct Tailscale path, one fixed 30-ticket measured prefix and one common arrival schedule. They should be revalidated on client hardware and a broader production ticket mix.
- **Capacity claim is bounded.** The A2 schedule was 211.76 tickets/hour, 23.53 times the modelled 9/hour client peak; it was not a direct 9/hour endurance test. All 12 speed runs completed 30/30 with no errors or unfinished requests, but the drain period allowed outstanding requests to finish.
- **Higher-rate queue warnings remain.** Gemma and Cascade S1 had no queue-growth flags; Cascade S2 had 1 of 3 and Mistral had 2 of 3. Therefore completion above 9/hour does not prove clean or unlimited scaling at the A2 rate.
- **Cascade benefit did not generalise.** Both cascades escalated 100% of speed-test tickets because every measured narrative exceeded both length thresholds. They were slower than Gemma alone and failed at least one accuracy category floor.
- **Cascade accuracy included infrastructure failures.** Original S1 recorded five HTTP 502 failures and S2 recorded one; all counted as incorrect. The immediate mechanism was temporary failure to resolve the `ollama` backend hostname, but the underlying Docker/WSL cause is unconfirmed. Pre-run residency was verified, not continuous residency throughout each run.
- **A1 and A2 timings are not directly comparable.** A2 used `POST /tickets` only, a non-wrapping feeder, an Ollama restart plus three warm-ups before each run, an idle service host, and calibrated timeout/drain settings. A1 also exercised search traffic and used a different warm-up/restart procedure.

## Compact slide version

If space is limited, use these five bullets:

1. Accuracy uses only 88 test tickets; category counts range from 6 to 22, so individual tickets have high influence.
2. The A2 split comes from the 175 tickets already evaluated in A1; calls were fresh and tuning used odd rows only, but this is not a fully unseen benchmark.
3. Findings apply to one CPU-only laptop, fixed resources/network, one 30-ticket prefix and one arrival rate—not all client hardware or complaint mixes.
4. All speed runs completed, but the drain allowed completion; Cascade S2 and Mistral showed possible queue growth at 211.76/hour. This supports the 9/hour peak only under tested conditions.
5. Both cascades escalated every speed ticket, were slower than Gemma and failed category floors; accuracy runs also had recorded backend DNS failures with no confirmed root cause.

## Model identity and licences

The tags and SHA-256 digests below are the exact artifacts recorded on the service host. Cascade S1 and S2 combine Llama 3.2 1B with Gemma 3 4B and do not introduce a separate model licence.

| Reported model | Ollama tag | Recorded digest | Licence/terms |
|---|---|---|---|
| Llama 3.2 1B | `llama3.2:1b` | `baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878` | Llama 3.2 Community License Agreement |
| Gemma 3 4B | `gemma3:4b` | `a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a` | Gemma Terms of Use |
| Mistral 7B Instruct v0.3, Q4_K_M | `mistral:7b-instruct` | `6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf` | Apache License 2.0 |

## References

Accessed 20 November 2026.

1. Google. *Gemma Terms of Use*. https://ai.google.dev/gemma/terms/
2. Google DeepMind. *Gemma 3 Model Card*. https://ai.google.dev/gemma/docs/core/model_card_3
3. Meta. *Llama 3.2 Community License Agreement*. https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/LICENSE
4. Meta. *Llama 3.2 Model Card*. https://github.com/meta-llama/llama-models/blob/main/models/llama3_2/MODEL_CARD.md
5. Mistral AI. *Mistral-7B-Instruct-v0.3 Model Card* (Apache-2.0). https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.3
6. Ollama. *Llama 3.2 model library*. https://ollama.com/library/llama3.2
7. Ollama. *Gemma 3 model library*. https://ollama.com/library/gemma3
8. Ollama. *Mistral model library*. https://ollama.com/library/mistral
9. Ollama. *Ollama API introduction*. https://docs.ollama.com/api/introduction
10. Ollama. *Ollama software repository*. https://github.com/ollama/ollama
11. Consumer Financial Protection Bureau. *Consumer Complaint Database*. https://www.consumerfinance.gov/data-research/consumer-complaints/

## Evidence traceability

- Environment, model digests and A1-to-A2 changes: `docs/a2_test_environment.md`
- Accuracy set sizes, category counts and outcomes: `docs/a2_accuracy_results.md`
- Backend failures and residency limitations: `docs/a2_accuracy_incidents.md`
- Scheduled rate, request accounting and queue flags: `docs/a2_rate_comparison.md`
- Accuracy-latency interpretation and cascade escalation: `docs/a2_tradeoff.md`
- Derived speed evidence: `results/a2/summary/a2_speed_runs.csv` and `results/a2/summary/a2_speed_configs.csv`
- Reviewed accuracy evidence: `results/a2/accuracy/summary_reviewed_r1/`
