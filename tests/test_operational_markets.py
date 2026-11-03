"""Operational safety gates; never download, fit, or modify research artifacts."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

from market_engine.operations.run import assert_hash, compare, eligible_dates, public_summary, verify_model

ROOT = Path(__file__).resolve().parents[1]


class OperationalGateTests(unittest.TestCase):
    def test_raw_gap_is_not_an_inference_date(self):
        dates = pd.date_range('2026-10-01', periods=4)
        features = pd.DataFrame({'feature': [1., 2., 3., 4.]}, index=dates)
        raw = pd.DataFrame({'equity': [1., 2., 3., 4.], 'credit': [1., np.nan, 2., np.nan]}, index=dates)
        self.assertEqual(list(eligible_dates(features, raw, ['equity', 'credit'], dates[0])), [dates[2]])

    def test_nonfinite_features_and_training_dates_excluded(self):
        dates = pd.date_range('2026-10-01', periods=3)
        features = pd.DataFrame({'feature': [1., np.inf, np.nan]}, index=dates)
        raw = pd.DataFrame({'price': [1., 2., 3.]}, index=dates)
        self.assertEqual(len(eligible_dates(features, raw, ['price'], dates[0])), 0)

    def test_model_order_mismatch_fails_before_prediction(self):
        columns = [f'f{i}' for i in range(17)]
        model = SimpleNamespace(feature_names_in_=columns[::-1], n_features_in_=17)
        with self.assertRaisesRegex(ValueError, 'schema/order'):
            verify_model(model, columns)

    def test_historical_revision_and_missing_date_fail_closed(self):
        reference = pd.DataFrame({'MSI': [1., 2.]}, index=['2026-01-01', '2026-01-02'])
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            compare(reference.assign(MSI=[1., 2.1]), reference, ['MSI'])
        with self.assertRaisesRegex(ValueError, 'dates unavailable'):
            compare(reference.iloc[:1], reference, ['MSI'])

    def test_hash_change_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'model'
            path.write_bytes(b'frozen')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            path.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'Hash mismatch'):
                assert_hash(path, sha)

    def test_export_current_is_exact_date_not_last_valid(self):
        data = json.loads((ROOT/'frontend/public/data/operational-markets.json').read_text())
        private = {'markets': {'us': {'availability': [{'date': '2026-10-30', 'values': {'SPY': 755.72}}],
                                     'history': [{'price': 755.72, 'risk': 0.1}],
                                     'current': None, 'lastValid': {'price': 755.72, 'risk': 0.1}}}}
        shared = public_summary(private)
        self.assertNotIn('values', shared['markets']['us']['availability'][0])
        self.assertIsNone(shared['markets']['us']['history'][0]['price'])
        self.assertIsNone(shared['markets']['us']['lastValid']['price'])
        self.assertEqual(shared['markets']['us']['history'][0]['risk'], 0.1)
        self.assertEqual(private['markets']['us']['history'][0]['price'], 755.72)
        self.assertFalse(data['sourceValuesIncluded'])
        for market in data['markets'].values():
            self.assertTrue(all('values' not in row for row in market.get('availability', [])))
            if market['status'] == 'CURRENT':
                self.assertIsNotNone(market['current'])
                self.assertEqual(market['current']['date'], market['expectedDate'])
            else:
                self.assertIsNone(market['current'])
            self.assertTrue(all(point['recordType'] in ['OPERATIONAL', 'RETROSPECTIVE_INFERENCE'] for point in market['history']))
            self.assertEqual(len({p['date'] for p in market['history']}), len(market['history']))
            for point in market['history']:
                self.assertIsNone(point['price'])
                self.assertGreater(point['date'], market['trainingCutoff'])
                self.assertTrue(0 <= point['risk'] <= 1)
                self.assertTrue(np.isfinite([point['msi'], point['threshold']]).all())


if __name__ == '__main__':
    unittest.main()
