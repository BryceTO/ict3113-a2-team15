"""Hand-checked model evaluation tests; no Ollama or official golden rows."""
import copy
from contextlib import ExitStack, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from support import (CATEGORIES, CONFIGS, build_run, cases_for_correct_counts, fixture,
                     perfect_cases, runner, save_complete_run, scorer,
                     tickets_for_counts, write_csv, write_json, write_log)


class SyntheticEvaluationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='yuhao_ml_')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Any accidental network access is a test failure, not a real request.
        network = patch('socket.create_connection', side_effect=AssertionError('ML tests must be offline'))
        network.start()
        self.addCleanup(network.stop)

    def score(self, tickets, cases_by_config, categories=None):
        runs, logs = {}, {}
        for config, cases in cases_by_config.items():
            runs[config], entries = build_run(config, tickets, cases)
            logs[config] = write_log(self.root / f'{config}.jsonl', entries)
        # Small fixtures narrow only the configured comparison/category scope.
        # No scorer, reconciliation, arithmetic or validation function is mocked.
        with ExitStack() as stack:
            stack.enter_context(patch.object(scorer, 'CONFIGS', list(cases_by_config)))
            if categories is not None:
                stack.enter_context(patch.object(scorer, 'CATEGORIES', categories))
            return scorer.score_runs(runs, logs, tickets)

    def five_ticket_inputs(self):
        data = fixture('five_tickets.json')
        tickets = [dict(row=r['row'], narrative='synthetic complaint', golden_label=r['golden_label'])
                   for r in data['tickets']]
        cases = [dict(prediction=r['prediction'], correct=r['correct']) for r in data['tickets']]
        return data, tickets, cases

    def cascade_inputs(self):
        data = fixture('cascade_routing.json')
        tickets = [dict(row=2 * (i + 1), narrative='x' * (data['cases'][i]['length'] if i < 8 else 20),
                        golden_label=CATEGORIES[i % 7]) for i in range(88)]
        cases = data['cases'] + perfect_cases(tickets[8:])
        return data, tickets, cases

    def test_five_tickets_three_correct_wrong_category_and_backend_failure(self):
        data, tickets, cases = self.five_ticket_inputs()
        tables = self.score(tickets, {'gemma3-4b': cases}, CATEGORIES[:2])
        overall = tables['overall.csv'][0]
        for field in ('correct', 'wrong', 'total', 'accuracy_percent'):
            self.assertEqual(overall[field], data['expected'][field])
        for row in tables['per_category.csv']:
            expected = data['expected']['per_category'][row['category']]
            self.assertEqual((row['correct'], row['total']), (expected['correct'], expected['total']))
            self.assertAlmostEqual(row['accuracy_percent'], expected['accuracy_percent'])
        nonzero = [[r['golden_label'], r['prediction'], r['count']]
                   for r in tables['confusion_matrices.csv'] if r['count']]
        self.assertCountEqual(nonzero, data['expected']['nonzero_confusion'])
        self.assertEqual(sum(r['count'] for r in tables['confusion_matrices.csv']), 5)

    def test_unclassified_and_failure_have_separate_confusion_columns(self):
        _, tickets, cases = self.five_ticket_inputs()
        cases[3].update(prediction='Unclassified', correct=False)
        tables = self.score(tickets, {'gemma3-4b': cases}, CATEGORIES[:2])
        self.assertEqual(tables['overall.csv'][0]['correct'], 2)
        self.assertEqual(tables['overall.csv'][0]['accuracy_percent'], 40)
        cells = {(r['golden_label'], r['prediction']): r['count']
                 for r in tables['confusion_matrices.csv']}
        self.assertEqual(cells['Debt collection', 'Unclassified'], 1)
        self.assertEqual(cells['Debt collection', 'Failure'], 1)
        debt = next(r for r in tables['per_category.csv'] if r['category'] == 'Debt collection')
        self.assertEqual((debt['correct'], debt['wrong'], debt['total']), (1, 2, 3))

    def test_complete_loader_counts_failures_in_the_full_88(self):
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        cases = perfect_cases(tickets)
        cases[0].update(prediction='Failure', correct=False)
        cases[1].update(prediction='Unclassified', correct=False)
        folder, _ = save_complete_run(self.root / 'complete', 'gemma3-4b', tickets, cases)
        _, rows = scorer.load_run(folder, tickets)
        self.assertEqual(len(rows), 88)
        self.assertEqual(sum(r['correct'] for r in rows), 86)
        self.assertFalse(rows[0]['correct'])
        self.assertFalse(rows[1]['correct'])

    def test_complete_loader_rejects_forged_correctness(self):
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        cases = perfect_cases(tickets)
        cases[0].update(prediction='Failure', correct=False)
        folder, _ = save_complete_run(self.root / 'forged', 'gemma3-4b', tickets, cases)
        rows = runner.read_csv(folder / 'predictions.csv')
        rows[0]['correct'] = 'True'
        write_csv(folder / 'predictions.csv', rows, runner.FIELDS)
        completion = runner.read_json(folder / 'complete.json')
        completion['predictions_sha256'] = runner.sha(folder / 'predictions.csv')
        write_json(folder / 'complete.json', completion)
        with self.assertRaisesRegex(ValueError, 'Incorrect stored correctness'):
            scorer.load_run(folder, tickets)

    def test_complete_loader_rejects_duplicate_and_odd_prediction_ids(self):
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        for kind, changed_row in [('duplicate', 2), ('odd', 3)]:
            with self.subTest(kind=kind):
                folder, _ = save_complete_run(self.root / kind, 'gemma3-4b', tickets, perfect_cases(tickets))
                rows = runner.read_csv(folder / 'predictions.csv')
                rows[1]['row'] = changed_row
                write_csv(folder / 'predictions.csv', rows, runner.FIELDS)
                completion = runner.read_json(folder / 'complete.json')
                completion['predictions_sha256'] = runner.sha(folder / 'predictions.csv')
                write_json(folder / 'complete.json', completion)
                with self.assertRaisesRegex(ValueError, 'Unexpected/duplicate test row'):
                    scorer.load_run(folder, tickets)

    def test_exact_overall_floor_passes_and_one_ticket_below_fails(self):
        # Reference 100/100 -> overall floor 90%; every category floor 85%.
        tickets = tickets_for_counts([20, 20, 20, 10, 10, 10, 10])
        reference = perfect_cases(tickets)
        candidate = cases_for_correct_counts(tickets, [18, 18, 18, 9, 9, 9, 9])
        tables = self.score(tickets, {'gemma3-4b': reference, 'llama3.2-1b': candidate})
        overall = next(r for r in tables['overall.csv'] if r['config'] == 'llama3.2-1b')
        self.assertEqual((overall['correct'], overall['total'], overall['floor_percent']), (90, 100, 90))
        self.assertTrue(overall['passes'])
        self.assertTrue(tables['eligibility.csv'][1]['accuracy_eligible'])
        candidate[0].update(prediction='Debt collection', small_category='Debt collection', correct=False)
        tables = self.score(tickets, {'gemma3-4b': reference, 'llama3.2-1b': candidate})
        eligibility = tables['eligibility.csv'][1]
        self.assertFalse(eligibility['overall_pass'])
        self.assertTrue(eligibility['all_categories_pass'])
        self.assertFalse(eligibility['accuracy_eligible'])

    def test_exact_category_floor_passes(self):
        # Reference 20/20 -> category floor 85%; candidate 17/20 is exactly on it.
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        candidate = cases_for_correct_counts(tickets, [17, 17, 10, 10, 10, 10, 8])
        tables = self.score(tickets, {'gemma3-4b': perfect_cases(tickets), 'llama3.2-1b': candidate})
        credit = next(r for r in tables['per_category.csv']
                      if r['config'] == 'llama3.2-1b' and r['category'] == 'Credit reporting')
        self.assertEqual((credit['correct'], credit['total'], credit['floor_percent']), (17, 20, 85))
        self.assertTrue(credit['passes'])
        self.assertTrue(tables['eligibility.csv'][1]['accuracy_eligible'])

    def test_overall_pass_cannot_hide_one_category_failure(self):
        # Candidate 84/88 passes overall; Credit reporting 16/20 fails its 85% floor.
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        candidate = cases_for_correct_counts(tickets, [16, 20, 10, 10, 10, 10, 8])
        tables = self.score(tickets, {'gemma3-4b': perfect_cases(tickets), 'llama3.2-1b': candidate})
        eligibility = tables['eligibility.csv'][1]
        self.assertTrue(eligibility['overall_pass'])
        self.assertFalse(eligibility['all_categories_pass'])
        self.assertFalse(eligibility['accuracy_eligible'])
        failed = [r['category'] for r in tables['per_category.csv']
                  if r['config'] == 'llama3.2-1b' and not r['passes']]
        self.assertEqual(failed, ['Credit reporting'])

    def test_fractional_floor_decision_precedes_display_rounding(self):
        # 69/88 - 10pp = 68.4090909...%; 60/88 fails, 61/88 passes overall.
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        reference = cases_for_correct_counts(tickets, [1, 20, 10, 10, 10, 10, 8])
        for counts, expected in [([0, 12, 10, 10, 10, 10, 8], False),
                                 ([0, 13, 10, 10, 10, 10, 8], True)]:
            with self.subTest(correct=sum(counts)):
                tables = self.score(tickets, {'gemma3-4b': reference,
                    'llama3.2-1b': cases_for_correct_counts(tickets, counts)})
                floor = tables['floors.csv'][0]
                self.assertEqual((floor['reference_correct'], floor['total']), (69, 88))
                self.assertAlmostEqual(floor['floor_percent'], 68.4090909090909)
                self.assertEqual(tables['eligibility.csv'][1]['overall_pass'], expected)

    def test_cascade_routing_denominators_and_group_accuracy(self):
        data, tickets, cases = self.cascade_inputs()
        cases_by_config = {c: cases if c.startswith('cascade') else perfect_cases(tickets) for c in CONFIGS}
        tables = self.score(tickets, cases_by_config)
        expected = data['expected']
        for summary in tables['cascade_escalation.csv']:
            with self.subTest(config=summary['config']):
                for field in ('total', 'known_decisions', 'accepted_count', 'accepted_correct',
                              'escalated_count', 'escalated_correct', 'unknown_count', 'unknown_correct'):
                    self.assertEqual(summary[field], expected[field])
                self.assertAlmostEqual(summary['escalation_fraction'], 5 / 87)
                self.assertAlmostEqual(summary['accepted_accuracy_percent'], 81 / 82 * 100)
                self.assertEqual(summary['escalated_accuracy_percent'], 40)
                self.assertEqual(summary['unknown_accuracy_percent'], 0)
        for config in ('cascade_s1', 'cascade_s2'):
            overall = next(r for r in tables['overall.csv'] if r['config'] == config)
            self.assertEqual((overall['correct'], overall['total']), (83, 88))
            eligibility = next(r for r in tables['eligibility.csv'] if r['config'] == config)
            self.assertTrue(eligibility['accuracy_eligible'])
            self.assertTrue(eligibility['must_speed_test'])

    def test_failure_before_routing_is_unknown_but_large_failure_is_escalated(self):
        _, tickets, cases = self.cascade_inputs()
        rows, entries = build_run('cascade_s1', tickets, cases)
        # Reverse the logs to require a request-ID join, rather than a positional zip.
        path = write_log(self.root / 'reversed.jsonl', list(reversed(entries)))
        decisions = scorer.reconcile(rows, path, tickets)
        self.assertEqual(decisions[4]['routing_group'], 'escalated')
        self.assertFalse(decisions[4]['correct'])
        self.assertEqual(decisions[5]['routing_group'], 'unknown')
        self.assertEqual(decisions[5]['reason'], 'not_reached')
        self.assertTrue(all(r['evidence_status'] == 'matched' for r in decisions))

    def test_all_unknown_routing_has_no_invented_escalation_rate(self):
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        unknown = [dict(prediction='Failure', correct=False, group='unknown') for _ in tickets]
        tables = self.score(tickets, {'gemma3-4b': perfect_cases(tickets), 'cascade_s1': unknown})
        summary = tables['cascade_escalation.csv'][0]
        self.assertEqual((summary['known_decisions'], summary['unknown_count']), (0, 88))
        self.assertIsNone(summary['escalation_fraction'])
        self.assertIsNone(summary['accepted_accuracy_percent'])
        self.assertIsNone(summary['escalated_accuracy_percent'])
        eligibility = next(r for r in tables['eligibility.csv'] if r['config'] == 'cascade_s1')
        self.assertFalse(eligibility['accuracy_eligible'])
        self.assertTrue(eligibility['must_speed_test'])

    def test_test_split_rejects_duplicates_odd_ids_and_changed_frozen_labels(self):
        tickets = tickets_for_counts([20, 20, 10, 10, 10, 10, 8])
        canonical = [dict(t, golden_label=t['golden_label'].lower()) for t in tickets]
        fingerprint = hashlib.sha256(json.dumps(canonical, ensure_ascii=False,
            separators=(',', ':')).encode()).hexdigest()
        rows = [dict(ROW=t['row'], NARRATIVE=t['narrative'], GOLDEN_LABEL=t['golden_label'])
                for t in tickets]
        path = self.root / 'synthetic-even.csv'
        write_csv(path, list(reversed(rows)))
        # Replace only the data fingerprint with that of our synthetic fixture.
        with patch.object(runner, 'FROZEN_HASH', fingerprint):
            self.assertEqual(runner.load_test(path), tickets)
            for kind, message in [('duplicate', 'Duplicate test row IDs'),
                                  ('odd', 'positive and even'),
                                  ('label', 'differs from the frozen')]:
                with self.subTest(kind=kind):
                    changed = copy.deepcopy(rows)
                    if kind == 'duplicate':
                        changed[1]['ROW'] = changed[0]['ROW']
                    elif kind == 'odd':
                        changed[0]['ROW'] = 1
                    else:
                        changed[0]['GOLDEN_LABEL'] = 'Debt collection'
                    write_csv(path, changed)
                    with self.assertRaisesRegex(ValueError, message):
                        runner.load_test(path)

    def test_inclusive_length_threshold_unicode_and_unclassified_escalation(self):
        for config, threshold in [('cascade_s1', 241), ('cascade_s2', 289)]:
            with self.subTest(config=config):
                tickets = [dict(row=2, narrative='\U0001f600' * threshold, golden_label='Credit reporting'),
                           dict(row=4, narrative='x' * (threshold + 1), golden_label='Debt collection'),
                           dict(row=6, narrative='x', golden_label='Mortgage')]
                cases = [dict(prediction='Credit reporting', correct=True, group='accepted', small_category='Credit reporting'),
                         dict(prediction='Debt collection', correct=True, group='escalated', small_category='Credit reporting'),
                         dict(prediction='Mortgage', correct=True, group='escalated', small_category='Unclassified')]
                rows, entries = build_run(config, tickets, cases)
                path = write_log(self.root / 'boundary.jsonl', entries)
                decisions = scorer.reconcile(rows, path, tickets)
                self.assertEqual([r['routing_group'] for r in decisions], ['accepted', 'escalated', 'escalated'])
                self.assertEqual([r['reason'] for r in decisions], ['short_enough', 'too_long', 'unclassified'])
                entries[0].update(escalated=True, escalation_reason='too_long', final_model='gemma3:4b')
                write_log(path, entries)
                with self.assertRaisesRegex(ValueError, 'violates frozen rule'):
                    scorer.reconcile(rows, path, tickets)

    def test_prediction_log_row_mismatch_is_rejected(self):
        _, tickets, cases = self.cascade_inputs()
        rows, entries = build_run('cascade_s1', tickets, cases)
        entries[0]['row_id'] = 9998
        path = write_log(self.root / 'wrong-row.jsonl', entries)
        with self.assertRaisesRegex(ValueError, 'row ID mismatch'):
            scorer.reconcile(rows, path, tickets)


