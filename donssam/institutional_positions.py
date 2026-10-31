"""Official COT plus separately identified, strictly sourced de-grossing observations."""
import calendar,copy,json,math,re
from datetime import datetime,date,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse
import requests
import short_interest
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'institutional_positions.json'
METRIC='ms_pb_steno_equity_ls_gross_flow_drawdown_pct_global_gross'
COT_API='https://publicreporting.cftc.gov/resource/gpe5-46if.json'
COT_REPORT='https://www.cftc.gov/dea/futures/financial_lf.htm'
SCHEDULE='https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm'
STENO_FEED='https://stenoresearch.com/feed/'
STENO_SEARCH='https://stenoresearch.com/wp-json/wp/v2/posts'
HEADERS={'User-Agent':'DonssamMarketMonitor/1.0 (public market data)','Accept':'application/json,text/html,application/xml'}
# Increment when summary rules change so an unchanged source is recalculated.
COT_SUMMARY_VERSION=2
GROUPS={
    'leveraged':('레버리지 펀드','lev_money_positions_long','lev_money_positions_short'),
    'asset_manager':('자산운용사·기관','asset_mgr_positions_long','asset_mgr_positions_short'),
    'dealer':('딜러·중개기관','dealer_positions_long_all','dealer_positions_short_all'),
    'other':('기타 보고대상','other_rept_positions_long','other_rept_positions_short'),
    'nonreportable':('비보고 포지션','nonrept_positions_long_all','nonrept_positions_short_all')}

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def get(url,params=None):
    r=requests.get(url,params=params,headers=HEADERS,timeout=(10,22));r.raise_for_status();return r

def parse_cot(raw,collected_at):
    result={}
    for r in raw:
        if r.get('cftc_contract_market_code')!='209742':raise ValueError('Unexpected CFTC contract')
        day=date.fromisoformat(r['report_date_as_yyyy_mm_dd'][:10])
        values=[int(r[k]) for k in ['lev_money_positions_long','lev_money_positions_short','open_interest_all']]
        long,short,oi=values
        if day>date.fromisoformat(collected_at[:10]) or min(values)<0 or max(long,short)>oi:raise ValueError('Invalid COT observation')
        row={'date':day.isoformat(),'long':long,'short':short,'net':long-short,'open_interest':oi,'source_url':COT_API,'collected_at':collected_at}
        positions={}
        for key,(_,lf,sf) in GROUPS.items():
            if lf not in r or sf not in r:continue
            gl,gs=int(r[lf]),int(r[sf])
            if min(gl,gs)<0 or max(gl,gs)>oi:raise ValueError('Invalid COT group observation')
            positions[key]={'long':gl,'short':gs,'net':gl-gs}
        if len(positions)==len(GROUPS):row.update(positions=positions,positions_collected_at=collected_at)
        if row['date'] in result and any(result[row['date']].get(k)!=row.get(k) for k in ['long','short','open_interest','positions']):raise ValueError('Conflicting duplicate COT date')
        result[row['date']]=row
    return sorted(result.values(),key=lambda r:r['date'])

def fetch_cot(collected_at,since=None):
    params={'$select':'market_and_exchange_names,report_date_as_yyyy_mm_dd,cftc_contract_market_code,lev_money_positions_long,lev_money_positions_short,open_interest_all',
            '$where':"cftc_contract_market_code='209742' AND report_date_as_yyyy_mm_dd >= '"+(since or '2010-01-01')+"T00:00:00'",'$order':'report_date_as_yyyy_mm_dd ASC','$limit':5000}
    params['$select']=','.join(dict.fromkeys(params['$select'].split(',')+[f for _,lf,sf in GROUPS.values() for f in (lf,sf)]))
    rows=parse_cot(get(COT_API,params).json(),collected_at)
    if not rows or (since is None and (len(rows)<260 or rows[0]['date']>'2016-01-01')):raise ValueError('Incomplete COT history')
    if any(len(r.get('positions',{}))!=len(GROUPS) for r in rows):raise ValueError('Incomplete COT participant groups')
    return rows

