"""Daily market-screen snapshot. Missing observations are never filled with invented values."""
import json, math, time, urllib.request, csv, io
from datetime import datetime, timezone
from pathlib import Path
import yfinance as yf
import requests
import pandas as pd
from sector_scoring import metrics, cci_weekly, clamp, score_sector, score_individual

SECTORS={"XLK":"기술","SOXX":"반도체","XLC":"통신서비스","XLY":"경기소비재","XLI":"산업재","XLF":"금융","XLE":"에너지","XLV":"헬스케어","XLP":"필수소비재","XLU":"유틸리티","XLB":"소재","XLRE":"부동산","FNGS":"M7"}
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
    # DBnomics mirrors FRED observations when fred.stlouisfed.org blocks CI.
    try:
        url="https://api.db.nomics.world/v22/series/FRED/"+code
        obj=requests.get(url,timeout=12).json()
        docs=obj.get("series",{}).get("docs",[])
        if docs:
            vals=[]
            for d,v in zip(docs[0].get("period",[]),docs[0].get("value",[])):
                try:
                    value=float(v)
                    if math.isfinite(value):vals.append((d,value))
                except (ValueError,TypeError):pass
            if vals:return vals[-1]
    except Exception as e:print("DBnomics",code,repr(e))
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
        ret6=(last/float(close.iloc[-126])-1)*100 if len(close)>126 else None
        ret12=(last/float(close.iloc[-252])-1)*100 if len(close)>252 else None
        return {"return6m":round(ret6,2) if ret6 is not None else None,"return12m":round(ret12,2) if ret12 is not None else None,"ticker":ticker,"price":round(last,2),"rsi14":round(float(rsi),1),"drawdown52":round((last/peak-1)*100,1),"date":str(close.index[-1].date())}
    except Exception as e:
        print("Price",ticker,repr(e));return None
# Keep last verified observation on temporary provider outage, with its ORIGINAL date.
try:
    previous=json.loads(Path("donssam/screen.json").read_text(encoding="utf-8"))
except (OSError,ValueError):
    previous={}
macro={}
for code,name in FRED.items():
    item=fred(code)
    macro[code]={"name":name,"date":item[0],"value":item[1],"source":"FRED/DBnomics"} if item else previous.get("macro",{}).get(code)
# Thresholds are transparent screening rules, not validated forecasts.
vix=macro.get("VIXCLS");oas=macro.get("BAMLH0A0HYM2");rate=macro.get("DGS10")
rules=[
 {"label":"변동성 과열 여부 (VIX ≤ 30)","status":("pass" if vix["value"]<=30 else "fail") if vix else "unknown","value":vix},
 {"label":"신용위험 확산 여부 (HY OAS ≤ 5%p)","status":("pass" if oas["value"]<=5 else "fail") if oas else "unknown","value":oas},
 {"label":"장기금리 압박 여부 (10Y ≤ 5%)","status":("pass" if rate["value"]<=5 else "fail") if rate else "unknown","value":rate}
]
allpass=all(r["status"]=="pass" for r in rules)

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
    missing=[t for t in tickers if t not in output]
    if missing:
        from concurrent.futures import ThreadPoolExecutor
        from price_history import chart_history
        def fallback(t):
            try:return t,metrics(chart_history(t),t)
            except Exception as exc:print('Chart fallback',t,type(exc).__name__);return t,None
        with ThreadPoolExecutor(max_workers=4) as pool:
            for t,value in pool.map(fallback,missing):
                if value:output[t]=value
    return output

sectorprices=batch_prices(list(SECTORS)+["SPY"])
spy=sectorprices.get("SPY")
sector=[]
for ticker,name in SECTORS.items():
    d=sectorprices.get(ticker)
    if not d:continue
    d=score_sector(d,spy,name)
    sector.append(d)
