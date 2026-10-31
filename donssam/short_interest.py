"""FINRA twice-monthly ETF short interest; never substitute daily short volume."""
import calendar,copy,math,re
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

API='https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest'
SOURCE='https://www.finra.org/finra-data/browse-catalog/equity-short-interest'
SCHEDULE='https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest'
SYMBOLS=('QQQ','SPY')
FIELDS=['symbolCode','settlementDate','currentShortPositionQuantity','previousShortPositionQuantity','daysToCoverQuantity','averageDailyVolumeQuantity','stockSplitFlag','revisionFlag']

def parse_rows(raw,stamp):
    result={};today=date.fromisoformat(stamp[:10])
    for item in raw:
        symbol=item['symbolCode'];day=date.fromisoformat(item['settlementDate'])
        if symbol not in SYMBOLS or day>today:raise ValueError('Unexpected short-interest symbol/date')
        def count(key):
            value=float(item[key])
            if not math.isfinite(value) or value<0 or not value.is_integer():raise ValueError('Invalid share count')
            return int(value)
        shares=count('currentShortPositionQuantity');previous=count('previousShortPositionQuantity')
        dtc=float(item.get('daysToCoverQuantity') or 0)
        if not math.isfinite(dtc) or dtc<0:raise ValueError('Invalid days to cover')
        row={'symbol':symbol,'date':day.isoformat(),'shares':shares,'previous_shares':previous,'days_to_cover':dtc if dtc!=999.99 else None,'average_volume':count('averageDailyVolumeQuantity'),'split':item.get('stockSplitFlag')=='S','revision':item.get('revisionFlag')=='R','source_url':API,'collected_at':stamp}
        key=(symbol,row['date'])
        if key in result and result[key]!=row:raise ValueError('Conflicting short-interest duplicate')
        result[key]=row
    rows=sorted(result.values(),key=lambda r:(r['date'],r['symbol']))
    if any(not any(r['symbol']==s for r in rows) for s in SYMBOLS):raise ValueError('Missing ETF short interest')
    return rows

def fetch_rows(stamp,since):
    body={'limit':5000,'fields':FIELDS,'compareFilters':[{'compareType':'greater','fieldName':'settlementDate','fieldValue':since}],'domainFilters':[{'fieldName':'symbolCode','values':list(SYMBOLS)}]}
    r=requests.post(API,json=body,headers={'Accept':'application/json','User-Agent':'DonssamMarketMonitor/1.0'},timeout=(10,30));r.raise_for_status()
    if int(r.headers.get('record-total','0'))>5000:raise ValueError('Truncated short-interest history')
    return parse_rows(r.json(),stamp)

def merge_rows(old,new):
    rows={(r['symbol'],r['date']):copy.deepcopy(r) for r in old};revisions=[]
    for r in new:
        key=(r['symbol'],r['date']);before=rows.get(key)
        if before and all(before.get(k)==v for k,v in r.items() if k!='collected_at'):continue
        if before:revisions.append({'symbol':r['symbol'],'date':r['date'],'previous':before,'replacement':r,'revised_at':r['collected_at']})
        rows[key]=r
    return sorted(rows.values(),key=lambda r:(r['date'],r['symbol'])),revisions

def summarize(rows):
    output={}
    for symbol in SYMBOLS:
        history=[r for r in rows if r['symbol']==symbol]
        if not history:continue
        latest=history[-1];previous=latest['previous_shares'];change=None if latest['split'] else latest['shares']-previous
        percent=round(change/previous*100,2) if change is not None and previous else None
        output[symbol]={'latest':latest,'change':change,'change_percent':percent,'rows':history}
    return output

def parse_calendar(body,year):
    soup=BeautifulSoup(body,'html.parser');heading=soup.find(string=re.compile(str(year)+r'\s+Short Interest Reporting Dates'))
    if not heading:raise ValueError('FINRA calendar year not found')
    table=heading.find_parent().find_next('table');rows=[]
    if table is None:raise ValueError('FINRA calendar table not found')
    months={name:i for i,name in enumerate(calendar.month_name) if name}
    def month_day(text):
        match=re.search(r'([A-Za-z]+)\s+(\d{1,2})',text)
        return months[match[1]],int(match[2])
    for tr in table.find_all('tr'):
        cells=[c.get_text(' ',strip=True) for c in tr.find_all('td')]
        if len(cells)<3:continue
        sm,sd=month_day(cells[0]);pm,pd=month_day(cells[2]);py=year+(pm<sm)
        publication=datetime(py,pm,pd,16,40,tzinfo=ZoneInfo('America/New_York'))
        rows.append({'date':date(year,sm,sd).isoformat(),'published_at':publication.astimezone(timezone.utc).isoformat(),'publication_date':publication.date().isoformat()})
    if len(rows)<20:raise ValueError('Incomplete FINRA calendar')
    return rows

def update(previous,now):
    result=copy.deepcopy(previous or {});stamp=now.isoformat();result.update(checked_at=stamp,source_url=SOURCE,api_url=API,fetch_ok=False,errors=[])
    old=result.get('raw_rows',[])
    try:
        full_stamp=datetime.fromisoformat(result.get('full_history_checked_at',''))
        full=not old or now-full_stamp>=timedelta(days=7) or full_stamp>now
    except (ValueError,TypeError):full=True
    try:start=now.date().replace(year=now.year-5)
    except ValueError:start=now.date().replace(year=now.year-5,day=28)
    since=start.isoformat() if full else (date.fromisoformat(max(r['date'] for r in old))-timedelta(days=65)).isoformat()
    try:
        new=fetch_rows(stamp,since);rows,revisions=merge_rows(old,new)
        if full and any(sum(r['symbol']==s for r in new)<20 for s in SYMBOLS):raise ValueError('Incomplete FINRA history')
        result.update(raw_rows=rows,series=summarize(rows),fetch_ok=True,last_success_at=stamp,revisions=result.get('revisions',[])+revisions)
        if full:result['full_history_checked_at']=stamp
    except Exception as exc:result['errors'].append('FINRA short interest: '+type(exc).__name__)
    schedule=result.get('release_calendar',{});year=now.astimezone(ZoneInfo('America/New_York')).year
    try:cached=now-datetime.fromisoformat(schedule.get('checked_at',''))<timedelta(days=7)
    except (ValueError,TypeError):cached=False
    if schedule.get('year')!=year or not schedule.get('rows') or not cached:
        try:
            r=requests.get(SCHEDULE,timeout=(10,25));r.raise_for_status()
            result['release_calendar']={'year':year,'rows':parse_calendar(r.text,year),'checked_at':stamp,'source_url':SCHEDULE}
        except Exception as exc:result['errors'].append('FINRA calendar: '+type(exc).__name__)
    return result
