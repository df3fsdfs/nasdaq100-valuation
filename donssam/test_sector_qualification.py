import unittest
import numpy as np
import pandas as pd
from sector_scoring import qualification,score_sector,score_individual,metrics,MODEL

class SectorQualificationTests(unittest.TestCase):
    def test_all_three_gates_and_boundaries(self):
        self.assertTrue(qualification(70,20,-100))
        self.assertFalse(qualification(69.9,20,-100))
        self.assertFalse(qualification(90,20.1,-200))
        self.assertFalse(qualification(90,10,-99.9))
        self.assertIsNone(qualification(None,10,-200))
        self.assertIsNone(qualification(90,10,None))
        self.assertIsNone(qualification(float('nan'),10,-200))
    def sample(self):
        return {'ticker':'EXAMPLE','drawdown52':-35,'rsi14':15,'rsi14_position65':0,'rsi30':15,'rsi30_position65':0,'cci_weekly':-200,'cci_monthly':-180,'return6m':-20,'return12m':-30,'dev20_change5':1,'dev60_change5':1,'ma120_slope20':1,'ma120_previous_slope20':.5,'ma200_slope20':1,'ma200_previous_slope20':.5,'atr_dev20':-2.2,'atr_dev60':-1.65,'atr_dev120':-.95,'atr_dev200':-.60}
    def test_stock_and_sector_share_all_horizons_and_caps(self):
        v=self.sample();spy={'return6m':0,'return12m':0,'date':'2026-10-30'}
        a=score_sector(v,spy,'Example');b=score_individual(v,spy)
        self.assertEqual(a['opportunity_score'],b['score'])
        self.assertEqual(b['relative_strength_points'],0)
        self.assertEqual(b['relative_adjustment_points'],35)
        self.assertEqual(b['oversold_points'],40)
        self.assertEqual(b['deviation_points'],25)
        self.assertEqual(b['score'],100)
        self.assertTrue(b['qualified'])
        self.assertEqual(b['scoring_model'],MODEL)
    def test_monthly_and_medium_rsi_are_not_short_term_substitutes(self):
        v=self.sample();spy={'return6m':0,'return12m':0}
        v['rsi30']=70;v['rsi30_position65']=100;v['cci_monthly']=100
        b=score_individual(v,spy)
        self.assertEqual(b['oversold_points'],25)
        self.assertEqual(b['score'],85)
    def test_relative_leadership_cannot_boost_correction_score(self):
        weak=self.sample();strong=dict(weak,return6m=20,return12m=30)
        benchmark={'return6m':0,'return12m':0}
        a=score_individual(weak,benchmark);b=score_individual(strong,benchmark)
        self.assertEqual(a['score']-b['score'],35)
        self.assertEqual(b['relative_strength_points'],35)
        self.assertEqual(b['relative_adjustment_points'],0)
    def test_less_negative_deviation_cannot_increase_opportunity(self):
        deep=self.sample();shallow=dict(deep,atr_dev20=1,atr_dev60=1,atr_dev120=1,atr_dev200=1)
        benchmark={'return6m':0,'return12m':0}
        a=score_individual(deep,benchmark);b=score_individual(shallow,benchmark)
        self.assertEqual(a['score']-b['score'],25)
        self.assertEqual(b['deviation_points'],0)
    def test_missing_long_history_does_not_inflate_remaining_weights(self):
        v=self.sample();v['cci_monthly']=None
        b=score_individual(v,{'return6m':0,'return12m':0})
        self.assertIsNone(b['score']);self.assertIsNone(b['qualified'])
        self.assertEqual(b['judgement'],'unknown')
    def test_real_metrics_compute_long_features_and_asof_only(self):
        i=np.arange(900);close=100+.03*i+10*np.sin(i/25)
        f=pd.DataFrame({'Close':close,'High':close+1,'Low':close-1},index=pd.bdate_range('2023-01-02',periods=900))
        out=metrics(f,'EXAMPLE')
        for k in ['rsi30','cci_monthly','ma120_slope20','ma200_previous_slope20','dev60_change5','atr_dev120','atr_dev200']:
            self.assertIsNotNone(out[k])
        cutoff=650
        first=metrics(f.iloc[:cutoff],'EXAMPLE')
        mutated=f.copy();mutated.iloc[cutoff:]*=10
        self.assertEqual(first,metrics(mutated.iloc[:cutoff],'EXAMPLE'))
        short=metrics(f.iloc[:260],'EXAMPLE')
        self.assertIsNone(short['cci_monthly'])

if __name__=='__main__':unittest.main()
