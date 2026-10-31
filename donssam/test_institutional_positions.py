import copy
import json
import tempfile
import unittest
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from unittest.mock import patch
import institutional_positions as p

class InstitutionalTests(unittest.TestCase):
    def test_incremental_refresh_keeps_weekly_full_revision_check(self):
        now=datetime(2026,11,1,tzinfo=timezone.utc)
        cot={'raw_rows':self.cot_rows(),'full_history_checked_at':now.isoformat()}
        self.assertEqual(p.cot_fetch_since(cot,now),(date.fromisoformat(cot['raw_rows'][-1]['date'])-timedelta(weeks=8)).isoformat())
        self.assertIsNone(p.cot_fetch_since(cot,now+timedelta(days=7)))
        self.assertIsNone(p.cot_fetch_since({'raw_rows':[]},now))
        self.assertFalse(p.cache_fresh('invalid',now))
        self.assertFalse(p.cache_fresh((now+timedelta(days=1)).isoformat(),now))
    def test_unchanged_data_reuses_summary_and_keeps_revision_history(self):
        from types import SimpleNamespace
        now=datetime.now(timezone.utc);stamp=now.isoformat();rows=self.cot_rows()
        summary=p.cot_summary(rows)
        old={'cot':{**summary,'raw_rows':rows,'revisions':[{'date':'2020-01-07','net':1}], 'full_history_checked_at':stamp,'summary_version':p.COT_SUMMARY_VERSION},'release_calendar':{'year':now.astimezone(p.ZoneInfo('America/New_York')).year,'rows':[{'release_date':'test'}],'checked_at':stamp}}
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'positions.json';out.write_text(json.dumps(old))
            with patch.object(p,'OUT',out),patch.object(p,'fetch_cot',return_value=copy.deepcopy(rows[-9:])) as fetch,patch.object(p,'get',side_effect=AssertionError('calendar cache should be reused')),patch.object(p,'cot_summary',side_effect=AssertionError('unchanged summary should be reused')),patch.object(p,'discover_degross',return_value=([],{'errors':[]})):
                p.main()
            result=json.loads(out.read_text())
        self.assertIsNotNone(fetch.call_args.args[1])
        self.assertEqual(result['cot']['raw_rows'],rows)
        self.assertEqual(result['cot']['rows'],summary['rows'])
        self.assertEqual(result['cot']['revisions'],old['cot']['revisions'])
        self.assertEqual(result['release_calendar'],old['release_calendar'])
    def test_official_contract_group_and_holiday_observation(self):
        row={'cftc_contract_market_code':'209742','report_date_as_yyyy_mm_dd':'2012-12-24T00:00:00','lev_money_positions_long':'103014','lev_money_positions_short':'72405','open_interest_all':'294127'}
        result=p.parse_cot([row,row],'2026-11-01T00:00:00+00:00')
        self.assertEqual(len(result),1);self.assertEqual(result[0]['net'],30609)
        wrong={**row,'cftc_contract_market_code':'209747'}
        with self.assertRaises(ValueError):p.parse_cot([wrong],'2026-11-01')
    def test_percentiles_ties_and_extremes(self):
        self.assertEqual(p.percentile(1,[1,2,3]),0)
        self.assertEqual(p.percentile(3,[1,2,3]),100)
        self.assertEqual(p.percentile(2,[2,2,2]),50)
        self.assertIsNone(p.percentile(1,[1]))
    def cot_rows(self):
        start=date(2020,1,7)
        return [{'date':(start+timedelta(weeks=i)).isoformat(),'long':1000+i,'short':1000,'net':i,'open_interest':10000,'collected_at':'2026-01-01','source_url':p.COT_API} for i in range(350)]
    def test_five_year_window_and_four_week_comparison(self):
        rows=self.cot_rows();rows[0]['net']=999999
        out=p.cot_summary(rows)
        self.assertEqual(out['latest']['percentile'],100)
        self.assertLess(out['latest']['percentile_n'],len(rows))
        self.assertEqual(out['net_change_4w'],4)
        self.assertEqual(out['long_change_4w'],4)
        self.assertEqual(out['short_change_4w'],0)
    def test_long_and_short_changes_not_inferred_from_net(self):
        rows=self.cot_rows();last=rows[-1];prev=rows[-2]
        last.update(long=prev['long']-10,short=prev['short']-50);last['net']=last['long']-last['short']
        out=p.cot_summary(rows)
        self.assertEqual(out['long_change_1w'],-10);self.assertEqual(out['short_change_1w'],-50)
        self.assertIn('롱·숏 모두 감소',out['interpretation'])
    def test_same_observation_does_not_replace_original_collection_date(self):
        old=self.cot_rows()[-1:];new=copy.deepcopy(old);new[0]['collected_at']='2026-11-01'
        merged,revisions=p.merge_cot(old,new)
        self.assertEqual(merged,old);self.assertEqual(revisions,[])
        new[0]['long']+=1;new[0]['net']+=1
        merged,revisions=p.merge_cot(old,new);self.assertEqual(len(revisions),1)
    def test_degrossing_only_explicit_matching_metric(self):
        text='Morgan Stanley equity long/short gross flow drawdown: -8.2%. Drawdown from running peak as % of total global gross exposure. Data as of Oct 30, 2026.'
        row=p.parse_steno_article(text,'https://stenoresearch.com/test','2026-11-01',date(2026,11,1))
        self.assertEqual(row['date'],'2026-10-30');self.assertEqual(row['value'],-8.2)
        self.assertIsNone(p.parse_steno_article(text.replace('gross flow drawdown:','gross leverage:'),'https://stenoresearch.com/test','2026-11-01',date(2026,11,1)))
        self.assertIsNone(p.parse_steno_article(text,'https://untrusted.example/test','2026-11-01',date(2026,11,1)))
        self.assertIsNone(p.parse_steno_article(text.replace('Data as of Oct 30, 2026.',''),'https://stenoresearch.com/test','2026-11-01',date(2026,11,1)))
    def test_public_feed_candidate_fetches_full_same_definition_article(self):
        from types import SimpleNamespace
        rss='<rss><channel><item><title>De-grossing update</title><link>https://stenoresearch.com/example</link><description>Read the full article</description></item></channel></rss>'
        article='Morgan Stanley equity long/short gross flow drawdown: -8.2%. Drawdown from running peak as % of total global gross exposure. Data as of Oct 30, 2026.'
        with patch.object(p,'get',side_effect=[SimpleNamespace(text=rss),SimpleNamespace(text=article)]):
            rows,monitor=p.discover_degross('2026-11-01',date(2026,11,1))
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['value'],-8.2)
        self.assertIn('https://stenoresearch.com/example',monitor['checked_sources'])
    def test_one_approximate_point_does_not_become_full_history_or_percentile(self):
        row={'date':'2026-10-27','value':-7.8,'quality':'recreated_approximate','source_url':'https://stenoresearch.com/test'}
        d=p.degross_summary([row])
        self.assertEqual(len(d['rows']),1);self.assertIsNone(d['change']);self.assertIsNone(d['historical_percentile'])
        self.assertEqual(d['direction'],'insufficient_history')
        d=p.degross_summary([row,{**row,'date':'2026-10-30','value':-7}]);self.assertEqual(d['direction'],'easing')
        with self.assertRaises(ValueError):p.validate_degross({**row,'metric_id':'gross_leverage'},date(2026,11,1))
    def test_source_failure_keeps_last_good_cot_and_degrossing(self):
        previous={'cot':{'raw_rows':self.cot_rows(),'last_success_at':'2026-10-30'},'degrossing':{'rows':[{'date':'2026-10-27','value':-7.8,'quality':'recreated_approximate','source_url':'https://stenoresearch.com/test','collected_at':'2026-10-30'}]}}
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'positions.json';out.write_text(json.dumps(previous))
            with patch.object(p,'OUT',out),patch.object(p,'fetch_cot',side_effect=RuntimeError('offline')),patch.object(p,'get',side_effect=RuntimeError('offline')),patch.object(p,'discover_degross',return_value=([],{'errors':[],'limitation':'test','schedule':'test'})):
                p.main()
            new=json.loads(out.read_text())
        self.assertEqual(new['cot']['raw_rows'],previous['cot']['raw_rows'])
        self.assertFalse(new['cot']['fetch_ok']);self.assertEqual(new['degrossing']['latest']['value'],-7.8)
        self.assertEqual(new['degrossing']['latest']['collected_at'],'2026-10-30')

if __name__=='__main__':unittest.main()
