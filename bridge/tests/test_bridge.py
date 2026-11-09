import importlib.util
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch
from pathlib import Path
spec=importlib.util.spec_from_file_location('bridge',Path(__file__).parents[1]/'baostock_bridge.py')
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.master=[dict(code='sz.002463',code_name='沪电股份',type='1',status='1'),dict(code='sh.000001',code_name='上证指数',type='2',status='1')]
    def test_alias(self):
        self.assertEqual(b.resolve(self.master,'002463'),b.resolve(self.master,'002463.SZ'))
    def test_wrong_suffix(self):
        with self.assertRaises(b.ProviderError): b.resolve(self.master,'002463.SH')
    def test_not_index(self):
        with self.assertRaises(b.ProviderError): b.resolve(self.master,'000001.SH')
    def test_bse_gap(self):
        with self.assertRaises(b.ProviderError) as caught: b.resolve(self.master,'920029.BJ')
        self.assertEqual(caught.exception.code,'MARKET_COVERAGE_UNAVAILABLE')
    def test_injection(self):
        for code in ['$(whoami)','002463;ls','../../x','002463.XX']:
            with self.assertRaises(b.ProviderError): b.parse_code(code)
    def test_duplicate_identity(self):
        with self.assertRaises(b.ProviderError): b.resolve(self.master*2,'002463')
    def test_b_share_rejected(self):
        with self.assertRaises(b.ProviderError): b.resolve([dict(code='sh.900901',type='1')],'900901.SH')
    def test_source_error_not_empty(self):
        class Result: error_code='100'; error_msg='failed'
        with self.assertRaises(b.ProviderError): b.rows(Result())
    def test_explicit_horizon_reaches_all_daily_queries_and_caps_future_date(self):
        captured = datetime.fromisoformat('2026-11-09T19:00:00+08:00')
        empty = Mock(error_code='0', fields=[])
        empty.next.return_value = False
        provider = Mock()
        for method in ('query_history_k_data_plus', 'query_trade_dates', 'query_adjust_factor'):
            getattr(provider, method).return_value = empty
        for requested, expected in (('2026-11-08', '2026-11-08'), ('2026-11-09', '2026-11-09'),
                                    ('2026-11-10', '2026-11-09')):
            provider.reset_mock()
            args = SimpleNamespace(cache='.', code='002463.SZ', command='snapshot', end=requested, start='2026-11-01')
            with patch.object(b, 'datetime') as clock, patch.object(b, 'master_data', return_value=self.master):
                clock.now.return_value = captured
                result = b.execute(provider, args)
            self.assertEqual(result['requestedEnd'], expected)
            self.assertEqual(result['finalityPolicy'], 'SESSION_AWARE_BAOSTOCK_R1')
            self.assertEqual([call.kwargs['end_date'] for call in provider.query_history_k_data_plus.call_args_list], [expected, expected])
            self.assertEqual(provider.query_adjust_factor.call_args.kwargs['end_date'], expected)

if __name__=='__main__': unittest.main()
