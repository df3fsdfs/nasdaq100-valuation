import unittest
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import bottom_check as b

class ChecklistTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,31,0,tzinfo=timezone.utc)
        i=pd.bdate_range('2010-01-01','2026-10-30')
        c=100+np.arange(len(i))*.05
        self.f=pd.DataFrame({'High':c+1,'Low':c-1,'Close':c,'Volume':100.},index=i)

    def test_incomplete_week_and_month(self):
        early=datetime(2026,10,30,18,tzinfo=timezone.utc)
        self.assertEqual(str(b.completed_bars(self.f,'W-FRI',early).index[-1].date()),'2026-10-23')
        self.assertEqual(str(b.completed_bars(self.f,'ME',early).index[-1].date()),'2026-09-30')
        self.assertEqual(str(b.completed_bars(self.f,'ME',self.now).index[-1].date()),'2026-10-31')

    def test_thresholds_missing_and_pattern_gate(self):
        self.f.iloc[-1,self.f.columns.get_loc('Volume')]=400
        frames={k:(self.f.copy(),'synthetic unit test') for k in b.ASSETS if k!='BTC'}
        d=b.build(self.now,frames,{'value':10.,'date':'2026-10-30','fresh':True})
        r={x['id']:x for x in d['checks']}
        self.assertEqual(r['tqqq_volume']['status'],'pass')
        self.assertEqual(r['soxl_volume']['value'],400)
        self.assertEqual(r['fear']['status'],'pass')
        self.assertEqual(r['btc']['status'],'unknown')
        self.assertEqual(r['joopjoop']['status'],'unknown')
        self.assertEqual(d['summary']['final_status'],'pending_definition')

    def test_stale_values_cannot_pass(self):
        self.assertEqual(b.row('x','x',-30,-20,'%', '2020-01-01',False)['status'],'unknown')
        self.assertEqual(b.row('x','x',-20,-20,'%', '2026-10-30',True)['status'],'pass')
        self.assertEqual(b.rsi(self.f.Close),100.)

if __name__=='__main__': unittest.main()
