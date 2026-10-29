"""Monthly OECD CLI data, independent of stock screening."""
import json,csv,io,urllib.request
from datetime import datetime,timezone
from pathlib import Path
codes={"G20":["G20LOLITOAASTSAM"],"G7":["G7LOLITOAASTSAM"],"USA":["USALOLITOAASTSAM"],"Korea":["KORLOLITOAASTSAM"],"Euro area":["EA19LOLITOAASTSAM","EA17LOLITOAASTSAM"]}
series={}
for area,options in codes.items():
    series[area]={"code":None,"rows":[],"latest":None}
    for code in options:
        try:
            req=urllib.request.Request("https://fred.stlouisfed.org/graph/fredgraph.csv?id="+code+"&cosd=2010-01-01",headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req,timeout=12) as r:raw=r.read().decode("utf-8-sig")
            rows=[]
            for line in csv.DictReader(io.StringIO(raw)):
                try:rows.append({"date":line.get("observation_date") or line.get("DATE"),"value":round(float(line[code]),3)})
                except (ValueError,KeyError,TypeError):pass
            if len(rows)>24:
                series[area]={"code":code,"rows":rows,"latest":rows[-1]["date"]}
                break
        except Exception as exc:print(area,code,str(exc))
Path("donssam/cli.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"series":series,"note":"Euro area is not EU."},ensure_ascii=False),encoding="utf-8")
print({k:len(v["rows"]) for k,v in series.items()})
