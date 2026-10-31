"""Monthly OECD CLI via official SDMX CSV endpoint."""
import json,csv,io,urllib.request
from datetime import datetime,timezone
from pathlib import Path
codes={"G7":"G7","USA":"USA"}
series={k:{"code":v,"rows":[],"latest":None} for k,v in codes.items()}
for name,code in codes.items():
    url="https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/"+code+".M.LI...AA...H?startPeriod=2018-01&dimensionAtObservation=AllDimensions&format=csvfile"
    try:
        req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"text/csv"})
        with urllib.request.urlopen(req,timeout=22) as response:body=response.read().decode("utf-8-sig")
        for row in csv.DictReader(io.StringIO(body)):
            date=row.get("TIME_PERIOD")
            val=row.get("OBS_VALUE")
            if date and val:
                try:series[name]["rows"].append({"date":date,"value":round(float(val),6)})
                except ValueError:pass
    except Exception as exc:print("CLI",name,repr(exc))
try: previous=json.loads(Path('donssam/cli.json').read_text()).get('series',{})
except (OSError,ValueError):previous={}
for k,v in series.items():
    if not v['rows'] and previous.get(k,{}).get('rows'):series[k]=previous[k]
for v in series.values():
    v["rows"].sort(key=lambda x:x["date"])
    v["latest"]=v["rows"][-1]["date"] if v["rows"] else None
if sum(len(v["rows"])>12 for v in series.values())<1:
    raise RuntimeError("OECD CLI returned no usable country series; preserving previous data")
Path("donssam/cli.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"series":series,"source":"OECD SDMX official API","note":"Euro area EA17 differs from EU; index is amplitude adjusted"},ensure_ascii=False),encoding="utf-8")
print({k:len(v["rows"]) for k,v in series.items()})

