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
  load('./bottom.json').then(d => {
    const stale = !d.generated_at || Date.now()-new Date(d.generated_at).getTime() > 30*3600000;
    document.getElementById('bottom-time').textContent = '마지막 점검 ' + kst(d.generated_at) + ' · 나스닥100(^NDX) 기준 · 확정봉 사용' + (stale ? ' · 갱신 지연' : '');
    document.getElementById('bottom-summary').textContent = stale ? '갱신 지연 · 전체 판정 보류' : '가격·공포·거래량 ' + d.summary.numeric_pass + '/' + d.summary.numeric_total + ' 충족 · 필수 줍줍·패턴 연결 대기';
    const tbody = document.getElementById('bottom-rows'); tbody.replaceChildren();
    for (const check of d.checks || []) {
      const tr = element('tr');
      tr.append(element('td', check.label), element('td', num(check.value, check.unit)), element('td', check.date || '—'));
      const state = stale ? 'unknown' : check.status;
      const td = element('td', state === 'pass' ? '충족' : state === 'fail' ? '미충족' : '판정 대기');
      td.style.color = state === 'pass' ? '#64d9b1' : state === 'fail' ? '#ffa476' : '#a1b6d0';
      if (check.note) td.title = check.note;
      tr.append(td); tbody.append(tr);
    }
    document.getElementById('bottom-method').textContent = Object.values(d.method || {}).join(' / ');
    const box = document.getElementById('bottom-assets'); box.replaceChildren();
    for (const [name, a] of Object.entries(d.assets || {})) {
      const card = element('div', null, 'checkpoint');
      card.append(element('strong', name), element('p', '종가 ' + num(a.price) + ' · 주봉 CCI ' + num(a.weekly_cci) + ' · 월봉 CCI ' + num(a.monthly_cci) + ' · 주봉 RSI ' + num(a.weekly_rsi)), element('small', '가격 ' + a.date + ' / 주봉 ' + a.weekly_date + ' / 월봉 ' + a.monthly_date));
      box.append(card);
    }
  }).catch(() => {
    document.getElementById('bottom-time').textContent = '첫 자동 점검 대기';
    document.getElementById('bottom-summary').textContent = '데이터 갱신 전 · 전체 판정 보류';
  });
})();
