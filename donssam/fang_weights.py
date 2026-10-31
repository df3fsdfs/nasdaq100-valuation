"""Published FANG+ index exposures (not invented ETN fund holdings)."""
import re,urllib.request
from datetime import datetime
from bs4 import BeautifulSoup

OFFICIAL='https://microsectors.com/fang/'
NAMES={'PALANTIR':'PLTR','MICROSOFT':'MSFT','MICRON':'MU','BROADCOM':'AVGO','AMAZON':'AMZN','APPLE':'AAPL','NVIDIA':'NVDA','ALPHABET':'GOOGL','META PLATFORMS':'META','NETFLIX':'NFLX'}
def parse_official(body):
    soup=BeautifulSoup(body,'html.parser');rows=[]
    for li in soup.find_all('li'):
        text=li.get_text(' ',strip=True)
        m=re.fullmatch(r'(\d+(?:\.\d+)?)%\s+(.+)',text)
        if not m:continue
        name=m[2].upper();matches=[ticker for needle,ticker in NAMES.items() if needle in name]
        if len(matches)!=1:raise ValueError('Unmapped official constituent: '+name)
        rows.append({'ticker':matches[0],'weight_pct':float(m[1]),'name':m[2]})
    text=soup.get_text(' ',strip=True)
    date=re.search(r'Components as of SOD\s+(\d{2}/\d{2}/\d{4})',text)
    if not date or len(rows)!=10 or len({x['ticker'] for x in rows})!=10:raise ValueError('Incomplete dated FANG+ composition')
    if abs(sum(x['weight_pct'] for x in rows)-100)>.3:raise ValueError('Invalid index weight total')
    observed=datetime.strptime(date[1],'%m/%d/%Y').date().isoformat()
    return [{**x,'weight_date':observed,'weight_kind':'index_exposure'} for x in rows if x['weight_pct']>=5],OFFICIAL+' · FANG+ 지수 노출비중 · SOD '+observed,'available'

def fetch_weights():
    with urllib.request.urlopen(urllib.request.Request(OFFICIAL,headers={'User-Agent':'Mozilla/5.0'}),timeout=18) as r:return parse_official(r.read().decode('utf-8'))
