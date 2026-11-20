# Residency check: llama3.2:1b + mistral:7b-instruct

- Verdict: **RESIDENT**
- Both listed by `ollama ps` after loading both: True
- Both listed after 3 alternating rounds: True
- Reloads during alternation (load_duration > 1 s): 0
- Host: Intel(R) Core(TM) Ultra 7 155H, 15.61 GB RAM; Docker: 22 CPUs, 9.713 GiB
- Ollama 0.35.0; settings: OLLAMA_MAX_QUEUE=512, OLLAMA_NUM_PARALLEL=1, OLLAMA_HOST=0.0.0.0:11434; num_ctx 4096; keep_alive 30m

| Step | Model | Wall ms | Load ms | Answer |
|---|---|---:|---:|---|
| load_small | llama3.2:1b | 10998.9 | 9521.9 | Debt collection |
| load_large | mistral:7b-instruct | 49834.7 | 42988.8 | Credit reporting |
| alt1_small | llama3.2:1b | 3449.5 | 14.2 | Bank account or service |
| alt1_large | mistral:7b-instruct | 2551.5 | 19.5 | Credit card |
| alt2_small | llama3.2:1b | 1014.7 | 13.6 | Bank account or service |
| alt2_large | mistral:7b-instruct | 2004.4 | 6.4 | Money transfer or service |
| alt3_small | llama3.2:1b | 925.8 | 6.2 | Bank account or service |
| alt3_large | mistral:7b-instruct | 2010.6 | 3.8 | Debt collection |

Files: environment.json (versions, digests, limits), ps_*.json/txt (`ollama ps` snapshots), calls.csv, docker_stats_end.txt.
