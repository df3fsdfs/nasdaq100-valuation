"""Shared current/historical sector scoring. Same methodology for both."""
import pandas as pd
import math

def finite(value):
    return isinstance(value,(int,float)) and math.isfinite(value)

def qualification(score,rsi,cci):
    if not all(finite(x) for x in (score,rsi,cci)):return None
    return score>70 and rsi<=20 and cci<=-100


def score_sector(data,spy,name):
    d=dict(data);dd=d['drawdown52'];rsi=d['rsi14'];cci=d['cci_weekly']
    oversold=round(25*clamp(-dd/35)+15*clamp((50-rsi)/30),1)
    if spy and d['return6m'] is not None and spy['return6m'] is not None:
        rel6=d['return6m']-spy['return6m']
        rel12=d['return12m']-spy['return12m'] if d['return12m'] is not None and spy['return12m'] is not None else None
        strength=round(20*clamp((rel6+20)/40)+15*clamp((rel12+30)/60),1) if rel12 is not None else None
    else:rel6=rel12=strength=None
    trend=round(15*clamp((d['ma200_gap']+20)/40)+10*clamp((cci+200)/400),1) if d['ma200_gap'] is not None and cci is not None else None
    score=round(oversold+strength+trend,1) if strength is not None and trend is not None else None
    passed=qualification(score,rsi,cci)
    d.update(name=name,oversold=bool(finite(rsi) and finite(cci) and rsi<=20 and cci<=-100),qualified=passed,judgement='unknown' if passed is None else 'pass' if passed else 'fail',score_direction='high_is_opportunity',scoring_model='strength35_oversold40_trend25',opportunity_score=score,oversold_points=oversold,relative_strength_points=strength,trend_points=trend,relative6m=round(rel6,1) if rel6 is not None else None,relative12m=round(rel12,1) if rel12 is not None else None)
    return d
def score_individual(data,spy):
    z=score_sector(data,spy,data.get('ticker',''))
    return {k:z[k] for k in ('opportunity_score','relative_strength_points','oversold_points','trend_points','relative6m','relative12m','qualified','judgement','scoring_model','score_direction')} | {'score':z['opportunity_score'],'benchmark':'SPY','benchmark_date':spy.get('date') if spy else None}

def cci_weekly(frame):
    try:
        w=frame[["High","Low","Close"]].resample("W-FRI").agg({"High":"max","Low":"min","Close":"last"}).dropna()
        tp=(w["High"]+w["Low"]+w["Close"])/3
        ma=tp.rolling(20).mean()
        md=tp.rolling(20).apply(lambda x:float(abs(x-x.mean()).mean()),raw=True)
        value=(tp-ma)/(0.015*md)
        return round(float(value.iloc[-1]),1) if pd.notna(value.iloc[-1]) else None
    except Exception:return None

def clamp(v):return max(0.,min(1.,float(v)))

def metrics(frame,ticker):
    try:
        frame=frame.dropna(subset=["Close"])
        if len(frame)<100:return None
        close=frame["Close"]
        delta=close.diff()
        gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        rsi=100-100/(1+gain.iloc[-1]/loss.iloc[-1]) if loss.iloc[-1]>0 else 100.
        last=float(close.iloc[-1]);high=float(close.tail(252).max())
        cci=cci_weekly(frame)
        ma200=float(close.tail(200).mean()) if len(close)>=200 else None
        ret6=(last/float(close.iloc[-126])-1)*100 if len(close)>126 else None
        ret12=(last/float(close.iloc[-252])-1)*100 if len(close)>252 else None
        return {"ticker":ticker,"price":round(last,2),"high52":round(high,2),"ma200":round(ma200,2) if ma200 else None,"return6m":round(ret6,2) if ret6 is not None else None,"return12m":round(ret12,2) if ret12 is not None else None,"rsi14":round(float(rsi),1),"drawdown52":round((last/high-1)*100,1),"cci_weekly":cci,"ma200_gap":round((last/ma200-1)*100,1) if ma200 else None,"date":str(close.index[-1].date())}
    except Exception as e:
        print("Metrics",ticker,str(e));return None

