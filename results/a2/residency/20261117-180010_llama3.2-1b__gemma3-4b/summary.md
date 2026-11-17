# Residency check: llama3.2:1b + gemma3:4b

- Verdict: **RESIDENT**
- Both listed by `ollama ps` after loading both: True
- Both listed after 3 alternating rounds: True
- Reloads during alternation (load_duration > 1 s): 0
- Host: Intel(R) Core(TM) Ultra 7 155H, 15.61 GB RAM; Docker: 22 CPUs, 9.713 GiB
- Ollama 0.35.0; settings: OLLAMA_MAX_QUEUE=512, OLLAMA_NUM_PARALLEL=1, OLLAMA_HOST=0.0.0.0:11434; num_ctx 4096; keep_alive 30m

| Step | Model | Wall ms | Load ms | Answer |
|---|---|---:|---:|---|
| load_small | llama3.2:1b | 5085.7 | 3894.7 | Debt collection |
| load_large | gemma3:4b | 26559.7 | 23020.7 | Credit reporting |
| alt1_small | llama3.2:1b | 2264.1 | 13.9 | Bank account or service |
| alt1_large | gemma3:4b | 3790.5 | 3.8 | Credit card |
| alt2_small | llama3.2:1b | 1235.8 | 7.3 | Bank account or service |
| alt2_large | gemma3:4b | 3036.8 | 3.1 | Money transfer or service |
| alt3_small | llama3.2:1b | 741.9 | 6.6 | Bank account or service |
| alt3_large | gemma3:4b | 2554.8 | 4.5 | Debt collection |

Files: environment.json (versions, digests, limits), ps_*.json/txt (`ollama ps` snapshots), calls.csv, docker_stats_end.txt.
