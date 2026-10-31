"""One dated observation per ticker; ETF rows contain exposure metadata only."""
import copy
from sector_scoring import score_individual
MEMBERSHIP_FIELDS=('ticker','weight_pct','weight_date','weight_kind','name')

def membership(row):
    return {k:row[k] for k in MEMBERSHIP_FIELDS if k in row}

def previous_observations(previous):
    output=copy.deepcopy(previous.get('stock_observations',{}))
    for group in previous.get('top_etf_holdings',[]):
        for row in group.get('holdings',[]):
            ticker=row['ticker']
            if row.get('date') and (ticker not in output or row['date']>output[ticker].get('date','')):
                output[ticker]={k:copy.deepcopy(v) for k,v in row.items() if k not in MEMBERSHIP_FIELDS or k=='ticker'}
    return output

def build_registry(groups,observations,benchmark,previous=None):
    old=previous_observations(previous or {});registry={};result=[]
    for group in groups:
        row={**group,'holdings':[membership(h) for h in group.get('holdings',[])]};result.append(row)
        for h in row['holdings']:
            t=h['ticker']
            if t in registry:continue
            fresh=observations.get(t);v=copy.deepcopy(fresh or old.get(t))
            if not v:
                registry[t]={'ticker':t,'opportunity':None,'observation_status':'unavailable'};continue
            v['ticker']=t;v['observation_status']='fresh' if fresh else 'cached'
            v['opportunity']=score_individual(v,benchmark)
            registry[t]=v
    return result,registry
