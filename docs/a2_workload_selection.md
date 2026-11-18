# Assignment 2 Speed-Test Workload Selection

## Purpose

This document records Team 15's fixed workload for the Assignment 2 speed tests. Every speed-tested configuration uses the measured tickets in the same order. The committed row list is `jmeter/a2_workload_rows.csv`; the generated `jmeter/feeder.tsv` is local and ignored by Git because it contains narratives from the private Team 15 extract.

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

The selector first removes every golden-set row. It sorts eligible candidates by narrative length and row ID, then chooses evenly spaced candidates without random sampling. Warm-up and calibration rows are selected from the typical band. The measured workload contains 24 typical and 6 long tickets. Within each purpose, committed order values are contiguous and fixed.

The final workload contains:

| Purpose | Count | Use |
|---|---:|---|
| Warm-up | 3 | Load and warm the model or models before each run; timings discarded |
| Calibration | 3 | Three different typical tickets used sequentially on the top model to determine `S`; timings not part of a speed run |
| Measured typical | 24 | Typical-length requests included in reported speed results |
| Measured long | 6 | Long requests included in reported speed results |
| Total | 36 | All selected rows across the three disjoint purposes |

Thirty measured tickets follow the assignment's expected run size when `S` is at least five seconds: one request every `2 x S` seconds for `S` minutes produces approximately 30 arrivals. Before the first official run, the benchmark owner must compare the calibrated `S`, schedule, and feeder count. If the five-minute minimum would produce more than 30 arrivals, the team must resolve the workload size before starting official measurements and record the change in a new pre-benchmark commit.

## Measured workload profile

The 30 measured narratives have the following character lengths:

- Minimum: 497
- Median: 888
- Mean: 1013.37
- Maximum: 1989

Their original source-label counts are:

| Source label | Count |
|---|---:|
| Bank account or service | 8 |
| Consumer loan | 5 |
| Credit card | 3 |
| Credit reporting | 2 |
| Debt collection | 2 |
| Money transfer or service | 2 |
| Mortgage | 8 |

These source labels are descriptive only and are not used as golden answers or as a balancing target. The selection rule is based on narrative length and reproducibility.

## Reproduction commands

Run from the repository root:

```powershell
python scripts/select_a2_workload.py --input docsbryan/team15_rows.csv --golden golden_set/golden_set.csv --output jmeter/a2_workload_rows.csv --measured-count 30 --long-count 6 --warmup-count 3 --calibration-count 3
python scripts/make_feeder.py --input docsbryan/team15_rows.csv --rows jmeter/a2_workload_rows.csv --golden golden_set/golden_set.csv --output jmeter/feeder.tsv
python -m pytest tests/workload -q
```

The first command is deterministic. Re-running it with unchanged inputs and options must reproduce the committed row list exactly.

## Freeze checks

The frozen row list passed the following checks:

- 36 selected row IDs and 36 unique row IDs
- 3 warm-up, 3 calibration, and 30 measured rows
- 24 typical and 6 long measured rows
- Zero overlap with all 175 golden rows
- No overlap between warm-up, calibration, and measured purposes
- Contiguous order values within every purpose
- Every selected row resolves to one source narrative
- Generated feeder contains exactly 30 physical lines
- Feeder JSON safely escapes embedded quotes, tabs, newlines, and non-ASCII characters
- All 23 workload selector and feeder tests pass

## Use during benchmarking

The measured rows and their order must remain unchanged across the top model, other qualifying single models, and both cascade settings. The three warm-up rows must be sent sequentially and discarded before each run. The three calibration rows must be sent sequentially to the top model when determining `S`. JMeter must not wrap the feeder or continue after it is exhausted.
