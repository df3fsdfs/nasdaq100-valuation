import unittest
import numpy as np
import pandas as pd
from sector_scoring import relative_points,relative_calibration

class SmoothRelativeTests(unittest.TestCase):
    def test_neutral_base_signed_soft_corrections(self):
        score,p=relative_points(0,0,0)
        self.assertEqual(score,17.5)
        self.assertEqual(p['longterm_correction'],0)
        for z,expected in [(1,4.6),(2,7.6),(3,9.1)]:
            high,h=relative_points(0,0,z);low,l=relative_points(0,0,-z)
            self.assertEqual(h['relative_correction'],expected)
            self.assertEqual(l['relative_correction'],-expected)
            self.assertAlmostEqual(high+low,35)
    def test_bounds_and_monotonicity(self):
        for r6 in [-1000,-20,0,20,1000]:
            values=[relative_points(r6,r6,z)[0] for z in [-100,-3,-1,0,1,3,100]]
            self.assertEqual(values,sorted(values))
            self.assertTrue(all(0<=v<=35 for v in values))
        self.assertGreater(relative_points(0,0,0)[0],relative_points(20,30,0)[0])
    def frames(self,n=900):
        i=np.arange(n);dates=pd.bdate_range('2022-01-03',periods=n)
        a=pd.DataFrame({'Close':100+0.03*i+8*np.sin(i/30)},index=dates)
        b=pd.DataFrame({'Close':100+0.02*i},index=dates)
        return a,b
    def test_reference_excludes_current_and_is_price_scale_invariant(self):
        a,b=self.frames();x=relative_calibration(a,b)
        self.assertEqual(x['relative_reference_count'],648)
        self.assertLess(x['relative_reference_end'],x['relative_observation_date'])
        shock=a.copy();shock.iloc[-1,0]*=.5;y=relative_calibration(shock,b)
        self.assertEqual(x['relative_drawdown_median'],y['relative_drawdown_median'])
        self.assertEqual(x['relative_drawdown_iqr'],y['relative_drawdown_iqr'])
        self.assertGreater(y['relative_z'],x['relative_z'])
        scaled=relative_calibration(a*10,b)
        self.assertAlmostEqual(x['relative_z'],scaled['relative_z'])
    def test_short_history_is_unknown_and_flat_history_uses_floor(self):
        a,b=self.frames(450);self.assertIsNone(relative_calibration(a,b)['relative_z'])
        a,b=self.frames();a['Close']=b.Close*2;x=relative_calibration(a,b)
        self.assertEqual(x['relative_z'],0)
        self.assertEqual(x['relative_scale'],1)

if __name__=='__main__':unittest.main()