def cache_fresh(stamp,now,days=7):
    try:return timedelta(0)<=now-datetime.fromisoformat(stamp)<timedelta(days=days)
    except (TypeError,ValueError):return False

def cot_fetch_since(cot,now):
    rows=cot.get('raw_rows',[])
    if len(rows)<260 or any(len(r.get('positions',{}))!=len(GROUPS) for r in rows) or not cache_fresh(cot.get('full_history_checked_at'),now):return None
    # Overlap catches recent revisions; weekly full refresh catches older corrections.
    return (date.fromisoformat(rows[-1]['date'])-timedelta(weeks=8)).isoformat()

def percentile(value,values):
    if len(values)<2:return None
    less=sum(v<value for v in values);equal=sum(v==value for v in values)
    return round(100*(less+(equal-1)/2)/(len(values)-1),1)

def cot_summary(rows):
    if not rows:return None
    enriched=[]
    for i,r in enumerate(rows):
        day=date.fromisoformat(r['date'])
        try:start=day.replace(year=day.year-5)
        except ValueError:start=day.replace(year=day.year-5,day=28)
        window=[v['net'] for v in rows[:i+1] if v['date']>=start.isoformat()]
        enriched.append({**{k:v for k,v in r.items() if k not in ['positions','positions_collected_at']},'percentile':percentile(r['net'],window) if len(window)>=200 else None,'percentile_n':len(window)})
    latest=enriched[-1];previous=enriched[-2] if len(enriched)>1 else None
    four=date.fromisoformat(latest['date'])-timedelta(weeks=4)
    past=next((r for r in reversed(enriched) if r['date']<=four.isoformat()),None)
    delta=lambda key,base:latest[key]-base[key] if base is not None else None
    dl,ds=delta('long',previous),delta('short',previous)
    p=latest['percentile'];bias='숏 편중' if p is not None and p<=10 else '롱 편중' if p is not None and p>=90 else '중간 구간'
    if ds is not None and ds<0 and dl is not None and dl<0:sentence='롱·숏 모두 감소: 선물 양방향 포지션 축소. 순포지션만으로 방향을 단정하지 않음.'
    elif p is not None and p<=10 and ds is not None and ds>0:sentence='과거 대비 숏 쏠림 속 숏 증가: 숏 노출 확대 흐름.'
    elif p is not None and p<=10 and ds is not None and ds<0:sentence='과거 대비 숏 쏠림 속 숏 감소: 숏 축소·커버 후보 변화.'
    elif p is not None and p>=90 and dl is not None and dl<0:sentence='과거 대비 롱 쏠림 속 롱 감소: 롱 포지션 축소 흐름.'
    elif ds is not None and ds<0:sentence='숏 포지션 감소가 관측됨. 순포지션 증감과 롱 변화는 함께 확인.'
    elif ds is not None and ds>0:sentence='숏 포지션 증가가 관측됨. 순포지션 증감과 롱 변화는 함께 확인.'
    else:sentence='롱·숏 변화를 각각 표시하며 다음 관측과 비교.'
    return {'latest':latest,'bias':bias,'interpretation':sentence,'long_change_1w':dl,'short_change_1w':ds,'net_change_1w':delta('net',previous),
            'comparison_1w_date':previous['date'] if previous else None,'comparison_4w_date':past['date'] if past else None,
            'long_change_4w':delta('long',past),'short_change_4w':delta('short',past),'net_change_4w':delta('net',past),
            'percentile_change_4w':round(p-past['percentile'],1) if p is not None and past and past['percentile'] is not None else None,
            'rows':[r for r in enriched if r['date']>='2016-01-01']}

