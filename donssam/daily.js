/* Static GitHub Pages reads versioned snapshots; no keys or browser-side writes. */
(() => {
  const element = (tag, text, cls) => {
    const e = document.createElement(tag);
    if (text != null) e.textContent = String(text);
    if (cls) e.className = cls;
    return e;
  };
  const num = (v, unit = '') => typeof v === 'number' && Number.isFinite(v) ? v.toLocaleString('ko-KR', {maximumFractionDigits: 2}) + unit : '—';
  const load = async path => {
    const r = await fetch(path + '?v=' + Date.now(), {cache: 'no-store'});
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };
  const kst = value => new Date(value).toLocaleString('ko-KR', {timeZone: 'Asia/Seoul'});
  load('./news.json').then(d => {
    const box = document.getElementById('news-items');
    box.replaceChildren();
    const cutoff = new Date(d.cutoff_at);
    const age = Date.now() - cutoff.getTime();
    const old = Number.isFinite(age) && age > 36*3600000;
    document.getElementById('news-time').textContent = kst(d.cutoff_at) + ' 기준 · ' + (old ? '이전 발행본' : '중요순') + ' · 조사 완료 후 게시';
    if (!Array.isArray(d.items) || !d.items.length) {
      box.textContent = '첫 뉴스 게시 대기'; return;
    }
    d.items.slice(0, 5).forEach((item, index) => {
      const card = element('article', null, 'checkpoint');
      card.style.marginBottom = '10px';
      card.append(element('strong', (index + 1) + '. ' + item.title));
      (item.sentences || []).forEach(sentence => {
        const p = element('p', sentence);
        p.style.marginBottom = '5px'; card.append(p);
      });
      const sources = element('small');
      (item.sources || []).slice(0, 3).forEach(source => {
        try {
          const url = new URL(source.url);
          if (!['https:', 'http:'].includes(url.protocol)) return;
          const a = element('a', source.label || url.hostname);
          a.href = url.href; a.target = '_blank'; a.rel = 'noopener noreferrer';
          a.style.color = '#9cc5ff'; a.style.marginRight = '12px'; sources.append(a);
        } catch (_) { /* invalid link is never inserted */ }
      });
      card.append(sources); box.append(card);
    });
  }).catch(() => {document.getElementById('news-items').textContent = '뉴스 파일을 불러오지 못했어. 잠시 후 새로고침해줘.';});
  const badge = (value, yes = '충족', no = '미충족') => element('span', value == null ? '자료 부족' : value ? yes : no, 'badge ' + (value == null ? 'wait' : value ? 'on' : 'off'));
  const line = (title, right) => {
    const e = element('div', null, 'signal-line'); e.append(element('span', title, 'signal-label'), right); return e;
  };
  load('./bottom.json').then(d => {
    if (d.schema_version !== 2) throw new Error('snapshot update pending');
    const stale = !d.generated_at || Date.now()-new Date(d.generated_at).getTime() > 30*3600000;
    document.getElementById('bottom-time').textContent = '마지막 점검 ' + kst(d.generated_at) + ' · 일/주/월 각각 판정 · 확정봉과 진행 중 봉 구분' + (stale ? ' · 갱신 지연' : '');
    const fg = document.getElementById('fear-grid'); fg.replaceChildren();
    for (const [key, name, url] of [['cnn','CNN 주식 공포·탐욕','https://www.cnn.com/markets/fear-and-greed'],['crypto','크립토 공포·탐욕 · Alternative.me','https://alternative.me/crypto/fear-and-greed-index/']]) {
      const x = d.fear?.[key]; const card = element('div', null, 'checkpoint');
      card.append(element('strong', name), element('div', num(x?.value), 'fear-number'));
      card.append(line('15 이하', badge(!x || !x.fresh || stale ? null : x.value <= 15)));
      const a = element('a', '출처 · ' + (x?.date || '수집 대기')); a.href = url; a.target='_blank'; a.rel='noopener noreferrer'; a.style.color='#9cc5ff';card.append(a);fg.append(card);
    }
    const box=document.getElementById('bottom-assets'); box.replaceChildren();
    for (const [key,title] of [['NDX','나스닥100 · NAS100'],['BTC','비트코인 · BTC']]) {
      const asset=d.assets?.[key]; const section=element('section', null, 'checkpoint');section.append(element('h3',title));
      if (!asset) {section.append(element('p','시세 수집 대기'));box.append(section);continue;}
      for (const [tf,label] of [['D','일봉'],['W','주봉'],['M','월봉']]) {
        const data=asset.timeframes[tf], c=data.confirmed, current=data.latest;
        const unavailable=stale || !asset.fresh;
        const card=element('div', null, 'tfcard');card.append(element('h4',label));
        card.append(line('확정 줍 · ' + c.date, badge(unavailable ? null : c.signals.buy, '신호 있음', '신호 없음')));
        card.append(line(data.forming ? '진행 중 줍 · 마감 전 변동 가능' : '최신 봉 · 마감 완료', badge(unavailable ? null : current.signals.buy,'신호 있음','신호 없음')));
        const cci=element('span',num(c.cci20));
        cci.append(document.createTextNode('  '),badge(c.cci20==null||unavailable?null:c.cci_below100,'≤ -100','> -100'),document.createTextNode(' '),badge(c.cci20==null||unavailable?null:c.cci_below200,'≤ -200','> -200'));
        card.append(line('CCI20 · 확정봉',cci));
        card.append(line('RSI14 · 확정봉',element('span',num(c.rsi['14']))));
        const relative=element('span',num(c.rsi_position)+' / 기준 ≤ '+c.rsi_limit+'  ');
        relative.append(badge(unavailable||c.rsi['14']==null?null:c.rsi_extreme));card.append(line('RSI 상대위치 · 별도 조건',relative));
        const detail=element('details',null,'signal-details');detail.append(element('summary','유형별 줍·RSI 조건 보기'));
        const names={sharp:'급락형',normal:'일반 조정형',time:'기간 조정형',restricted:'재상승형'};
        for (const [k,n] of Object.entries(names)) detail.append(line(n,badge(unavailable?null:c.signals[k])));
        detail.append(element('p','RSI14/30/100/200: '+['14','30','100','200'].map(n=>num(c.rsi[n])).join(' / ')));
        const conditions={sharp_rsi_drop:'급락형 RSI 하락폭: 5봉 11.5 또는 10봉 17 이상',sharp_rsi_low:'급락형 RSI 상대위치 ≤22',normal_rsi_low:'일반형 RSI14 ≤42 또는 RSI30 ≤46',normal_rsi_cooling:'일반형 RSI30 <10봉 전',long_rsi_cooling:'기간형 RSI100 ≤48 · RSI200 ≤54',short_rsi_turning:'기간형 RSI14 ≤48 · 전봉보다 상승'};
        for (const [k,n] of Object.entries(conditions)) detail.append(line(n,badge(unavailable || (k==='long_rsi_cooling' && !c.long_history_ready)?null:c.rsi_checks[k])));
        detail.append(element('p','최근 확정 줍: '+(c.last_buy_date||'관측 이력 내 없음')));
        if (!c.long_history_ready) detail.append(element('p','RSI200 계산 이력 부족 · 장기 RSI가 필요한 유형은 원본처럼 미충족 처리'));
        detail.append(element('p','진행 중 CCI20 '+num(current.cci20)+' / RSI14 '+num(current.rsi['14'])+' / RSI 상대위치 '+num(current.rsi_position)));
        card.append(detail);section.append(card);
      }
      box.append(section);
    }
    document.getElementById('signal-volume').textContent='거래량 참고 · '+Object.entries(d.volume||{}).map(([key,x])=>key+' '+num(x.value,'%')+' ('+x.date+')').join(' · ')+' · 직전20일 평균 대비 400%=4배';
    document.getElementById('bottom-method').textContent=Object.values(d.method||{}).join(' / ');
  }).catch(() => {
    document.getElementById('bottom-time').textContent='신호 데이터 갱신 대기';
  });
})();
