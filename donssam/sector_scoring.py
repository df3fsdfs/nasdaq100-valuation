"""Shared sector/stock opportunity scoring using short, medium and long horizons."""
import math
import pandas as pd
from pine_buy import rsi as pine_rsi, rma

MODEL='relative_base17p5_long7p5_drawdown10_v4'
METHOD='조정기회100=완만한상대점수35+과매도40+ATR이격25. 상대점수=17.5−7.5tanh(zL/2)+10tanh(zR/2). zL=(20/35)×SPY대비6개월초과수익률/20+(15/35)×12개월초과수익률/30. 상대가격=종목수정종가/SPY수정종가; 상대조정률=1−상대가격/직전252거래일포함최고상대가격. zR=(현재상대조정률−과거중앙값)/max(과거IQR,1%p). 기준분포는 현재일 제외 직전최대1260공통거래일, 최소252개. 과매도40·ATR이격25와 통과조건은 유지.'

def finite(value):
    return isinstance(value,(int,float)) and math.isfinite(value)

def clamp(v):
    return max(0.,min(1.,float(v)))

def qualification(score,rsi,cci):
    if not all(finite(x) for x in (score,rsi,cci)):return None
    return score>=70 and rsi<=20 and cci<=-100

def rsi_opportunity(value,position):
    if not all(finite(x) for x in (value,position)):return None
    return .5*clamp((50-value)/35)+.5*clamp(1-position/100)

def trend_strength(slope,previous):
    if not all(finite(x) for x in (slope,previous)):return None
    # Half for slope level, half for improvement. Flat/unchanged scores 50%.
    return .5*clamp(.5+slope/2)+.5*clamp(.5+(slope-previous))

def relative_calibration(frame,benchmark_frame):
    """Align by session date; reference distribution excludes the observation date."""
    empty={'relative_z':None,'relative_reference_count':0}
    if benchmark_frame is None:return empty
    def dated(f):
        x=pd.Series(f.Close.to_numpy(),index=pd.Index(f.index.date))
        return x[~x.index.duplicated(keep='last')]
    joined=pd.concat([dated(frame).rename('asset'),dated(benchmark_frame).rename('benchmark')],axis=1,join='inner').dropna().sort_index()
    if joined.empty:return empty
    ratio=joined.asset/joined.benchmark
    drawdown=1-ratio/ratio.rolling(252,min_periods=252).max()
    past=drawdown.iloc[:-1].dropna().tail(1260)
    empty['relative_reference_count']=len(past)
    if len(past)<252 or pd.isna(drawdown.iloc[-1]):return empty
    median=float(past.median());iqr=float(past.quantile(.75)-past.quantile(.25));scale=max(iqr,.01)
    return {'relative_z':float((drawdown.iloc[-1]-median)/scale),
            'relative_drawdown':float(drawdown.iloc[-1]*100),'relative_drawdown_median':median*100,
            'relative_drawdown_iqr':iqr*100,'relative_scale':scale*100,'relative_reference_count':len(past),
            'relative_reference_start':str(past.index[0]),'relative_reference_end':str(past.index[-1]),
            'relative_observation_date':str(joined.index[-1])}

def relative_points(rel6,rel12,z):
    if not all(finite(v) for v in (rel6,rel12,z)):return None,None
    long_z=(20/35)*rel6/20+(15/35)*rel12/30
    long_correction=round(-7.5*math.tanh(long_z/2),1)
    correction=round(10*math.tanh(z/2),1)
    return round(17.5+long_correction+correction,1),{
        'base':17.5,'longterm_correction':long_correction,'relative_correction':correction,
        'longterm_z':long_z,'relative_z':z}