def parse_schedule(body,year):
    soup=BeautifulSoup(body,'html.parser');heading=soup.find(string=re.compile(str(year)+r'\s+Release Schedule'))
    if not heading:raise ValueError('Current-year CFTC schedule not found')
    table=heading.find_parent().find_next('table')
    if not table:raise ValueError('CFTC schedule table missing')
    months={calendar.month_name[i]:i for i in range(1,13)};rows=[]
    for tr in table.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all(['td','th'])]
        if not cells or cells[0] not in months:continue
        for cell in cells[1:]:
            m=re.match(r'^(\d{1,2})',cell)
            if not m:continue
            d=date(year,months[cells[0]],int(m[1]));report=d-timedelta(days=(d.weekday()-1)%7 or 7)
            release=datetime(d.year,d.month,d.day,15,30,tzinfo=ZoneInfo('America/New_York'))
            rows.append({'release_date':d.isoformat(),'scheduled_at':release.astimezone(timezone.utc).isoformat(),'expected_report_date':report.isoformat()})
    if len(rows)<45:raise ValueError('Incomplete release calendar')
    return sorted(rows,key=lambda r:r['scheduled_at'])

def merge_cot(old,new):
    merged={r['date']:copy.deepcopy(r) for r in old};revisions=[]
    for r in new:
        previous=merged.get(r['date'])
        same=previous and all(previous.get(k)==r[k] for k in ['long','short','net','open_interest'])
        same_groups=previous and previous.get('positions')==r.get('positions')
        if same and same_groups:continue
        updated=copy.deepcopy(r)
        if previous:
            if not same or (previous.get('positions') and not same_groups):revisions.append({'date':r['date'],'previous_net':previous['net'],'net':r['net'],'revised_at':r['collected_at'],'previous_positions':previous.get('positions'),'positions':r.get('positions')})
            if same:updated['collected_at']=previous['collected_at']
            if same_groups and previous.get('positions_collected_at'):updated['positions_collected_at']=previous['positions_collected_at']
        merged[r['date']]=updated
    return sorted(merged.values(),key=lambda r:r['date']),revisions

def validate_degross(row,today):
    if row.get('metric_id',METRIC)!=METRIC:raise ValueError('Different de-grossing definition')
    day=date.fromisoformat(row['date']);value=row['value']
    if day>today or not isinstance(value,(float,int)) or not math.isfinite(value) or not -100<=value<=0:raise ValueError('Invalid de-grossing date/value')
    if row.get('quality') not in ['recreated_approximate','primary_verified']:raise ValueError('Unsupported evidence quality')
    if not row.get('source_url','').startswith('https://'):raise ValueError('Source URL required')
    return copy.deepcopy(row)

def parse_steno_article(body,url,collected_at,today):
    """Accept text with the SAME metric definition and an explicit as-of date only."""
    if urlparse(url).hostname not in ['stenoresearch.com','www.stenoresearch.com']:return None
    text=BeautifulSoup(body,'html.parser').get_text(' ',strip=True)
    if not all(re.search(pattern,text,re.I) for pattern in ['gross flow','drawdown from (?:the )?running peak','total global gross exposure','Morgan Stanley']):return None
    date_match=re.search(r'data\s+as\s+of\s+([A-Za-z]{3,9}\.?\s+\d{1,2},?\s+20\d{2}|20\d{2}-\d{2}-\d{2})',text,re.I)
    value_match=re.search(r'gross\s+flow\s+(?:drawdown|de[- ]grossing)\s*(?:of|:|at|is|=)?\s*(-?\d+(?:\.\d+)?)\s*%',text,re.I)
    if not date_match or not value_match:return None
    raw=date_match[1].replace('.','').replace(',','');day=None
    for fmt in ['%Y-%m-%d','%b %d %Y','%B %d %Y']:
        try:day=datetime.strptime(raw,fmt).date();break
        except ValueError:pass
    if day is None:return None
    row={'date':day.isoformat(),'value':-abs(float(value_match[1])),'quality':'recreated_approximate','source_name':'Steno Research / Morgan Stanley Prime Brokerage 재구성',
         'source_url':url,'collected_at':collected_at,'evidence':'동일한 gross flow 정의와 as-of 날짜가 명시된 공개 본문'}
    return validate_degross(row,today)