sector.sort(key=lambda d:(d["opportunity_score"] is None,-(d["opportunity_score"] or 0)))
eligible=[d["ticker"] for d in sector if d.get("qualified") is True]
# Drill-down for every tracked sector ETF (11 GICS sectors plus semiconductors).
# ETF weights must come from fund holdings, not from an assumed ticker basket.
def holdings_above_five(etf):
    if etf=='FNGS':
        from fang_weights import fetch_weights
        try:return fetch_weights()
        except Exception as exc:
            print('FANG+ weights',type(exc).__name__)
            return [],'https://microsectors.com/fang/','holdings_unavailable'

    # First use reported holdings; SOXX falls back to BlackRock/iShares CSV.
    try:
        raw=yf.Ticker(etf).funds_data.top_holdings
        if raw is not None and not raw.empty:
            rows=[]
            for symbol,row in raw.iterrows():
                weight=row.get("Holding Percent")
                if weight is None or pd.isna(weight):continue
                weight=float(weight)
                if weight>1:weight/=100
                symbol=str(symbol).strip().upper().replace(".","-")
                if weight>=0.05 and symbol not in ("CASH","USD","") and symbol.isascii():
                    rows.append({"ticker":symbol,"weight_pct":round(weight*100,2)})
            return sorted(rows,key=lambda z:-z["weight_pct"]),"Yahoo Finance fund holdings","available"
    except Exception as exc:print("Yahoo ETF holdings",etf,repr(exc))
    if etf=="SOXX":
        try:
            url="https://www.ishares.com/us/products/239705/ishares-phlx-semiconductor-etf/1467271812596.ajax?fileType=csv&fileName=SOXX_holdings&dataType=fund"
            response=requests.get(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/csv,*/*"},timeout=16)
            response.raise_for_status()
            raw=response.content.decode("utf-8-sig",errors="replace")
            lines=list(csv.reader(io.StringIO(raw)))
            idx=next(i for i,r in enumerate(lines) if len(r)>5 and "Ticker" in r and "Weight (%)" in r)
            head=lines[idx]
            ti=head.index("Ticker");wi=head.index("Weight (%)")
            rows=[]
            for r in lines[idx+1:]:
                if len(r)<=max(ti,wi):continue
                symbol=r[ti].strip().upper().replace(".","-")
                try:weight=float(r[wi].replace(",",""))
                except (ValueError,TypeError):continue
                if weight>=5 and symbol and symbol!="-" and symbol.isascii():
                    rows.append({"ticker":symbol,"weight_pct":round(weight,2)})
            return sorted(rows,key=lambda z:-z["weight_pct"]),"BlackRock iShares official SOXX holdings CSV","available"
        except Exception as exc:print("iShares SOXX holdings",repr(exc))
    return [],"No confirmed source","holdings_unavailable"

top_three=sector
holdings_data={z["ticker"]:holdings_above_five(z["ticker"]) for z in top_three}
holdings={etf:result[0] for etf,result in holdings_data.items()}
names=list(dict.fromkeys(h["ticker"] for arr in holdings.values() for h in arr))
stock_prices=batch_prices(names) if names else {}
def individual_score(v):
    return score_individual(v,spy)
top_holdings=[]
for z in top_three:
    etf=z["ticker"]
    rows=[]
    for h in holdings[etf]:
        v=stock_prices.get(h["ticker"])
        if v:
            rows.append({**h,**v,"opportunity":individual_score(v)})
        else:
            rows.append({**h,"price":None,"high52":None,"drawdown52":None,"ma200":None,"rsi14":None,"cci_weekly":None,"opportunity":None})
    top_holdings.append({"etf":etf,"rank":sector.index(z)+1,"holdings":rows,"holdings_source":holdings_data[etf][1],"status":holdings_data[etf][2]})
# Major indices: actual daily closes, normalized to 100 for comparison.
market_indices={}
for symbol,name in [("^GSPC","SPX"),("^NDX","NAS100"),("SOXX","SOXX"),("IWM","Russell 2000"),("BTC-USD","Bitcoin")]:
    try:
        df=yf.Ticker(symbol).history(period="1y",auto_adjust=True)
        close=df["Close"].dropna()
        if len(close)>10:
            market_indices["SPX" if symbol=="^GSPC" else "NAS100" if symbol=="^NDX" else symbol]={"name":name,"rows":[{"date":str(dt.date()),"close":round(float(val),4)} for dt,val in close.items()]}
    except Exception as e:print("Market index",symbol,repr(e))
# Retain last confirmed data when a temporary market-data outage occurs.
for symbol,old in previous.get("market_indices",{}).items():
    if symbol in ("SPY","^GSPC","QQQ"):continue
    if symbol not in market_indices and old.get("rows"):
        market_indices[symbol]=old
for row in top_holdings:
    if row["status"]!="available":
        old=next((z for z in previous.get("top_etf_holdings",[]) if z.get("etf")==row["etf"] and z.get("status") in ("available","stale") and z.get("holdings")),None)
        if old:
            row.update(holdings=[{**h,"opportunity":individual_score(h)} if h.get("return6m") is not None else {**h,"opportunity":None} for h in old["holdings"]],holdings_source=old.get("holdings_source","previous snapshot")+" (이전 수집)",status="stale")
stocks=[]
result={"generated_at":datetime.now(timezone.utc).isoformat(),"macro":macro,"rules":rules,"macro_pass":allpass,"sectors":sector,"eligible_sectors":eligible,"stocks":[],"top_etf_holdings":top_holdings,"market_indices":market_indices,"method":{"sector":"기회점수 100점: 과매도 40, S&P500 대비 6·12개월 상대강도 35, 200일선·주봉CCI 추세 25. 이익률/실적성장은 미포함이므로 수익성 순위로 해석 금지.","note":"전체 산업 ETF에서 공시 보유비중 5% 이상 종목만 개별 점수 산출. 보유비중을 확인하지 못하면 종목을 추정하지 않음. 산업·개별종목 공통: 상대강도35·과매도40·추세25. 통과=점수70초과 AND RSI14≤20 AND 주봉CCI≤-100. 개별 점수 100=기회 높음, 0=기회 낮음."}}
Path("donssam").mkdir(exist_ok=True)
Path("donssam/screen.json").write_text(json.dumps(result,ensure_ascii=False,allow_nan=False),encoding="utf-8")
print("Sectors:",len(sector),"eligible:",eligible)


