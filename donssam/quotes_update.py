"""Delayed public extended-session quotes, separately labelled from daily signals."""
import json,math,urllib.request
from urllib.parse import quote
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parent

def read(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

def parse_quote(data,symbol,now):
    meta=data['meta'];q=data['indicators']['quote'][0]['close'];pairs=[(int(t),float(p)) for t,p in zip(data.get('timestamp',[]),q) if p is not None and math.isfinite(p)]
    if not pairs:raise ValueError('No quote observations')
    stamp,value=pairs[-1];ts=datetime.fromtimestamp(stamp,timezone.utc);local=ts.astimezone(ZoneInfo('America/New_York'));minutes=local.hour*60+local.minute
    future=symbol in ('NQ=F','ES=F')
    kind='crypto' if symbol=='BTC-USD' else 'futures' if future else 'index' if symbol.startswith('^') else 'postmarket' if minutes>=16*60 else 'premarket' if minutes<9*60+30 else 'regular'
    regular=meta.get('regularMarketPrice')
    # chartPreviousClose for range=5d can refer to the beginning of that range,
    # not yesterday. Derive the previous session from the intraday observations.
    sessions={}
    for t,p in pairs:
        observed=datetime.fromtimestamp(t,timezone.utc)
        day=observed.date() if kind=='crypto' else observed.astimezone(ZoneInfo('America/New_York')).date()
        et=observed.astimezone(ZoneInfo('America/New_York'));minute=et.hour*60+et.minute
        if kind=='crypto' or 9*60+30<=minute<16*60:sessions[day]=p
    current_day=ts.date() if kind=='crypto' else local.date()
    previous_days=[day for day in sessions if day<current_day]
    prior=sessions[max(previous_days)] if previous_days else meta.get('previousClose')
    reference=regular if kind in ('postmarket','premarket') and isinstance(regular,(int,float)) else prior
    if future:reference=None  # settlement comparison is filled from daily bars below
    age=max(0,(now-ts).total_seconds()/60)
    return {'symbol':symbol,'price':value,'quote_at':ts.isoformat(),'session':kind,'regular_price':regular,'reference_price':reference,'change_pct':(value/reference-1)*100 if reference else None,'age_minutes':round(age,1),'currency':meta.get('currency','USD'),'source':'Yahoo Finance chart · 공개 지연 시세','retrieved_at':now.isoformat(),'cached':False}

def fetch_quote(symbol,now):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?range=5d&interval=5m&includePrePost=true'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=16) as r:data=json.load(r)['chart']['result'][0]
    result=parse_quote(data,symbol,now)
    if symbol in ('NQ=F','ES=F'):
        daily_url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?range=5d&interval=1d'
        try:
            with urllib.request.urlopen(urllib.request.Request(daily_url,headers={'User-Agent':'Mozilla/5.0'}),timeout=12) as r:daily=json.load(r)['chart']['result'][0]
            closes=[float(p) for p in daily['indicators']['quote'][0]['close'] if p is not None]
            if len(closes)>1:
                result['reference_price']=closes[-2];result['change_pct']=(result['price']/closes[-2]-1)*100
        except Exception:pass
    return result

def main():
    now=datetime.now(timezone.utc);screen=read(ROOT/'screen.json');old=read(ROOT/'quotes.json').get('quotes',{})
    symbols=['^GSPC','^NDX','NQ=F','ES=F','SOXX','IWM','BTC-USD']
    symbols+= [x['ticker'] for x in screen.get('sectors',[])]
    symbols+= [x['ticker'] for e in screen.get('top_etf_holdings',[]) for x in e.get('holdings',[])]
    errors=[]
    def one(symbol):
        try:return symbol,fetch_quote(symbol,now)
        except Exception as exc:
            errors.append(symbol+': '+type(exc).__name__)
            prior=old.get(symbol)
            return symbol,{**prior,'cached':True} if prior else None
    with ThreadPoolExecutor(max_workers=4) as pool:quotes={k:v for k,v in pool.map(one,list(dict.fromkeys(symbols))) if v}
    result={'generated_at':now.isoformat(),'quotes':quotes,'errors':errors,'method':'30분 간격 수집 목표 + 제공처 지연. 선물은 23시간·주5일 거래로 24/7 아님. 현물 지수·선물·시간외를 분리; 지표 계산은 정규장/확정봉 기준.'}
    (ROOT/'quotes.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
    print('Quotes:',len(quotes),'errors:',len(errors))

if __name__=='__main__':main()