def discover_degross(collected_at,today):
    candidates=[];errors=[];checked=[];attempted=[];rows=[]
    try:
        attempted.append(STENO_FEED);body=get(STENO_FEED).text;checked.append(STENO_FEED)
        import xml.etree.ElementTree as ET
        root=ET.fromstring(body)
        for item in root.findall('.//item'):
            title=item.findtext('title','');url=item.findtext('link','');excerpt=' '.join(item.itertext())
            if re.search(r'de[- ]gross|gross flow',title+' '+excerpt,re.I):candidates.append((url,excerpt))
    except Exception as exc:errors.append('Steno RSS: '+type(exc).__name__)
    if not candidates:
        try:
            attempted.append(STENO_SEARCH);response=get(STENO_SEARCH,{'search':'gross flow','per_page':10}).json();checked.append(STENO_SEARCH)
            for post in response if isinstance(response,list) else []:candidates.append((post.get('link',''),post.get('content',{}).get('rendered','')))
        except Exception as exc:errors.append('Steno public articles: '+type(exc).__name__)
    seen=set()
    for url,body in candidates[:8]:
        if url in seen:continue
        seen.add(url)
        if urlparse(url).hostname not in ['stenoresearch.com','www.stenoresearch.com']:continue
        try:
            candidate=parse_steno_article(body,url,collected_at,today)
            if candidate is None:
                article=get(url).text;checked.append(url)
                candidate=parse_steno_article(article,url,collected_at,today)
            if candidate:rows.append(candidate)
        except (ValueError,KeyError,TypeError):errors.append('Steno candidate: rejected invalid metric/date/value')
        except requests.RequestException:errors.append('Steno candidate: public article unavailable')
    return rows,{'mode':'public_text_monitor','checked_sources':checked,'attempted_sources':attempted,'source_status':'unavailable' if not checked else 'checked','candidate_count':len(seen),'errors':errors,
                'schedule':'매일 07:05 KST 공개 본문 확인; 정의·관측일·수치가 모두 일치할 때만 반영',
                'limitation':'원본 정기 시계열·고정 발표일은 연결되지 않음. 이미지·유료자료만 있으면 숫자를 자동 갱신하지 않음.'}

def degross_summary(rows):
    if not rows:return {'latest':None,'rows':[],'direction':'no_data','interpretation':'동일 정의의 관측치 수집 대기'}
    rows=sorted(rows,key=lambda r:r['date']);latest=rows[-1];previous=rows[-2] if len(rows)>1 else None
    delta=latest['value']-previous['value'] if previous else None
    direction='easing' if delta is not None and delta>0 else 'deepening' if delta is not None and delta<0 else 'unchanged' if delta==0 else 'insufficient_history'
    text='축소폭 완화' if direction=='easing' else '축소폭 확대' if direction=='deepening' else '직전 관측과 동일' if direction=='unchanged' else '확인된 인용값 1개 · 확대·완화 비교는 추가 관측부터 표시'
    return {'latest':latest,'previous':previous,'change':delta,'direction':direction,'interpretation':text,'rows':rows,
            'history_coverage':'공개 확인 관측만 표시. 2016년 이후 연속 원자료는 미확보.',
            'historical_percentile':None,'historical_extreme':latest.get('historical_extreme_claim')}

def combined(cot,dg):
    if not cot or not dg.get('latest'):return '두 지표는 서로 다른 기관 표본이며 각각 독립적으로 해석해.'
    if dg['direction']=='easing' and (cot.get('short_change_1w') or 0)<0:return '디그로싱 축소폭 완화와 선물 숏 감소가 함께 관측됨. 서로 다른 표본의 변화 신호이며 주가 방향을 확정하지 않아.'
    p=cot['latest']['percentile']
    if p is not None and p<=10 and dg.get('historical_extreme'):return '선물 포지션은 과거 대비 숏 쪽에 쏠려 있고, 공개 재구성 차트는 큰 디그로싱을 보고했어. 위험 축소 진행의 단서이며 추가 하락·숏커버 여부는 롱·숏 후속 변화를 확인해.'
    return 'COT는 선물 롱·숏 쏠림, 디그로싱은 별도 PB 표본의 위험 축소를 보여줘. 두 값을 합쳐 상승·하락 확률로 계산하지 않아.'