def score_sector(data,spy,name):
    d=dict(data);rsi=d.get('rsi14');cci=d.get('cci_weekly')
    parts={}
    factors=[('drawdown',10,-d['drawdown52']/35 if finite(d.get('drawdown52')) else None),
             ('rsi14',5,rsi_opportunity(rsi,d.get('rsi14_position65'))),
             ('rsi30',10,rsi_opportunity(d.get('rsi30'),d.get('rsi30_position65'))),
             ('weekly_cci',10,-cci/200 if finite(cci) else None),
             ('monthly_cci',5,-d['cci_monthly']/180 if finite(d.get('cci_monthly')) else None)]
    for key,weight,value in factors:parts[key]=round(weight*clamp(value),1) if finite(value) else None
    oversold=round(sum(parts.values()),1) if all(finite(v) for v in parts.values()) else None
    benchmark_ok=spy and all(finite(z) for z in (d.get('return6m'),d.get('return12m'),spy.get('return6m'),spy.get('return12m')))
    if benchmark_ok:
        rel6=d['return6m']-spy['return6m'];rel12=d['return12m']-spy['return12m']
        strength=round(20*clamp((rel6+20)/40)+15*clamp((rel12+30)/60),1)
    else:rel6=rel12=strength=None
    short=[d.get('dev20_change5'),d.get('dev60_change5')]
    trend_parts={'short':round(5*sum(clamp(x) for x in short)/2,1) if all(finite(x) for x in short) else None}
    for n,key in [(120,'medium'),(200,'long')]:
        value=trend_strength(d.get('ma'+str(n)+'_slope20'),d.get('ma'+str(n)+'_previous_slope20'))
        trend_parts[key]=round(10*value,1) if finite(value) else None
    trend=round(sum(trend_parts.values()),1) if all(finite(v) for v in trend_parts.values()) else None
    adjustment,relative_breakdown=relative_points(rel6,rel12,d.get('relative_z'))
    dev={n:d.get('atr_dev'+str(n)) for n in (20,60,120,200)}
    deviation_parts={
        'short':round(5*(clamp(-dev[20]/2.20)+clamp(-dev[60]/1.65))/2,1) if all(finite(dev[n]) for n in (20,60)) else None,
        'medium':round(10*clamp(-dev[120]/.95),1) if finite(dev[120]) else None,
        'long':round(10*clamp(-dev[200]/.60),1) if finite(dev[200]) else None}
    deviation=round(sum(deviation_parts.values()),1) if all(finite(v) for v in deviation_parts.values()) else None
    score=round(adjustment+oversold+deviation,1) if all(finite(v) for v in (adjustment,oversold,deviation)) else None
    passed=qualification(score,rsi,cci)
    d.update(name=name,oversold=bool(finite(rsi) and finite(cci) and rsi<=20 and cci<=-100),qualified=passed,
             judgement='unknown' if passed is None else 'pass' if passed else 'fail',score_direction='high_is_opportunity',
             scoring_model=MODEL,opportunity_score=score,oversold_points=oversold,relative_strength_points=strength,
             trend_points=trend,relative_adjustment_points=adjustment,relative_breakdown=relative_breakdown,deviation_points=deviation,deviation_breakdown=deviation_parts,relative6m=round(rel6,1) if rel6 is not None else None,relative12m=round(rel12,1) if rel12 is not None else None,
             oversold_breakdown=parts,trend_breakdown=trend_parts)
    return d

def score_individual(data,spy):
    if spy and data.get('date') and spy.get('date')!=data.get('date'):spy=None
    z=score_sector(data,spy,data.get('ticker',''))
    return {k:z[k] for k in ('opportunity_score','relative_strength_points','oversold_points','trend_points','relative6m','relative12m','qualified','judgement','scoring_model','score_direction','oversold_breakdown','trend_breakdown','relative_adjustment_points','deviation_points','deviation_breakdown','relative_breakdown')} | {'score':z['opportunity_score'],'benchmark':'SPY','benchmark_date':spy.get('date') if spy else None}

def cci_value(frame):
    tp=(frame.High+frame.Low+frame.Close)/3
    ma=tp.rolling(20).mean();md=tp.rolling(20).apply(lambda x:float(abs(x-x.mean()).mean()),raw=True)
    result=(tp-ma)/(0.015*md)
    return round(float(result.iloc[-1]),3) if pd.notna(result.iloc[-1]) and math.isfinite(result.iloc[-1]) else None

def cci_weekly(frame):
    return cci_value(frame[['High','Low','Close']].resample('W-FRI').agg({'High':'max','Low':'min','Close':'last'}).dropna())

def metrics(frame,ticker,benchmark_frame=None):
    try:
        frame=frame.dropna(subset=['Close'])
        if len(frame)<100:return None
        close=frame.Close;last=float(close.iloc[-1]);high=float(frame.High.tail(252).max())
        out={'ticker':ticker,'price':round(last,2),'high52':round(high,2),'drawdown52':round((last/high-1)*100,1),'date':str(close.index[-1].date())}
        def number(value):return round(float(value),6) if pd.notna(value) and math.isfinite(value) else None
        for n in (14,30):
            series=pine_rsi(close,n);recent=series.tail(65);span=recent.max()-recent.min()
            out['rsi'+str(n)]=number(series.iloc[-1])
            out['rsi'+str(n)+'_position65']=number((series.iloc[-1]-recent.min())/span*100 if span>0 else 50.)
        out['cci_weekly']=cci_weekly(frame)
        monthly=frame[['High','Low','Close']].resample('ME').agg({'High':'max','Low':'min','Close':'last'}).dropna()
        out['cci_monthly']=cci_value(monthly)
        tr=pd.concat([frame.High-frame.Low,(frame.High-close.shift()).abs(),(frame.Low-close.shift()).abs()],axis=1).max(axis=1)
        atr=rma(tr,14).replace(0,float('nan'))
        out['atr14']=number(atr.iloc[-1])
        for n in (20,60,120,200):
            ma=close.rolling(n,min_periods=n).mean()
            out['ma'+str(n)]=number(ma.iloc[-1])
            out['atr_dev'+str(n)]=number(((close-ma)/atr).iloc[-1])
            if n in (20,60):
                dev=(close-ma)/atr
                out['dev'+str(n)+'_change5']=number((dev-dev.shift(5)).iloc[-1])
            else:
                slope=(ma-ma.shift(20))/atr
                out['ma'+str(n)+'_slope20']=number(slope.iloc[-1])
                out['ma'+str(n)+'_previous_slope20']=number(slope.iloc[-21])
        out['ma200_gap']=round((last/out['ma200']-1)*100,1) if out['ma200'] else None
        out['return6m']=round((last/float(close.iloc[-126])-1)*100,2) if len(close)>126 else None
        out['return12m']=round((last/float(close.iloc[-252])-1)*100,2) if len(close)>252 else None
        out.update(relative_calibration(frame,benchmark_frame))
        return out
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        print('Metrics',ticker,str(exc));return None
