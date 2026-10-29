import csv, io, json, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

BASE="https://fred.stlouisfed.org/graph/fredgraph.csv?id="
SERIES={"WALCL":1.0,"WTREGEN":1.0,"RRPONTSYD":1000.0,"WRESBAL":1.0} # all in millions USD
def load(code):
    req=urllib.request.Request(BASE+code,headers={"User-Agent":"donssam-liquidity/1.0"})
    with urllib.request.urlopen(req,timeout=40) as r: data=r.read().decode("utf-8-sig")
    out={}
    for row in csv.DictReader(io.StringIO(data)):
        try:
            day=row.get("observation_date") or row.get("DATE")
            val=float(row[code])
            datetime.strptime(day,"%Y-%m-%d")
            out[day]=val*SERIES[code]
        except (ValueError,TypeError,KeyError): continue
    if not out: raise RuntimeError("No observations for "+code)
    return out
raw={k:load(k) for k in SERIES}
# Weekly Wednesday alignment: take latest observed value no later than each Wednesday,
# max 7 days old. Do not extrapolate a stale series.
from datetime import timedelta
dates=sorted(raw["WALCL"])
rows=[]
for d in dates:
    dt=datetime.strptime(d,"%Y-%m-%d").date()
    if dt.weekday()!=2: continue
    vals={}
    for code,series in raw.items():
        candidates=[(datetime.strptime(k,"%Y-%m-%d").date(),v) for k,v in series.items() if dt-timedelta(days=7)<datetime.strptime(k,"%Y-%m-%d").date()<=dt]
        if not candidates: break
        vals[code]=max(candidates)[1]
    if len(vals)!=4: continue
    pool=(vals["WTREGEN"]+vals["RRPONTSYD"])/2
    rows.append({"date":d,**{k:round(v/1e6,5) for k,v in vals.items()},"net":round((vals["WALCL"]-vals["WTREGEN"]-vals["RRPONTSYD"])/1e6,5),"pool":round(pool/1e6,5)})
for i,row in enumerate(rows):
    if i>=51:
        ma=sum(r["pool"] for r in rows[i-51:i+1])/52
        row["ma52"]=round(ma,5)
        row["deviation"]=round((row["pool"]/ma-1)*100,3) if ma else None
    else:
        row["ma52"]=None
        row["deviation"]=None
out={"generated_at":datetime.now(timezone.utc).isoformat(),"unit":"USD trillion","latest_observations":{k:max(v) for k,v in raw.items()},"rows":rows}
Path("fed-liquidity").mkdir(exist_ok=True)
Path("fed-liquidity/data.json").write_text(json.dumps(out,ensure_ascii=False,separators=(",",":")),encoding="utf-8")
print("Wrote",len(rows),"rows")
