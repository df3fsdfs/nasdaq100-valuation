import unittest
from datetime import datetime,timezone
from fang_weights import parse_official,NAMES
from quotes_update import parse_quote
from sentiment import normalize_snapshot
from market_insights import opportunity_changes

class RefreshTests(unittest.TestCase):
    def test_direction_migration_is_idempotent(self):
        old={'score_direction':'zero_is_opportunity','equity':{'score':69.9},'crypto':{'score':78.8}}
        new=normalize_snapshot(old)
        self.assertEqual(new['equity']['score'],30.1)
        self.assertEqual(new['crypto']['score'],21.2)
        self.assertEqual(normalize_snapshot(new),new)
        self.assertEqual(old['equity']['score'],69.9)
        history={'history':[dict(old,date='2026-10-29'),dict(new,date='2026-10-30')]}
        self.assertEqual(opportunity_changes(history)['equity']['delta'],0)
    def test_fang_requires_dated_full_composition(self):
        body='<ul>'+''.join('<li>10.0% '+name+'</li>' for name in NAMES)+'</ul> Components as of SOD 10/29/2026'
        rows,source,status=parse_official(body)
        self.assertEqual(len(rows),10);self.assertEqual(sum(x['weight_pct'] for x in rows),100)
        self.assertEqual(rows[0]['weight_date'],'2026-10-29')
        with self.assertRaises(ValueError):parse_official(body.replace('Components as of SOD 10/29/2026',''))
    def test_extended_price_compares_to_regular_close(self):
        dates=['2026-10-29T19:55:00+00:00','2026-10-30T19:55:00+00:00','2026-10-30T23:00:00+00:00']
        data={'meta':{'regularMarketPrice':105,'chartPreviousClose':80},'timestamp':[int(datetime.fromisoformat(x).timestamp()) for x in dates],'indicators':{'quote':[{'close':[100,105,110]}]}}
        now=datetime(2026,10,31,tzinfo=timezone.utc)
        q=parse_quote(data,'MSFT',now)
        self.assertEqual(q['session'],'postmarket');self.assertEqual(q['reference_price'],105)
        self.assertAlmostEqual(q['change_pct'],(110/105-1)*100)
        q=parse_quote(data,'^NDX',now)
        self.assertEqual(q['reference_price'],100)

if __name__=='__main__':unittest.main()
