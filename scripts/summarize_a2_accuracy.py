"""Score five complete A2 runs; offline only. Uses exact fractions for floor decisions."""
import argparse
import json
import math
import shutil
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

from run_a2_accuracy import (CATEGORIES, CONFIGS, FIELDS, FROZEN_HASH, MODELS, OUTPUT,
                             THRESHOLDS, portable_path, health_issues, boolean, expected_config, import_a1, label,
                             load_test, read_csv, read_json, require, sha, write_csv, write_json)


def load_run(folder, tickets):
    folder = Path(folder)
    manifest = read_json(folder / 'manifest.json')
    complete = read_json(folder / 'complete.json')
    config = manifest['config']
    require(config in CONFIGS and manifest['schema_version'] == 1, 'Unsupported run manifest')
    require(manifest['test_sha256'] == FROZEN_HASH, 'Wrong frozen test set')
    require(manifest['expected_config'] == expected_config(config), 'Run configuration mismatch')
    require(complete['rows'] == 88 and complete['predictions_sha256'] == sha(folder / 'predictions.csv'),
            'Incomplete or changed predictions')
    rows = read_csv(folder / 'predictions.csv')
    require(len(rows) == 88, 'Expected 88 predictions')
    golden = {r['row']: r['golden_label'] for r in tickets}
    ids, rids = set(), set()
    for row in rows:
        require(set(FIELDS).issubset(row), 'Missing prediction columns')
        row['row'] = int(row['row'])
        require(row['row'] in golden and row['row'] not in ids, 'Unexpected/duplicate test row')
        ids.add(row['row'])
        require(row['config'] == config and row['run_id'] == manifest['run_id'], 'Mixed config/run IDs')
        require(row['source'] == manifest['source'] and row['source'] in ('live', 'a1_import'), 'Wrong record source')
        require(row['golden_label'] == golden[row['row']], 'Golden label mismatch')
        require(row['prediction'] in CATEGORIES + ['Unclassified', 'Failure'], 'Invalid prediction')
        row['http_status'] = int(row['http_status'])
        require(row['http_status'] == 0 or 100 <= row['http_status'] <= 599, 'Invalid HTTP status')
        latency = float(row['latency_seconds'])
        require(math.isfinite(latency) and latency >= 0, 'Invalid latency')
        failure = row['http_status'] != 200 or bool(row['error'])
        require((row['prediction'] == 'Failure') == failure, 'Failure representation mismatch')
        require(failure or row['request_id'], 'Successful request missing ID')
        if row['request_id']:
            require(row['request_id'] not in rids, 'Duplicate prediction request ID')
            rids.add(row['request_id'])
        correct = not failure and row['prediction'] == golden[row['row']]
        require(boolean(row['correct']) == correct, 'Incorrect stored correctness flag')
        row['correct'] = correct
    require(ids == set(golden), 'Missing test row')
    require(complete['failures'] == sum(r['prediction'] == 'Failure' for r in rows), 'Failure count mismatch')
    if manifest['source'] == 'a1_import':
        require(config in MODELS, 'Cannot import a cascade')
        approval = read_json(folder / 'reuse_approval.json')
        # Revalidate the original approval against the archived evidence paths.
        from run_a2_accuracy import DIGESTS, REUSE_CHECKS
        require(approval.get('eligible') is True and approval.get('config') == config and
                approval.get('reviewer') and approval.get('reviewed_at') and
                approval.get('model_digest') == DIGESTS[config] and
                approval.get('source_sha256') == sha(folder / 'a1_source.csv'), 'Invalid reuse approval')
        evidence_ids = set()
        for i, item in enumerate(approval['evidence']):
            require(item['id'] not in evidence_ids, 'Duplicate reuse evidence ID')
            evidence_ids.add(item['id'])
            require(sha(folder / 'reuse_evidence' / str(i)) == item['sha256'], 'Archived reuse evidence changed')
        for key in REUSE_CHECKS:
            check = approval['checks'][key]
            require(check.get('verified') is True and check.get('explanation') and check.get('evidence_ids') and
                    set(check['evidence_ids']).issubset(evidence_ids), 'Unverified reuse check')
        imported = import_a1(folder / 'a1_source.csv', config, manifest['run_id'], tickets)
        by_row = {r['row']: r for r in imported}
        for row in rows:
            for field in FIELDS:
                a, b = row[field], by_row[row['row']][field]
                require(float(a) == float(b) if field == 'latency_seconds' else str(a) == str(b),
                        f'Imported record differs from A1 source: {field}')
    else:
        from run_a2_accuracy import validate_health
        health = read_json(folder / 'health_before.json')
        require(health['http_status'] == 200, 'Missing successful preflight')
        validate_health(json.loads(health['body']), manifest['expected_config'])
        events = [json.loads(line) for line in (folder / 'requests.jsonl').read_text(encoding='utf-8').splitlines()]
        require(len(events) == 176, 'Raw journal must contain one attempt/response pair per ticket')
        for row, attempt, response in zip(rows, events[::2], events[1::2]):
            require(attempt['event'] == 'attempt' and response['event'] == 'response' and
                    attempt['row'] == response['row'] == row['row'], 'Raw journal order/row mismatch')
            ticket = next(t for t in tickets if t['row'] == row['row'])
            require(attempt['payload'] == {'narrative': ticket['narrative'], 'row_id': row['row']},
                    'Raw request differs from frozen ticket')
            rid = next((v for k, v in response['headers'].items() if k.lower() == 'x-request-id'), '')
            require(response['http_status'] == row['http_status'] and response['error'] == row['error'] and
                    rid == row['request_id'], 'Raw response differs from predictions')
            if row['prediction'] != 'Failure':
                body = json.loads(response['body'])
                require(body['id'] == rid and label(body['category']) == row['prediction'], 'Raw prediction mismatch')
    return manifest, rows


