"""Revision audit, independent price publication, and preserved research boundaries."""
import copy
import unittest

import pandas as pd

from market_engine.operations.us_refresh import merge_export, revision_audit


class USRefreshTests(unittest.TestCase):
    def test_revision_is_measured_instead_of_hiding_it_in_a_tolerance(self):
        index = pd.to_datetime(['2026-10-01', '2026-10-02'])
        reference = pd.DataFrame({'SPY_1D_Return': [0.01, 0.02], 'MSI': [1., 2.],
                                  'Stress_Threshold': [2., 2.]}, index=index)
        features = reference[['SPY_1D_Return']].copy()
        features.iloc[1, 0] += 0.001
        audit = revision_audit(features, reference, reference, ['SPY_1D_Return'])
        self.assertEqual(audit['SPY_1D_Return']['changed'], 1)
        self.assertAlmostEqual(audit['SPY_1D_Return']['maxAbsoluteChange'], 0.001)
        self.assertEqual(audit['MSI']['changed'], 0)

    def test_missing_history_and_nonfinite_values_are_not_accepted_as_revisions(self):
        index = pd.to_datetime(['2026-10-01', '2026-10-02'])
        reference = pd.DataFrame({'f': [1., 2.], 'MSI': [1., 2.],
                                  'Stress_Threshold': [2., 2.]}, index=index)
        for frame in [reference.iloc[:1], reference.assign(f=float('inf'))]:
            with self.assertRaises(ValueError):
                revision_audit(frame, reference, reference, ['f'])
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            revision_audit(pd.concat([reference, reference]), reference, reference, ['f'])

    @staticmethod
    def inputs():
        point = {'date': '2026-11-06', 'price': 735., 'risk': .4, 'msi': .7, 'threshold': 1.2,
                 'recordType': 'OPERATIONAL'}
        korea = {'history': [copy.deepcopy(point)], 'current': point, 'lastValid': point}
        prior = {'generatedAt': '2026-11-03T00:00:00Z', 'markets': {'korea': korea, 'us': {}}}
        market = {'priceHistory': [{'date': '2026-11-09', 'price': 752.}],
                  'availability': [{'date': '2026-11-06', 'values': {'DBAA': 5.2, 'DGS10': 4.1}}],
                  'history': [point], 'lastValid': point, 'current': None}
        return prior, market

    def test_prices_require_explicit_publication_and_yields_are_always_private(self):
        prior, market = self.inputs()
        before = copy.deepcopy((prior, market))
        private = merge_export(prior, market, '2026-11-10T00:00:00Z')
        self.assertFalse(private['sourceValuesIncluded'])
        self.assertNotIn('priceHistory', private['markets']['us'])
        self.assertIsNone(private['markets']['us']['lastValid']['price'])
        public = merge_export(prior, market, '2026-11-10T00:00:00Z', publish_prices=True)
        self.assertTrue(public['sourceValuesIncluded'])
        self.assertEqual(public['markets']['us']['priceHistory'][-1]['price'], 752.)
        self.assertEqual(public['markets']['us']['lastValid']['price'], 735.)
        self.assertIsNone(public['markets']['us']['current'])  # no fabricated current date
        for output in [private, public]:
            self.assertNotIn('values', output['markets']['us']['availability'][0])
        self.assertEqual((prior, market), before)

    def test_us_refresh_does_not_relabel_koreas_collection_as_new(self):
        prior, market = self.inputs()
        result = merge_export(prior, market, '2026-11-10T00:00:00Z', True)
        self.assertEqual(result['markets']['korea']['generatedAt'], prior['generatedAt'])
        self.assertEqual(result['markets']['korea']['current']['risk'], prior['markets']['korea']['current']['risk'])
        self.assertIsNone(result['markets']['korea']['current']['price'])


if __name__ == '__main__':
    unittest.main()
