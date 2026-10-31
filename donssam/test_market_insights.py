import unittest
from market_insights import cli_analysis,compare,crossing

def rows(values):
    return [{'date':'2026-'+str(i+1).zfill(2),'value':x} for i,x in enumerate(values)]

class DerivativeTests(unittest.TestCase):
    def test_acceleration_cross_is_not_jerk_cross(self):
        x=cli_analysis(rows([100,101,101.5,101.6,101.8]))
        self.assertGreater(x['velocity'],0)
        self.assertEqual(x['acceleration_cross'],'negative_to_positive')
        self.assertEqual(x['jerk_cross'],'none')
        self.assertAlmostEqual(x['acceleration'],.1)
    def test_jerk_can_cross_while_acceleration_stays_negative(self):
        x=cli_analysis(rows([100,102,103.5,104.3,104.5]))
        self.assertLess(x['acceleration'],0)
        self.assertEqual(x['acceleration_cross'],'none')
        self.assertEqual(x['jerk_cross'],'negative_to_positive')
        self.assertIn('상승 속도 둔화',x['interpretation'])
    def test_mean_excludes_current_and_deduplicates(self):
        x=compare([{'date':'2026-01-01','value':1},{'date':'2026-01-02','value':3},{'date':'2026-01-03','value':100}],2)
        self.assertEqual(x['mean'],2)
        self.assertEqual(x['mean_n'],2)
        self.assertEqual(x['delta'],97)
    def test_missing_month_is_not_one_month_change(self):
        r=rows([100,101,102,103,104,105]);r[-2]['date']='2025-12'
        self.assertIsNone(cli_analysis(r))
    def test_zero_is_not_a_sign_crossing(self):
        self.assertEqual(crossing(-1,0),'at_zero')
        self.assertEqual(crossing(1,-1),'positive_to_negative')

if __name__=='__main__':unittest.main()
