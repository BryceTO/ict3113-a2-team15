"""A2 accuracy collection/import. No requests are sent on import of this module."""
import argparse
import csv
import hashlib
import json
import math
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / 'golden_set/a2/test (even).csv'
OUTPUT = ROOT / 'results/a2/accuracy'
FROZEN_HASH = '05967ef4b64a87efdc3b5f12e48d3564804ddeea190e41c0b158990a7be3a19c'
CATEGORIES = ['Credit reporting', 'Debt collection', 'Mortgage', 'Credit card',
              'Bank account or service', 'Consumer loan', 'Money transfer or service']
LABELS = {s.lower(): s for s in CATEGORIES}
MODELS = {'llama3.2-1b': 'llama3.2:1b', 'gemma3-4b': 'gemma3:4b',
          'mistral-7b-instruct': 'mistral:7b-instruct'}
DIGESTS = {
    'llama3.2-1b': 'baf6a787fdffd633537aa2eb51cfd54cb93ff08e28040095462bb63daf552878',
    'gemma3-4b': 'a2af6cc3eb7fa8be8504abaf9b04e88f17a119ec3f04a3addf55f92841195f5a',
    'mistral-7b-instruct': '6577803aa9a036369e481d648a2baebb381ebc6e897f2bb9a766a2aa7bfbc1cf',
}
THRESHOLDS = {'cascade_s1': 241, 'cascade_s2': 289}
CONFIGS = list(MODELS) + list(THRESHOLDS)
FIELDS = ['row', 'config', 'run_id', 'source', 'golden_label', 'prediction',
          'correct', 'http_status', 'request_id', 'latency_seconds', 'error']
REUSE_CHECKS = ['model_digest', 'classification_prompt', 'category_matching',
                'ollama_version', 'machine_resources', 'inference_settings']


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def portable_path(path):
    try:
        return Path(path).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return Path(path).name


def health_issues(evidence, expected):
    try:
        require(evidence.get('http_status') == 200, 'Post-run health request failed')
        validate_health(json.loads(evidence['body']), expected)
        return []
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        return [str(exc)]


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def write_csv(path, rows, fields):
    with Path(path).open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def label(value):
    return LABELS.get(str(value).strip().lower(), 'Unclassified')


def boolean(value):
    require(str(value).lower() in ('true', 'false'), f'Invalid boolean: {value!r}')
    return str(value).lower() == 'true'


def load_test(path=TEST):
    rows = read_csv(path)
    require(len(rows) == 88, 'Expected exactly 88 test tickets')
    result = []
    for r in rows:
        row = int(r['ROW'])
        gold = label(r['GOLDEN_LABEL'])
        require(row % 2 == 0 and row > 0, 'Test row IDs must be positive and even')
        require(gold in CATEGORIES and r['NARRATIVE'].strip(), 'Invalid golden ticket')
        result.append({'row': row, 'narrative': r['NARRATIVE'], 'golden_label': gold})
    result.sort(key=lambda r: r['row'])
    require(len({r['row'] for r in result}) == 88, 'Duplicate test row IDs')
    canonical = [dict(r, golden_label=r['golden_label'].lower()) for r in result]
    digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False,
                                      separators=(',', ':')).encode()).hexdigest()
    require(digest == FROZEN_HASH, 'Test data differs from the frozen even-row split')
    return result


def expected_config(config):
    require(config in CONFIGS, 'Unknown configuration ID')
    expected = ({'mode': 'single', 'models': [MODELS[config]]} if config in MODELS else
                {'mode': 'cascade', 'models': [MODELS['llama3.2-1b'], MODELS['gemma3-4b']],
                 'rule': 'length', 'rule_setting': THRESHOLDS[config]})
    saved = read_json(ROOT / 'jmeter/a2_configs.json')[config]
    require(saved['mode'] == expected['mode'] and saved['models'] == expected['models'],
            'Benchmark configuration differs from the frozen configuration')
    if config in THRESHOLDS:
        for key in ('rule', 'rule_setting'):
            require(saved.get(key) is None or str(saved[key]) == str(expected[key]),
                    f'Benchmark {key} conflicts with the frozen setting')
    return expected


