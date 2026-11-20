"""Implementation smoke tests, not Yuhao's independent suite; no network calls."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import run_a2_accuracy as runner
import summarize_a2_accuracy as scorer


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tickets = [dict(row=2*(i+1), narrative='x' * (241 if i % 2 else 290),
                             golden_label=runner.CATEGORIES[i % 7]) for i in range(88)]

    def collect(self, config, after='ok', failure=False):
        expected = runner.expected_config(config)
        health = dict(status='ok', ollama='up', **expected,
                      configured_models=expected['models'], loaded_models=expected['models'],
                      all_configured_loaded=True)
        rid = f'a2_{config}_accuracy_synthetic'
        entries, calls = [], []

        def fake_request(opener, url, timeout, payload=None):
            self.assertEqual(timeout, 630)
            calls.append(payload)
            if payload is None:
                if len(calls) > 1:
                    if after == 'transport':
                        raise TimeoutError('synthetic health timeout')
                    if after == 'malformed':
                        return 200, {}, 'invalid json'
                    if after == 'http':
                        return 503, {}, '{}'
                    if after == 'config':
                        return 200, {}, json.dumps(dict(health, mode='wrong'))
                    if after == 'residency':
                        return 200, {}, json.dumps(dict(health, loaded_models=[], all_configured_loaded=False))
                return 200, {}, json.dumps(health)
            ticket = next(t for t in self.tickets if t['row'] == payload['row_id'])
            request_id = f'request-{ticket["row"]}'
            failed = failure and ticket['row'] == 2
            entry = dict(run_id=rid, request_id=request_id, row_id=ticket['row'],
                         endpoint='POST /tickets', status=502 if failed else 200,
                         mode=expected['mode'], category=ticket['golden_label'])
            if config in runner.MODELS:
                entry.update(model=runner.MODELS[config], ollama_load_ns=100)
                if not failed:
                    entry['final_model'] = runner.MODELS[config]
            else:
                escalated = len(ticket['narrative']) > runner.THRESHOLDS[config]
                entry.update(small_model=expected['models'][0], large_model=expected['models'][1],
                             rule='length', rule_setting=expected['rule_setting'], routing='decided',
                             small_category=ticket['golden_label'], escalated=escalated,
                             escalation_reason='too_long' if escalated else 'short_enough',
                             final_model=expected['models'][int(escalated)], small_load_ns=100)
                if escalated and not failed:
                    entry['large_load_ns'] = 100
            entries.append(entry)
            if failed and failure == 'timeout':
                raise TimeoutError('synthetic accuracy timeout')
            return entry['status'], {'X-Request-ID': request_id}, json.dumps(
                dict(id=request_id, category=ticket['golden_label']))

        with patch.object(runner, 'OUTPUT', self.root), patch.object(runner, 'load_test', return_value=self.tickets), \
                patch.object(runner, 'request', side_effect=fake_request):
            code = runner.main(['--config', config, '--run-id', rid, '--url', 'http://synthetic.invalid'])
        folder = self.root / rid
        log = self.root / (config + '.jsonl')
        log.write_text('\n'.join(map(json.dumps, entries)), encoding='utf-8')
        self.assertEqual(sum(p is not None for p in calls), 88)
        self.assertEqual(len(calls), 90)
        manifest, rows = scorer.load_run(folder, self.tickets)
        self.assertEqual(len(rows), 88)
        return code, folder, log, rows, entries

    def test_five_configurations_and_cli(self):
        args = []
        for config in runner.CONFIGS:
            code, folder, log, rows, entries = self.collect(config, failure=True)
            self.assertEqual(code, 0)
            self.assertEqual(rows[0]['prediction'], 'Failure')
            evidence = scorer.reconcile(rows, log, self.tickets)
            self.assertTrue(all(e['evidence_status'] == 'matched' for e in evidence))
            args += ['--run', str(folder), '--log', f'{config}={log}']
        with patch.object(scorer, 'OUTPUT', self.root), patch.object(scorer, 'load_test', return_value=self.tickets):
            self.assertEqual(scorer.main(args + ['--summary-id', 'synthetic']), 0)
        summary = self.root / 'summary_synthetic'
        self.assertEqual(len(runner.read_csv(summary / 'service_reconciliation.csv')), 440)
        self.assertTrue(all(int(r['total']) == 88 for r in runner.read_csv(summary / 'overall.csv')))
        self.assertNotIn(str(self.root), (summary / 'provenance.json').read_text())
        # Post-run evidence changes are flagged while predictions and summary survive.
        first = self.root / 'a2_llama3.2-1b_accuracy_synthetic'
        (first / 'health_after.json').write_text('{}')
        with patch.object(scorer, 'OUTPUT', self.root), patch.object(scorer, 'load_test', return_value=self.tickets):
            self.assertEqual(scorer.main(args + ['--summary-id', 'bad_health']), 2)
        self.assertTrue((self.root / 'summary_bad_health/complete.json').is_file())

    def test_post_run_failures_preserve_completion(self):
        for after in ('transport', 'malformed', 'http', 'config', 'residency'):
            with self.subTest(after=after):
                # Separate roots avoid overwriting evidence between synthetic cases.
                self.root = self.root / after
                self.root.mkdir()
                code, folder, _, _, _ = self.collect('cascade_s1', after=after)
                self.assertEqual(code, 2)
                self.assertTrue((folder / 'complete.json').is_file())
                self.assertTrue(runner.read_json(folder / 'health_after.json')['validation_issues'])

    def test_single_log_mismatches_and_unmatched_evidence(self):
        _, _, log, rows, entries = self.collect('llama3.2-1b', failure=True)
        for field, value in [('row_id', -1), ('status', 201), ('mode', 'cascade'),
                             ('model', 'wrong'), ('final_model', 'wrong'), ('category', 'wrong')]:
            changed = copy.deepcopy(entries)
            changed[1][field] = value
            log.write_text('\n'.join(map(json.dumps, changed)))
            with self.subTest(field=field), self.assertRaises(ValueError):
                scorer.reconcile(rows, log, self.tickets)
        log.write_text('\n'.join(map(json.dumps, entries)))
        rows[0]['request_id'] = ''
        evidence = scorer.reconcile(rows, log, self.tickets)
        self.assertEqual(evidence[0]['evidence_status'], 'unmatched_prediction')
        self.assertEqual(evidence[-1]['evidence_status'], 'unmatched_service_log')
        self.assertEqual(rows[0]['request_id'], '')
        entries[1]['run_id'] = 'wrong-run'
        entries[2]['small_load_ns'] = 1_000_000_001
        log.write_text('\n'.join(map(json.dumps, entries)))
        evidence = scorer.reconcile(rows, log, self.tickets)
        self.assertEqual(evidence[1]['reason'], 'missing_service_log')
        self.assertTrue(evidence[2]['possible_reload'])

    def test_accuracy_timeout_and_historical_log_identity(self):
        _, _, log, rows, entries = self.collect('gemma3-4b', failure='timeout')
        self.assertEqual(rows[0]['http_status'], 0)
        self.assertEqual(rows[0]['request_id'], '')
        self.assertEqual(rows[0]['prediction'], 'Failure')
        evidence = scorer.reconcile(rows, log, self.tickets)
        self.assertEqual(evidence[0]['evidence_status'], 'unmatched_prediction')
        for row in rows:
            row['source'] = 'a1_import'
        for entry in entries:
            entry['run_id'] = 'historical-reviewed-run'
            entry.pop('mode')
            entry.pop('final_model', None)
        log.write_text('\n'.join(map(json.dumps, entries)))
        evidence = scorer.reconcile(rows, log, self.tickets, 'historical-reviewed-run')
        self.assertTrue(all(e['evidence_status'] == 'matched' for e in evidence[1:88]))

    def test_explicit_warmups_keep_official_evidence_checks(self):
        _, _, log, rows, entries = self.collect('cascade_s1')
        warmups = [dict(entries[0], row_id=-i, request_id=f'warmup-{i}',
                        small_load_ns=2_000_000_000) for i in (1, 2, 3)]
        log.write_text('\n'.join(map(json.dumps, warmups + entries)))
        evidence = scorer.reconcile(rows, log, self.tickets)
        self.assertEqual(len(evidence), 88)
        self.assertTrue(all(e['evidence_status'] == 'matched' for e in evidence))
        self.assertFalse(any(e['possible_reload'] for e in evidence))
        # Missing/unknown row IDs cannot be assumed to be warm-ups.
        for row_id in (None, 99999, -4, '-1'):
            extra = dict(entries[0], row_id=row_id, request_id='unmatched-official')
            log.write_text('\n'.join(map(json.dumps, warmups + entries + [extra])))
            with self.subTest(row_id=row_id):
                self.assertEqual(scorer.reconcile(rows, log, self.tickets)[-1]['evidence_status'],
                                 'unmatched_service_log')
        # A second attempt at a test row still fails, regardless of its claimed purpose.
        duplicate = dict(entries[0], request_id='warmup-claim', purpose='warmup')
        log.write_text('\n'.join(map(json.dumps, warmups + entries + [duplicate])))
        with self.assertRaisesRegex(ValueError, 'More than one service attempt'):
            scorer.reconcile(rows, log, self.tickets)
        # An official request ID cannot be hidden by a reserved warm-up row ID.
        disguised = dict(entries[0], row_id=-1)
        log.write_text('\n'.join(map(json.dumps, [disguised] + entries[1:])))
        with self.assertRaisesRegex(ValueError, 'row ID mismatch'):
            scorer.reconcile(rows, log, self.tickets)


if __name__ == '__main__':
    unittest.main()
