/* Public presentation only. Scores and signal states are computed privately. */
(() => {
  const $=id=>document.getElementById(id);
  const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!=null)x.textContent=String(text);if(cls)x.className=cls;return x;};
  const fmt=(v,d=2)=>typeof v==='number'&&Number.isFinite(v)?v.toLocaleString('ko-KR',{maximumFractionDigits:d}):'—';
  const sign=v=>typeof v==='number'?(v>0?'+':'')+fmt(v):'—';
  const kst=t=>t?new Date(t).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'}):'—';
  const load=async url=>{const r=await fetch(url+'?v='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('snapshot unavailable');return r.json();};
  const link=(name,url)=>{const a=el('a',name);if(/^https?:\/\//.test(url||'')){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}return a;};
  const state=v=>v===true?'충족':v===false?'미충족':'확인 대기';
  const drop=v=>v==null?'확인 대기':v===2?'2차 신호':v===1?'1차 신호':'미발생';
  const badge=(text,on)=>el('span',text,'badge '+(on===true?'on':on===false?'off':'wait'));
  const layout=title=>({paper_bgcolor:'#0f2033',plot_bgcolor:'#0f2033',font:{color:'#b8cbe2'},margin:{l:46,r:12,t:15,b:55},xaxis:{gridcolor:'#233d56'},yaxis:{gridcolor:'#233d56',title},legend:{orientation:'h',y:-.25},hovermode:'x unified'});
  const plot=(id,traces,title,extra={})=>{if(typeof Plotly!=='undefined'&&traces.length)Plotly.newPlot(id,traces,{...layout(title),...extra},{responsive:true,displayModeBar:false});};
  function baseline(c){return '직전 '+(c.previous_date||'—')+' '+fmt(c.previous)+' → 현재 '+fmt(c.value)+' ('+sign(c.delta)+'점) · 이전 '+(c.mean_n||0)+'거래일 평균 '+fmt(c.mean)+' 대비 '+sign(c.mean_delta)+'점';}
  function transition(s){const c=s.comparison||{};return c.previous_qualified_known?'판정 '+state(c.previous_qualified)+' → '+state(s.qualified):'현재 '+state(s.qualified)+' · 이전 판정 비교 준비';}
  function changeItem(title,body,day,good){const row=el('div',null,'change-item');row.append(el('strong',title,good===true?'rise-good':good===false?'rise-bad':''),el('div',body),el('small',day||''));return row;}
  let snapshot,allSectors=false;
  function checkpoints(d){
    const box=$('change-groups');box.replaceChildren();
    for(const [id,title] of [['market','① 시장 기회 변화'],['sector','② 산업 기회 변화'],['stock','③ 종목 기회 변화'],['activity','④ 바닥관찰지수 · 공포 변화'],['short-interest-checkpoint','⑤ 공매도 잔고 변화']]){
      const section=el('section',null,'change-group');section.id=id;section.append(el('h3',title));box.append(section);
    }
    for(const item of d.insights.market_changes||[])$('market').append(changeItem(item.title,item.body,item.date,item.good));
    if(!$('market').querySelector('.change-item'))$('market').append(el('p','현재 기준상 새 변화 없음','hint'));
    for(const s of d.screen.sectors){const c=s.comparison||{};if(c.value==null)continue;
      const changed=typeof c.previous_qualified==='boolean'&&c.previous_qualified!==s.qualified;
      const listed=(d.insights.sector_changes||[]).some(x=>x.title.startsWith(s.ticker+' '));if(!changed&&!listed)continue;
      $('sector').append(changeItem(s.ticker+' '+fmt(s.score)+'점',baseline(c)+' · '+(changed?'판정 '+state(c.previous_qualified)+' → ':'현재 ')+state(s.qualified),s.date,s.qualified===true||c.delta>0));
    }
    const sectorItems=[...$('sector').querySelectorAll('.change-item')];
    if(sectorItems.length>5){sectorItems.slice(5).forEach(r=>r.classList.add('stock-more'));const button=el('button','전체 '+sectorItems.length+'개 변화 보기','tinybtn');button.onclick=()=>{$('sector').classList.toggle('expanded');button.textContent=$('sector').classList.contains('expanded')?'5개만 보기':'전체 '+sectorItems.length+'개 변화 보기';};$('sector').append(button);}
    if(!$('sector').querySelector('.change-item'))$('sector').append(el('p','현재 기준상 새 변화 없음','hint'));
    const stocks=d.screen.stock_changes||[];
    stocks.forEach((s,i)=>{const row=changeItem(s.ticker+' '+fmt(s.score)+'점 · '+sign(s.comparison?.delta)+'점',baseline(s.comparison||{})+' · '+transition(s)+' · '+s.etfs.join(' / '),s.date,s.qualified);if(i>=5)row.classList.add('stock-more');$('stock').append(row);});
    if(stocks.length>5){const button=el('button','전체 '+stocks.length+'종목 보기','tinybtn');button.onclick=()=>{$('stock').classList.toggle('expanded');button.textContent=$('stock').classList.contains('expanded')?'5개만 보기':'전체 '+stocks.length+'종목 보기';};$('stock').append(button);}
    if(!stocks.length)$('stock').append(el('p','70점 이상 대상의 비교 자료 수집 중','hint'));
    $('stock').append(el('small','현재·직전 70점 이상 종목 · 현재 ETF 편입종목 기준 과거 비교','hint'));
    for(const [symbol,x] of Object.entries(d.bottom.activity||{})){
      const row=changeItem(symbol+' '+fmt(x.score)+'점','이전 '+(x.mean_n||0)+'거래일 평균 '+fmt(x.mean_score)+'점 · 직전 '+(x.previous_date||'—')+' '+fmt(x.previous_score)+'점',x.date,x.active);
      if(x.active)row.classList.add('activity-highlight');$('activity').append(row);
    }
    for(const [key,name] of [['cnn','CNN 공포'],['crypto','크립토 공포']]){const x=d.bottom.fear?.[key];if(x)$('activity').append(changeItem(name+' '+fmt(x.value),fearCompare(x),x.date,null));}
    document.dispatchEvent(new Event('checkpoints-ready'));
    $('change-summary').textContent='시장·산업·종목의 실제 변화와 관측일을 함께 확인해 · '+kst(d.insights.generated_at);
  }
  function fearCompare(x){return '직전 '+(x.previous_date||'관측')+' '+fmt(x.previous)+' 대비 '+(x.previous!=null?sign(x.value-x.previous):'—')+'점 · 이전 '+(x.mean_n||0)+'관측 평균 '+fmt(x.mean)+' 대비 '+(x.mean!=null?sign(x.value-x.mean):'—')+'점';}
  function signals(d){
    $('bottom-time').textContent='마지막 점검 '+kst(d.generated_at)+' · 확정봉과 진행 중 봉 구분';
    const fear=$('fear-grid');fear.replaceChildren();
    for(const [key,name] of [['cnn','CNN 주식 공포·탐욕'],['crypto','크립토 공포·탐욕']]){
      const x=d.fear?.[key],card=el('div',null,'checkpoint');card.append(el('strong',name),el('div',fmt(x?.value),'fear-number'));
      if(x){card.append(el('p',fearCompare(x)),link('출처 · '+x.date,x.source));if(!x.fresh)card.append(el('small','이전 확인값 · 발표일 확인','institution-warning'));}fear.append(card);
    }
    const box=$('bottom-assets');box.replaceChildren();
    for(const [key,name] of [['NDX','나스닥100 · NAS100'],['BTC','비트코인 · BTC']]){
      const a=d.assets?.[key],section=el('section',null,'checkpoint');section.append(el('h3',name));
      if(!a){section.append(el('p','자료 수집 대기'));box.append(section);continue;}
      const stale=!a.fresh||Date.now()-Date.parse(d.generated_at)>30*3600000;
      if(stale)section.append(el('p','갱신 지연 · 마지막 확정 일봉 '+a.daily_date,'institution-warning'));
      for(const [tf,label] of [['D','일봉'],['W','주봉'],['M','월봉']]){
        const t=a.timeframes?.[tf];if(!t)continue;const c=t.confirmed,current=t.latest,card=el('div',null,'tfcard');card.append(el('h4',label));
        card.append(el('p','확정 줍줍신호 · '+c.date+' '),badge(stale?'갱신 대기':c.signals.buy?'발생':'미발생',stale?null:c.signals.buy));
        card.append(el('p',(t.forming?'진행 중 · 마감 전 변동 가능':'마감 완료')+' · '+current.date+' '),badge(stale?'갱신 대기':current.signals.buy?'발생':'미발생',stale?null:current.signals.buy));
        card.append(el('p','상대신호 '+state(c.relative_signal)+' · 급락신호 '+drop(c.drop_signal)));
        const details=el('details',null,'signal-details');details.append(el('summary','유형별 신호 보기'));
        for(const [k,title] of [['sharp','급락형'],['normal','일반형'],['time','기간형'],['restricted','재상승형']])details.append(el('p',title+' · '+(stale?'갱신 대기':c.signals[k]?'발생':'미발생')));
        details.append(el('p','최근 확정 줍줍신호 '+(c.last_buy_date||'관측 이력 내 없음')));card.append(details);section.append(card);
      }box.append(section);
    }
    const activity=$('signal-activity');activity.replaceChildren();
    for(const [symbol,x] of Object.entries(d.activity||{})){
      const card=el('div',null,'checkpoint '+(x.active?'activity-highlight':''));card.append(el('strong',symbol+' 바닥관찰지수'),el('div',fmt(x.score)+'점','fear-number'),el('p','이전 '+(x.mean_n||0)+'거래일 평균 '+fmt(x.mean_score)+'점'),el('small',x.date+' 관측 · 평균 구간 '+(x.mean_start||'—')+'~'+(x.mean_end||'—')));activity.append(card);
    }
  }
  function tableRows(rows,id,isStock=false){
    const body=$(id);body.replaceChildren();
    for(const s of rows){const tr=el('tr');if(s.qualified)tr.className='qualified-row';const title=el('td');
      if(!isStock){const button=el('button',s.name+' ('+s.ticker+') ▾','table-button');button.onclick=()=>openEtf(s.ticker);title.append(button);}else title.textContent=s.ticker;
      tr.append(title,el('td',fmt(s.score),'score-cell '+(s.score>=70?'lime':'')),el('td',sign(s.comparison?.delta)),el('td',state(s.qualified)),el('td',state(s.relative_signal)),el('td',drop(s.drop_signal)));
      if(isStock)tr.append(el('td',fmt(s.weight_pct)+'%'));
      const price=el('td','$'+fmt(s.price));price.dataset.quoteSymbol=s.ticker;tr.append(price,el('td',s.date||'—'));body.append(tr);
    }
  }
  function renderSectors(){const sectors=snapshot.screen.sectors;tableRows(allSectors?sectors:sectors.slice(0,5),'sectorrows');$('showallsectors').textContent=allSectors?'TOP 5만 보기':'전체 산업 보기';$('sectorstatus').textContent='산업 '+sectors.length+'개 · 70점 이상 '+sectors.filter(x=>x.score>=70).length+'개 · 판정 충족 '+sectors.filter(x=>x.qualified).length+'개';}
  function openEtf(ticker){
    const group=snapshot.screen.top_etf_holdings.find(x=>x.etf===ticker);$('etfdetail').style.display='block';$('etftitle').textContent=ticker+' 구성종목 기회';
    const rows=(group?.holdings||[]).map(h=>({...snapshot.screen.stock_observations[h.ticker],...h}));tableRows(rows,'etfrows',true);
    $('etfstatus').textContent='비중 5% 이상 · '+(group?.holdings_source||'공식 편입비중 확인 중')+' · 점수와 판정은 각 종목 관측일 기준';
    $('etfdetail').scrollIntoView({behavior:'smooth',block:'start'});if(window.refreshLiveQuotes)window.refreshLiveQuotes();
  }
  function meter(prefix,value){$(prefix+'score').textContent=fmt(value);$(prefix+'pin').style.left=(typeof value==='number'?value:50)+'%';}
  function market(d){
    $('updated').textContent='지표·점수 기준일 '+(d.screen.observation_date||'—')+' 정규장 · 재계산 '+kst(d.screen.scored_at)+' · 최신 시세는 별도';
    meter('eq',d.sentiment.equity);meter('cr',d.sentiment.crypto);meter('cnn',d.bottom.fear?.cnn?.value);
    $('eqlabel').textContent='100에 가까울수록 기회';$('crlabel').textContent='100에 가까울수록 기회';$('cnnlabel').textContent=fearCompare(d.bottom.fear?.cnn||{});
    plot('sentchart',[['equity','증시','#6ea8ff'],['crypto','크립토','#ffa44e']].map(([key,name,color])=>({x:d.sentiment.history.map(r=>r.date),y:d.sentiment.history.map(r=>r[key]),name,mode:'lines+markers',line:{color}})),'점수',{yaxis:{range:[0,100],gridcolor:'#233d56'}});
    plot('indiceschart',Object.values(d.screen.market_indices||{}).filter(s=>s.rows?.length).map(s=>({name:s.name,x:s.rows.map(r=>r.date),y:s.rows.map(r=>r.close/s.rows[0].close*100),mode:'lines'})),'첫 관측일=100');
    const risk=$('risk-rows');risk.replaceChildren();
    for(const key of ['hy','vix','skew','yield10']){const x=d.insights.risk?.[key];if(!x)continue;const card=el('div',null,'kpi');card.append(el('span',x.name),el('strong',fmt(x.value)+(key==='hy'?'%p':key==='yield10'?'%':'')));const small=el('small','직전 '+x.previous_date+' '+fmt(x.previous)+' 대비 '+sign(x.delta)+' · 이전 '+x.mean_n+'관측 평균 '+fmt(x.mean)+' 대비 '+sign(x.mean_delta)+' · '+x.date);small.className='risk-mini';card.append(small);risk.append(card);}
    const net=d.insights.liquidity?.net;$('weekly-net').textContent=net?'순유동성 '+fmt(net.value,3)+'조 달러 · 전주 '+sign(net.delta)+' · 이전 '+net.mean_n+'주 평균 대비 '+sign(net.mean_delta)+' · '+net.date:'';
    renderSectors();
  }
  function cycles(d){
    const colors={USA:'#6ea8ff',G7:'#c299ff',Korea:'#ff8a9d',G20:'#f2bd6a'},names={USA:'미국',G7:'G7',Korea:'한국',G20:'G20'};
    const series=d.cli.series||{};const keys=['USA','G7','Korea','G20'].filter(k=>series[k]?.rows?.length);
    plot('cli-level-chart',keys.map(k=>({name:names[k],x:series[k].rows.map(r=>r.date),y:series[k].rows.map(r=>r.value),mode:'lines',line:{color:colors[k],width:2}})),'경기선행지수');
    plot('clichart',keys.map(k=>({name:names[k],x:series[k].acceleration.map(r=>r.date),y:series[k].acceleration.map(r=>r.value),mode:'lines+markers',line:{color:colors[k],width:2}})),'가속도',{yaxis:{gridcolor:'#233d56',zeroline:true,zerolinecolor:'#ddd'}});
    const box=$('cli-analysis');box.replaceChildren();for(const [k,x] of Object.entries(d.insights.cli||{})){if(!x)continue;const card=el('div',null,'cli-card');card.append(el('strong',(names[k]||k)+' · '+x.date),el('p',x.interpretation));box.append(card);}
  }
  load('./public_dashboard.json').then(d=>{snapshot=d;checkpoints(d);signals(d.bottom);market(d);cycles(d);}).catch(()=>{$('updated').textContent='공개용 자료를 불러오지 못했어. 새로고침 후 확인해.';});
  load('./news.json').then(d=>{const box=$('news-items');box.replaceChildren();$('news-time').textContent=kst(d.cutoff_at)+' 기준';(d.items||[]).forEach((x,i)=>{const card=el('article',null,'checkpoint');card.append(el('strong',(i+1)+'. '+x.title));(x.sentences||[]).forEach(t=>card.append(el('p',t)));(x.sources||[]).forEach(s=>card.append(link(s.label,s.url)));box.append(card);});}).catch(()=>{});
  load('../fed-liquidity/data.json').then(d=>{const keys=[['WALCL','총자산'],['WTREGEN','TGA'],['RRPONTSYD','ON RRP'],['WRESBAL','지급준비금'],['net','순유동성']];plot('chart',keys.map(([key,name])=>({name,x:d.rows.map(r=>r.date),y:d.rows.map(r=>r[key]),mode:'lines'})),'조 달러');const render=all=>{$('liqrows').replaceChildren();(all?d.rows.slice().reverse():d.rows.slice(-3).reverse()).forEach(r=>{const tr=el('tr');tr.append(el('td',r.date));keys.forEach(([key])=>tr.append(el('td',fmt(r[key],3))));$('liqrows').append(tr);});};render(false);let all=false;$('toggle-liquidity').onclick=()=>{all=!all;render(all);$('toggle-liquidity').textContent=all?'최근 3주만 보기':'이전 주간 수치 펼치기';};$('liqdate').textContent='최근 주간 관측 '+(d.rows.at(-1)?.date||'—');}).catch(()=>{});
  $('showallsectors').onclick=()=>{allSectors=!allSectors;renderSectors();};
  document.querySelectorAll('[data-table-toggle]').forEach(b=>b.onclick=()=>{$(b.dataset.tableToggle).classList.toggle('show-details');});
})();