def validate_health(health, expected):
    require(health.get('status') == 'ok' and health.get('ollama') == 'up', 'Service/Ollama not healthy')
    require(health.get('mode') == expected['mode'], 'Wrong service mode')
    require(health.get('configured_models') == expected['models'], 'Wrong configured models')
    if expected['mode'] == 'cascade':
        require(health.get('rule') == 'length' and
                str(health.get('rule_setting')) == str(expected['rule_setting']), 'Wrong cascade rule/setting')
        require(health.get('all_configured_loaded') is True and
                set(expected['models']).issubset(health.get('loaded_models', [])),
                'Both cascade models must be resident')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(opener, url, timeout, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        response = opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        response = exc  # preserve HTTP failure body, status and request ID
    with response:
        return response.code, dict(response.headers.items()), response.read().decode('utf-8', errors='replace')


def validate_reuse(path, config, source):
    require(config in MODELS, 'A1 import is supported only for single models')
    approval = read_json(path)
    require(approval.get('config') == config and approval.get('eligible') is True,
            'Reuse evidence must explicitly approve this model')
    require(approval.get('service_run_id'), 'Missing historical service_run_id')
    require(approval.get('reviewer') and approval.get('reviewed_at'), 'Missing reuse reviewer/date')
    require(approval.get('source_sha256') == sha(source), 'A1 source hash does not match approval')
    require(approval.get('model_digest') == DIGESTS[config], 'Full model digest mismatch')
    evidence = approval.get('evidence', [])
    require(evidence, 'Missing supporting reuse evidence')
    names = set()
    for item in evidence:
        file = Path(path).resolve().parent / item['path']
        require(file.is_file() and sha(file) == item['sha256'], 'Reuse evidence missing or changed')
        require(item['id'] not in names, 'Duplicate evidence ID')
        names.add(item['id'])
    for key in REUSE_CHECKS:
        check = approval.get('checks', {}).get(key, {})
        require(check.get('verified') is True and check.get('explanation') and
                check.get('evidence_ids') and set(check['evidence_ids']).issubset(names),
                f'Reuse check is not verified: {key}')
    return approval


def import_a1(source, config, run_id, tickets):
    # Filter by IDs before examining outcomes. Failed A1 rows are retained, never dropped.
    wanted = {r['row']: r for r in tickets}
    selected = {}
    with Path(source).open(encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            row = int(r['row'])
            if row not in wanted:
                continue
            require(row not in selected, 'Duplicate A1 test row')
            require(r['model'] == MODELS[config], 'A1 model mismatch')
            require(label(r['golden_label']) == wanted[row]['golden_label'], 'A1 golden label mismatch')
            status = int(r['http_status'] or 0)
            latency = float(r['latency_seconds'])
            require(math.isfinite(latency) and latency >= 0, 'Invalid A1 latency')
            error = r['error'] or (f'HTTP {status}' if status != 200 else '')
            prediction = 'Failure' if error else label(r['predicted_label'])
            correct = prediction == wanted[row]['golden_label']
            require(boolean(r['correct']) == correct, 'A1 correctness field conflicts with outcome')
            require(error or r['request_id'], 'Successful A1 row lacks request ID')
            selected[row] = dict(row=row, config=config, run_id=run_id, source='a1_import',
                                 golden_label=wanted[row]['golden_label'], prediction=prediction,
                                 correct=correct, http_status=status, request_id=r['request_id'],
                                 latency_seconds=latency, error=error)
    require(set(selected) == set(wanted), 'A1 records do not cover all 88 test rows')
    ids = [r['request_id'] for r in selected.values() if r['request_id']]
    require(len(ids) == len(set(ids)), 'Duplicate A1 request ID')
    return [selected[row] for row in sorted(selected)]


def run_live(args, tickets, expected, folder):
    opener = urllib.request.build_opener(NoRedirect())  # no retry adapter, no redirects
    status, headers, body = request(opener, args.url.rstrip('/') + '/health', args.timeout)
    write_json(folder / 'health_before.json', {'http_status': status, 'headers': headers, 'body': body})
    require(status == 200, 'Health request failed')
    validate_health(json.loads(body), expected)
    seen = set()
    with (folder / 'predictions.csv').open('x', encoding='utf-8', newline='') as out, \
            (folder / 'requests.jsonl').open('x', encoding='utf-8') as raw:
        writer = csv.DictWriter(out, fieldnames=FIELDS)
        writer.writeheader()
        out.flush()
        for ticket in tickets:
            payload = {'narrative': ticket['narrative'], 'row_id': ticket['row']}
            # Persist the attempt BEFORE sending: interrupted runs are not resumable/retried.
            raw.write(json.dumps({'event': 'attempt', 'row': ticket['row'], 'payload': payload}) + '\n')
            raw.flush()
            start = time.perf_counter()
            status, headers, body, rid, error, prediction = 0, {}, '', '', '', 'Failure'
            try:
                status, headers, body = request(opener, args.url.rstrip('/') + '/tickets', args.timeout, payload)
                rid = next((v for k, v in headers.items() if k.lower() == 'x-request-id'), '')
                require(status == 200, f'HTTP {status}')
                result = json.loads(body)
                require(isinstance(result, dict) and isinstance(result.get('category'), str), 'Invalid response schema')
                require(rid and result.get('id') == rid, 'Missing/mismatched X-Request-ID')
                require(rid not in seen, 'Duplicate request ID')
                prediction = label(result['category'])
            except (OSError, ValueError, TypeError) as exc:
                error = str(exc)
                prediction = 'Failure'
            latency = time.perf_counter() - start
            if rid:
                seen.add(rid)
            record = dict(row=ticket['row'], config=args.config, run_id=args.run_id, source='live',
                          golden_label=ticket['golden_label'], prediction=prediction,
                          correct=prediction == ticket['golden_label'], http_status=status,
                          request_id=rid, latency_seconds=round(latency, 6), error=error)
            raw.write(json.dumps({'event': 'response', 'row': ticket['row'], 'http_status': status,
                                  'headers': headers, 'body': body, 'error': error}) + '\n')
            raw.flush()
            writer.writerow(record)
            out.flush()
    evidence = {'http_status': 0, 'headers': {}, 'body': '', 'error': ''}
    try:
        status, headers, body = request(opener, args.url.rstrip('/') + '/health', args.timeout)
        evidence.update(http_status=status, headers=headers, body=body)
    except (OSError, ValueError, TypeError) as exc:
        evidence['error'] = str(exc)
    evidence['validation_issues'] = health_issues(evidence, expected)
    write_json(folder / 'health_after.json', evidence)
    return read_csv(folder / 'predictions.csv')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', choices=CONFIGS, required=True)
    parser.add_argument('--run-id', required=True, help='Also set service RUN_ID to this exact ID for live runs')
    parser.add_argument('--url', help='Live service base URL; no requests for A1 import')
    parser.add_argument('--timeout', type=float, default=630)
    parser.add_argument('--import-a1', type=Path)
    parser.add_argument('--reuse-evidence', type=Path)
    args = parser.parse_args(argv)
    require(bool(args.url) != bool(args.import_a1), 'Choose exactly one of --url or --import-a1')
    require(math.isfinite(args.timeout) and args.timeout > 0, 'Timeout must be positive and finite')
    require(re.fullmatch(r'a2_' + re.escape(args.config) + r'_accuracy_[A-Za-z0-9_-]+', args.run_id),
            'Run ID must be a2_<config>_accuracy_<unique suffix>')
    tickets = load_test()
    expected = expected_config(args.config)
    imported, approval = None, None
    if args.import_a1:
        require(args.reuse_evidence is not None, '--reuse-evidence is required for import')
        approval = validate_reuse(args.reuse_evidence, args.config, args.import_a1)
        imported = import_a1(args.import_a1, args.config, args.run_id, tickets)
    else:
        require(args.reuse_evidence is None, '--reuse-evidence is only valid with --import-a1')
        require(args.url.startswith(('http://', 'https://')), 'Expected HTTP(S) URL')
    folder = OUTPUT / args.run_id
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'manifest.json', {'schema_version': 1, 'run_id': args.run_id,
               'config': args.config, 'source': 'a1_import' if imported is not None else 'live',
               'started_at': datetime.now(timezone.utc).isoformat(), 'test_sha256': FROZEN_HASH,
               'expected_config': expected, 'timeout': args.timeout,
               'runner_sha256': sha(__file__), 'frozen_commit': 'fafe5bfbf5b389e8e8f07cbda18a4a34cb6fe2f4'})
    if imported is not None:
        shutil.copyfile(args.import_a1, folder / 'a1_source.csv')
        write_json(folder / 'reuse_approval.json', dict(approval, evidence=[
            dict(item, path=f'reuse_evidence/{i}') for i, item in enumerate(approval['evidence'])]))
        # Archive each approved source so the provenance remains available after handoff.
        archive = folder / 'reuse_evidence'
        archive.mkdir()
        for index, evidence in enumerate(approval['evidence']):
            shutil.copyfile(args.reuse_evidence.resolve().parent / evidence['path'], archive / str(index))
        write_csv(folder / 'predictions.csv', imported, FIELDS)
        records = imported
    else:
        records = run_live(args, tickets, expected, folder)
    write_json(folder / 'complete.json', {'rows': len(records), 'predictions_sha256': sha(folder / 'predictions.csv'),
               'health_after_sha256': sha(folder / 'health_after.json') if imported is None else None,
               'completed_at': datetime.now(timezone.utc).isoformat(),
               'failures': sum(r['prediction'] == 'Failure' for r in records)})
    print(portable_path(folder))
    if imported is None:
        issues = read_json(folder / 'health_after.json')['validation_issues']
        if issues:
            print('VALIDATION ISSUE: ' + '; '.join(issues), file=sys.stderr)
            return 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(2)
