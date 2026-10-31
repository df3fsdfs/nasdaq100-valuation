(() => {
  const $=id=>document.getElementById(id);
  const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
  const num=(v,d=0)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{minimumFractionDigits:d,maximumFractionDigits:d}):'—';
  const sign=(v,d=0)=>typeof v==='number'?(v>0?'+':'')+num(v,d):'—';
  const age=day=>day?(Date.now()-Date.parse(day+'T00:00:00Z'))/86400000:Infinity;
  const local=stamp=>stamp?new Date(stamp).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'—';
  const source=(label,url)=>{const a=el('a',label);if(/^https:\/\//.test(url||'')){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}return a;};
  let data;
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
  function graphs(){
    const cot=$('cot-history-details'),dg=$('dg-history-details');
    cot.addEventListener('toggle',()=>{if(!cot.open)return;const rows=data?.cot?.rows||[];if(!rows.length)return;
      Plotly.newPlot('cot-history',[{x:rows.map(x=>x.date),y:rows.map(x=>x.net),name:'순포지션(롱−숏)',mode:'lines',line:{color:'#6ea8ff',width:2}},
        {x:rows.map(x=>x.date),y:rows.map(x=>x.long),name:'롱',visible:'legendonly',mode:'lines',line:{color:'#64d9b1'}},
        {x:rows.map(x=>x.date),y:rows.map(x=>x.short),name:'숏',visible:'legendonly',mode:'lines',line:{color:'#ff8a9d'}}],layout('계약'),{responsive:true,displayModeBar:false});});
    dg.addEventListener('toggle',()=>{if(!dg.open)return;const rows=data?.degrossing?.rows||[];if(!rows.length)return;
      const plot=layout('% / 전체 gross exposure');
      if(rows.length===1){plot.xaxis.range=[new Date(Date.parse(rows[0].date)-7*86400000).toISOString().slice(0,10),new Date(Date.parse(rows[0].date)+7*86400000).toISOString().slice(0,10)];}
      Plotly.newPlot('dg-history',[{x:rows.map(x=>x.date),y:rows.map(x=>x.value),text:rows.map(x=>(x.quality==='recreated_approximate'?'재구성 근사치':'원자료 확인')+' · '+x.date),hovertemplate:'%{x}<br>%{y:.1f}%<br>%{text}<extra></extra>',name:'확인된 관측',mode:rows.length>1?'lines+markers':'markers',marker:{size:10,color:'#ffa74f'},line:{color:'#ffa74f'}}],plot,{responsive:true,displayModeBar:false});});
  }
  function render(){
    const c=data.cot,l=c?.latest,d=data.degrossing,dl=d?.latest,f=freshness();
    $('institution-time').textContent='수집 확인 '+local(data.generated_at)+' KST · 관측일·공개 인용 여부는 각 지표에 표시';
    if(l){
      $('cot-value').textContent=num(l.percentile,1)+'%';$('cot-gauge-pin').style.left=(l.percentile??50)+'%';$('cot-gauge').setAttribute('aria-valuenow',l.percentile??0);
      $('cot-bias').textContent=c.bias+' · 5년 '+num(l.percentile_n)+'개 보고';
      $('cot-fourweek').textContent='4주 백분위 '+sign(c.percentile_change_4w,1)+'%p · 순포지션 '+sign(c.net_change_4w)+'계약';
      $('cot-counts').textContent='롱 '+num(l.long)+' / 숏 '+num(l.short)+' / 순 '+sign(l.net)+'계약';
      $('cot-week').textContent='전주 대비 롱 '+sign(c.long_change_1w)+' · 숏 '+sign(c.short_change_1w)+' · 순 '+sign(c.net_change_1w)+'계약';
      $('cot-date').textContent=l.date+' '+new Date(l.date+'T00:00:00Z').toLocaleDateString('ko-KR',{weekday:'long',timeZone:'UTC'})+' 관측 · '+(f.cot?'갱신 지연 · 마지막 정상값 유지':c.fetch_ok?'공식 자료 확인':'최근 정상값 유지 · 수집 재시도');
      $('cot-date').className=f.cot?'institution-warning':'hint';$('cot-reading').textContent=c.interpretation;
      $('cot-source').replaceChildren(source('CFTC 공식 TFF · Nasdaq mini #209742',c.source_url));
      $('cot-method').textContent=data.method.cot+' 계약수 기준이며 OI 대비 비율과 구분해. 보고는 보통 금요일 15:30 뉴욕시간, 화요일 포지션을 공개. 한국시간 토요일 04:30(서머타임)/05:30(겨울) 이후 매일07:05에 확인하며 미발표 시 다음날 재확인해.';
    }else{$('cot-reading').textContent='CFTC 공식 자료 수집 재시도 중';$('cot-date').textContent='확인된 관측치 없음';}
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
  graphs();
  fetch('./institutional_positions.json?v='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('data');return r.json();}).then(d=>{data=d;render();}).catch(()=>{
    $('institution-time').textContent='기관 포지션 자료 로딩 재시도 필요';$('cot-reading').textContent='마지막 저장 자료를 불러오지 못했어. 새로고침 후 확인해.';
    const box=$('degrossing-checkpoint');if(box)box.replaceChildren(el('h3','⑤ 디그로싱 변화'),el('p','저장 자료 로딩 재시도','hint'));
  });
})();
