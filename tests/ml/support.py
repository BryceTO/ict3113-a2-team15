"""Synthetic input builders only; expected scores live in tests and JSON fixtures."""
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import run_a2_accuracy as runner
import summarize_a2_accuracy as scorer

CATEGORIES = [
    'Credit reporting', 'Debt collection', 'Mortgage', 'Credit card',
    'Bank account or service', 'Consumer loan', 'Money transfer or service',
]
CONFIGS = ['llama3.2-1b', 'gemma3-4b', 'mistral-7b-instruct', 'cascade_s1', 'cascade_s2']
FIXTURES = Path(__file__).with_name('fixtures')


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def write_csv(path, rows, fields=None):
    path = Path(path)
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def write_log(path, entries):
    Path(path).write_text(''.join(json.dumps(e) + '\n' for e in entries), encoding='utf-8')
    return Path(path)


def tickets_for_counts(counts):
    labels = [category for category, n in zip(CATEGORIES, counts) for _ in range(n)]
    return [dict(row=2 * (i + 1), narrative='synthetic ticket', golden_label=gold)
            for i, gold in enumerate(labels)]


def perfect_cases(tickets):
    return [dict(prediction=t['golden_label'], correct=True, group='accepted',
                 small_category=t['golden_label']) for t in tickets]


def cases_for_correct_counts(tickets, correct_counts):
    cases = perfect_cases(tickets)
    for category, n_correct in zip(CATEGORIES, correct_counts):
        indices = [i for i, t in enumerate(tickets) if t['golden_label'] == category]
        for i in indices[n_correct:]:
            wrong = 'Debt collection' if category == 'Credit reporting' else 'Credit reporting'
            cases[i].update(prediction=wrong, small_category=wrong, correct=False)
    return cases


def build_run(config, tickets, cases):
    """Translate explicit fixture outcomes into prediction and service-log schemas."""
    if len(tickets) != len(cases):
        raise ValueError('Synthetic ticket and outcome counts must match')
    run_id = f'a2_{config}_synthetic_ml'
    predictions, entries = [], []
    for ticket, case in zip(tickets, cases):
        rid = f'{config}-synthetic-{ticket["row"]}'
        prediction = case['prediction']
        failed = prediction == 'Failure'
        status = 502 if failed else 200
        predictions.append(dict(row=ticket['row'], config=config, run_id=run_id,
            source='live', golden_label=ticket['golden_label'], prediction=prediction,
            correct=case['correct'], http_status=status, request_id=rid,
            latency_seconds=0.25, error='synthetic backend failure' if failed else ''))
        entry = dict(run_id=run_id, request_id=rid, row_id=ticket['row'],
                     endpoint='POST /tickets', status=status)
        if config in runner.MODELS:
            entry.update(mode='single', model=runner.MODELS[config])
            if not failed:
                entry.update(final_model=runner.MODELS[config], category=prediction)
        else:
            group = case.get('group', 'accepted')
            entry.update(mode='cascade', small_model='llama3.2:1b', large_model='gemma3:4b',
                         rule='length', rule_setting=str(runner.THRESHOLDS[config]),
                         routing='not_reached' if group == 'unknown' else 'decided',
                         escalated=group == 'escalated')
            if group == 'unknown':
                entry['error_stage'] = 'small'
            else:
                small = case.get('small_category', ticket['golden_label'])
                entry.update(small_category=small,
                    escalation_reason=('unclassified' if small == 'Unclassified' else
                                       'too_long' if group == 'escalated' else 'short_enough'))
                if failed:
                    entry['error_stage'] = 'large'
                else:
                    entry.update(category=prediction,
                        final_model='gemma3:4b' if group == 'escalated' else 'llama3.2:1b')
        entries.append(entry)
    return predictions, entries


def save_complete_run(folder, config, tickets, cases):
    """Build a strict 88-row live-run envelope, entirely from synthetic inputs."""
    folder = Path(folder)
    folder.mkdir()
    predictions, entries = build_run(config, tickets, cases)
    expected = runner.expected_config(config)
    write_json(folder / 'manifest.json', dict(schema_version=1, config=config,
        run_id=predictions[0]['run_id'], source='live', test_sha256=runner.FROZEN_HASH,
        expected_config=expected))
    health = dict(status='ok', ollama='up', mode=expected['mode'],
                  configured_models=expected['models'], loaded_models=expected['models'],
                  all_configured_loaded=True)
    if config in runner.THRESHOLDS:
        health.update(rule='length', rule_setting=str(runner.THRESHOLDS[config]))
    write_json(folder / 'health_before.json', dict(http_status=200, body=json.dumps(health)))
    write_csv(folder / 'predictions.csv', predictions, runner.FIELDS)
    events = []
    for ticket, row in zip(tickets, predictions):
        events.append(dict(event='attempt', row=row['row'],
            payload=dict(row_id=row['row'], narrative=ticket['narrative'])))
        events.append(dict(event='response', row=row['row'], http_status=row['http_status'],
            error=row['error'], headers={'X-Request-ID': row['request_id']},
            body=json.dumps(dict(id=row['request_id'], category=row['prediction']))))
    write_log(folder / 'requests.jsonl', events)
    write_json(folder / 'complete.json', dict(rows=88,
        failures=sum(c['prediction'] == 'Failure' for c in cases),
        predictions_sha256=runner.sha(folder / 'predictions.csv')))
    return folder, entries
