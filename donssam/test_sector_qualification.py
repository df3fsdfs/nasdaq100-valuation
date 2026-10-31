import unittest
from sector_scoring import qualification,score_sector,score_individual

class SectorQualificationTests(unittest.TestCase):
    def test_all_three_gates_and_boundaries(self):
        self.assertTrue(qualification(70.1,20,-100))
        self.assertFalse(qualification(70,20,-100))
        self.assertFalse(qualification(90,20.1,-200))
        self.assertFalse(qualification(90,10,-99.9))
        self.assertIsNone(qualification(None,10,-200))
        self.assertIsNone(qualification(90,10,None))
        self.assertIsNone(qualification(float('nan'),10,-200))
    def test_stock_and_sector_use_same_components(self):
        v={'ticker':'EXAMPLE','drawdown52':-35,'rsi14':20,'cci_weekly':-100,'ma200_gap':0,'return6m':20,'return12m':30}
        spy={'return6m':0,'return12m':0,'date':'2026-10-30'}
        a=score_sector(v,spy,'Example');b=score_individual(v,spy)
        self.assertEqual(a['opportunity_score'],b['score'])
        self.assertEqual(b['relative_strength_points'],35)
        self.assertEqual(b['oversold_points'],40)
        self.assertEqual(b['trend_points'],10)
        self.assertEqual(b['score'],85)
        self.assertTrue(b['qualified'])
        self.assertEqual(b['judgement'],'pass')
        self.assertEqual(b['benchmark_date'],'2026-10-30')
    def test_missing_returns_do_not_get_fabricated_strength(self):
        v={'ticker':'NEW','drawdown52':-35,'rsi14':20,'cci_weekly':-100,'ma200_gap':0,'return6m':20,'return12m':None}
        b=score_individual(v,{'return6m':0,'return12m':0,'date':'2026-10-30'})
        self.assertIsNone(b['score'])
        self.assertIsNone(b['qualified'])
        self.assertEqual(b['judgement'],'unknown')

if __name__=='__main__':unittest.main()
