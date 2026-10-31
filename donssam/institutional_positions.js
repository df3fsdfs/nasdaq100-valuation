(() => {
  const $=id=>document.getElementById(id);
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const num=(v,d=0)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const sign=(v,d=0)=>typeof v==='number'?(v>0?'+':'')+num(v,d):'—';
  const age=day=>day?(Date.now()-Date.parse(day+'T00:00:00Z'))/86400000:Infinity;
  const local=stamp=>stamp?new Date(stamp).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'—';
  const source=(label,url)=>{const a=el('a',label);if(/^https:\/\//.test(url||'')){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}return a;};
  let data;
  let selected='leveraged';
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
    const am=groups.asset_manager;
    $('cot-manager-summary').textContent=am?'자산운용사·기관 · 5년 백분위 '+num(am.latest.percentile,1)+'% · 순 '+sign(am.latest.net)+'계약 · 전주 '+sign(am.net_change_1w)+'계약':'';
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
  function freshness(){
    const cot=data?.cot,l=cot?.latest;
    const released=(data?.release_calendar?.rows||[]).filter(x=>Date.parse(x.scheduled_at)+12*3600000<Date.now()).at(-1);
    const calendarCurrent=released&&Date.now()-Date.parse(released.scheduled_at)<14*86400000;
    return {cot:!l||(calendarCurrent?Date.parse(released.expected_report_date)-2*86400000>Date.parse(l.date):age(l.date)>12),dg:!data?.degrossing?.latest||age(data.degrossing.latest.date)>14};
  }
  function checkpoint(){
    let box=$('degrossing-checkpoint');if(!data)return;if(!box&&$('change-groups')){box=el('section',null,'change-group');box.id='degrossing-checkpoint';$('change-groups').append(box);}if(!box)return;
    box.replaceChildren(el('h3','⑤ 디그로싱 변화'));
    const d=data.degrossing,l=d?.latest,f=freshness();
    if(!l){box.append(el('p','동일 정의의 관측치 수집 대기','hint'));return;}
    const row=el('div',null,'change-item');
    row.append(el('strong',num(l.value,1)+'% · '+(d.direction==='easing'?'축소폭 완화':d.direction==='deepening'?'축소폭 확대':'공개차트 인용값'),d.direction==='easing'?'rise-good':d.direction==='deepening'?'rise-bad':'neutral-change'));
    row.append(el('div',d.interpretation),el('small',l.date+' 관측 · '+(l.quality==='recreated_approximate'?'재구성 근사치':'원자료 확인값')));
    if(f.dg)row.append(el('small','갱신 지연 · 마지막 확인값 유지','institution-warning'));
    box.append(row,el('small','새 관측치가 확인될 때만 방향을 갱신해.','hint'));
  }
  const layout=title=>({paper_bgcolor:'#0f2033',plot_bgcolor:'#0f2033',font:{color:'#b8cbe2'},margin:{l:60,r:15,t:15,b:55},xaxis:{gridcolor:'#233d56'},yaxis:{gridcolor:'#233d56',title},legend:{orientation:'h',y:-.25},hovermode:'x unified'});
  function cotGraph(){
    const rows=selectedCot()?.rows||[];if(!rows.length)return;
    Plotly.react('cot-history',[{x:rows.map(x=>x.date),y:rows.map(x=>x.net),name:'순포지션(롱−숏)',mode:'lines',line:{color:'#6ea8ff',width:2}},
      {x:rows.map(x=>x.date),y:rows.map(x=>x.long),name:'롱',visible:'legendonly',mode:'lines',line:{color:'#64d9b1'}},
      {x:rows.map(x=>x.date),y:rows.map(x=>x.short),name:'숏',visible:'legendonly',mode:'lines',line:{color:'#ff8a9d'}}],layout('계약'),{responsive:true,displayModeBar:false});
  }
  function graphs(){
    const cot=$('cot-history-details'),dg=$('dg-history-details');
    cot.addEventListener('toggle',()=>{if(cot.open&&data)cotGraph();});
    dg.addEventListener('toggle',()=>{if(!dg.open)return;const rows=data?.degrossing?.rows||[];if(!rows.length)return;
      const plot=layout('% / 전체 gross exposure');
      if(rows.length===1){plot.xaxis.range=[new Date(Date.parse(rows[0].date)-7*86400000).toISOString().slice(0,10),new Date(Date.parse(rows[0].date)+7*86400000).toISOString().slice(0,10)];}
      Plotly.newPlot('dg-history',[{x:rows.map(x=>x.date),y:rows.map(x=>x.value),text:rows.map(x=>(x.quality==='recreated_approximate'?'재구성 근사치':'원자료 확인')+' · '+x.date),hovertemplate:'%{x}<br>%{y:.1f}%<br>%{text}<extra></extra>',name:'확인된 관측',mode:rows.length>1?'lines+markers':'markers',marker:{size:10,color:'#ffa74f'},line:{color:'#ffa74f'}}],plot,{responsive:true,displayModeBar:false});});
  }
  function render(){
    const c=selectedCot(),l=c?.latest,d=data.degrossing,dl=d?.latest,f=freshness();
    $('cot-title').textContent='COT · Nasdaq-100 '+(c.label||'레버리지 펀드');
    $('cot-participant-note').textContent=notes[selected][0];
    $('cot-opportunity-note').textContent=notes[selected][1]+' 선물 일부의 변화이므로 가격·줍줍 조건과 함께 확인해.';
    participants();
    $('institution-time').textContent='수집 확인 '+local(data.generated_at)+' KST · 관측일·공개 인용 여부는 각 지표에 표시';
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
    if(dl){
      $('dg-value').textContent=num(dl.value,1)+'%';$('dg-quality').textContent=dl.quality==='recreated_approximate'?'공개 재구성 차트 · 근사치':'원자료 확인값';
      $('dg-date').textContent=dl.date+' 관측 · '+(f.dg?'갱신 지연 · 마지막 확인값 유지':'원본 정기 시계열은 미연결');$('dg-date').className=f.dg?'institution-warning':'hint';
      $('dg-reading').textContent=d.interpretation;
      $('dg-extreme').textContent=d.historical_extreme?'역사적 수준: '+d.historical_extreme+' · 자체 백분위는 계산하지 않음':'동일 정의의 충분한 과거 관측치가 없어 역사 백분위는 표시하지 않음';
      $('dg-source').replaceChildren(source('공개 인용 출처',dl.source_url),el('span',' · '+dl.source_name));
      $('dg-history-note').textContent=d.history_coverage+' 현재 '+num(d.rows.length)+'개 관측. 값 사이를 임의로 채우지 않아.';
      $('dg-collection').textContent='수치 최초 확인 '+local(dl.collected_at)+' KST · 자동 수집 시도 '+local(d.checked_at)+' KST';
      $('dg-method').textContent='원차트 정의: '+d.definition+'. 현재 총노출 수준의 단순 고점 대비 수익률과 다른 지표야. '+d.monitor.limitation+' '+(d.monitor.source_status==='unavailable'?'현재 공개 수집 경로 응답 실패로 기존 인용값을 유지하고 있어. ':'')+d.monitor.schedule+' 출처 본문에 같은 정의·관측일·수치가 명시된 경우에만 자동 반영해.';
    }else{$('dg-reading').textContent='동일 정의의 공개 관측치 수집 대기';}
    const aligned=l&&dl&&Math.abs(Date.parse(l.date)-Date.parse(dl.date))<=14*86400000;
    $('institution-combined').textContent=f.cot||f.dg||!aligned?'두 지표의 관측일과 표본을 각각 확인해. 시점이 오래되거나 서로 다르면 동시 변화 신호를 표시하지 않아.':data.combined;
    checkpoint();
  }
  document.addEventListener('checkpoints-ready',checkpoint);
  $('cot-participant-select').addEventListener('change',event=>{selected=event.target.value;if(!data)return;render();if($('cot-history-details').open)cotGraph();});
  graphs();
  fetch('./institutional_positions.json?v='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('data');return r.json();}).then(d=>{data=d;render();}).catch(()=>{
    $('institution-time').textContent='기관 포지션 자료 로딩 재시도 필요';$('cot-reading').textContent='마지막 저장 자료를 불러오지 못했어. 새로고침 후 확인해.';
    const box=$('degrossing-checkpoint');if(box)box.replaceChildren(el('h3','⑤ 디그로싱 변화'),el('p','저장 자료 로딩 재시도','hint'));
  });
})();
