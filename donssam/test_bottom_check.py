import unittest
import json,tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import bottom_check as b
from pine_buy import evaluate,rma,rsi

class PineTests(unittest.TestCase):
    def frame(self,n=700):
        values=np.linspace(50,180,n)
        values[-10:]=[172,169,164,160,155,145,130,110,85,65]
        return pd.DataFrame({'High':values+1,'Low':values-1,'Close':values,'Volume':100.}, index=pd.date_range('2020-01-01',periods=n))
    def test_wilder_seed_and_no_neutral_rsi_fabrication(self):
        out=rma(pd.Series([1.,2.,3.,4.,5.]),3)
        self.assertTrue(pd.isna(out.iloc[1]));self.assertEqual(out.iloc[2],2.)
        self.assertAlmostEqual(out.iloc[3],8/3)
        self.assertTrue(rsi(pd.Series([100.]*50),14).isna().all())
    def test_sharp_signal_and_prefix_invariance(self):
        f=self.frame();out=evaluate(f,'D')
        self.assertTrue(out.sharp.iloc[-1]);self.assertTrue(out.buy.iloc[-1])
        pd.testing.assert_series_equal(out.buy.iloc[:600],evaluate(f.iloc[:600],'D').buy)
        self.assertTrue((out.buy==(out.sharp|out.normal|out.time|out.restricted)).all())
    def test_timeframe_limits(self):
        for tf,limit in [('D',22),('W',27),('M',32)]:self.assertEqual(evaluate(self.frame(),tf).attrs['rsi_limit'],limit)
    def test_short_monthly_history_keeps_independent_sharp_branch(self):
        out=evaluate(self.frame(100),'M')
        self.assertTrue(pd.isna(out.rsi200.iloc[-1]));self.assertFalse(out.time.iloc[-1])
        self.assertTrue(out.sharp.iloc[-1]);self.assertTrue(out.buy.iloc[-1])
    def test_calendar_and_forming_candles(self):
        idx=pd.bdate_range('2010-01-01','2026-10-30');v=np.arange(len(idx))+100.
        f=pd.DataFrame({'High':v+1,'Low':v-1,'Close':v,'Volume':100.},index=idx)
        early=datetime(2026,10,30,18,tzinfo=timezone.utc);late=datetime(2026,10,31,0,tzinfo=timezone.utc)
        self.assertEqual(str(b.completed_bars(f,'W-FRI',early).index[-1].date()),'2026-10-23')
        self.assertEqual(str(b.completed_bars(f,'ME',early).index[-1].date()),'2026-09-30')
        self.assertEqual(str(b.completed_bars(f,'ME',late).index[-1].date()),'2026-10-31')
        self.assertEqual(b.build(late,{},errors=[])['schema_version'],2)

    def test_full_collection_does_not_shadow_history_function(self):
        frame=self.frame()
        def api(url):
            if 'alternative.me' in url:return {'data':[{'value':'20','timestamp':'1793404800','value_classification':'Fear'},{'value':'25','timestamp':'1793318400'}]}
            return {'fear_and_greed':{'score':22,'timestamp':'2026-10-30T20:00:00Z','previous_close':25},'fear_and_greed_historical':{'data':[]}}
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(b,'ROOT',Path(folder)),patch.object(b,'history',return_value=(frame,'test fixture')) as fetch,patch.object(b,'request_json',side_effect=api):
                b.main()
                result=json.loads((Path(folder)/'bottom.json').read_text())
                self.assertEqual(fetch.call_count,4)
                self.assertEqual(set(result['assets']),{'NDX','BTC'})
                self.assertFalse(result['errors'])

if __name__=='__main__':unittest.main()
