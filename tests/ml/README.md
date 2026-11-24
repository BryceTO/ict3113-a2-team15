# Independent ML evaluation regression tests — Yuhao

These tests exercise Liando's actual `summarize_a2_accuracy.py`,
`run_a2_accuracy.py`, `tune_cascade.py` and `tune_length.py` using synthetic
inputs and hand-checked expectations. They complement the implementation
smoke tests in `tests/test_a2_accuracy_workflow.py`.

## Run

From the repository root (the directory containing `scripts` and `tests`),
using Python 3.10 or newer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r tests/ml/requirements.txt
.\.venv\Scripts\python.exe -B -m unittest discover -s tests/ml -v
```

If `.venv` already exists, use its Python without recreating it. Pandas is
required by the existing tuning scripts. A missing dependency fails the
suite rather than silently skipping tuning validation.

Run the independent suite and existing accuracy workflow tests together:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

This combined command discovers the ML suite and accuracy workflow tests.
Service tests have their own command in the repository README.

## Hand-checked expectations

| Case | Expected result |
|---|---|
| Five tickets | 3 correct, 1 wrong category, 1 backend failure: **3/5 = 60%** |
| Five-ticket categories | Credit reporting **1/2 = 50%**; Debt collection **2/3 = 66.666...%** |
| Replace one correct answer with Unclassified | **2/5 = 40%**; separate Unclassified and Failure confusion columns, one entry each |
| Strict 88-ticket loader | One backend failure and one Unclassified remain in the denominator: **86/88** correct |
| Exact overall floor | Reference **100/100** gives a **90%** overall floor; **90/100** passes, **89/100** fails |
| Exact category floor | Reference **20/20** gives an **85%** category floor; **17/20** passes |
| Overall pass, category fail | Candidate **84/88** passes overall, but Credit reporting **16/20 = 80%** fails its **85%** floor |
| Fractional floor | Reference **69/88**, minus 10 percentage points, gives **68.4090909...%**; **60/88** fails overall and **61/88** passes overall |
| Cascade fixture | **83/88** correct; accepted **81/82**, escalated **2/5**, unknown **0/1** |
| Escalation denominator | **5/87**, including the failed large-model call and excluding the failure before routing |
| No routing decisions | 88 unknown; escalation fraction and empty-group accuracies are **None**, not zero |
| Length boundaries | 241/289 code points accepted inclusively; one extra code point escalates; short Unclassified output also escalates |
| Held-out isolation | Changing every even-row prediction, label and status changes **no output CSV bytes** for either tuner |
| Invalid inputs | Duplicate/wrong-split IDs, missing tuning predictions and mismatched labels stop reports before any output CSV is produced |

`fixtures/five_tickets.json` stores explicit labels, predictions, correctness
flags and expected nonzero confusion cells. Its four nonzero cells are:

| True label | Prediction | Count |
|---|---|---:|
| Credit reporting | Credit reporting | 1 |
| Credit reporting | Debt collection | 1 |
| Debt collection | Debt collection | 2 |
| Debt collection | Failure | 1 |

`fixtures/cascade_routing.json` stores eight explicit routing cases and
expected totals. Another 80 synthetic accepted-correct tickets complete the
88-ticket fixture. The five escalations are two correct answers, one wrong
category, one large-model backend failure and one Unclassified final answer.
The unknown ticket fails at the small model before routing. There is also an
accepted wrong answer, so accepted accuracy cannot be assumed to be 100%.

Floor fixtures generate the seven categories with explicit counts and
correct-count budgets in the test source. These are synthetic reference
results, independent of the official A2 results. The 89/100 boundary case
still passes every category floor, isolating the overall-floor decision.

## Interface and isolation

- No official golden rows, recorded model predictions or measured logs are
  read. The strict run-loader tests read the configuration definitions in
  `jmeter/a2_configs.json`, but use synthetic run manifests and journals.
- Predictions, service logs, run envelopes, tuning inputs and tuner outputs
  are written only under temporary directories and cleaned up afterward.
- Socket connection attempts fail the tests. No Ollama instance is needed.
- No scoring, reconciliation or tuning function is mocked. Paths are
  redirected to synthetic inputs. For tiny metric/floor fixtures, only
  `CONFIGS` and, for the five-ticket case, the two-category `CATEGORIES`
  scope are narrowed temporarily. This lets the existing scorer evaluate a
  small fixture without changing its production CLI contract.
- The actual strict loader is tested separately with 88 synthetic tickets.
  Cascade aggregate tests also use 88 tickets, matching the current scorer's
  fixed-size contract. They do not assert support for arbitrary-size
  cascade summaries.
- The frozen-data fingerprint is replaced only in the synthetic test-split
  loader case. Duplicate/parity/label/fingerprint validation remains active.
- The official split, scorer, rule, prediction record and saved evidence
  are not edited or regenerated by this suite.

## Validation

On 20 November 2026, all **20 independent test methods** passed using
Python 3.11.9 and pandas 2.2.3, including the parameterized subcases.
The combined run passed **25 methods** (20 independent and five existing
workflow tests). The existing workflow tests deliberately emit validation
warnings while exercising unhealthy-run cases; these are expected when
the final unittest result is `OK`.

The 83/88 routing fixture passes both accuracy floors. The separate
all-unknown cascade case verifies mandatory speed testing despite accuracy
failure.
No production scorer or tuning fix was needed for the covered cases.

Passing synthetic tests validates these evaluation behaviors; it does not
establish that measured runs were healthy or that the production cascade
supports variable-sized datasets.
