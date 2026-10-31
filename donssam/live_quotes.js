(() => {
  const el=(tag,text)=>{const x=document.createElement(tag);if(text!=null)x.textContent=String(text);return x;};
  const fmt=x=>typeof x==='number'?x.toLocaleString('ko-KR',{maximumFractionDigits:2,minimumFractionDigits:2}):'—';
  const label={crypto:'24시간 현물',futures:'선물',index:'현물 지수',postmarket:'시간외',premarket:'프리마켓',regular:'정규장'};
  let quotes={};
  const time=x=>new Date(x).toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'});
  const text=q=>(label[q.session]||'최근값')+' · '+time(q.quote_at)+' KST'+(q.cached?' · 이전 확인값':'');
  function priceCell(td,q){if(!td||!q)return;td.replaceChildren(el('strong',fmt(q.price)));const small=el('small',text(q));small.style.display='block';small.style.fontSize='10px';td.append(small);}
  window.refreshLiveStockCells=ticker=>{
    const data=(window.etfHoldings||[]).find(x=>x.etf===ticker);if(!data)return;
    const trs=document.querySelectorAll('#etfrows tr');
    (data.holdings||[]).forEach((x,i)=>{if(trs[i]?.cells.length>3)priceCell(trs[i].cells[3],quotes[x.ticker]);});
  };
  window.refreshLiveQuotes=()=>{
    if(!Object.keys(quotes).length)return;
    const box=document.getElementById('indexstats');box.replaceChildren();
    for(const [symbol,name] of [['^GSPC','SPX 현물'],['ES=F','S&P500 선물'],['^NDX','NAS100 현물'],['NQ=F','나스닥100 선물'],['SOXX','SOXX'],['IWM','Russell 2000 ETF'],['BTC-USD','Bitcoin']]){
      const q=quotes[symbol];if(!q)continue;const row=el('div');row.className='kpi';const left=el('span',name);const stamp=el('small',text(q));stamp.style.display='block';left.append(stamp);
      const value=el('strong',fmt(q.price));value.style.textAlign='right';const pct=el('small',typeof q.change_pct==='number'?(q.change_pct>0?'+':'')+fmt(q.change_pct)+'%':'비교 기준 수집 대기');pct.style.display='block';pct.title=['postmarket','premarket'].includes(q.session)?'정규장 가격 대비':'제공처 이전 종가 대비';value.append(pct);row.append(left,value);box.append(row);
    }
    for(const row of document.querySelectorAll('#sectorrows tr')){
      const ticker=row.querySelector('button')?.textContent.match(/\(([A-Z]+)\)\s*▾/)?.[1];
      if(ticker&&row.cells.length>8)priceCell(row.cells[8],quotes[ticker]);
    }
    if(window.selectedETF)window.refreshLiveStockCells(window.selectedETF);
  };
  async function refresh(){
    try{const r=await fetch('./quotes.json?v='+Date.now(),{cache:'no-store'});if(!r.ok)return;const d=await r.json();quotes=d.quotes||{};window.refreshLiveQuotes();}
    catch(_){} // Existing dated daily observations stay visible when the quote file is unavailable.
  }
  refresh();setInterval(refresh,5*60*1000);
})();
