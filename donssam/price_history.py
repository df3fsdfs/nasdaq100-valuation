"""Public Yahoo chart OHLC fallback when the yfinance cookie endpoint fails."""
import json
import urllib.request
from urllib.parse import quote
import pandas as pd

def chart_history(symbol):
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe='')+'?range=2y&interval=1d'
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=16) as r:obj=json.load(r)['chart']['result'][0]
    q=obj['indicators']['quote'][0]
    index=pd.to_datetime(obj['timestamp'],unit='s',utc=True).tz_convert(obj['meta'].get('exchangeTimezoneName','America/New_York'))
    f=pd.DataFrame({k.title():q[k] for k in ['high','low','close','volume']},index=index)
    adj=obj['indicators'].get('adjclose',[{}])[0].get('adjclose')
    if adj:
        ratio=pd.Series(adj,index=index)/f.Close
        for k in ['High','Low','Close']:f[k]=f[k]*ratio
    return f.dropna(subset=['Close'])
