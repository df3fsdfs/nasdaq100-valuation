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
    for attempt in range(1):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=8) as r: raw=r.read().decode("utf-8-sig")
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
# S&P 500 constituent membership and GICS sector are fetched at each refresh.
# No off-index stock can enter the screen.
GICS={"Information Technology":"XLK","Communication Services":"XLC","Consumer Discretionary":"XLY","Industrials":"XLI","Financials":"XLF","Energy":"XLE","Health Care":"XLV","Consumer Staples":"XLP","Utilities":"XLU","Materials":"XLB","Real Estate":"XLRE"}
constituents=[]
try:
    import requests
    from bs4 import BeautifulSoup
    url="https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    response=requests.get(url,headers={"User-Agent":"Mozilla/5.0 (compatible; DonssamResearch/1.0; research@example.org)"},timeout=35)
    response.raise_for_status()
    soup=BeautifulSoup(response.text,"html.parser")
    table=soup.select_one("table#constituents")
    if table is None:raise RuntimeError("S&P 500 constituents table missing")
    for tr in table.select("tr")[1:]:
        td=tr.find_all("td")
        if len(td)<4:continue
        ticker=td[0].get_text(" ",strip=True).replace(".","-")
        name=td[1].get_text(" ",strip=True)
        sector=GICS.get(td[2].get_text(" ",strip=True))
        if sector:constituents.append({"ticker":ticker,"company":name,"sector":sector})
    if len(constituents)<450:raise RuntimeError("S&P 500 membership incomplete")
except Exception as e:
    raise RuntimeError("S&P 500 membership cannot be verified; refusing stale or invented universe") from e

def cci_weekly(frame):
    try:
        w=frame[["High","Low","Close"]].resample("W-FRI").agg({"High":"max","Low":"min","Close":"last"}).dropna()
        tp=(w["High"]+w["Low"]+w["Close"])/3
        ma=tp.rolling(20).mean()
        md=tp.rolling(20).apply(lambda x:float(abs(x-x.mean()).mean()),raw=True)
        value=(tp-ma)/(0.015*md)
        return round(float(value.iloc[-1]),1) if pd.notna(value.iloc[-1]) else None
    except Exception:return None
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
        return {"ticker":ticker,"price":round(last,2),"rsi14":round(float(rsi),1),"drawdown52":round((last/high-1)*100,1),"cci_weekly":cci,"ma200_gap":round((last/ma200-1)*100,1) if ma200 else None,"date":str(close.index[-1].date())}
    except Exception as e:
        print("Metrics",ticker,str(e));return None

def batch_prices(tickers):
    output={}
    for i in range(0,len(tickers),75):
        group=tickers[i:i+75]
        try:
            frame=yf.download(group,period="18mo",interval="1d",group_by="ticker",auto_adjust=True,threads=True,progress=False,timeout=12)
            for ticker in group:
                try:
                    item=frame[ticker] if isinstance(frame.columns,pd.MultiIndex) else frame
                    result=metrics(item,ticker)
                    if result:output[ticker]=result
                except Exception as exc:print("Ticker",ticker,str(exc))
        except Exception as exc:print("Batch",i,str(exc))
    return output

sectorprices=batch_prices(list(SECTORS))
sector=[]
for ticker,name in SECTORS.items():
    d=sectorprices.get(ticker)
    if d:
        # An oversold sector needs both meaningful drawdown and weak momentum.
        d.update(name=name,oversold=d["drawdown52"]<=-12 and (d["rsi14"]<=40 or (d["cci_weekly"] is not None and d["cci_weekly"]<=-100)))
        sector.append(d)
sector.sort(key=lambda d:(not d["oversold"],d["cci_weekly"] if d["cci_weekly"] is not None else 999,d["drawdown52"]))
eligible=[d["ticker"] for d in sector if d["oversold"]]
# Research every verified constituent so users can open any industry, even when not yet oversold.
stockprices=batch_prices([x["ticker"] for x in constituents])
stocks=[]
for item in constituents:
    d=stockprices.get(item["ticker"])
    if d:
        d.update(company=item["company"],sector=item["sector"],oversold=d["drawdown52"]<=-20 and (d["rsi14"]<=35 or (d["cci_weekly"] is not None and d["cci_weekly"]<=-100)))
        d["eligible"]=bool(d["oversold"] and d["sector"] in eligible and allpass)
        stocks.append(d)
stocks.sort(key=lambda d:(not d["eligible"],not d["oversold"],d["cci_weekly"] if d["cci_weekly"] is not None else 999,d["drawdown52"]))
result={"generated_at":datetime.now(timezone.utc).isoformat(),"macro":macro,"rules":rules,"macro_pass":allpass,"sectors":sector,"eligible_sectors":eligible,"stocks":stocks,"universe":"S&P 500 constituents from current public GICS membership","universe_count":len(constituents),"priced_count":len(stocks),"method":{"macro":"VIX≤30, HY OAS≤5%p, 10Y≤5%; 경고 필터로만 활용, 바닥 매수 신호와 구분","sector":"52주 고점 대비 -12% 이하 + (일봉 RSI14≤40 또는 주봉 CCI20≤-100)","stock":"S&P 500 구성종목 한정, 52주 고점 대비 -20% 이하 + (일봉 RSI14≤35 또는 주봉 CCI20≤-100)","eligible":"거시 3개 통과 + 산업 과매도 + 종목 과매도 모두 충족","note":"사용자의 바닥 포착 프레임 중 주봉 CCI, 낙폭, 시장 위험을 자동화. F&G 극단, NQ 고점 -20%, SOXX 절대가격, 거래량 4배, 200주선, VP/OB/ICT 트랩, 기업가치·실적 검증은 별도 확인 필요. 종목 결과는 기술적 후보군이며 매수 권유가 아님."}}
Path("donssam").mkdir(exist_ok=True)
Path("donssam/screen.json").write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding="utf-8")
print("Sectors:",len(sector),"eligible:",eligible,"stocks:",len(stocks))

