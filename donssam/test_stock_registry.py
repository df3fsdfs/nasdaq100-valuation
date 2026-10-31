import unittest
from stock_registry import build_registry
import test_sector_qualification as fixtures

class StockRegistryTests(unittest.TestCase):
    def test_duplicates_share_one_observation_and_only_weights_differ(self):
        v=fixtures.SectorQualificationTests().sample()|{'ticker':'NVDA','date':'2026-10-30','price':100}
        groups=[{'etf':'SOXX','holdings':[{'ticker':'NVDA','weight_pct':8,'price':999,'opportunity':{'score':1}}]}, {'etf':'FNGS','holdings':[{'ticker':'NVDA','weight_pct':10,'price':888,'opportunity':{'score':99}}]}]
        rows,registry=build_registry(groups,{'NVDA':v},{'return6m':0,'return12m':0,'date':'2026-10-30'})
        self.assertEqual(len(registry),1)
        self.assertEqual(registry['NVDA']['price'],100)
        self.assertEqual(registry['NVDA']['opportunity']['score'],86)
        self.assertEqual(rows[0]['holdings'],[{'ticker':'NVDA','weight_pct':8}])
        self.assertEqual(rows[1]['holdings'],[{'ticker':'NVDA','weight_pct':10}])
    def test_outage_keeps_old_date_without_borrowing_new_benchmark(self):
        v=fixtures.SectorQualificationTests().sample()|{'ticker':'NVDA','date':'2026-10-29','price':100}
        _,registry=build_registry([{'etf':'SOXX','holdings':[{'ticker':'NVDA','weight_pct':8}]}],{}, {'return6m':0,'return12m':0,'date':'2026-10-30'}, {'stock_observations':{'NVDA':v}})
        self.assertEqual(registry['NVDA']['date'],'2026-10-29')
        self.assertEqual(registry['NVDA']['observation_status'],'cached')
        self.assertIsNone(registry['NVDA']['opportunity']['score'])

if __name__=='__main__':unittest.main()
