(() => {
  const $=id=>document.getElementById(id);
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const num=(v,d=0)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const sign=(v,d=0)=>typeof v==='number'?(v>0?'+':'')+num(v,d):'—';
  const age=day=>day?(Date.now()-Date.parse(day+'T00:00:00Z'))/86400000:Infinity;
  const local=stamp=>stamp?new Date(stamp).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'—';
  const source=(label,url)=>{const a=el('a',label);if(/^https:\/\//.test(url||'')){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}return a;};
  let data;
  let shortChartDrawn=false;
  let cotComparisonDrawn=false;
  let selected='leveraged';
  const cotSeries=[['asset_manager','#64d9b1','자산운용사·기관'],['leveraged','#6ea8ff','레버리지 펀드'],['dealer','#ff8a9d','딜러·중개기관'],['other','#f5bb65','기타 보고대상'],['nonreportable','#c3a6ff','비보고 포지션']];
  const notes={
    leveraged:['헤지펀드·CTA 등 레버리지를 활용하는 운용 주체.','기회 관찰: 숏 쏠림 뒤 실제 숏 감소는 숏커버 후보. 숏이 계속 늘면 쏠림만으로 바닥을 판단하지 않아.'],
    asset_manager:['연기금·보험·펀드 등 기관 자산을 운용하는 주체.','기회 관찰: 롱 축소가 둔화되거나 롱이 다시 늘면 기관 선물 노출 회복 단서. 현물 매수와는 구분해.'],
    dealer:['은행·증권사 등 고객 거래를 중개하고 위험을 관리하는 주체.','기회 관찰: 고객 포지션의 반대편·헤지 영향이 커. 순롱·순숏만으로 매수 신호를 만들지 않아.'],
    other:['위 세 분류에 속하지 않는 기타 대형 보고 주체.','기회 관찰: 성격이 섞인 집단이라 다른 참여자의 변화와 함께 참고해. 단독 바닥 신호로 쓰지 않아.'],
    nonreportable:['보고 기준 미만의 잔여 포지션. 개인만을 뜻하지 않아.','기회 관찰: 작은 포지션 집단의 쏠림을 참고하되, 반대로 매매하면 유리하다고 단정하지 않아.']};
  function selectedCot(){
    const group=data?.cot?.groups?.[selected];
    return group?{...data.cot,...group}:selected==='leveraged'?data?.cot:{...data?.cot,latest:null,rows:[],label:$('cot-participant-select').selectedOptions[0].textContent};
  }
  function participants(){
    const box=$('cot-participants');box.replaceChildren();
    const groups=data.cot?.groups||{};
    Object.entries(groups).forEach(([key,g])=>{
      const card=el('div',null,'cot-participant');
      card.append(el('h4',g.label),el('strong','5년 백분위 '+num(g.latest.percentile,1)+'% · '+g.bias));
      card.append(el('p',notes[key][0],'hint'));
      card.append(el('p','롱 '+num(g.latest.long)+' / 숏 '+num(g.latest.short)+' / 순 '+sign(g.latest.net)));
      card.append(el('p','전주 롱 '+sign(g.long_change_1w)+' · 숏 '+sign(g.short_change_1w)+' · 순 '+sign(g.net_change_1w)));
      card.append(el('p','4주 백분위 '+sign(g.percentile_change_4w,1)+'%p · 순 '+sign(g.net_change_4w)+'계약','hint'));
      card.append(el('p',g.interpretation,'hint'));box.append(card);
      card.append(el('p',notes[key][1],'hint'));
    });
  }
  // Weekly holdings changes describe balances, not individual executions or motives.
  function cotFlow(g){
    const l=g?.long_change_1w,s=g?.short_change_1w;
    if(!Number.isFinite(l)||!Number.isFinite(s))return '전주 비교 자료 부족';
    if(l<0&&s>0)return '롱 축소 · 숏 확대';
    if(l>0&&s<0)return '롱 확대 · 숏 축소';
    if(l<0&&s<0)return '양방향 축소'+(s<l?' · 숏 감소 우세':l<s?' · 롱 감소 우세':' · 감소 폭 같음');
    if(l>0&&s>0)return '양방향 확대'+(l>s?' · 롱 증가 우세':s>l?' · 숏 증가 우세':' · 증가 폭 같음');
    if(l===0&&s===0)return '롱·숏 변화 없음';
    return '롱 '+(l>0?'확대':l<0?'축소':'유지')+' · 숏 '+(s>0?'확대':s<0?'축소':'유지');
  }
  function cotMain(){
    const groups=data.cot?.groups||{},a=groups.asset_manager,h=groups.leveraged;
    const box=$('cot-main-cards');box.replaceChildren();
    const aligned=a?.latest&&h?.latest&&a.latest.date===h.latest.date;
    $('cot-main-reading').textContent=aligned?'기관: '+cotFlow(a)+' / 레버리지 펀드: '+cotFlow(h):'두 집단의 같은 관측일 자료가 부족해. 각 카드의 기준일을 확인해.';
    for(const [key,color] of [['asset_manager','#64d9b1'],['leveraged','#6ea8ff']]){
      const g=groups[key],card=el('div',null,'cot-main-card');card.style.setProperty('--group-color',color);
      card.append(el('h4',key==='asset_manager'?'자산운용사·기관':'레버리지 펀드'),el('small',notes[key][0]));
      if(!g?.latest){card.append(el('p','확인된 관측치 없음'));box.append(card);continue;}
      card.append(el('strong',num(g.latest.percentile,1)+' / 100','cot-percentile'),el('small','자기 과거 5년 순포지션 백분위'));
      card.append(el('p','전주 롱 '+sign(g.long_change_1w)+'계약'),el('p','전주 숏 '+sign(g.short_change_1w)+'계약'));
      card.append(el('p',cotFlow(g)));
      if(g.net_change_1w>0&&g.long_change_1w<=0&&g.short_change_1w<0)card.append(el('small','순포지션 개선은 롱 잔고 증가가 아닌 숏 잔고 감소에서 나왔어.'));
      if(key==='asset_manager')card.append(el('small','선물 숏에는 현물 보유분의 헤지가 포함될 수 있어.'));
      card.append(el('small',g.latest.date+' 관측'));box.append(card);
    }
    $('cot-main-date').textContent=(freshness().cot?'갱신 지연 · 마지막 정상값 유지 · ':'')+(data.cot?.fetch_ok?'CFTC 공식 자료':'최근 정상값 · 수집 재시도')+' · 전주 대비 주간 잔고 변화이며 개별 거래·의도는 알 수 없어.';
    $('cot-main-date').className=freshness().cot?'institution-warning':'hint';
    if(cotComparisonDrawn)return;
    const available=cotSeries.filter(([key])=>groups[key]?.rows?.length);
    if(!available.length)return;
    const end=available.map(([key])=>groups[key].rows.at(-1).date).sort().at(-1),plot=layout('백분위');
    plot.margin={l:42,r:65,t:45,b:110};
    plot.yaxis={...plot.yaxis,range:[0,100],fixedrange:true,tickvals:[0,10,50,90,100]};
    plot.xaxis={...plot.xaxis,type:'date',range:[new Date(Date.parse(end)-365*86400000).toISOString().slice(0,10),end],rangeselector:{buttons:[{count:1,label:'1년',step:'year',stepmode:'backward'},{count:3,label:'3년',step:'year',stepmode:'backward'},{label:'전체',step:'all'}],bgcolor:'#1d3c58',activecolor:'#426c9a',font:{color:'#d9eaff'}}};
    plot.legend={orientation:'h',y:-.22,font:{size:11}};
    plot.shapes=[{y0:0,y1:10},{y0:90,y1:100}].map(b=>({type:'rect',xref:'paper',x0:0,x1:1,yref:'y',...b,fillcolor:'#b7cce8',opacity:.09,line:{width:0},layer:'below'}));
    plot.shapes.push(...[10,90].map(y=>({type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:y,y1:y,line:{color:'#7890ac',width:1,dash:'dot'}})));
    const traces=available.map(([key,color,name])=>({x:groups[key].rows.map(r=>r.date),y:groups[key].rows.map(r=>r.percentile),name,mode:'lines',connectgaps:false,line:{color,width:2},hovertemplate:name+' %{x}<br>백분위 %{y:.1f} / 100<extra></extra>'}));
    const total=data.cot?.total,rows=total?.rows||[];
    plot.yaxis2={title:'전체 순포지션 · 계약',overlaying:'y',side:'right',showgrid:false,zeroline:false,...(rows.length&&rows.every(r=>r.net===0)?{range:[-1,1],tickvals:[0]}:{})};
    if(rows.length)traces.push({x:rows.map(r=>r.date),y:rows.map(r=>r.net),name:'전체 순포지션 · 계약(오른쪽)',yaxis:'y2',mode:'lines',line:{color:'#ffffff',width:2,dash:'dash'},hovertemplate:'전체 %{x}<br>순포지션 %{y:,.0f}계약<extra></extra>'});
    Plotly.newPlot('cot-comparison-chart',traces,plot,{responsive:true,displayModeBar:false});
    const netPlot=layout('순포지션 · 계약');
    netPlot.margin={l:65,r:15,t:45,b:110};netPlot.xaxis={...plot.xaxis};netPlot.legend={...plot.legend};
    const netTraces=available.map(([key,color,name])=>({x:groups[key].rows.map(r=>r.date),y:groups[key].rows.map(r=>r.net),name,mode:'lines',connectgaps:false,line:{color,width:2},hovertemplate:name+' %{x}<br>순포지션 %{y:,.0f}계약<extra></extra>'}));
    if(rows.length)netTraces.push({x:rows.map(r=>r.date),y:rows.map(r=>r.net),name:'전체 순포지션',mode:'lines',line:{color:'#ffffff',width:2,dash:'dash'},hovertemplate:'전체 %{x}<br>순포지션 %{y:,.0f}계약<extra></extra>'});
    Plotly.newPlot('cot-net-comparison-chart',netTraces,netPlot,{responsive:true,displayModeBar:false});
    $('cot-total-reading').textContent=rows.length?'전체 순포지션 '+sign(rows.at(-1).net)+'계약 · '+rows.at(-1).date+' 관측. 전체는 5개 참여자의 같은 날짜 순포지션 합계야. 합계가 0인 시계열은 쏠림 백분위를 표시하지 않아.':'전체 합산에 필요한 5개 참여자의 같은 날짜 자료가 부족해.';
    cotComparisonDrawn=true;
  }
  function freshness(){
    const cot=data?.cot,l=cot?.latest;
    const released=(data?.release_calendar?.rows||[]).filter(x=>Date.parse(x.scheduled_at)+12*3600000<Date.now()).at(-1);
    const calendarCurrent=released&&Date.now()-Date.parse(released.scheduled_at)<14*86400000;
    return {cot:!l||(calendarCurrent?Date.parse(released.expected_report_date)-2*86400000>Date.parse(l.date):age(l.date)>12)};
  }
  function shortStale(series){
    const l=series?.latest;if(!l)return true;
    const releases=data?.short_interest?.release_calendar?.rows||[];
    const due=releases.filter(x=>Date.parse(x.published_at)+12*3600000<Date.now()).at(-1);
    return due&&Date.now()-Date.parse(due.published_at)<45*86400000?l.date<due.date:age(l.date)>45;
  }
  const published=r=>r?.publication_date||'공식 발표일 확인 중';
  function shortComparison(g){
    const previous=g.previous;
    return '직전 관측 '+(previous?.date||'—')+' / 발표 '+published(previous)+' · '+num(previous?.shares/10000,1)+'만 주 대비 '+sign(g.change_percent,2)+'%';
  }
  function shortMean(g){return '직전 4개 관측 평균 '+num(g.mean4==null?null:g.mean4/10000,1)+'만 주 대비 '+sign(g.mean4_percent,2)+'%'+(g.mean4_n<4?' · 평균 이력 확인 중':'');}
  function checkpoint(){
    let box=$('short-interest-checkpoint');if(!data)return;
    if(!box&&$('change-groups')){box=el('section',null,'change-group');box.id='short-interest-checkpoint';$('change-groups').append(box);}if(!box)return;
    box.replaceChildren(el('h3','⑤ 공매도 잔고 변화'));
    for(const symbol of ['QQQ','SPY']){
      const g=data.short_interest?.series?.[symbol];if(!g){box.append(el('p',symbol+' 공식 잔고 수집 대기','hint'));continue;}
      const row=el('div',null,'change-item');
      row.append(el('strong',symbol+' '+num(g.latest.shares/10000,1)+'만 주'),el('div',shortComparison(g)),el('div',shortMean(g)),el('small','현재 관측 '+g.latest.date+' / 발표 '+published(g.latest)));
      const detail=el('details');detail.append(el('summary','평균에 사용한 4개 관측·발표일'));
      for(const r of g.mean4_observations||[])detail.append(el('p','관측 '+r.date+' / 발표 '+published(r)+' · '+num(r.shares/10000,1)+'만 주','hint'));
      row.append(detail);if(shortStale(g))row.append(el('small','갱신 지연 · 마지막 정상값 유지','institution-warning'));box.append(row);
    }
    box.append(el('small','월 2회 발표 · 평균은 현재를 제외한 직전 4개 관측 기준','hint'));
  }
  function shortRender(){
    const si=data.short_interest||{},cards=$('short-interest-cards');cards.replaceChildren();
    for(const symbol of ['QQQ','SPY']){
      const g=si.series?.[symbol],card=el('div',null,'short-interest-stat');card.append(el('h4',symbol));
      if(!g){card.append(el('p','공식 자료 수집 대기'));cards.append(card);continue;}
      card.append(el('strong',num(g.latest.shares/10000,1)+'만 주'));
      card.append(el('small',shortComparison(g)),el('small',shortMean(g)));
      card.append(el('small',g.latest.date+' 관측 / '+published(g.latest)+' 발표'),el('small','상환일수 '+num(g.latest.days_to_cover,2)+'일'));
      if(shortStale(g))card.append(el('small','갱신 지연 · 마지막 정상값 유지','institution-warning'));
      cards.append(card);
    }
    const q=si.series?.QQQ,p=si.series?.SPY,aligned=q&&p&&q.latest.date===p.latest.date;
    const direction=g=>g.change===null?'주식분할로 단순 증감 생략':g.change<0?'잔고 감소':g.change>0?'잔고 증가':'변화 없음';
    $('short-interest-reading').textContent=aligned?'QQQ '+direction(q)+' · SPY '+direction(p)+'. '+(q.change>0&&p.change<0?'나스닥100 ETF와 S&P500 ETF의 숏 흐름이 갈렸어.':q.change<0&&p.change<0?'두 ETF 모두 숏 잔고가 줄었어. 숏 축소 단서로 가격 안정 여부도 함께 확인해.':q.change>0&&p.change>0?'두 ETF 모두 숏 잔고가 늘었어. 숏이 쌓였다는 이유만으로 바닥으로 보진 않아.':'잔고 변화는 헤지·차익거래를 포함한 결과야.'):'두 ETF의 관측일이 다르거나 자료가 부족해. 같은 기준일의 수집을 재확인해.';
    const calendar=si.release_calendar?.rows||[],next=calendar.find(x=>Date.parse(x.published_at)>Date.now());
    $('short-interest-date').textContent='수집 확인 '+local(si.checked_at)+' KST · '+(si.fetch_ok?'공식 API 확인':'최근 정상값 유지 · 수집 재시도')+(next?' · 다음 발표 '+local(next.published_at)+' KST':' · 월 2회 발표 후 확인');
    $('short-interest-source').replaceChildren(source('FINRA 공식 공매도 잔고',si.source_url));
    $('short-interest-method').textContent=(data.method.short_interest||'')+' 실제 상환 기한을 뜻하지 않아. 관측일과 발표일을 구분해.';
    if(!shortChartDrawn&&q&&p){
      const plot=layout('백만 주');plot.margin.t=45;
      plot.xaxis={...plot.xaxis,type:'date',range:[new Date(Date.parse(q.latest.date)-365*86400000).toISOString().slice(0,10),q.latest.date],rangeselector:{buttons:[{count:1,label:'1년',step:'year',stepmode:'backward'},{count:3,label:'3년',step:'year',stepmode:'backward'},{label:'전체',step:'all'}],bgcolor:'#1d3c58',activecolor:'#426c9a',font:{color:'#d9eaff'}}};
      Plotly.newPlot('short-interest-chart',[['QQQ','#6ea8ff'],['SPY','#f5bb65']].map(([symbol,color])=>{const rows=si.series[symbol].rows;return {x:rows.map(r=>r.date),y:rows.map(r=>r.split?null:r.shares/1e6),name:symbol,mode:'lines+markers',marker:{size:3},line:{color,width:2},connectgaps:false,hovertemplate:symbol+' %{x}<br>%{y:.2f}백만 주<extra></extra>'};}),plot,{responsive:true,displayModeBar:false});shortChartDrawn=true;
    }
  }
  const layout=title=>({paper_bgcolor:'#0f2033',plot_bgcolor:'#0f2033',font:{color:'#b8cbe2'},margin:{l:60,r:15,t:15,b:55},xaxis:{gridcolor:'#233d56'},yaxis:{gridcolor:'#233d56',title},legend:{orientation:'h',y:-.25},hovermode:'x unified'});
  function cotGraph(){
    const rows=selectedCot()?.rows||[];if(!rows.length)return;
    Plotly.react('cot-history',[{x:rows.map(x=>x.date),y:rows.map(x=>x.net),name:'순포지션(롱−숏)',mode:'lines',line:{color:'#6ea8ff',width:2}},
      {x:rows.map(x=>x.date),y:rows.map(x=>x.long),name:'롱',visible:'legendonly',mode:'lines',line:{color:'#64d9b1'}},
      {x:rows.map(x=>x.date),y:rows.map(x=>x.short),name:'숏',visible:'legendonly',mode:'lines',line:{color:'#ff8a9d'}}],layout('계약'),{responsive:true,displayModeBar:false});
  }
  function graphs(){
    const cot=$('cot-history-details');
    cot.addEventListener('toggle',()=>{if(cot.open&&data)cotGraph();});
  }
  function render(){
    const c=selectedCot(),l=c?.latest,f=freshness();
    $('cot-detail-title').textContent='참여자 상세 · '+(c.label||'레버리지 펀드');
    $('cot-participant-note').textContent=notes[selected][0];
    $('cot-opportunity-note').textContent=notes[selected][1]+' 선물 일부의 변화이므로 가격·줍줍 조건과 함께 확인해.';
    participants();
    cotMain();
    $('institution-time').textContent='수집 확인 '+local(data.generated_at)+' KST · 선물·ETF별 관측일은 각 지표에 표시';
    if(l){
      $('cot-value').textContent=num(l.percentile,1)+'%';$('cot-gauge-pin').style.left=(l.percentile??50)+'%';$('cot-gauge').setAttribute('aria-valuenow',l.percentile??0);
      $('cot-bias').textContent='과거 대비 '+c.bias+' · 5년 '+num(l.percentile_n)+'개 보고';
      $('cot-fourweek').textContent='4주 백분위 '+sign(c.percentile_change_4w,1)+'%p · 순포지션 '+sign(c.net_change_4w)+'계약';
      $('cot-counts').textContent='롱 '+num(l.long)+' / 숏 '+num(l.short)+' / 순 '+sign(l.net)+'계약';
      $('cot-week').textContent='전주 대비 롱 '+sign(c.long_change_1w)+' · 숏 '+sign(c.short_change_1w)+' · 순 '+sign(c.net_change_1w)+'계약';
      $('cot-date').textContent=l.date+' '+new Date(l.date+'T00:00:00Z').toLocaleDateString('ko-KR',{weekday:'long',timeZone:'UTC'})+' 관측 · '+(f.cot?'갱신 지연 · 마지막 정상값 유지':c.fetch_ok?'공식 자료 확인':'최근 정상값 유지 · 수집 재시도');
      $('cot-date').className=f.cot?'institution-warning':'hint';$('cot-reading').textContent=c.interpretation;
      $('cot-source').replaceChildren(source('CFTC 공식 TFF · Nasdaq mini #209742',c.source_url));
      $('cot-method').textContent=data.method.cot+' 계약수 기준이며 OI 대비 비율과 구분해. 보고는 보통 금요일 15:30 뉴욕시간, 화요일 포지션을 공개. 한국시간 토요일 04:30(서머타임)/05:30(겨울) 이후 매일07:05에 확인하며 미발표 시 다음날 재확인해.';
    }else{
      ['cot-value','cot-bias','cot-fourweek','cot-counts','cot-week'].forEach(id=>$(id).textContent='—');
      $('cot-gauge-pin').style.left='50%';$('cot-gauge').removeAttribute('aria-valuenow');
      $('cot-reading').textContent='선택한 참여자의 공식 자료 수집 재시도 중';$('cot-date').textContent='확인된 관측치 없음';
    }
    shortRender();
    $('institution-combined').textContent='COT는 나스닥100 선물의 참여자별 포지션, 공매도 잔고는 QQQ·SPY ETF의 미청산 숏이야. 표본·관측일이 달라 각각의 증감을 확인해.';
    checkpoint();
  }
  document.addEventListener('checkpoints-ready',checkpoint);
  $('cot-participant-select').addEventListener('change',event=>{selected=event.target.value;if(!data)return;render();if($('cot-history-details').open)cotGraph();});
  graphs();
  fetch('./institutional_positions_public.json?v='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('data');return r.json();}).then(d=>{data=d;render();}).catch(()=>{
    $('cot-main-reading').textContent='저장 자료를 불러오지 못했어. 새로고침 후 확인해.';
    $('institution-time').textContent='기관 포지션 자료 로딩 재시도 필요';$('cot-reading').textContent='마지막 저장 자료를 불러오지 못했어. 새로고침 후 확인해.';
    const box=$('short-interest-checkpoint');if(box)box.replaceChildren(el('h3','⑤ 공매도 잔고 변화'),el('p','저장 자료 로딩 재시도','hint'));
  });
})();

