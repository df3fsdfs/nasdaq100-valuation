# This file is subject to the Mozilla Public License 2.0.
# https://mozilla.org/MPL/2.0/  Original Pine buy logic: © moodcomp.
# Python adaptation of the user-supplied buySignal only. Sell/plot code is not used.
import numpy as np
import pandas as pd

def rma(source, length):
    """Wilder average, SMA seeded, ignoring missing source observations."""
    values=[]; previous=None; output=[]
    for value in source:
        if pd.isna(value):
            output.append(previous if previous is not None else np.nan); continue
        if previous is None:
            values.append(float(value))
            if len(values)==length: previous=sum(values)/length
        else: previous=(previous*(length-1)+float(value))/length
        output.append(previous if previous is not None else np.nan)
    return pd.Series(output,index=source.index,dtype=float)

def rsi(source,length):
    delta=source.diff()
    up=rma(delta.clip(lower=0),length)
    down=rma(-delta.clip(upper=0),length)
    result=100-100/(1+up/down)
    result=result.mask((down==0)&(up>0),100).mask((up==0)&(down>0),0)
    # Both zero: Pine's 0/0 remains na rather than inventing a neutral RSI.
    return result

def evaluate(f,tf):
    close,high,low=f.Close,f.High,f.Low
    lookback,rsi_limit={'D':(65,22),'W':(45,27),'M':(26,32)}[tf]
    rs={n:rsi(close,n) for n in (14,30,100,200)}
    s,m,l,x=(rs[n] for n in (14,30,100,200))
    tr=pd.concat([high-low,(high-close.shift()).abs(),(low-close.shift()).abs()],axis=1).max(axis=1)
    atr=rma(tr,14)
    ma={n:close.rolling(n,min_periods=n).mean() for n in (20,60,120,200)}
    dev={n:((close-ma[n])/atr).mask(atr<=0,0) for n in ma}
    d20,d60,d120,d200=(dev[n] for n in (20,60,120,200))
    highest=s.rolling(lookback,min_periods=1).max()
    lowest=s.rolling(lookback,min_periods=1).min()
    span=highest-lowest
    pos=((s-lowest)/span*100).where(span>0,50.)
    mature_long=(l.rolling(250,min_periods=1).max()>=60)&(x.rolling(350,min_periods=1).max()>=58)
    ch=high.rolling(300,min_periods=1).max();cl=low.rolling(300,min_periods=1).min()
    cp=((close-cl)/(ch-cl)*100).where(ch>cl,50.)
    mature=mature_long&(cp.rolling(150,min_periods=1).max()>=75)
    sharp=(d20<=-2.20)&(((s.shift(5)-s)>=11.5)|((s.shift(10)-s)>=17))&(pos<=22)&((d60<=-1.65)|(s<33))
    normal=(d60<=-1.15)&(d120<=-.95)&((s<=42)|(m<=46))&(m<m.shift(10))&((close<ma[60])|(close<ma[120]))&(mature|(d60<=-2.))
    cooling=(d20<d20.shift(10))&((d60<d60.shift(10))|(d120<d120.shift(10)))
    turning=(d20>d20.shift())|(d60>d60.shift())|(d120>d120.shift())
    time=mature&(d120<=-.80)&(d200<=-.60)&cooling&turning&(l<=48)&(x<=54)&((l<l.shift(10))|(x<x.shift(10)))&(s<=48)&(s>s.shift())
    mid_double=(m.rolling(18,min_periods=1).min()<=47)&(m.shift(5).rolling(12,min_periods=1).min()<=48)&(m.shift(5).rolling(10,min_periods=1).max()>=53)
    mid_turn=(m>m.shift())&(m>m.shift(3))
    mid_structure=mid_double|((m.rolling(25,min_periods=1).min()<=47)&mid_turn)
    restricted=mid_structure&(s.shift(2)>s.shift(5))&(s<=s.shift(2))&(s>=43)&((s.shift(2)-s)<=7)&(s>s.shift())&(s>54)&(d20<=.35)&(d20>d20.shift())&(close>ma[20])&(close>close.shift(3))&(mature|normal|time)
    out=pd.DataFrame({'sharp':sharp,'normal':normal,'time':time,'restricted':restricted,'buy':sharp|normal|time|restricted,'rsi_position':pos,'rsi_extreme':pos<=rsi_limit,'atr14':atr,'mature_cycle':mature})
    for n,series in rs.items():out['rsi'+str(n)]=series
    for n,series in dev.items():out['dev'+str(n)]=series
    # Diagnostic thresholds below are not extra gates on buySignal.
    out['sharp_rsi_drop']=((s.shift(5)-s)>=11.5)|((s.shift(10)-s)>=17)
    out['sharp_rsi_low']=pos<=22
    out['normal_rsi_low']=(s<=42)|(m<=46)
    out['normal_rsi_cooling']=m<m.shift(10)
    out['long_rsi_cooling']=(l<=48)&(x<=54)
    out['short_rsi_turning']=(s<=48)&(s>s.shift())
    out.attrs['rsi_limit']=rsi_limit
    return out
