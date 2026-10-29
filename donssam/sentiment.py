"""Daily Donssam equity and crypto sentiment, 0=fear, 100=greed."""
import json, math, time, io, csv, urllib.request
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
import yfinance as yf
import requests
OUT=Path("donssam/sentiment.json")
def bound(x):return max(0.,min(100.,float(x)))
def scale(v,lo,hi):return round(bound(100*(v-lo)/(hi-lo)),1)
def fetch(symbol):
    x=yf.Ticker(symbol).history(period="6y",interval="1d",auto_adjust=True)
    if x.empty or len(x)<260:raise ValueError("Missing "+symbol)
    return x.dropna(subset=["Close"])
def rsi(s):
    d=s.diff();u=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean();v=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    return float((100-100/(1+u/v.replace(0,float("nan")))).iloc[-1])
def cci(f):
    w=f[["High","Low","Close"]].resample("W-FRI").agg({"High":"max","Low":"min","Close":"last"}).dropna()
    tp=(w.High+w.Low+w.Close)/3;m=tp.rolling(20).mean();md=tp.rolling(20).apply(lambda x:abs(x-x.mean()).mean(),raw=True)
    return float(((tp-m)/(0.015*md)).iloc[-1])
def metrics(f):
    c=f.Close;last=float(c.iloc[-1]);wk=c.resample("W-FRI").last().dropna()
    return {"date":str(c.index[-1].date()),"price":round(last,2),"drawdown":round((last/float(c.tail(252).max())-1)*100,2),"rsi":round(rsi(c),2),"cci":round(cci(f),2),"ma200w_gap":round((last/float(wk.tail(200).mean())-1)*100,2)}
def fred(code):
    url="https://fred.stlouisfed.org/graph/fredgraph.csv?id="+code+"&cosd=2023-01-01"
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req,timeout=35) as r:body=r.read().decode("utf-8-sig")
        rows=[]
        for item in csv.DictReader(io.StringIO(body)):
            try:
                val=float(item[code]);day=item.get("observation_date") or item.get("DATE")
                if math.isfinite(val):rows.append((day,val))
            except (ValueError,KeyError,TypeError):pass
        return rows[-1] if rows else None
    except Exception as e:print("FRED",code,e);return None
def cnn():
    # CNN Fear & Greed historical endpoint is unofficial; gracefully omit if unavailable.
    try:
        r=requests.get("https://production.dataviz.cnn.io/index/fearandgreed/graphdata",headers={"User-Agent":"Mozilla/5.0","Referer":"https://edition.cnn.com/"},timeout=15)
        r.raise_for_status();obj=r.json().get("fear_and_greed",{})
        val=float(obj["score"]);return {"value":round(val,1),"date":str(obj.get("timestamp",""))[:10],"source":"CNN Fear & Greed"}
    except Exception as e:print("CNN unavailable",e);return None
def alternative():
    try:
        obj=requests.get("https://api.alternative.me/fng/?limit=1",timeout=15).json()["data"][0]
        return {"value":float(obj["value"]),"date":datetime.fromtimestamp(int(obj["timestamp"]),timezone.utc).date().isoformat(),"source":"Alternative.me Crypto Fear & Greed"}
    except Exception as e:print("Crypto F&G unavailable",e);return None
def component(label,weight,score,value,unit,observed,details):
    return {"name":label,"weight":weight,"score":round(score,1),"points":round(weight*score/100,2),"value":value,"unit":unit,"date":observed,"rule":details}
