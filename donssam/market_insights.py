"""Observed changes, not buy predictions. Discrete CLI derivatives are explicit."""
import csv,io,json,math,statistics,urllib.request
from pathlib import Path
from datetime import datetime,timezone
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from price_history import chart_history
from sector_scoring import metrics,score_sector

ROOT=Path(__file__).resolve().parent
def read(path,default=None):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {} if default is None else default

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=18) as r:return r.read().decode('utf-8-sig')

def compare(rows,window=20):
    rows=sorted({r['date']:r for r in rows if isinstance(r.get('value'),(int,float)) and math.isfinite(r['value'])}.values(),key=lambda r:r['date'])
    if not rows:return None
    current=rows[-1];base=rows[-window-1:-1];prev=rows[-2] if len(rows)>1 else None
    avg=statistics.mean(r['value'] for r in base) if base else None
    return {**current,'previous':prev['value'] if prev else None,'previous_date':prev['date'] if prev else None,'delta':current['value']-prev['value'] if prev else None,'mean':avg,'mean_delta':current['value']-avg if avg is not None else None,'mean_n':len(base),'window':window,'rows':rows[-window-2:]}

def fred(code):
    try:
        body=get('https://fred.stlouisfed.org/graph/fredgraph.csv?id='+code+'&cosd=2025-01-01')
        rows=[]
        for r in csv.DictReader(io.StringIO(body)):
            try:rows.append({'date':r.get('observation_date') or r.get('DATE'),'value':float(r[code])})
            except (ValueError,TypeError):pass
        if rows:return rows
    except Exception:pass
    d=json.loads(get('https://api.db.nomics.world/v22/series/FRED/'+code))['series']['docs'][0]
    return [{'date':day,'value':float(v)} for day,v in zip(d['period'],d['value']) if isinstance(v,(float,int)) and math.isfinite(v)]

def risk_one(item):
    key,name,code=item
    if key in ('vix','skew'):
        source='https://cdn.cboe.com/api/global/us_indices/daily_prices/'+key.upper()+'_History.csv'
        rows=[]
        for r in csv.DictReader(io.StringIO(get(source))):
            try:rows.append({'date':pd.Timestamp(r['DATE']).date().isoformat(),'value':float(r['CLOSE'] if key=='vix' else r['SKEW'])})
            except (ValueError,TypeError,KeyError):pass
    else:source='https://fred.stlouisfed.org/series/'+code;rows=fred(code)
    return key,{'name':name,'source':source,**(compare(rows) or {})}

def sign(x):return 1 if x>1e-9 else -1 if x< -1e-9 else 0
def crossing(previous,current):
    a,b=sign(previous),sign(current)
    return 'negative_to_positive' if a<0<b else 'positive_to_negative' if a>0>b else 'at_zero' if b==0 else 'none'

def cli_analysis(rows):
    series=pd.Series({pd.Period(r['date'],freq='M'):float(r['value']) for r in rows}).sort_index()
    if len(series)<5:return None
    series=series.reindex(pd.period_range(series.index[0],series.index[-1],freq='M'))
    velocity=series.diff();acceleration=velocity.diff();jerk=acceleration.diff()
    if pd.isna(jerk.iloc[-2:]).any():return None
    a0,a1=float(acceleration.iloc[-2]),float(acceleration.iloc[-1]);j0,j1=float(jerk.iloc[-2]),float(jerk.iloc[-1]);v=float(velocity.iloc[-1])
    direction='상승' if v>0 else '하락' if v<0 else '보합'
    interpretation=(direction+' 중 · '+('상승 속도 확대' if a1>0 else '상승 속도 둔화' if a1<0 else '상승 속도 유지')) if v>0 else (direction+' 중 · '+('하락 속도 완화' if a1>0 else '하락 속도 확대' if a1<0 else '하락 속도 유지')) if v<0 else '수준 보합'
    return {'date':str(series.index[-1]),'previous_date':str(series.index[-2]),'level':float(series.iloc[-1]),'previous_level':float(series.iloc[-2]),'velocity':v,'previous_velocity':float(velocity.iloc[-2]),'acceleration':a1,'previous_acceleration':a0,'jerk':j1,'previous_jerk':j0,'acceleration_cross':crossing(a0,a1),'jerk_cross':crossing(j0,j1),'interpretation':interpretation,'rows':[{'date':str(day),'value':float(value)} for day,value in series.iloc[-24:].items() if pd.notna(value)]}

