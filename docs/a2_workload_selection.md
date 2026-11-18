# Assignment 2 Speed-Test Workload Selection

## Purpose

This document records Team 15's fixed workload for the Assignment 2 speed tests. Every speed-tested configuration uses the measured tickets in the same order. The committed row list is `jmeter/a2_workload_rows.csv`; the generated `jmeter/feeder.tsv` is local and ignored by Git because it contains narratives from the private Team 15 extract.

This 60-row measured workload supersedes the earlier 30-row freeze in commit `843f09a`. No official benchmark run used the earlier list. The selector was rerun for 60 rows rather than appending to the old list, so only 6 of the old 30 measured rows remain in v2. All slides, run metadata, and evidence indexes must cite the v2 freeze `641d383`. Assignment 1 evidence indicated that the top model's calibration time could be below five seconds, so the five-minute minimum run window required a longer feeder.

## Inputs

- Private source extract: `docsbryan/team15_rows.csv`
- Complete frozen golden set: `golden_set/golden_set.csv`
- A2 test split: `golden_set/a2/test (even).csv`
- A2 tuning split: `golden_set/a2/tuning (odd).csv`
- Selector: `scripts/select_a2_workload.py`
- Feeder generator: `scripts/make_feeder.py`

The private source contains 1,000 unique rows numbered 15000-15999. The complete golden set contains 175 rows. All golden rows are excluded from warm-up, calibration, and measured speed-test selection, leaving 825 eligible non-golden rows.

Yuhao's committed split was checked before the workload was frozen:

- Test: 88 rows, all even row IDs
- Tuning: 87 rows, all odd row IDs
- Combined: all 175 golden rows, with no duplicate, missing, or extra IDs

## Selection rule

Ticket length is the narrative character count. The length bands use the existing Assignment 1 evidence and are recalculated deterministically from the complete 1,000-row Team 15 extract using linear percentile interpolation:

- Typical: p25 through p75, or 488.75-1216.50 characters
- Long: p90 or above, or at least 1604.10 characters

The selector first removes every golden-set row. It sorts eligible candidates by narrative length and row ID, then chooses evenly spaced candidates without random sampling. Warm-up and calibration rows are selected from the typical band. The measured workload contains 48 typical and 12 long tickets. Within each purpose, committed order values are contiguous and fixed.

The final workload contains:

| Purpose | Count | Use |
|---|---:|---|
| Warm-up | 3 | Load and warm the model or models before each run; timings discarded |
| Calibration | 3 | Three different typical tickets used sequentially on the top model to determine `S`; timings not part of a speed run |
| Measured typical | 48 | Typical-length requests available for reported speed results |
| Measured long | 12 | Long requests available for reported speed results |
| Total | 66 | All selected rows across the three disjoint purposes |

Thirty measured tickets follow the assignment's expected run size when `S` is at least five seconds: one request every `2 x S` seconds for `S` minutes produces 30 scheduled arrivals. When `S` is below five seconds, the current JMeter schedule rounds the five-minute count down, so `N = floor(150 / S)`. This gives 37 rows at `S = 4`, 50 at `S = 3`, and 60 at `S = 2.5`. The calibration output and each run's `.meta.json` record the exact `N` and are authoritative for reporting.

After calibration, the benchmark owner takes the exact scheduled request count `N` from the calibration output and verifies it against the run metadata. Every configuration must consume the same first `N` measured rows in the committed order. The remaining feeder rows are unused. If `S < 2.5` seconds or the configured schedule would send more than 60 requests, official runs must not start until Bryan extends and re-freezes the workload. When `N = 30`, the v2 prefix contains 25 typical and 5 long tickets.

## Measured workload profile

The 60 measured narratives have the following character lengths:

- Minimum: 497
- Median: 882
- Mean: 1012.70
- Maximum: 1989

Their original source-label counts are:

| Source label | Count |
|---|---:|
| Bank account or service | 10 |
| Consumer loan | 9 |
| Credit card | 5 |
| Credit reporting | 9 |
| Debt collection | 8 |
| Money transfer or service | 9 |
| Mortgage | 10 |

These source labels are descriptive only and are not used as golden answers or as a balancing target. The selection rule is based on narrative length and reproducibility.

## Reproduction commands

Run from the repository root:

```powershell
python scripts/select_a2_workload.py --input docsbryan/team15_rows.csv --golden golden_set/golden_set.csv --output jmeter/a2_workload_rows.csv --measured-count 60 --long-count 12 --warmup-count 3 --calibration-count 3
python scripts/make_feeder.py --input docsbryan/team15_rows.csv --rows jmeter/a2_workload_rows.csv --golden golden_set/golden_set.csv --output jmeter/feeder.tsv
python -m pytest tests/workload -q
```

The first command is deterministic. Re-running it with unchanged inputs and options must reproduce the committed row list exactly.

## Freeze checks

The frozen row list passed the following checks:

- 66 selected row IDs and 66 unique row IDs
- 3 warm-up, 3 calibration, and 60 measured rows
- 48 typical and 12 long measured rows
- Zero overlap with all 175 golden rows
- No overlap between warm-up, calibration, and measured purposes
- Contiguous order values within every purpose
- Every selected row resolves to one source narrative
- Generated feeder contains exactly 60 physical lines
- Feeder JSON safely escapes embedded quotes, tabs, newlines, and non-ASCII characters
- All 23 workload selector and feeder tests pass

## Use during benchmarking

The measured rows and their order must remain unchanged across the top model, other qualifying single models, and both cascade settings. After calibration, each configuration uses the same first `N` rows required by the common schedule. The three warm-up rows must be sent sequentially and discarded before each run. The three calibration rows must be sent sequentially to the top model when determining `S`. JMeter must not wrap the feeder or continue after it is exhausted.
