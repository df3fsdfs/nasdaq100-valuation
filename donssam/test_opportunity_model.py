import copy
import unittest
from unittest.mock import patch
import pandas as pd
import sentiment as s

class OpportunityModelTests(unittest.TestCase):
    def test_relative_rsi_and_atr_boundaries(self):
        a={'rsi':50,'rsi_position65':0,'atr_dev20':-2.2,'atr_dev60':-1.65}
        self.assertEqual(s.rsi_opportunity(a),50)
        self.assertEqual(s.atr_opportunity(a),100)
        a.update(rsi=15,rsi_position65=100,atr_dev20=1,atr_dev60=1)
        self.assertEqual(s.rsi_opportunity(a),50)
        self.assertEqual(s.atr_opportunity(a),0)
    def test_migration_preserves_macro_and_does_not_apply_twice(self):
        asset={'date':'2026-10-30','price':100,'rsi':50,'drawdown':-20,'cci':-100,'pattern':{'qualified':True}}
        def part(name,w):return {'name':name,'weight':w,'score':0,'points':0,'value':0}
        row={'score_direction':'high_is_opportunity','assets':{k:copy.deepcopy(asset) for k in ['SPY','SOXX','BTC']},'equity':{'components':[part('S&P 500 낙폭·속도',12.5),part('SOXX 낙폭·속도',12.5),part('S&P 500 주봉·일봉 과매도',10),part('SOXX 주봉·일봉 과매도',10),part('macro',55)]},'crypto':{'components':[part('BTC 주봉·일봉 과매도',15),part('macro',85)]}}
        frame=pd.DataFrame({'Close':[99,101]},index=pd.to_datetime(['2026-10-29','2026-10-30']))
        features={'rsi_position65':0,'atr_dev20':-2.2,'atr_dev60':-1.65}
        with patch.object(s,'fetch',return_value=frame),patch.object(s,'refinements',return_value=features):
            new=s.revise_snapshot(row)
        self.assertEqual(new['equity']['components'][-1],row['equity']['components'][-1])
        self.assertEqual(new['crypto']['components'][-1],row['crypto']['components'][-1])
        self.assertNotIn('model_version',row)
        self.assertEqual(new['model_version'],s.MODEL_VERSION)
        self.assertGreater(new['equity']['score'],0)
        with patch.object(s,'fetch',side_effect=AssertionError('Must not recalculate a migrated row')):
            self.assertEqual(s.revise_snapshot(new),new)

if __name__=='__main__':unittest.main()
