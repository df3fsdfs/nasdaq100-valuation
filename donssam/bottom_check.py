"""User's bottom checklist. Unknown pattern definitions never become buy signals."""
import json
import math
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

ROOT = Path(__file__).resolve().parent
ASSETS = {"NDX": "^NDX", "SOXX": "SOXX", "NQ": "NQ=F", "BTC": "BTC-USD", "TQQQ": "TQQQ", "SOXL": "SOXL"}

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
    if symbol == "BTC-USD":
        f = f[f.index.date < now.date()]  # UTC daily candle must have closed.
    else:
        local = now.astimezone(ZoneInfo("America/New_York"))
        # Conservatively wait until 18:00 ET for NQ daily settlement too.
        hour = 18 if symbol == "NQ=F" else 16
        f = f[(f.index.date < local.date()) | ((f.index.date == local.date()) & (local.hour >= hour))]
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

def metrics(frame, symbol, now):
    crypto = symbol == "BTC-USD"
    w = completed_bars(frame, "W-SUN" if crypto else "W-FRI", now, crypto)
    m = completed_bars(frame, "ME", now, crypto)
    return {"date": frame.index[-1].date().isoformat(), "price": finite(frame.Close.iloc[-1]),
            "peak_close": finite(frame.Close.max()), "drawdown_pct": finite((frame.Close.iloc[-1]/frame.Close.max()-1)*100),
            "weekly_cci": finite(cci(w).iloc[-1]) if len(w) >= 20 else None,
            "monthly_cci": finite(cci(m).iloc[-1]) if len(m) >= 20 else None,
            "weekly_rsi": finite(rsi(w.Close)),
            "weekly_date": w.index[-1].date().isoformat() if len(w) else None,
            "monthly_date": m.index[-1].date().isoformat() if len(m) else None,
            "volume_pct": finite(frame.Volume.iloc[-1]/frame.Volume.iloc[-21:-1].mean()*100) if len(frame)>=21 and frame.Volume.iloc[-21:-1].mean()>0 else None}

def row(key, label, value, threshold, unit, date, fresh, note=""):
    status = "unknown" if value is None or not fresh else ("pass" if value <= threshold else "fail")
    return {"id":key,"label":label,"value":value,"threshold":threshold,"unit":unit,"date":date,"status":status,"note":note}

def build(now, frames, fear=None, errors=None):
    assets = {}
    for name, (frame, source) in frames.items():
        a = metrics(frame, ASSETS[name], now)
        a["source"] = source
        observed=pd.Timestamp(a["date"]).date()
        if name=="BTC":
            a["fresh"] = observed == now.date()-timedelta(days=1)
        else:
            import exchange_calendars as xcals
            cal=xcals.get_calendar("XNYS")
            sessions=cal.sessions_in_range(pd.Timestamp(now.date()-timedelta(days=10)),pd.Timestamp(now.date()))
            # NQ settlement is accepted conservatively after 18:00 ET.
            clock=now-timedelta(hours=2) if name=="NQ" else now
            closed=[s for s in sessions if cal.session_close(s)<=pd.Timestamp(clock)]
            a["fresh"] = bool(closed) and observed == closed[-1].date()
        assets[name] = a
    def get(name, key): return assets.get(name, {}).get(key)
    checks = []
    for key, label, name, field, threshold, unit in [
        ("ndx_dd","나스닥100 고점 대비 -20% 이하","NDX","drawdown_pct",-20,"%"),
        ("fear","CNN 공포·탐욕 10 이하",None,None,10,"점"),
        ("soxx","SOXX 400달러 이하","SOXX","price",400,"달러"),
        ("nq","미니 나스닥 선물 26,000 이하","NQ","price",26000,"pt"),
        ("btc","BTC 73,000달러 이하","BTC","price",73000,"달러")]:
        a = fear or {} if name is None else assets.get(name,{})
        checks.append(row(key,label,a.get("value") if name is None else a.get(field),threshold,unit,a.get("date"),a.get("fresh",False)))
    for name in ("TQQQ","SOXL"):
        a=assets.get(name,{})
        z=row(name.lower()+"_volume",name+" 거래량 20일 평균의 400% 이상",a.get("volume_pct"),400,"%",a.get("date"),a.get("fresh",False))
        if z["status"]!="unknown": z["status"]="pass" if z["value"]>=400 else "fail"
        z["note"]="당일 제외 직전 20거래일 평균 대비 · 400%=4배"
        checks.append(z)
    for key,label,field,threshold in [("weekly_cci200","나스닥100 주봉 CCI -200 이하","weekly_cci",-200),("weekly_cci100","나스닥100 주봉 CCI -100 이하","weekly_cci",-100),("monthly_cci100","나스닥100 월봉 CCI -100 이하","monthly_cci",-100)]:
        a=assets.get("NDX",{})
        checks.append(row(key,label,a.get(field),threshold,"",a.get("monthly_date" if field.startswith("monthly") else "weekly_date"),a.get("fresh",False),"수치 조건만 표시 · 패턴 포함 최종 판정은 아래 별도"))
    for key,label in [("joopjoop","필수: 전 자산 주봉·월봉 줍줍신호"),("weekly_pattern","주봉 CCI -200 송곳형 또는 -100 쌍바닥"),("monthly_pattern","월봉 CCI -100·쌍바닥 또는 주봉 RSI 상승 다이버전스")]:
        checks.append({"id":key,"label":label,"status":"unknown","value":None,"threshold":None,"unit":"","date":None,"note":"원본 지표·패턴 정의 연결 대기"})
    return {"schema_version":1,"generated_at":now.isoformat(),"assets":assets,"fear":fear,"checks":checks,
            "summary":{"numeric_pass":sum(z["status"]=="pass" for z in checks[:7]),"numeric_total":7,"final_status":"pending_definition"},
            "method":{"benchmark":"NASDAQ-100 (^NDX), 나스닥 종합·QQQ 대체 안 함","drawdown":"확보한 전체 일별 종가의 최고값 대비 (최소 1980년부터 요청)","indicators":"CCI20(HLC3), 주봉 RSI14(Wilder); 기존 사이트 기간을 사용. 확정봉만 판정","volume":"당일을 제외한 직전 20거래일 평균, 400%=4배. 분할 발생 구간은 주의","nq":"Yahoo NQ=F 근월물 연속 시세, 만기 교체 영향 있음","pending":"줍줍 원본·전 자산 범위·송곳형/쌍바닥/다이버전스 정의 확정 후 최종 조건 연결"},"errors":errors or []}

def main():
    now=datetime.now(timezone.utc)
    frames, errors={},[]
    for name,symbol in ASSETS.items():
        try: frames[name]=history(symbol,now)
        except Exception as exc: errors.append(name+": "+type(exc).__name__)
    fear=None
    try:
        obj=request_json("https://production.dataviz.cnn.io/index/fearandgreed/graphdata")["fear_and_greed"]
        v=float(obj["score"])
        if not 0<=v<=100: raise ValueError("invalid score")
        day=pd.Timestamp(obj["timestamp"]).date()
        fear={"value":finite(v),"date":day.isoformat(),"fresh":0<=(now.date()-day).days<=5,"source":"https://www.cnn.com/markets/fear-and-greed"}
    except Exception as exc: errors.append("CNN: "+type(exc).__name__)
    result=build(now,frames,fear,errors)
    # Failed retrieval cannot retain yesterday's green pass under today's timestamp.
    (ROOT/"bottom.json").write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2),encoding="utf-8")
    print("Bottom checklist:",len(frames),"assets;",len(errors),"source errors")

if __name__=="__main__": main()
