"""Daily Donssam equity bottom opportunity and crypto sentiment."""
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
def monthly_cci(f):
    m=f[["High","Low","Close"]].resample("ME").agg({"High":"max","Low":"min","Close":"last"}).dropna()
    tp=(m.High+m.Low+m.Close)/3
    avg=tp.rolling(20).mean()
    dev=tp.rolling(20).apply(lambda x:abs(x-x.mean()).mean(),raw=True)
    return float(((tp-avg)/(0.015*dev)).iloc[-1])
def bottom_pattern(f):
    c=f.Close.dropna();a=c.tail(90)
    fast=(float(c.iloc[-1])/float(c.iloc[-21])-1)*100
    dd=(float(c.iloc[-1])/float(c.tail(252).max())-1)*100
    local=[]
    for i in range(3,len(a)-3):
        if float(a.iloc[i])==float(a.iloc[i-3:i+4].min()):local.append((i,float(a.iloc[i])))
    near=[(i,v) for i,v in local if v<=float(a.min())*1.05]
    separated=[]
    for i,v in near:
        if not separated or i-separated[-1][0]>=8:separated.append((i,v))
    count=len(separated)
    knife=fast<=-15 and dd<=-15
    multi=count>=2 and dd<=-12 and float(c.iloc[-1])<=float(a.min())*1.12
    return {"pattern":"송곳형 급락" if knife else ("삼중바닥 후보" if count>=3 and multi else ("쌍바닥 후보" if multi else "미확인")),"fast20_pct":round(fast,2),"lows":count,"qualified":knife or multi}
def metrics(f):
    c=f.Close;last=float(c.iloc[-1]);wk=c.resample("W-FRI").last().dropna()
    return {"date":str(c.index[-1].date()),"price":round(last,2),"drawdown":round((last/float(c.tail(252).max())-1)*100,2),"rsi":round(rsi(c),2),"cci":round(cci(f),2),"ma200w_gap":round((last/float(wk.tail(200).mean())-1)*100,2),"monthly_cci":round(monthly_cci(f),2),"pattern":bottom_pattern(f)}
def fred(code,asof=None):
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
        return next((x for x in reversed(rows) if asof is None or x[0]<=asof),None)
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
    return {"name":label,"weight":weight,"score":round(score,1) if score is not None else None,"points":round(weight*score/100,2) if score is not None else None,"value":value,"unit":unit,"date":observed,"rule":details}