def sector_history(screen):
    tickers=[x['ticker'] for x in screen.get('sectors',[])];frames={}
    def load(t):
        try:return t,chart_history(t,years=5)
        except Exception:return t,None
    with ThreadPoolExecutor(max_workers=4) as pool:
        frames={t:f for t,f in pool.map(load,list(dict.fromkeys(tickers+['SPY']))) if f is not None}
    if 'SPY' not in frames:return {}
    dates=frames['SPY'].index[-22:];output={}
    for ticker in tickers:
        if ticker not in frames:continue
        values=[]
        for day in dates:
            # Recompute weekly CCI from data available on that date, never future OHLC.
            f=frames[ticker];partial=f[f.index.date<=day.date()]
            spy=frames['SPY'];spy=spy[spy.index.date<=day.date()]
            a=metrics(partial,ticker);b=metrics(spy,'SPY')
            if a and b:
                z=score_sector(a,b,ticker)
                if z['opportunity_score'] is not None:values.append({'date':a['date'],'value':z['opportunity_score']})
        output[ticker]=compare(values)
        if output[ticker]:output[ticker].update(oversold=z['oversold'],qualified=z['qualified'],rsi14=z['rsi14'],cci_weekly=z['cci_weekly'])
    return output

def opportunity_changes(sentiment):
    output={}
    for key in ('equity','crypto'):
        rows=[]
        for r in sentiment.get('history',[]):
            value=r.get(key,{}).get('score');direction=r.get('score_direction')
            if value is not None and direction in ('zero_is_opportunity','high_is_opportunity'):
                rows.append({'date':r['date'],'value':round(100-value,1) if direction=='zero_is_opportunity' else value})
        output[key]=compare(rows)
    return output

def checkpoints(bottom,opportunities,sectors):
    groups={'signals':[],'opportunity':[],'sectors':[],'other':[]}
    today=datetime.now(timezone.utc).date()
    for asset,a in bottom.get('assets',{}).items():
        for tf,z in a.get('timeframes',{}).items():
            c=z['confirmed'];prev=c.get('previous_buy')
            if prev is not None and c['signals']['buy']!=prev:
                age=(today-pd.Timestamp(c['date']).date()).days
                if 0<=age<=3:groups['signals'].append({'title':asset+' '+{'D':'일봉','W':'주봉','M':'월봉'}[tf]+(' 새 줍' if c['signals']['buy'] else ' 줍 종료'),'good':c['signals']['buy'],'body':'직전 확정봉 '+('있음' if prev else '없음')+' → 현재 '+('있음' if c['signals']['buy'] else '없음'),'date':c['date']})
            if z.get('forming') and z['latest']['signals']['buy']!=c['signals']['buy']:
                groups['signals'].append({'title':asset+' '+tf+' 진행 중 줍 변화','good':z['latest']['signals']['buy'],'body':'확정봉 '+('있음' if c['signals']['buy'] else '없음')+' → 진행 중 '+('있음' if z['latest']['signals']['buy'] else '없음')+' · 마감 전 변동 가능','date':bottom.get('generated_at','')[:10]})
    for key,z in opportunities.items():
        if z and z.get('mean_delta') is not None and (abs(z['mean_delta'])>=10 or abs(z.get('delta') or 0)>=10):
            groups['opportunity'].append({'title':('증시' if key=='equity' else '크립토')+' 기회지수 급변','good':z['mean_delta']>0,'body':'최근 '+str(z['mean_n'])+'거래일 평균 '+str(round(z['mean'],1))+' → '+str(z['value'])+' ('+f"{z['mean_delta']:+.1f}"+'점) · 100에 가까울수록 기회','date':z['date']})
    for ticker,z in sectors.items():
        if z and z.get('mean_delta') is not None and (abs(z['mean_delta'])>=10 or abs(z.get('delta') or 0)>=8):
            groups['sectors'].append({'title':ticker+' 기회점수 '+('급상승' if z['mean_delta']>0 else '급하락'),'good':z['mean_delta']>0,'oversold':bool(z.get('oversold')),'qualified':z.get('qualified'),'body':str(z['mean_n'])+'거래일 평균 '+str(round(z['mean'],1))+' → '+str(z['value'])+' ('+f"{z['mean_delta']:+.1f}"+'점) · 전일 '+f"{z['delta']:+.1f}"+'점 · 종합판정 '+('통과' if z.get('qualified') else '미충족'),'date':z['date']})
    groups['sectors'].sort(key=lambda x:(not x['good'],x['title']))
    for key,x in bottom.get('fear',{}).items():
        if x and x.get('previous') is not None and (abs(x['value']-x['previous'])>=10 or (x['previous']>15>=x['value'])):
            groups['other'].append({'title':key.upper()+' 공포 급변','good':x['value']<x['previous'],'body':str(x.get('mean_n',0))+'일 평균 '+str(x.get('mean','—'))+' → '+str(x['value'])+' · 직전 '+str(x['previous']),'date':x['date']})
    for key,x in bottom.get('volume',{}).items():
        if x.get('pass'):groups['other'].append({'title':key+' 거래량 급증','good':True,'body':'직전20거래일 평균의 '+str(round(x['value']))+'%','date':x['date']})
    return groups