def possible_reload(entry):
    return bool(entry) and any(isinstance(entry.get(k), (int, float)) and entry[k] > 1_000_000_000
        for k in ('ollama_load_ns', 'small_load_ns', 'large_load_ns'))


def reconcile(rows, path, tickets, service_run_id=None):
    run_id, config = rows[0]['run_id'], rows[0]['config']
    run_id = service_run_id or run_id
    logs, logged_rows = {}, set()
    test_ids = {r['row'] for r in tickets}
    prediction_ids = {r['request_id'] for r in rows if r['request_id']}
    for number, line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get('run_id') != run_id or entry.get('endpoint') != 'POST /tickets':
            continue
        rid = entry.get('request_id')
        # Reserved accuracy warm-up IDs; never infer warm-up from a missing ID,
        # an arbitrary non-test row, or timing. A prediction ID always wins.
        if (type(entry.get('row_id')) is int and entry['row_id'] in (-1, -2, -3)
                and entry['row_id'] not in test_ids and rid not in prediction_ids):
            continue
        require(rid and rid not in logs, f'Duplicate/missing service request ID at line {number}')
        if entry.get('row_id') in test_ids:
            require(entry['row_id'] not in logged_rows, 'More than one service attempt for a test row in this run')
            logged_rows.add(entry['row_id'])
        logs[rid] = entry
    lengths = {r['row']: len(r['narrative']) for r in tickets}
    decisions = []
    used = set()
    for row in rows:
        decision, reason = 'unknown', 'missing_request_id'
        entry = None
        if row['request_id'] and row['request_id'] not in logs:
            reason = 'missing_service_log'
        if row['request_id'] in logs:
            used.add(row['request_id'])
            entry = logs[row['request_id']]
            require(entry.get('row_id') == row['row'], 'Prediction/log row ID mismatch')
            require(entry.get('status') == row['http_status'], 'Prediction/log HTTP status mismatch')
            if config in MODELS:
                require(entry.get('mode') == 'single' or (row['source'] == 'a1_import' and 'mode' not in entry), 'Wrong logged service mode')
                require(entry.get('model') == MODELS[config], 'Wrong logged single model')
                if entry.get('final_model') is not None or (row['prediction'] != 'Failure' and row['source'] == 'live'):
                    require(entry.get('final_model') == MODELS[config], 'Wrong final single model')
                if row['prediction'] != 'Failure':
                    require(isinstance(entry.get('category'), str) and
                            label(entry['category']) == row['prediction'], 'Final category mismatch')
                decision, reason = 'not_applicable', 'matched'
            else:
                require(entry.get('mode') == 'cascade' and entry.get('small_model') == MODELS['llama3.2-1b'] and
                        entry.get('large_model') == MODELS['gemma3-4b'] and entry.get('rule') == 'length' and
                        str(entry.get('rule_setting')) == str(THRESHOLDS[config]), 'Wrong logged cascade configuration')
                require(entry.get('routing') in ('decided', 'not_reached'), 'Invalid logged routing state')
                reason = entry.get('routing')
                if reason == 'decided':
                    require(type(entry.get('escalated')) is bool, 'Missing boolean escalation decision')
                    small = entry.get('small_category')
                    require(small in CATEGORIES + ['Unclassified'], 'Missing/invalid small category')
                    escalation = small == 'Unclassified' or lengths[row['row']] > THRESHOLDS[config]
                    require(entry['escalated'] == escalation, 'Logged decision violates frozen rule')
                    reason = ('unclassified' if small == 'Unclassified' else
                              'too_long' if escalation else 'short_enough')
                    require(entry.get('escalation_reason') == reason, 'Wrong escalation reason')
                    decision = 'escalated' if escalation else 'accepted'
                if row['prediction'] != 'Failure':
                    require(decision != 'unknown', 'Successful request has no routing decision')
                    expected_model = MODELS['gemma3-4b'] if decision == 'escalated' else MODELS['llama3.2-1b']
                    require(entry.get('final_model') == expected_model and isinstance(entry.get('category'), str)
                            and label(entry['category']) == row['prediction'],
                            'Final model/category mismatch')
        decisions.append({'config': config, 'row': row['row'], 'request_id': row['request_id'],
                          'routing_group': decision, 'reason': reason, 'correct': row['correct'],
                          'evidence_status': 'matched' if entry else 'unmatched_prediction',
                          'load_durations_ns': json.dumps({k: entry[k] for k in
                              ('ollama_load_ns', 'small_load_ns', 'large_load_ns')
                              if entry and k in entry}),
                          'possible_reload': possible_reload(entry)})
    for rid, entry in logs.items():
        if rid not in used:
            decisions.append(dict(config=config, row=entry.get('row_id'), request_id=rid,
                routing_group='unknown', reason='no_prediction_request_id_match', correct=False,
                evidence_status='unmatched_service_log', load_durations_ns=json.dumps({k: entry[k]
                    for k in ('ollama_load_ns', 'small_load_ns', 'large_load_ns') if k in entry}),
                possible_reload=possible_reload(entry)))
    return decisions


