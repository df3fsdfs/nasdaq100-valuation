"""User's bottom checklist. Unknown pattern definitions never become buy signals."""
import json
import math
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = Path(__file__).resolve().parent
ASSETS = {"NDX": "^NDX", "BTC": "BTC-USD", "TQQQ": "TQQQ", "SOXL": "SOXL"}

def request_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", "Content-Type":"application/json", "Accept": "application/json, text/plain, */*", "Referer": "https://www.cnn.com/markets/fear-and-greed"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.load(response)

def history(symbol, now):
    from urllib.parse import quote
    # Raw closing prices: price thresholds must not use dividend-adjusted prices.
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + quote(symbol, safe="") + "?period1=315532800&period2=" + str(int(now.timestamp())) + "&interval=1d&events=splits"
    result = request_json(url)["chart"]["result"][0]
    q = result["indicators"]["quote"][0]
    dates = pd.to_datetime(result["timestamp"], unit="s", utc=True)
    zone = result["meta"].get("exchangeTimezoneName", "America/New_York")
    f = pd.DataFrame({k: q[k] for k in ("high", "low", "close", "volume")}, index=dates.tz_convert(zone).date)
    f.columns = ["High", "Low", "Close", "Volume"]
    f.index = pd.DatetimeIndex(f.index)
    f = f.dropna(subset=["High", "Low", "Close"])
    # Compare share counts on today's split basis (leveraged ETFs can reverse split).
    for event in result.get("events", {}).get("splits", {}).values():
        ratio=float(event["numerator"])/float(event["denominator"])
        split_day=pd.Timestamp(event["date"],unit="s",tz="UTC").tz_convert(zone).date()
        f.loc[f.index.date < split_day,"Volume"] *= ratio
    if len(f) < 500:
        raise ValueError("insufficient history")
    return f, url

def cci(frame):
    tp = (frame.High + frame.Low + frame.Close) / 3
    mean = tp.rolling(20).mean()
    deviation = tp.rolling(20).apply(lambda a: abs(a-a.mean()).mean(), raw=True)
    return (tp-mean)/(0.015*deviation.replace(0, float("nan")))

def rsi(close):
    # Wilder RMA: SMA seed, then recursive smoothing (Pine ta.rsi convention).
    delta = close.diff().dropna()
    if len(delta) < 14:
        return None
    gain, loss = delta.clip(lower=0), -delta.clip(upper=0)
    up, down = float(gain.iloc[:14].mean()), float(loss.iloc[:14].mean())
    for u, d in zip(gain.iloc[14:], loss.iloc[14:]):
        up, down = (up*13+u)/14, (down*13+d)/14
    return 100. if down == 0 and up > 0 else (50. if down == up == 0 else 100-100/(1+up/down))

def completed_bars(frame, frequency, now, crypto=False):
    bars = frame.resample(frequency).agg({"High":"max", "Low":"min", "Close":"last", "Volume":"sum"}).dropna()
    local = now if crypto else now.astimezone(ZoneInfo("America/New_York"))
    last = bars.index[-1].date()
    if crypto:
        # Bitcoin weekly candles run Monday-Sunday UTC, months end at UTC midnight.
        complete = last < local.date()
    else:
        # Calendar handles early closes and month/week endings on exchange holidays.
        import exchange_calendars as xcals
        cal = xcals.get_calendar("XNYS", start="1980-01-01", end=str(now.year+1)+"-12-31")
        end = pd.Timestamp(last)
        start = end - pd.Timedelta(days=6) if frequency == "W-FRI" else end.replace(day=1)
        sessions = cal.sessions_in_range(start, end)
        complete = bool(len(sessions)) and pd.Timestamp(now) >= cal.session_close(sessions[-1])
    if not complete:
        bars = bars.iloc[:-1]
    return bars

def finite(value):
    return round(float(value), 3) if value is not None and math.isfinite(float(value)) else None

def serialize_bar(frame, tf):
    from pine_buy import evaluate
    series=evaluate(frame,tf)
    z=series.iloc[-1]
    rsilimit=series.attrs['rsi_limit']
    signals={k:bool(z[k]) for k in ['buy','sharp','normal','time','restricted']}
    last_buy=series.index[series.buy]
    return {"date":str(frame.index[-1].date()),"bars":len(frame),"signals":signals,"previous_buy":bool(series.buy.iloc[-2]) if len(series)>1 else None,
            "cci20":finite(cci(frame).iloc[-1]),
            "cci_below100":bool(cci(frame).iloc[-1]<=-100),"cci_below200":bool(cci(frame).iloc[-1]<=-200),
            "rsi":{str(n):finite(z['rsi'+str(n)]) for n in (14,30,100,200)},
            "rsi_position":finite(z.rsi_position),"rsi_limit":rsilimit,"rsi_extreme":bool(z.rsi_extreme),
            "rsi_checks":{k:bool(z[k]) for k in ['sharp_rsi_drop','sharp_rsi_low','normal_rsi_low','normal_rsi_cooling','long_rsi_cooling','short_rsi_turning']},
            "last_buy_date":str(last_buy[-1].date()) if len(last_buy) else None,
            "long_history_ready":bool(pd.notna(z.rsi200)),
            "deviations":{str(n):finite(z['dev'+str(n)]) for n in (20,60,120,200)}}

def daily_closed(frame,now,crypto):
    if crypto:return frame[frame.index.date<now.date()]
    local=now.astimezone(ZoneInfo('America/New_York'))
    return frame[(frame.index.date<local.date())|((frame.index.date==local.date())&(local.hour>=16))]

def asset_result(frame,name,now,source):
    crypto=name=='BTC'
    closed=daily_closed(frame,now,crypto)
    result={"source":source,"daily_date":str(closed.index[-1].date()),"timeframes":{}}
    for tf,freq in [('D',None),('W','W-SUN' if crypto else 'W-FRI'),('M','ME')]:
        complete=closed if tf=='D' else completed_bars(closed,freq,now,crypto)
        forming=frame if tf=='D' else frame.resample(freq).agg({'High':'max','Low':'min','Close':'last','Volume':'sum'}).dropna()
        result['timeframes'][tf]={"confirmed":serialize_bar(complete,tf),"latest":serialize_bar(forming,tf),"forming":bool(complete.index[-1]!=forming.index[-1] or not complete.iloc[-1].equals(forming.iloc[-1]))}
    observed=pd.Timestamp(result['daily_date']).date()
    if crypto:result['fresh']=observed==now.date()-timedelta(days=1)
    else:
        import exchange_calendars as xcals
        cal=xcals.get_calendar('XNYS')
        sessions=cal.sessions_in_range(pd.Timestamp(now.date()-timedelta(days=10)),pd.Timestamp(now.date()))
        done=[x for x in sessions if cal.session_close(x)<=pd.Timestamp(now)]
        result['fresh']=bool(done) and observed==done[-1].date()
    return result

def build(now,frames,fear=None,errors=None,crypto_fear=None):
    assets={}
    for name,(frame,source) in frames.items():
        if name not in ('NDX','BTC'):continue
        try:assets[name]=asset_result(frame,name,now,source)
        except Exception as exc:(errors if errors is not None else []).append(name+': '+type(exc).__name__)
    return {"schema_version":2,"generated_at":now.isoformat(),"assets":assets,
            "fear":{"cnn":fear,"crypto":crypto_fear},"errors":errors or [],
            "method":{"signals":"moodcomp 제공 Pine buySignal 이식: 급락형/일반조정형/기간조정형/재상승형 OR. 매도·MA 표시 코드는 제외.",
                      "basis":"확정봉과 진행 중 봉을 나란히 표시. 진행 중 신호는 봉 마감 전 바뀔 수 있음.",
                      "sources":"나스닥100 ^NDX / BTC-USD Yahoo OHLC. TradingView의 거래소·봉 구성에 따라 수치 차이가 있을 수 있음.",
                      "indicators":"CCI20(HLC3) -100/-200은 별도 참고 조건. RSI14/30/100/200은 Wilder RMA. RSI 상대위치 한도: 일22/주27/월32.",
                      "unused":"Pine의 priceExtreme·rsiExtreme·atrLimit는 최종 buySignal의 필수조건이 아님. RSI 상대위치 조건은 별도 참고 표시.",
                      "history":"RSI200은 201개 종가 필요. 이력이 짧은 분기는 원본 Pine처럼 충족되지 않으며 이력 부족을 별도 표기.",
                      "thresholds":"고정 가격·고점대비 하락률 조건은 제거. 원본 줍 신호 내부의 이동평균·ATR 가격식은 유지.",
                      "volume":"TQQQ/SOXL은 직전20거래일 평균 대비 400%=4배를 별도 참고 표시"}}

def main():
    now=datetime.now(timezone.utc)
    frames,errors={},[]
    for name,symbol in ASSETS.items():
        try:frames[name]=history(symbol,now)
        except Exception as exc:errors.append(name+': '+type(exc).__name__)
    fear=crypto_fear=None
    try:
        payload=request_json('https://production.dataviz.cnn.io/index/fearandgreed/graphdata')
        obj=payload['fear_and_greed']
        value=float(obj['score']);day=pd.Timestamp(obj['timestamp']).date()
        if not 0<=value<=100:raise ValueError('invalid score')
        fear={"value":finite(value),"date":day.isoformat(),"fresh":0<=(now.date()-day).days<=5,"source":"https://www.cnn.com/markets/fear-and-greed","previous":finite(obj.get("previous_close"))}
    except Exception as exc:errors.append('CNN: '+type(exc).__name__)
    try:
        items=request_json('https://api.alternative.me/fng/?limit=21')['data']
        obj=items[0]
        value=float(obj['value']);day=datetime.fromtimestamp(int(obj['timestamp']),timezone.utc).date()
        if not 0<=value<=100:raise ValueError('invalid score')
        crypto_fear={"value":value,"date":day.isoformat(),"fresh":0<=(now.date()-day).days<=2,"source":"https://alternative.me/crypto/fear-and-greed-index/","label":obj.get('value_classification'),"previous":float(items[1]["value"]) if len(items)>1 else None}
    except Exception as exc:errors.append('Crypto Fear: '+type(exc).__name__)
    if fear:
        try:
            points=payload.get('fear_and_greed_historical',{}).get('data',[])
            cnn_history={pd.Timestamp(p['x'],unit='ms',tz='UTC').date().isoformat():float(p['y']) for p in points if p.get('x') is not None and p.get('y') is not None}
            values=[v for d,v in sorted(cnn_history.items()) if d<fear['date']][-20:]
            fear.update(mean=finite(sum(values)/len(values)) if values else None,mean_n=len(values))
        except Exception:pass
    if crypto_fear:
        values=[float(x['value']) for x in items[1:21]]
        crypto_fear.update(mean=finite(sum(values)/len(values)) if values else None,mean_n=len(values))
    result=build(now,frames,fear,errors,crypto_fear)
    result['volume']={}
    for name in ('TQQQ','SOXL'):
        if name in frames:
            f=daily_closed(frames[name][0],now,False)
            value=finite(f.Volume.iloc[-1]/f.Volume.iloc[-21:-1].mean()*100) if len(f)>20 and f.Volume.iloc[-21:-1].mean()>0 else None
            result['volume'][name]={"value":value,"date":str(f.index[-1].date()),"pass":value>=400 if value is not None else None}
    (ROOT/'bottom.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    print('Pine signal snapshot:',list(result['assets']),'; source errors:',errors)

if __name__=='__main__':main()