def main():
    previous=read(ROOT/'insights.json');errors=[];risks={}
    items=[('vix','VIX',None),('skew','SKEW',None),('hy','HY OAS','BAMLH0A0HYM2'),('yield10','미국 10년물','DGS10')]
    def safe(item):
        try:return risk_one(item)
        except Exception as exc:errors.append(item[0]+': '+type(exc).__name__);return item[0],previous.get('risk',{}).get(item[0])
    with ThreadPoolExecutor(max_workers=4) as pool:risks={k:v for k,v in pool.map(safe,items) if v}
    liquidity=read(ROOT.parent/'fed-liquidity/data.json').get('rows',[])
    liq={k:compare([{'date':r['date'],'value':r[k]} for r in liquidity if r.get(k) is not None],13) for k in ['net','WALCL','WTREGEN','RRPONTSYD','WRESBAL']}
    cli=read(ROOT/'cli.json');analysis={k:cli_analysis(v['rows']) for k,v in cli.get('series',{}).items() if k in ('USA','G7')}
    screen=read(ROOT/'screen.json');sectors=sector_history(screen)
    if not sectors:sectors=previous.get('sector_changes',{});errors.append('Sector comparison history unavailable')
    opportunities=opportunity_changes(read(ROOT/'sentiment.json'));bottom=read(ROOT/'bottom.json')
    result={'generated_at':datetime.now(timezone.utc).isoformat(),'risk':risks,'liquidity':liq,'cli':analysis,'sector_changes':sectors,'opportunity_changes':opportunities,'checkpoints':checkpoints(bottom,opportunities,sectors),'errors':errors,'method':{'risk':'전일=직전 관측 거래일; 평균=현재일 제외 직전20관측 거래일. 관측일은 지표별 표시.','liquidity':'수요일 정렬 주간값. 전주 및 현재주 제외 직전13주 평균 대비.','cli':'v=ΔCLI, a=Δ²CLI, j=Δ³CLI. a의 0선 전환=속도의 극점/수준 곡률 전환 후보; j의 0선 전환=가속도의 극점 후보. 서로 다른 사건. 최신 빈티지에서 월간 차분하며 추후 개정 가능.','checkpoints':'신호 전환(최근3일), 기회지수 전일 또는 평균 대비10점 이상, 산업 전일8점 또는20일평균10점 이상. 점수 변화는 %가 아닌 점 단위. 증시/크립토 기회지수는 실제 보관된 일별 기록만 사용하며 초기 평균 표본 수 명시.'}}
    (ROOT/'insights.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2))
    print('Insights:',len(risks),'risk series;',len(sectors),'sector histories;',errors)

if __name__=='__main__':main()