def compute(asof=None):
    def historical(t):
        x=fetch(t)
        return x.loc[x.index.date<=pd.Timestamp(asof).date()] if asof else x
    sp=metrics(historical("SPY"));semi=metrics(historical("SOXX"));btc=metrics(historical("BTC-USD"))
    effective=sp['date']
    hy=fred("BAMLH0A0HYM2",effective);vix=fred("VIXCLS",effective)
    cnnfg=cnn() if asof is None else None
    crypto_fg=alternative() if asof is None else None
    liq=None
    try:
        obj=json.loads(Path("fed-liquidity/data.json").read_text(encoding="utf-8"))
        liq=[x for x in obj["rows"] if x.get("net") is not None and (asof is None or x.get("date","")<=effective)]
        liq=liq[-1] if liq else None
        prev=next((x for x in reversed(obj["rows"]) if x.get("date","")<=str(pd.Timestamp(liq["date"])-pd.Timedelta(days=28)) and x.get("net") is not None),None) if liq else None
        liq={"date":liq["date"],"net":liq["net"],"change4w_pct":round((liq["net"]/prev["net"]-1)*100,2)} if liq and prev and prev["net"] else None
    except Exception as e:print("Liquidity unavailable",e)
    def opportunity(asset,label,weight):
        obs=asset["date"];p=asset["pattern"];dd=asset["drawdown"]
        # Deep drawdown, weekly/daily oversold, monthly CCI, 200-week MA and a bottom pattern.
        raw=[
          (label+" 낙폭·속도",25,0.65*scale(-dd,0,40)+0.35*scale(-p["fast20_pct"],0,22),str(dd)+"% / 20일 "+str(p["fast20_pct"])+"%"),
          (label+" 주봉·일봉 과매도",20,0.6*scale(-asset["cci"],0,200)+0.4*scale(50-asset["rsi"],0,35),str(asset["cci"])+" / "+str(asset["rsi"])),
          (label+" 월봉 CCI",10,scale(-asset["monthly_cci"],0,180),asset["monthly_cci"]),
          (label+" 200주선 접근",15,scale(25-abs(asset["ma200w_gap"]),0,25),asset["ma200w_gap"]),
          (label+" 바닥형태",20,90 if p["qualified"] else 0,p["pattern"])
        ]
        return [component(n,round(w*weight,3),v,value,"",obs,"높을수록 바닥매수 기회") for n,w,v,value in raw]
    eq=opportunity(sp,"S&P 500",0.5)+opportunity(semi,"SOXX",0.5)
    # Macro stress is useful only as corroboration; missing credit data is not fabricated.
    eq.append(component("HY OAS 신용 스트레스",6,scale(hy[1],2,8),round(hy[1],2),"%p",hy[0],"높은 신용스프레드 = 높은 공포") if hy else component("HY OAS 신용 스트레스",6,None,None,"%p",None,"자료 없음"))
    eq.append(component("CNN 공포·탐욕 역점수",4,100-cnnfg["value"],cnnfg["value"],"점",cnnfg["date"],"CNN 0이면 기회점수 100") if cnnfg else component("CNN 공포·탐욕 역점수",4,None,None,"점",None,"CNN API 차단 시 제외"))
    cr=[
      component("BTC 자체 낙폭",40,scale(-btc["drawdown"],0,65),btc["drawdown"],"%",btc["date"],"낙폭 클수록 바닥 기회 근접"),
      component("BTC 주봉·일봉 과매도",15,0.6*scale(-btc["cci"],0,200)+0.4*scale(50-btc["rsi"],0,35),str(btc["cci"])+" / "+str(btc["rsi"]),"",btc["date"],"주봉 CCI·일봉 RSI"),
      component("BTC 월봉 CCI·200주선",15,0.5*scale(-btc["monthly_cci"],0,180)+0.5*scale(25-abs(btc["ma200w_gap"]),0,25),str(btc["monthly_cci"])+" / "+str(btc["ma200w_gap"]),"",btc["date"],"월봉 CCI·200주선 괴리"),
      component("BTC 급락·바닥형태",10,90 if btc["pattern"]["qualified"] else 0,btc["pattern"]["pattern"],"",btc["date"],"송곳형 급락·쌍/삼중바닥 후보"),
      component("S&P 500 낙폭",5,scale(-sp["drawdown"],0,35),sp["drawdown"],"%",sp["date"],"미국 증시 위험 전이"),
    ]
    cr.append(component("신용위험 HY OAS",5,scale(hy[1],2,8),round(hy[1],2),"%p",hy[0],"신용 스트레스 증가") if hy else component("신용위험 HY OAS",5,None,None,"%p",None,"자료 없음"))
    cr.append(component("연준 순유동성 4주 변화",5,scale(-liq["change4w_pct"],-5,5),liq["change4w_pct"],"%",liq["date"],"유동성 위축 시 위험·기회 증가") if liq else component("연준 순유동성 4주 변화",5,None,None,"%",None,"자료 없음"))
    cr.append(component("크립토 공포·탐욕 역점수",5,100-crypto_fg["value"],crypto_fg["value"],"점",crypto_fg["date"],"공포 심할수록 바닥 기회 근접") if crypto_fg else component("크립토 공포·탐욕 역점수",5,None,None,"점",None,"자료 없음"))
    def pack(parts):
        available=[p for p in parts if p["score"] is not None]
        used=sum(p["weight"] for p in available)
        return {"score":round(100-sum(p["points"] for p in available)/used*100,1) if used>=65 else None,"coverage":round(used,1),"components":parts}
    equity=pack(eq)
    # Without a sharp selloff or repeated lows, do not label gradual weakness as an extreme bottom opportunity.
    if not sp["pattern"]["qualified"] and not semi["pattern"]["qualified"] and equity["score"] is not None:
        equity["score"]=max(equity["score"],45)
    crypto=pack(cr)
    if not btc["pattern"]["qualified"] and crypto["score"] is not None:
        crypto["score"]=max(crypto["score"],40)
    # Observation dates differ; explicitly preserve each.
    return {"date":sp["date"],"generated_at":datetime.now(timezone.utc).isoformat(),"equity":equity,"crypto":crypto,"assets":{"SPY":sp,"SOXX":semi,"BTC":btc},"source_notes":"CNN은 공식 공개 JSON 접근 가능할 때만 사용. FRED HY OAS, 순유동성, ETF·BTC 가격의 관측일은 서로 다름.","score_direction":"zero_is_opportunity","method":"증시·크립토 모두 0=바닥매수 기회 가까움, 100=기회 멀다. 선형 점수 기준은 연구용이며 백테스트되지 않음. 누락 항목은 제외 후 가용 가중치로 재정규화; 커버리지 70% 미만은 점수 보류."}
def main():
    today=compute()
    history=[]
    if OUT.exists():
        try:history=json.loads(OUT.read_text(encoding="utf-8")).get("history",[])
        except Exception:pass
    # Seed two real historical market sessions; historical CNN/crypto F&G are unavailable and omitted.
    existing={x.get("date"):x for x in history if x.get("score_direction")=="zero_is_opportunity"}
    sessions=fetch("SPY").index[-3:].date
    for day in sessions:
        key=day.isoformat()
        if key not in existing and key!=today["date"]:
            try:existing[key]=compute(key)
            except Exception as exc:print("Historical snapshot unavailable",key,exc)
    existing[today["date"]]=today
    history=list(existing.values())
    history.sort(key=lambda x:x["date"])
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps({"latest":today,"history":history[-730:]},ensure_ascii=False,allow_nan=False),encoding="utf-8")
    print("Sentiment",today["date"],today["equity"]["score"],today["crypto"]["score"])
if __name__=="__main__":main()