def compute():
    sp=metrics(fetch("SPY"));semi=metrics(fetch("SOXX"));btc=metrics(fetch("BTC-USD"))
    hy=fred("BAMLH0A0HYM2");vix=fred("VIXCLS");cnnfg=cnn();crypto_fg=alternative()
    liq=None
    try:
        obj=json.loads(Path("fed-liquidity/data.json").read_text(encoding="utf-8"))
        liq=[x for x in obj["rows"] if x.get("net") is not None]
        liq=liq[-1] if liq else None
        prev=next((x for x in reversed(obj["rows"]) if x.get("date","")<=str(pd.Timestamp(liq["date"])-pd.Timedelta(days=28)) and x.get("net") is not None),None) if liq else None
        liq={"date":liq["date"],"net":liq["net"],"change4w_pct":round((liq["net"]/prev["net"]-1)*100,2)} if liq and prev and prev["net"] else None
    except Exception as e:print("Liquidity unavailable",e)
    eq=[
      component("S&P 500 고점 대비 낙폭",30,scale(sp["drawdown"],-35,0),sp["drawdown"],"%",sp["date"],"-35% 이하 극단 공포 / 0% 중립 이상"),
      component("SOXX 고점 대비 낙폭",25,scale(semi["drawdown"],-45,0),semi["drawdown"],"%",semi["date"],"-45% 이하 극단 공포 / 0% 중립 이상"),
      component("S&P 500 주봉 CCI",15,scale(sp["cci"],-200,200),sp["cci"],"CCI",sp["date"],"-200 공포 / +200 탐욕"),
      component("SOXX 일봉 RSI",15,scale(semi["rsi"],20,80),semi["rsi"],"RSI",semi["date"],"20 공포 / 80 탐욕")
    ]
    if cnnfg:eq.append(component("CNN 공포·탐욕",15,cnnfg["value"],cnnfg["value"],"점",cnnfg["date"],"CNN 원지수 (참고)"))
    else:eq.append(component("CNN 공포·탐욕",15,None, None,"점",None,"자료 미확보 · 점수 계산에서 제외"))
    cr=[
      component("BTC 고점 대비 낙폭",40,scale(btc["drawdown"],-65,0),btc["drawdown"],"%",btc["date"],"-65% 이하 극단 공포 / 0% 중립 이상"),
      component("BTC 주봉 CCI",15,scale(btc["cci"],-200,200),btc["cci"],"CCI",btc["date"],"-200 공포 / +200 탐욕"),
      component("BTC 일봉 RSI",10,scale(btc["rsi"],20,80),btc["rsi"],"RSI",btc["date"],"20 공포 / 80 탐욕"),
      component("S&P 500 낙폭",10,scale(sp["drawdown"],-35,0),sp["drawdown"],"%",sp["date"],"미국 증시 위험 전이"),
    ]
    cr.append(component("신용위험 HY OAS",10,scale(hy[1],8,2),round(hy[1],2) if hy else None,"%p",hy[0] if hy else None,"8%p 이상 공포 / 2%p 이하 탐욕") if hy else component("신용위험 HY OAS",10,None,None,"%p",None,"자료 미확보"))
    cr.append(component("연준 순유동성 4주 변화",10,scale(liq["change4w_pct"],-5,5),liq["change4w_pct"] if liq else None,"%",liq["date"] if liq else None,"-5% 유동성 위축 / +5% 확대") if liq else component("연준 순유동성 4주 변화",10,None,None,"%",None,"자료 미확보"))
    cr.append(component("크립토 공포·탐욕",5,crypto_fg["value"],crypto_fg["value"],"점",crypto_fg["date"],"Alternative.me 원지수") if crypto_fg else component("크립토 공포·탐욕",5,None,None,"점",None,"자료 미확보"))
    def pack(parts):
        available=[p for p in parts if p["score"] is not None]
        used=sum(p["weight"] for p in available)
        return {"score":round(sum(p["points"] for p in available)/used*100,1) if used>=70 else None,"coverage":used,"components":parts}
    # Observation dates differ; explicitly preserve each.
    return {"date":sp["date"],"generated_at":datetime.now(timezone.utc).isoformat(),"equity":pack(eq),"crypto":pack(cr),"assets":{"SPY":sp,"SOXX":semi,"BTC":btc},"source_notes":"CNN은 공식 공개 JSON 접근 가능할 때만 사용. FRED HY OAS, 순유동성, ETF·BTC 가격의 관측일은 서로 다름.","method":"0=극단적 공포/과매도, 100=탐욕/과열. 선형 점수 기준은 연구용이며 백테스트되지 않음. 누락 항목은 제외 후 가용 가중치로 재정규화; 커버리지 70% 미만은 점수 보류."}
def main():
    today=compute()
    history=[]
    if OUT.exists():
        try:history=json.loads(OUT.read_text(encoding="utf-8")).get("history",[])
        except Exception:pass
    history=[x for x in history if x.get("date")!=today["date"]]+[today]
    history.sort(key=lambda x:x["date"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"latest":today,"history":history[-730:]},ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print("Sentiment",today["date"],today["equity"]["score"],today["crypto"]["score"])
if __name__=="__main__":main()