def score_runs(runs, logs, tickets, service_run_ids=None):
    require(set(runs) == set(CONFIGS), 'Supply exactly one complete run for each of the five configurations')
    reference = runs['gemma3-4b']
    groups = ['overall'] + CATEGORIES
    floors, floor_values = [], {}
    for group in groups:
        subset = [r for r in reference if group == 'overall' or r['golden_label'] == group]
        require(subset, f'Empty reference category: {group}')
        correct = sum(r['correct'] for r in subset)
        tolerance = 10 if group == 'overall' else 15
        floor = Fraction(correct * 100, len(subset)) - tolerance
        floor_values[group] = floor
        floors.append(dict(category=group, reference_correct=correct, total=len(subset),
                           reference_accuracy_percent=correct / len(subset) * 100,
                           tolerance_pp=tolerance, floor_percent=float(floor)))
    overall, categories, eligibility, confusion, escalation, routing = [], [], [], [], [], []
    reconciliation = []
    for config in CONFIGS:
        rows = runs[config]
        passes = {}
        for group in groups:
            subset = [r for r in rows if group == 'overall' or r['golden_label'] == group]
            n, correct = len(subset), sum(r['correct'] for r in subset)
            passes[group] = Fraction(correct * 100, n) >= floor_values[group]
            record = dict(config=config, category=group, correct=correct, wrong=n-correct, total=n,
                          accuracy_percent=correct/n*100, floor_percent=float(floor_values[group]),
                          passes=passes[group])
            (overall if group == 'overall' else categories).append(record)
        eligible = all(passes.values())
        eligibility.append(dict(config=config, overall_pass=passes['overall'],
                                all_categories_pass=all(passes[c] for c in CATEGORIES),
                                accuracy_eligible=eligible, must_speed_test=config in THRESHOLDS or eligible,
                                reason='cascade_required_regardless_of_accuracy' if config in THRESHOLDS else
                                'passes_both_floors' if eligible else 'fails_accuracy_floor'))
        counts = Counter((r['golden_label'], r['prediction']) for r in rows)
        for gold in CATEGORIES:
            for prediction in CATEGORIES + ['Unclassified', 'Failure']:
                confusion.append(dict(config=config, golden_label=gold, prediction=prediction,
                                      count=counts[gold, prediction]))
        require(config in logs, f'--log {config}=PATH is required')
        evidence = reconcile(rows, logs[config], tickets, (service_run_ids or {}).get(config))
        reconciliation.extend(evidence)
        if config in THRESHOLDS:
            decisions = [e for e in evidence if e['evidence_status'] != 'unmatched_service_log']
            routing.extend({k: d[k] for k in ('config', 'row', 'request_id', 'routing_group', 'reason', 'correct')}
                           for d in decisions)
            counts = Counter(r['routing_group'] for r in decisions)
            known = counts['accepted'] + counts['escalated']
            summary = dict(config=config, total=88, known_decisions=known,
                           escalation_fraction=counts['escalated']/known if known else None)
            for group in ('accepted', 'escalated', 'unknown'):
                n = counts[group]
                correct = sum(r['correct'] for r in decisions if r['routing_group'] == group)
                summary.update({group+'_count': n, group+'_correct': correct,
                                group+'_accuracy_percent': correct/n*100 if n else None})
            escalation.append(summary)
    return {'service_reconciliation.csv': reconciliation, 'overall.csv': overall, 'per_category.csv': categories, 'floors.csv': floors,
            'eligibility.csv': eligibility, 'confusion_matrices.csv': confusion,
            'cascade_escalation.csv': escalation, 'cascade_routing.csv': routing}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='append', type=Path, required=True, help='Run directory; repeat five times')
    parser.add_argument('--log', action='append', default=[], help='CONFIG=PATH; required for all five configurations')
    parser.add_argument('--summary-id', required=True, help='Unique output subdirectory name')
    args = parser.parse_args(argv)
    import re
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', args.summary_id), 'Unsafe summary ID')
    tickets, runs, manifests, log_paths = load_test(), {}, [], {}
    validation = []
    service_run_ids = {}
    for folder in args.run:
        manifest, rows = load_run(folder, tickets)
        require(manifest['config'] not in runs, 'Duplicate configuration')
        runs[manifest['config']] = rows
        if manifest['source'] == 'a1_import':
            approval = read_json(folder / 'reuse_approval.json')
            require(approval.get('service_run_id'), 'Missing historical service_run_id')
            service_run_ids[manifest['config']] = approval['service_run_id']
        if manifest['source'] == 'live':
            try:
                issues = health_issues(read_json(folder / 'health_after.json'), manifest['expected_config'])
                if read_json(folder / 'complete.json').get('health_after_sha256') != sha(folder / 'health_after.json'):
                    issues.append('Post-run health hash missing or changed')
            except (OSError, ValueError):
                issues = ['Missing/invalid health_after.json']
            validation.append(dict(config=manifest['config'], issues=issues))
        manifests.append({'path': portable_path(folder), 'manifest_sha256': sha(folder/'manifest.json'),
                          'predictions_sha256': sha(folder/'predictions.csv')})
    for item in args.log:
        config, path = item.split('=', 1)
        require(config in CONFIGS and config not in log_paths, 'Unexpected/duplicate log mapping')
        log_paths[config] = Path(path)
    tables = score_runs(runs, log_paths, tickets, service_run_ids)
    folder = OUTPUT / ('summary_' + args.summary_id)
    folder.mkdir(parents=True, exist_ok=False)
    for filename, rows in tables.items():
        write_csv(folder / filename, rows, list(rows[0]))
    for config, path in log_paths.items():
        shutil.copyfile(path, folder / (config + '.service.jsonl'))
    write_json(folder / 'provenance.json', {'schema_version': 1, 'test_sha256': FROZEN_HASH,
               'scorer_sha256': sha(__file__), 'runs': manifests, 'service_run_ids': service_run_ids,
               'logs': {c: {'path': portable_path(p), 'sha256': sha(p)} for c, p in log_paths.items()}})
    unmatched = sum(r['evidence_status'] != 'matched' for r in tables['service_reconciliation.csv'])
    reloads = sum(r['possible_reload'] for r in tables['service_reconciliation.csv'])
    write_json(folder / 'validation.json', {'health': validation, 'unmatched_evidence': unmatched,
               'possible_reload_requests': reloads, 'review_required': bool(unmatched or reloads or any(v['issues'] for v in validation))})
    write_json(folder / 'complete.json', {'files': {p.name: sha(p) for p in folder.iterdir() if p.is_file()}})
    print('Configuration         Accuracy eligible   Must speed-test')
    for row in tables['eligibility.csv']:
        print(f'{row["config"]:22} {str(row["accuracy_eligible"]):19} {row["must_speed_test"]}')
    print(portable_path(folder))
    if unmatched or reloads or any(v['issues'] for v in validation):
        print('VALIDATION ISSUE: review validation.json and service_reconciliation.csv', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