def main():
    now=datetime.now(timezone.utc);stamp=now.isoformat();previous=read(OUT);errors=[]
    old_cot=previous.get('cot',{});old_rows=old_cot.get('raw_rows',[]);rows=old_rows;cot_ok=False;revisions=[]
    since=cot_fetch_since(old_cot,now)
    try:rows,revisions=merge_cot(old_rows,fetch_cot(stamp,since));cot_ok=True
    except Exception as exc:errors.append('CFTC: '+type(exc).__name__)
    summary_keys=['latest','bias','interpretation','long_change_1w','short_change_1w','net_change_1w','comparison_1w_date','comparison_4w_date','long_change_4w','short_change_4w','net_change_4w','percentile_change_4w','rows']
    summary=({k:old_cot[k] for k in summary_keys} if rows==old_rows and old_cot.get('summary_version')==COT_SUMMARY_VERSION and all(k in old_cot for k in summary_keys) else cot_summary(rows))
    cot={**(summary or {}),'raw_rows':rows,'source_url':COT_REPORT,'api_url':COT_API,'contract':'209742','group':'Leveraged Funds','report_type':'TFF Futures Only','checked_at':stamp,
         'last_success_at':stamp if cot_ok else old_cot.get('last_success_at'),'fetch_ok':cot_ok,'revisions':old_cot.get('revisions',[])+revisions,
         'full_history_checked_at':stamp if cot_ok and since is None else old_cot.get('full_history_checked_at'),'summary_version':COT_SUMMARY_VERSION}
    if rows==old_rows and old_cot.get('summary_version')==COT_SUMMARY_VERSION and old_cot.get('groups'):
        cot['groups']=old_cot['groups']
    else:
        cot['groups']={key:{'label':label,**cot_summary([{**r['positions'][key],'date':r['date']} for r in rows if key in r.get('positions',{})])} for key,(label,_,_) in GROUPS.items() if any(key in r.get('positions',{}) for r in rows)}
    schedule=previous.get('release_calendar',{})
    year=now.astimezone(ZoneInfo('America/New_York')).year
    if schedule.get('year')!=year or not schedule.get('rows') or not cache_fresh(schedule.get('checked_at'),now):
        try:schedule={'source_url':SCHEDULE,'year':year,'rows':parse_schedule(get(SCHEDULE).text,year),'checked_at':stamp}
        except Exception as exc:errors.append('CFTC calendar: '+type(exc).__name__)
    # Retain the retired observations as an archive; no de-grossing network checks.
    dg=previous.get('degrossing')
    if dg is None:
        seed=read(ROOT/'degrossing_observations.json')
        dg=degross_summary(seed.get('observations',[]))
    si=short_interest.update(previous.get('short_interest',{}),now)
    output={'generated_at':stamp,'cot':cot,'degrossing':dg,'short_interest':si,'release_calendar':schedule,'errors':errors+si.get('errors',[]),
            'method':{'cot':'5년=관측일부터 5년 전 이후의 공식 주간 순계약. 백분위=100×(현재보다 작은 관측 수+(동일값 관측 수−1)/2)/(관측 수−1). 4주 변화는 4주 전 또는 그 이전 가장 가까운 보고와 비교. 스프레드 포지션은 롱−숏에서 제외.',
                      'short_interest':'FINRA 공식 공매도 잔고(미청산 주식 수). 일별 공매도 거래량과 다름. 월 2회 결제일 기준이며 발표일은 별도. 직전 발표 대비 변화는 FINRA의 previousShortPositionQuantity와 비교. 주식분할 표시가 있으면 단순 증감을 생략. 발행주식 수 대비 비율·헤지펀드만의 숏으로 해석하지 않음.',
                      'degrossing':previous.get('method',{}).get('degrossing','퇴역 자료 보관')}}
    temporary=OUT.with_suffix('.tmp')
    temporary.write_text(json.dumps(output,ensure_ascii=False,allow_nan=False,separators=(',',':')))
    temporary.replace(OUT)
    print('COT',cot.get('latest',{}).get('date'),cot.get('latest',{}).get('percentile'),'short-interest', {k:v['latest']['date'] for k,v in si.get('series',{}).items()})
    print('Source checks:',output['errors'])

if __name__=='__main__':main()
