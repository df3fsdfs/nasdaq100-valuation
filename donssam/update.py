"""Weekly market-screen snapshot. Missing observations are never filled with invented values."""
import json, math, time, urllib.request, csv, io
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf
import pandas as pd

SECTORS={"XLK":"기술","SOXX":"반도체","XLC":"통신서비스","XLY":"경기소비재","XLI":"산업재","XLF":"금융","XLE":"에너지","XLV":"헬스케어","XLP":"필수소비재","XLU":"유틸리티","XLB":"소재","XLRE":"부동산"}
STOCKS={"SOXX":["NVDA","AVGO","AMD","MU","AMAT","LRCX","KLAC","QCOM","TXN"],"XLK":["MSFT","AAPL","ORCL","CRM","ADBE","NOW","PANW"],"XLC":["GOOGL","META","NFLX","DIS"],"XLY":["AMZN","TSLA","HD","MCD","NKE","SBUX"],"XLI":["CAT","GE","DE","ETN","HON","UPS"],"XLF":["JPM","BAC","GS","MS","V","MA"],"XLE":["XOM","CVX","COP","SLB"],"XLV":["LLY","UNH","JNJ","ABBV","MRK"],"XLP":["WMT","COST","PG","KO","PEP"],"XLU":["NEE","DUK","SO"],"XLB":["LIN","SHW","FCX"],"XLRE":["PLD","AMT","EQIX"]}
FRED={"VIXCLS":"VIX","BAMLH0A0HYM2":"하이일드 OAS","DGS10":"미국 10년물","T10YIE":"10년 기대인플레","UNRATE":"실업률"}
def fred(code):
    url="https://fred.stlouisfed.org/graph/fredgraph.csv?id="+code+"&cosd=2024-01-01"
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=55) as r: raw=r.read().decode("utf-8-sig")
            arr=[]
            for row in csv.DictReader(io.StringIO(raw)):
                try:
                    v=float(row[code]);d=row.get("observation_date") or row.get("DATE")
                    if math.isfinite(v):arr.append((d,v))
                except (ValueError,KeyError,TypeError):pass
            if arr:return arr[-1]
        except Exception as e:print("FRED",code,repr(e))
        time.sleep(2*(attempt+1))
    return None
def calc(ticker):
    try:
        frame=yf.Ticker(ticker).history(period="18mo",auto_adjust=True)
        close=frame["Close"].dropna()
        if len(close)<65:return None
        change=close.diff()
        up=change.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        down=(-change.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
        rs=up.iloc[-1]/down.iloc[-1] if down.iloc[-1]>0 else float("inf")
        rsi=100-100/(1+rs)
        last=float(close.iloc[-1]);peak=float(close.tail(252).max())
        return {"ticker":ticker,"price":round(last,2),"rsi14":round(float(rsi),1),"drawdown52":round((last/peak-1)*100,1),"date":str(close.index[-1].date())}
    except Exception as e:
        print("Price",ticker,repr(e));return None
macro={}
for code,name in FRED.items():
    item=fred(code)
    macro[code]={"name":name,"date":item[0],"value":item[1]} if item else None
# Thresholds are transparent screening rules, not validated forecasts.
vix=macro.get("VIXCLS");oas=macro.get("BAMLH0A0HYM2");rate=macro.get("DGS10")
rules=[
 {"label":"변동성 과열 여부 (VIX ≤ 30)","status":("pass" if vix["value"]<=30 else "fail") if vix else "unknown","value":vix},
 {"label":"신용위험 확산 여부 (HY OAS ≤ 5%p)","status":("pass" if oas["value"]<=5 else "fail") if oas else "unknown","value":oas},
 {"label":"장기금리 압박 여부 (10Y ≤ 5%)","status":("pass" if rate["value"]<=5 else "fail") if rate else "unknown","value":rate}
]
allpass=all(r["status"]=="pass" for r in rules)
sector=[]
for ticker,name in SECTORS.items():
    d=calc(ticker)
    if d:
        d.update(name=name,oversold=d["rsi14"]<=35 and d["drawdown52"]<=-15)
        sector.append(d)
sector.sort(key=lambda d:(not d["oversold"],d["rsi14"],d["drawdown52"]))
eligible=[d["ticker"] for d in sector if d["oversold"]]
stocks=[]
for sec in eligible:
    for ticker in STOCKS.get(sec,[]):
        d=calc(ticker)
        if d:
            d.update(sector=sec,oversold=d["rsi14"]<=35 and d["drawdown52"]<=-20)
            stocks.append(d)
stocks.sort(key=lambda d:(not d["oversold"],d["rsi14"],d["drawdown52"]))
result={"generated_at":datetime.now(timezone.utc).isoformat(),"macro":macro,"rules":rules,"macro_pass":allpass,"sectors":sector,"eligible_sectors":eligible,"stocks":stocks,"method":{"macro":"VIX≤30, HY OAS≤5%p, 10Y≤5%; 모두 충족해야 다음 단계 통과","sector":"RSI(14)≤35 및 52주 고점 대비 -15% 이하","stock":"해당 산업의 사전 지정 대형주 중 RSI(14)≤35 및 52주 고점 대비 -20% 이하","note":"선별 조건은 연구용 임계값이며 매수 신호가 아님. 주가 종가 기준, FRED 관측일과 갱신일 구분. 데이터 결측은 통과로 간주하지 않음."}}
Path("donssam").mkdir(exist_ok=True)
Path("donssam/screen.json").write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding="utf-8")
print("Sectors:",len(sector),"eligible:",eligible,"stocks:",len(stocks))
