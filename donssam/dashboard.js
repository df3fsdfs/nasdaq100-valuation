(() => {
  const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!=null)x.textContent=String(text);if(cls)x.className=cls;return x;};
  const fmt=(x,d=2)=>typeof x==='number'&&Number.isFinite(x)?x.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const signed=(x,d=2)=>typeof x==='number'?(x>0?'+':'')+fmt(x,d):'—';
  const load=async url=>{const r=await fetch(url+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error(r.status);return r.json();};
  const change=(x,goodUp,scale=1,unit='')=>{
    const known=typeof x==='number';const positive=known&&x>0;
    const good=known&&x!==0&&(goodUp?positive:!positive);
    return el('span',(known?(x>0?'↑ ':x<0?'↓ ':'→ '):'')+signed(known?x*scale:null)+unit,known&&x!==0?(good?'rise-good':'rise-bad'):'neutral-change');
  };
  const crossLabel=(code,kind)=>code==='negative_to_positive'?(kind==='a'?'가속도 음→양 전환':'가속도 변화 음→양 전환'):code==='positive_to_negative'?(kind==='a'?'가속도 양→음 전환':'가속도 변화 양→음 전환'):code==='at_zero'?'현재 0 · 다음 관측 확인':'0선 부호 전환 없음';
  load('./insights.json').then(d=>{
    const risk=document.getElementById('risk-rows');risk.replaceChildren();
    for(const key of ['hy','vix','skew','yield10']){
      const x=d.risk?.[key];const row=el('div',null,'kpi');row.style.alignItems='start';
      row.append(el('span',x?.name||key.toUpperCase()));const right=el('div');right.style.textAlign='right';
      right.append(el('strong',fmt(x?.value)+(key==='hy'?'%p':key==='yield10'?'%':'')));
      if(x){const bp=['hy','yield10'].includes(key),scale=bp?100:1,unit=bp?'bp':'pt';
        const a=el('small',null,'risk-mini');a.append(document.createTextNode('전일 '),change(x.delta,false,scale,unit));
        a.append(document.createElement('br'),document.createTextNode(x.mean_n+'일 평균 '+fmt(x.mean)+' 대비 '),change(x.mean_delta,false,scale,unit));
        a.append(document.createElement('br'),document.createTextNode(x.date));right.append(a);
      }row.append(right);risk.append(row);
    }
    const net=d.liquidity?.net,mini=document.getElementById('weekly-net');mini.replaceChildren();
    if(net){mini.append(el('strong','순유동성 '+fmt(net.value,3)+'조 달러'));
      const line=el('div');line.append(document.createTextNode('전주 '),change(net.delta,true,1,'조'),document.createTextNode(' · '+net.mean_n+'주 평균 대비 '),change(net.mean_delta,true,1,'조'));mini.append(line,el('small','주간 관측 '+net.date));}
    const box=document.getElementById('cli-analysis');box.replaceChildren();
    const traces=[];
    for(const [key,name] of [['USA','미국'],['G7','G7']]){
      const x=d.cli?.[key];const card=el('article',null,'cli-card');card.append(el('h3',name+' · '+(x?.date||'수집 대기')));
      if(!x){card.append(el('p','연속 월간 자료 수집 대기'));box.append(card);continue;}
      card.append(el('p',x.interpretation,'cli-main'));
      const trend=x.acceleration<0?(x.jerk>0?'감속 강도는 전월보다 완화 · 가속도는 아직 음수':x.jerk<0?'감속 강도가 전월보다 확대':'감속 강도 유지'):(x.acceleration>0?(x.jerk<0?'가속 강도는 전월보다 약화':x.jerk>0?'가속 강도가 전월보다 확대':'가속 강도 유지'):'가속도 0 · 다음 월 방향 확인');
      card.append(el('p',trend));
      const detail=el('details');detail.append(el('summary','전월 수치·계산 펼치기'));
      detail.append(el('p','변화량 v: '+signed(x.previous_velocity,4)+' → '+signed(x.velocity,4)+' pt/월'));
      const a=el('p','가속도 a: '+signed(x.previous_acceleration,4)+' → '+signed(x.acceleration,4)+' pt/월²','cli-main');a.style.color=x.acceleration>0?'#b4ff60':x.acceleration<0?'#ff8a9d':'#a1b6d0';detail.append(a);
      detail.append(el('p',crossLabel(x.acceleration_cross,'a')));
      detail.append(el('p','가속도 변화 j: '+signed(x.previous_jerk,4)+' → '+signed(x.jerk,4)+' pt/월³'));
      detail.append(el('p',crossLabel(x.jerk_cross,'j')));
      const diff=el('small','수준 '+fmt(x.previous_level,4)+' → '+fmt(x.level,4)+' · 직전 비교 '+x.previous_date);detail.append(diff);card.append(detail);box.append(card);
      const aRows=x.rows.slice(2).map((r,i)=>({date:r.date,value:r.value-2*x.rows[i+1].value+x.rows[i].value}));
      traces.push({x:aRows.map(r=>r.date),y:aRows.map(r=>r.value),name:name+' 가속도',mode:'lines+markers',line:{width:2,color:key==='USA'?'#6ea8ff':'#c299ff'}});
    }
    load('./cli.json').then(raw=>{
      const colors={G20:'#f2bd6a',G7:'#c299ff',USA:'#6ea8ff',Korea:'#ff8a9d'};
      const lines=['G20','G7','USA','Korea'].filter(k=>raw.series?.[k]?.rows?.length).map(k=>({name:k==='USA'?'미국':k==='Korea'?'한국':k,x:raw.series[k].rows.map(r=>r.date),y:raw.series[k].rows.map(r=>r.value),mode:'lines',line:{color:colors[k],width:2}}));
      Plotly.newPlot('cli-level-chart',lines,{paper_bgcolor:'#0f2033',plot_bgcolor:'#0f2033',font:{color:'#b8cbe2'},margin:{l:45,r:10,t:10,b:45},xaxis:{gridcolor:'#233d56'},yaxis:{gridcolor:'#233d56',title:'CLI'},legend:{orientation:'h',y:-.3},hovermode:'x unified'},{responsive:true,displayModeBar:false});
    }).catch(()=>{});
    if(traces.length&&typeof Plotly!=='undefined')Plotly.newPlot('clichart',traces,{paper_bgcolor:'#0f2033',plot_bgcolor:'#0f2033',font:{color:'#b8cbe2'},margin:{l:55,r:10,t:10,b:45},xaxis:{gridcolor:'#233d56'},yaxis:{gridcolor:'#233d56',zeroline:true,zerolinecolor:'#e7eaf0',title:'가속도 a'},legend:{orientation:'h',y:-.3},hovermode:'x unified'},{responsive:true,displayModeBar:false});
    const groups=document.getElementById('change-groups');groups.replaceChildren();
    const labels={signals:'① 줍줍신호 전환',opportunity:'② 기회지수 급변',sectors:'③ 산업 기회 급변',other:'④ 공포·거래량 변화'};
    for(const [key,title] of Object.entries(labels)){
      const card=el('section',null,'change-group');card.append(el('h3',title));
      const items=d.checkpoints?.[key]||[];
      if(!items.length)card.append(el('p','현재 기준상 급변 없음','hint'));
      for(const item of items.slice(0,6)){
        const r=el('div',null,'change-item');r.append(el('strong',(item.good?'↑ ':'↓ ')+item.title,item.good?'rise-good':'rise-bad'),el('div',item.body),el('small',item.date));card.append(r);
      }
      if(key==='opportunity'){
        const n=d.opportunity_changes?.equity?.mean_n||0;
        if(n<20)card.append(el('small','실제 보관 기록 '+n+'/20거래일 · 초기 평균은 가용 기록만 사용','hint'));
      }groups.append(card);
    }
    const c=d.checkpoints||{};const count=k=>(c[k]||[]).filter(x=>x.good).length;
    document.getElementById('change-summary').textContent='최근 새 줍 '+count('signals')+'건 · 기회지수 개선 '+count('opportunity')+'건 · 산업 점수 상승 '+count('sectors')+'곳 (종합 통과 '+(c.sectors||[]).filter(x=>x.good&&x.qualified).length+'곳) · '+new Date(d.generated_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'});
    // A compact weekly comparison under each latest liquidity value.
    const liqnote=document.getElementById('liqdate');if(liqnote){
      const detail=el('div',null,'compact-note');
      for(const [key,name,goodUp] of [['WALCL','총자산',true],['WTREGEN','TGA',false],['RRPONTSYD','ON RRP',false],['WRESBAL','지급준비금',true],['net','순유동성',true]]){
        const x=d.liquidity?.[key];if(!x)continue;const line=el('div');
        line.append(document.createTextNode(name+' · 전주 '),change(x.delta,goodUp,1000,'십억$'),document.createTextNode(' · '+x.mean_n+'주 평균 대비 '),change(x.mean_delta,goodUp,1000,'십억$'));detail.append(line);
      }liqnote.after(detail);
    }
  }).catch(()=>{document.getElementById('change-summary').textContent='변화 분석 갱신 대기';});
  document.getElementById('toggle-sector-details').onclick=()=>{const table=document.querySelector('.sector-table');const open=table.classList.toggle('show-details');document.getElementById('toggle-sector-details').textContent=open?'핵심 열만 보기':'가격·낙폭·날짜 열 보기';};
  document.getElementById('toggle-liquidity').onclick=()=>{
    const r=window.liqAllRows;if(!r)return;window.liqExpanded=!window.liqExpanded;
    const keys=['WALCL','WTREGEN','RRPONTSYD','WRESBAL','net'];const body=document.getElementById('liqrows');body.replaceChildren();
    for(const z of (window.liqExpanded?r:r.slice(-3)).slice().reverse()){
      const tr=el('tr');tr.append(el('td',z.date));for(const key of keys)tr.append(el('td',fmt(z[key],3)));body.append(tr);
    }
    document.getElementById('toggle-liquidity').textContent=window.liqExpanded?'최근 3주만 보기':'이전 주간 수치 펼치기';
  };
})();