class TuningSeparationTests(unittest.TestCase):
    def setUp(self):
        # Missing pandas is an actionable dependency error, never a silently skipped test.
        import tune_cascade
        import tune_length
        self.category_tuner = tune_cascade
        self.length_tuner = tune_length
        temporary = tempfile.TemporaryDirectory(prefix='yuhao_tuning_')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.tuning_path = self.root / 'odd.csv'
        self.llama_path = self.root / 'llama.csv'
        self.gemma_path = self.root / 'gemma.csv'
        self.odd_rows = [dict(ROW=2 * i + 1, NARRATIVE='x' * (20 + i), GOLDEN_LABEL=CATEGORIES[i % 7])
                         for i in range(87)]
        self.predictions = [dict(row=r['ROW'], golden_label=r['GOLDEN_LABEL'],
                                 predicted_label=r['GOLDEN_LABEL'], http_status=200)
                            for r in self.odd_rows]
        self.even_rows = [dict(row=2 * (i + 1), golden_label=CATEGORIES[i % 7],
                               predicted_label='Credit reporting', http_status=200) for i in range(88)]
        write_csv(self.tuning_path, self.odd_rows)
        write_csv(self.llama_path, self.predictions + self.even_rows)
        write_csv(self.gemma_path, self.predictions + self.even_rows)
        network = patch('socket.create_connection', side_effect=AssertionError('ML tests must be offline'))
        network.start()
        self.addCleanup(network.stop)

    def run_tuner(self, module, output):
        with ExitStack() as stack:
            # tune_length imports loader functions whose globals belong to tune_cascade.
            for target in (self.category_tuner, self.length_tuner):
                for name, value in [('TUNING_FILE', self.tuning_path), ('LLAMA_FILE', self.llama_path),
                                    ('GEMMA_FILE', self.gemma_path), ('OUT_DIR', output)]:
                    stack.enter_context(patch.object(target, name, value))
            with redirect_stdout(io.StringIO()):
                module.main()

    def test_even_predictions_cannot_change_category_or_length_tuning_outputs(self):
        for module in (self.category_tuner, self.length_tuner):
            with self.subTest(tuner=module.__name__):
                write_csv(self.llama_path, self.predictions + self.even_rows)
                write_csv(self.gemma_path, self.predictions + self.even_rows)
                before = self.root / (module.__name__ + '_before')
                after = self.root / (module.__name__ + '_after')
                self.run_tuner(module, before)
                changed = [dict(r, golden_label='invalid even label', predicted_label='Unclassified',
                                http_status=502) for r in self.even_rows]
                write_csv(self.llama_path, self.predictions + changed)
                write_csv(self.gemma_path, self.predictions + changed)
                self.run_tuner(module, after)
                outputs = {p.name: p.read_bytes() for p in before.glob('*.csv')}
                self.assertTrue(outputs)
                self.assertEqual(outputs, {p.name: p.read_bytes() for p in after.glob('*.csv')})

    def test_duplicate_or_even_tuning_ids_stop_both_reports(self):
        for kind in ('duplicate', 'even'):
            changed = copy.deepcopy(self.odd_rows)
            changed[1]['ROW'] = 1 if kind == 'duplicate' else 2
            write_csv(self.tuning_path, changed)
            for module in (self.category_tuner, self.length_tuner):
                with self.subTest(kind=kind, tuner=module.__name__):
                    output = self.root / (kind + module.__name__)
                    with self.assertRaisesRegex(ValueError, 'Duplicate tuning|Even rows'):
                        self.run_tuner(module, output)
                    self.assertEqual(list(output.glob('*.csv')), [])

    def test_even_only_predictions_cannot_substitute_for_tuning_predictions(self):
        write_csv(self.llama_path, self.even_rows)
        for module in (self.category_tuner, self.length_tuner):
            with self.subTest(tuner=module.__name__):
                output = self.root / ('even_only_' + module.__name__)
                with self.assertRaisesRegex(ValueError, 'Missing tuning predictions'):
                    self.run_tuner(module, output)
                self.assertEqual(list(output.glob('*.csv')), [])

    def test_invalid_label_or_missing_tuning_ticket_stops_both_reports(self):
        invalid_label = copy.deepcopy(self.odd_rows)
        invalid_label[0]['GOLDEN_LABEL'] = 'not a category'
        for name, rows, message in [('label', invalid_label, 'Invalid golden label'),
                                    ('count', self.odd_rows[1:], 'Expected 87 tuning tickets')]:
            write_csv(self.tuning_path, rows)
            for module in (self.category_tuner, self.length_tuner):
                with self.subTest(case=name, tuner=module.__name__):
                    output = self.root / (name + module.__name__)
                    with self.assertRaisesRegex(ValueError, message):
                        self.run_tuner(module, output)
                    self.assertEqual(list(output.glob('*.csv')), [])

    def test_duplicate_missing_and_mislabelled_odd_predictions_stop_reports(self):
        variants = [('duplicate', self.predictions + [self.predictions[0]], 'Duplicate tuning predictions'),
                    ('missing', self.predictions[1:], 'Missing tuning predictions')]
        wrong_label = copy.deepcopy(self.predictions)
        wrong_label[0]['golden_label'] = 'Debt collection'
        variants.append(('label', wrong_label, 'Golden label mismatch'))
        for name, predictions, message in variants:
            write_csv(self.llama_path, predictions + self.even_rows)
            for module in (self.category_tuner, self.length_tuner):
                with self.subTest(case=name, tuner=module.__name__):
                    output = self.root / (name + module.__name__)
                    with self.assertRaisesRegex(ValueError, message):
                        self.run_tuner(module, output)
                    self.assertEqual(list(output.glob('*.csv')), [])


if __name__ == '__main__':
    unittest.main()
