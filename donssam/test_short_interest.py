import copy,unittest
from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch
import short_interest as s

class ShortInterestTests(unittest.TestCase):
    def raw(self):
        return [{'symbolCode':symbol,'settlementDate':'2026-10-15','currentShortPositionQuantity':amount,'previousShortPositionQuantity':previous,'averageDailyVolumeQuantity':10000000,'daysToCoverQuantity':2.4,'stockSplitFlag':None,'revisionFlag':None} for symbol,amount,previous in [('QQQ',82001618,70458005),('SPY',92995326,98476070)]]
    def test_official_counts_changes_and_both_etfs_required(self):
        rows=s.parse_rows(self.raw(),'2026-11-01');summary=s.summarize(rows)
        self.assertEqual(summary['QQQ']['change'],11543613);self.assertEqual(summary['QQQ']['change_percent'],16.38)
        self.assertEqual(summary['SPY']['change_percent'],-5.57)
        with self.assertRaises(ValueError):s.parse_rows(self.raw()[:1],'2026-11-01')
        bad=self.raw();bad[0]['currentShortPositionQuantity']=-1
        with self.assertRaises(ValueError):s.parse_rows(bad,'2026-11-01')
        bad=self.raw();bad[0]['settlementDate']='2027-01-01'
        with self.assertRaises(ValueError):s.parse_rows(bad,'2026-11-01')
    def test_split_avoids_false_change_and_unknown_cover_sentinel(self):
        raw=self.raw();raw[0].update(stockSplitFlag='S',daysToCoverQuantity=999.99)
        q=s.summarize(s.parse_rows(raw,'2026-11-01'))['QQQ']
        self.assertIsNone(q['change']);self.assertIsNone(q['change_percent']);self.assertIsNone(q['latest']['days_to_cover'])
    def test_merge_keeps_collection_dates_and_full_revision_values(self):
        old=s.parse_rows(self.raw(),'2026-10-27');new=s.parse_rows(self.raw(),'2026-11-01')
        rows,revisions=s.merge_rows(old,new);self.assertEqual(rows,old);self.assertEqual(revisions,[])
        new[0]['shares']+=10
        rows,revisions=s.merge_rows(old,new);self.assertEqual(len(revisions),1)
        self.assertEqual(revisions[0]['previous']['shares'],old[0]['shares']);self.assertEqual(len(rows),2)
    def test_calendar_distinguishes_observation_publication_and_year_rollover(self):
        body='<h2>2026 Short Interest Reporting Dates</h2><table>'+''.join('<tr><td>October 30 (Friday)</td><td>November 3</td><td>November 10 (Tuesday)</td></tr>' for _ in range(20))+'<tr><td>December 31</td><td>January 5</td><td>January 12</td></tr></table>'
        rows=s.parse_calendar(body,2026)
        self.assertEqual(rows[0]['date'],'2026-10-30');self.assertTrue(rows[0]['published_at'].startswith('2026-11-10T21:40'))
        self.assertEqual(rows[-1]['publication_date'],'2027-01-12')
    def test_api_failure_preserves_history(self):
        now=datetime(2026,11,1,tzinfo=timezone.utc);rows=s.parse_rows(self.raw(),'2026-10-27')
        previous={'raw_rows':rows,'series':s.summarize(rows),'full_history_checked_at':now.isoformat(),'release_calendar':{'year':2026,'rows':[{'date':'2026-10-30'}],'checked_at':now.isoformat()}}
        with patch.object(s,'fetch_rows',side_effect=RuntimeError('offline')),patch.object(s.requests,'get',side_effect=AssertionError('cached calendar')):
            result=s.update(previous,now)
        self.assertEqual(result['raw_rows'],rows);self.assertEqual(result['series'],previous['series']);self.assertFalse(result['fetch_ok'])
    def test_incremental_refresh_does_not_drop_older_observations(self):
        now=datetime(2026,11,1,tzinfo=timezone.utc);rows=s.parse_rows(self.raw(),'2026-10-27');older=copy.deepcopy(rows)
        for r in older:r['date']='2021-11-15'
        previous={'raw_rows':older+rows,'full_history_checked_at':now.isoformat(),'release_calendar':{'year':2026,'rows':[{}],'checked_at':now.isoformat()}}
        with patch.object(s,'fetch_rows',return_value=s.parse_rows(self.raw(),now.isoformat())) as fetch:
            result=s.update(previous,now)
        self.assertEqual(len(result['raw_rows']),4);self.assertTrue(result['fetch_ok']);self.assertEqual(fetch.call_args.args[1],'2026-08-11')

if __name__=='__main__':unittest.main()
