"""Monthly OECD CLI via official SDMX CSV endpoint."""
import json,csv,io,urllib.request
from datetime import datetime,timezone
from pathlib import Path
codes={"G20":"G20","G7":"G7","USA":"USA","Korea":"KOR","Euro area":"EA17"}
series={k:{"code":v,"rows":[],"latest":None} for k,v in codes.items()}
url="https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.1/G20+G7+USA+KOR+EA17.M.LI...AA...H?startPeriod=2010-01&dimensionAtObservation=AllDimensions&format=csvfile"
req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"csv"})
with urllib.request.urlopen(req,timeout=55) as response:body=response.read().decode("utf-8-sig")
reader=csv.DictReader(io.StringIO(body))
for row in reader:
    area=row.get("REF_AREA") or row.get("Reference area")
    date=row.get("TIME_PERIOD") or row.get("Time period")
    val=row.get("OBS_VALUE") or row.get("Observation value")
    for name,code in codes.items():
        if area==code and date and val:
            try:series[name]["rows"].append({"date":date,"value":round(float(val),3)})
            except ValueError:pass
for v in series.values():
    v["rows"].sort(key=lambda x:x["date"])
    v["latest"]=v["rows"][-1]["date"] if v["rows"] else None
if sum(len(v["rows"])>12 for v in series.values())<4:
    raise RuntimeError("OECD CLI returned fewer than four usable country series; preserving previous data")
Path("donssam/cli.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"series":series,"source":"OECD SDMX official API","note":"Euro area EA17 differs from EU; index is amplitude adjusted"},ensure_ascii=False),encoding="utf-8")
print({k:len(v["rows"]) for k,v in series.items()})
