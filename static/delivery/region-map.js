/* 지역 현황 지도(8단계). 외부 라이브러리 없이 인라인 SVG로 그린다.
   데이터: #rmap-data(서버 계산 결과, 네 조합), 경계: korea-lite.json(전국, SVG 경로, 1단위=500m),
   sido/<코드>.json(시·도 세밀 경계, 확대할 때만 불러옴. 같은 좌표계). */
(function () {
  'use strict';
  var root = document.querySelector('[data-rmap]');
  var dataEl = document.getElementById('rmap-data');
  if (!root || !dataEl) return;
  var data = JSON.parse(dataEl.textContent);
  // tier: 전국 숫자에서 고른 보기 — all(전체) / wide(광역만) / basic(기초만)(형우 17:17)
  var state = { family: data.families[0].key, target: data.targets[0].key, sido: null, tier: 'all' };
  var SVG = 'http://www.w3.org/2000/svg';
  var $ = function (sel) { return root.querySelector(sel); };
  var canvas = $('[data-rmap-canvas]'), errorBox = $('[data-rmap-error]'), stage = $('[data-rmap-stage]');
  var bar = $('[data-rmap-bar]'), panel = $('[data-rmap-panel]'), head = $('[data-rmap-panel-head]');
  var summary = $('[data-rmap-summary]'), body = $('[data-rmap-panel-body]');
  var tip = $('[data-rmap-tip]'), card = $('[data-rmap-card]'), legendFac = $('[data-rmap-legend-fac]');
  var sheetToggle = $('[data-rmap-sheet-toggle]');
  // CSS의 좁은 화면 기준과 같다(리뷰 28)
  var narrow = window.matchMedia('(max-width: 900px), (max-width: 1100px) and (orientation: portrait)');
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var geo = null, svg = null, viewBox = null, sidoBox = {}, detailLoaded = {}, anim = null;
  var facLayer = null, centers = {}, cardOpener = null, unitLayer = null, selLayer = null, shadowPath = null;
  var badgeLayer = document.createElement('div');
  badgeLayer.className = 'rmap-badges';
  var labelLayer = document.createElement('div');  // 확대했을 때 시군구 이름(11d)
  labelLayer.className = 'rmap-labels';
  labelLayer.hidden = true;
  var zoomBox = null, pointers = {}, dragMoved = false, suppressClick = false, viewTimer = null;
  var MAX_ZOOM = 14;
  var legendBadge = $('[data-rmap-legend-badge]');

  /* ---------- 도우미 ---------- */
  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }
  function combo() { return data.combos[state.family + ':' + state.target]; }
  function label(list, key) { return list.filter(function (x) { return x.key === key; })[0].label; }
  function noun() { return state.target === 'council' ? '의회' : '지자체'; }
  function sidoRow(code) { return combo().sido.filter(function (s) { return s.code === code; })[0]; }
  function sidoInfo(code) { return data.sido.filter(function (s) { return s.code === code; })[0]; }
  /* 의회를 볼 때는 "천안시의회"처럼 대상이 드러나게 부른다(리뷰 26) */
  function unitLabel(code) { return data.units[code].name + (state.target === 'council' ? '의회' : ''); }
  function meter(adopted, total) {
    var m = el('span', { 'class': 'rmap-meter', 'aria-hidden': 'true' });
    var b = el('i');
    b.style.width = (total ? Math.round(adopted / total * 1000) / 10 : 0) + '%';
    m.appendChild(b);
    return m;
  }
  function symbol(org) {
    var s = el('span', { 'class': 'rmap-symbol', 'aria-hidden': 'true' });
    if (org.logo) { s.appendChild(el('img', { src: org.logo, alt: '' })); } else { s.textContent = org.initial; }
    return s;
  }
  function section(title, count) {
    var sec = el('section', { 'class': 'rmap-section' });
    var h = el('h2', { 'class': 'rmap-section-title' }, title);
    if (count != null) h.appendChild(el('span', {}, count + '곳'));
    sec.appendChild(h);
    return sec;
  }
  /* 제품 마킹 배지(S, I, B, D, P, C). 제품명 대신 보인다(spec v4 6) */
  function marks(org) {
    var box = el('span', { 'class': 'rmap-marks', 'aria-label': '제품 ' + org.markers.join(', ') });
    org.markers.forEach(function (m) {
      var mk = el('span', { 'class': 'rmap-mark', 'aria-hidden': 'true' }, m);
      mk.style.setProperty('--mark-color', (org.marker_colors || {})[m] || '#6B7580');  // 제품 관리 색
      box.appendChild(mk);
    });
    return box;
  }
  function facDot() { return el('span', { 'class': 'rmap-fac-dot', 'aria-hidden': 'true', 'data-fac': '' }); }
  function whenVisible(fn) {
    if (document.visibilityState === 'visible') requestAnimationFrame(fn); else fn();
  }

  /* ---------- 배치 재기(리뷰 1·4·16·29) ---------- */
  function layout() {
    natCache = null;
    root.style.setProperty('--rmap-sbw', (window.innerWidth - document.documentElement.clientWidth) + 'px');
    if (narrow.matches) {
      // 모바일(v5, 18:45 형우): 지도가 머리띠 아래 화면 전체를 쓰고, 전환 띠와 시트는 지도 위에 뜬다
      var top = stage.getBoundingClientRect().top + window.scrollY;
      root.style.setProperty('--rmap-stage-h', Math.max(420, window.innerHeight - top) + 'px');
      root.style.setProperty('--rmap-bar-h', (bar.offsetHeight + 8 + 8) + 'px');
      if (root.dataset.sheet === 'closed' && !root.dataset.sheetDrag) peekH = panel.offsetHeight;
      // 지도의 '보여줄 범위'는 접힌 시트 위까지(펼쳐도 지도를 다시 맞추지 않는다)
      root.style.setProperty('--rmap-sheet-h', peekH + 'px');
      document.body.style.paddingBottom = peekH + 'px';  // 바닥글이 접힌 시트 뒤에 가려지지 않게
    } else {
      document.body.style.paddingBottom = '';
      root.style.removeProperty('--rmap-sheet-h');
      root.style.setProperty('--rmap-bar-h', (bar.offsetHeight + 28 + 16) + 'px');
      // 지도 높이 = 창 높이 - (지도 밖 페이지 높이). 데스크톱에서 세로 스크롤 없이 한 화면에 들어오게 한다
      // body.scrollHeight는 창 높이에 묶이지 않는 실제 내용 높이라, 창을 키워도 다시 늘어난다
      var rest = document.body.scrollHeight - stage.offsetHeight;
      root.style.setProperty('--rmap-stage-h', Math.max(560, window.innerHeight - rest) + 'px');
    }
  }

  /* ---------- 아래 시트(v5): 접힘 / 반 / 전부 3단. 손잡이를 끌면 가까운 단에 붙고, 누르면 접힘↔반 ---------- */
  var peekH = 90, sheetDrag = null, suppressSheetClick = false;
  function setSheet(open) {
    var st = open === 'full' ? 'full' : open ? 'open' : 'closed';
    root.dataset.sheet = st;
    panel.style.height = '';
    sheetToggle.setAttribute('aria-expanded', String(st !== 'closed'));
    sheetToggle.setAttribute('aria-label', st === 'closed' ? '목록 펼치기' : '목록 접기');
    sheetTouchAction();
    if (narrow.matches) whenVisible(layout);
  }
  function sheetStops() {
    var top = stage.getBoundingClientRect().top;
    return { closed: peekH, open: Math.round(window.innerHeight * 0.52), full: Math.round(window.innerHeight - Math.max(top, 0) - 8) };
  }
  sheetToggle.addEventListener('click', function () {
    if (suppressSheetClick) { suppressSheetClick = false; return; }
    setSheet(root.dataset.sheet === 'closed');
  });
  /* 시트 끌기(19:50 형우): 손잡이뿐 아니라 패널 어디서든 끈다. '전부'일 때 목록 안에서는 목록이 스크롤되고,
     위쪽(손잡이·머리·요약)을 끌면 내려간다. 카드가 떠 있으면 시트와 같이 올라가며 흐려지다 사라진다 */
  function sheetTouchAction() {
    body.style.touchAction = !narrow.matches ? '' : root.dataset.sheet === 'full' ? 'pan-y' : 'none';
  }
  panel.addEventListener('pointerdown', function (ev) {
    if (!narrow.matches || (ev.pointerType === 'mouse' && ev.button !== 0)) return;
    if (root.dataset.sheet === 'full' && body.contains(ev.target)) return;  // 전부: 목록은 스크롤
    sheetDrag = { y: ev.clientY, h: panel.offsetHeight, moved: false, id: ev.pointerId };
  });
  window.addEventListener('pointermove', function (ev) {
    if (!sheetDrag || ev.pointerId !== sheetDrag.id) return;
    var dy = ev.clientY - sheetDrag.y;
    if (!sheetDrag.moved && Math.abs(dy) < 6) return;
    if (!sheetDrag.moved) {  // 끌기 시작: 목록을 보이게 하고 높이를 손가락에 맞춘다
      sheetDrag.moved = true;
      root.dataset.sheetDrag = '1';
      if (root.dataset.sheet === 'closed') root.dataset.sheet = 'open';
      try { panel.setPointerCapture(ev.pointerId); } catch (e) { /* 합성 이벤트 등 */ }
    }
    var st = sheetStops(), h = Math.max(st.closed, Math.min(st.full, sheetDrag.h - dy));
    panel.style.height = h + 'px';
    if (!card.hidden) {
      var up = Math.max(0, h - sheetDrag.h);
      card.style.transform = 'translateY(' + (-up) + 'px)';
      card.style.opacity = String(Math.max(0, 1 - up / 160));
    }
  });
  function endSheetDrag(ev) {
    if (!sheetDrag || ev.pointerId !== sheetDrag.id) return;
    var moved = sheetDrag.moved;
    sheetDrag = null;
    root.dataset.sheetDrag = '';
    if (!moved) return;  // 누름은 click이 처리한다
    suppressSheetClick = true;
    setTimeout(function () { suppressSheetClick = false; }, 0);
    var h = panel.offsetHeight, st = sheetStops(), best = 'closed';
    ['open', 'full'].forEach(function (k) { if (Math.abs(h - st[k]) < Math.abs(h - st[best])) best = k; });
    if (!card.hidden) { if (best !== 'closed') { closeCard(false); } else { card.style.transform = ''; card.style.opacity = ''; } }
    setSheet(best === 'closed' ? false : best === 'full' ? 'full' : true);
  }
  window.addEventListener('pointerup', endSheetDrag);
  window.addEventListener('pointercancel', endSheetDrag);
  panel.addEventListener('click', function (ev) {  // 끌고 난 뒤 손을 뗀 자리의 버튼은 눌리지 않게
    if (suppressSheetClick) { ev.stopPropagation(); ev.preventDefault(); }
  }, true);

  /* 모바일 머리띠(v5): 지도 화면의 좁은 화면에서는 메뉴를 ☰ 버튼 안에 접는다(다른 화면은 그대로, CSS도 이 화면에만) */
  (function () {
    var inner = document.querySelector('.topbar-inner');
    if (!inner || !inner.querySelector('nav, form')) return;
    var mb = el('button', { type: 'button', 'class': 'rmap-menu-btn', 'aria-expanded': 'false', 'aria-label': '메뉴 열기', 'data-rmap-menu': '' });
    mb.appendChild(el('span', { 'aria-hidden': 'true' }));
    mb.addEventListener('click', function () {
      var open = document.body.classList.toggle('rmap-menu-open');
      mb.setAttribute('aria-expanded', String(open));
      mb.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
      layout();
    });
    inner.appendChild(mb);
  })();

  /* ---------- 전환(한 번만 만들고 상태만 바꾼다. 리뷰 18) ---------- */
  [['family', data.families], ['target', data.targets]].forEach(function (pair) {
    var box = $('[data-rmap-switch="' + pair[0] + '"]');
    pair[1].forEach(function (opt) {
      var b = el('button', { type: 'button', 'data-value': opt.key }, opt.label);
      b.addEventListener('click', function () { state[pair[0]] = opt.key; update(); });
      box.appendChild(b);
    });
  });
  function syncSwitches() {
    root.querySelectorAll('[data-rmap-switch]').forEach(function (box) {
      var key = box.dataset.rmapSwitch;
      box.querySelectorAll('button').forEach(function (b) {
        b.setAttribute('aria-pressed', String(state[key] === b.dataset.value));
      });
    });
    if (legendBadge) legendBadge.lastChild.textContent = state.target === 'council' ? '의회' : '광역';
    root.dataset.tier = state.tier;
  }

  /* ---------- 패널 ---------- */
  /* 요약 숫자. parts가 있으면 아래에 광역·기초 두 줄을 나눠 보인다(spec v4 7) */
  function renderSummary(title, adopted, total, parts) {
    summary.textContent = '';
    summary.appendChild(el('p', { 'class': 'rmap-summary-label' }, title));
    var v = el('p', { 'class': 'rmap-summary-value', 'data-rmap-national': '' });
    v.appendChild(el('strong', {}, String(adopted)));
    v.appendChild(el('span', {}, '/ ' + total));
    summary.appendChild(v);
    var m = meter(adopted, total);
    m.classList.add('rmap-summary-bar');
    summary.appendChild(m);
    if (!parts) return;
    // 광역·기초 칸은 보기 버튼이다. 누르면 그것만 지도·목록에 보이고, 다시 누르면 전체로 돌아간다
    var dl = el('div', { 'class': 'rmap-summary-parts', role: 'group', 'aria-label': '광역·기초 나눠 보기' });
    parts.forEach(function (pt) {
      // 광역 = 켜고 끄는 보기 버튼. 기초 = 원래 보기로 돌아가는 버튼(눌린 상태 없음, 17:34 형우)
      var row = el('button', { type: 'button', 'data-rmap-part': pt.key });
      if (pt.key === 'wide') row.setAttribute('aria-pressed', String(state.tier === 'wide'));
      row.appendChild(el('span', { 'class': 'rmap-part-label' }, pt.label));
      var dd = el('span', { 'class': 'rmap-part-value', 'data-part-value': '' });
      dd.appendChild(el('b', {}, String(pt.adopted)));
      dd.appendChild(document.createTextNode(' / ' + pt.total));
      row.appendChild(dd);
      row.addEventListener('click', function () {
        state.tier = pt.key === 'wide' && state.tier !== 'wide' ? 'wide' : 'all';
        update();
        var again = summary.querySelector('[data-rmap-part="' + pt.key + '"]');
        if (again) again.focus({ preventScroll: true });
      });
      dl.appendChild(row);
    });
    summary.appendChild(dl);
  }

  function renderNational() {
    var c = combo();
    head.textContent = '';
    var n = c.national, council = state.target === 'council', tier = state.tier;
    var top = tier === 'wide' ? n.wide : n;
    var tierWord = tier === 'wide' ? (council ? ' · 광역의회' : ' · 광역') : '';
    renderSummary(label(data.families, state.family) + ' 도입 ' + noun() + tierWord, top.adopted, top.total, [
      { key: 'wide', label: council ? '광역의회' : '광역', adopted: n.wide.adopted, total: n.wide.total },
      { key: 'basic', label: council ? '기초의회' : '기초', adopted: n.basic.adopted, total: n.basic.total }
    ]);
    body.textContent = '';
    if (tier === 'wide') { renderWideList(c); return; }
    var list = el('ol', { 'class': 'rmap-sido-list', 'aria-label': '시·도별 도입 현황' });
    c.sido.forEach(function (s) {
      var li = el('li');
      var row = el('button', { type: 'button', 'class': 'rmap-sido-row', 'data-sido': s.code, title: s.name });
      row.appendChild(el('span', { 'class': 'rmap-sido-name' }, s.short));
      row.appendChild(meter(s.adopted, s.total));
      var cnt = el('span', { 'class': 'rmap-sido-count' });
      cnt.appendChild(el('b', {}, String(s.adopted)));
      cnt.appendChild(document.createTextNode(' / ' + s.total));
      row.appendChild(cnt);
      row.setAttribute('aria-label', s.name + ' ' + s.total + '곳 중 ' + s.adopted + '곳 도입');
      row.addEventListener('click', function () { selectSido(s.code, true); });
      li.appendChild(row);
      list.appendChild(li);
    });
    body.appendChild(list);
    // 미지정 기관 안내: 서버가 기획팀(관리자)에게만 목록을 보낸다(리뷰 9)
    if (c.unassigned.length) {
      var un = section('지도에 올리지 못한 기관', c.unassigned.length);
      un.setAttribute('data-rmap-unassigned', '');
      un.appendChild(el('p', { 'class': 'rmap-empty-note' }, '소재지가 비어 있어 지도에 칠하지 못했습니다. 고객사 관리에서 소재지를 정하면 지도에 나옵니다.'));
      var ul = el('ul', { 'class': 'rmap-orgs' });
      c.unassigned.forEach(function (o) { ul.appendChild(orgItem(o, null)); });
      un.appendChild(ul);
      body.appendChild(un);
    }
  }

  function orgItem(org, unitCode) {
    var li = el('li');
    var row = el(unitCode ? 'button' : 'div', { 'class': 'rmap-org', 'data-org': org.id });
    if (unitCode) {
      row.setAttribute('type', 'button');
      row.addEventListener('click', function () { openCardFrom(row, unitCode); });
    }
    row.appendChild(symbol(org));
    var t = el('span', { 'class': 'rmap-org-text' });
    t.appendChild(el('span', { 'class': 'rmap-org-name' }, org.name));
    var meta = el('span', { 'class': 'rmap-org-meta' });
    meta.appendChild(marks(org));
    meta.appendChild(el('span', { 'class': 'rmap-org-year' }, org.year));
    t.appendChild(meta);
    row.appendChild(t);
    li.appendChild(row);
    return li;
  }

  /* 광역 보기의 왼쪽 목록: 막대 대신 광역 기관 카드(심볼·이름·마킹·도입 연도). 빈 칸은 '미도입' 카드. 누르면 그 시·도로 */
  function renderWideList(c) {
    var list = el('ul', { 'class': 'rmap-wide-list', 'data-rmap-wide-list': '', 'aria-label': '광역 기관 도입 현황' });
    c.sido.forEach(function (s) {
      // 세종·제주는 그 한 면의 기관이 곧 광역 기관이다
      var orgs = s.whole ? ((c.units[s.adopted_units.concat(s.missing)[0]] || {}).orgs || []) : s.wide_orgs;
      var cards = orgs.slice(0, s.wide_slots).map(function (o) { return [o, true]; });
      while (cards.length < s.wide_slots) cards.push([{ name: wideName(s.code) }, false]);
      cards.forEach(function (pair) {
        var li = el('li');
        var b = wideCard(pair[0], pair[1], 'button');
        b.setAttribute('data-sido', s.code);
        b.addEventListener('click', function () { selectSido(s.code, true); });
        li.appendChild(b);
        list.appendChild(li);
      });
    });
    body.appendChild(list);
  }

  function wideCard(org, isIn, tag) {
    var box = el(tag || 'div', { 'class': 'rmap-wide-card' + (isIn ? ' is-in' : ''), 'data-rmap-wide-card': isIn ? 'in' : 'out' });
    if (tag === 'button') box.setAttribute('type', 'button');
    if (org.id) box.setAttribute('data-org', org.id);
    box.appendChild(isIn ? symbol(org) : el('span', { 'class': 'rmap-symbol is-empty', 'aria-hidden': 'true' }, org.name.slice(0, 1)));
    var t = el('span', { 'class': 'rmap-wide-text' });
    t.appendChild(el('span', { 'class': 'rmap-org-name' }, org.name));
    if (isIn) {
      var meta = el('span', { 'class': 'rmap-org-meta' });
      meta.appendChild(marks(org));
      meta.appendChild(el('span', { 'class': 'rmap-org-year' }, org.year));
      t.appendChild(meta);
    }
    box.appendChild(t);
    box.appendChild(el('span', { 'class': 'rmap-status' + (isIn ? ' is-in' : ''), 'data-field': 'status' }, isIn ? '도입' : '미도입'));
    return box;
  }

  function renderSido() {
    var c = combo();
    var s = sidoRow(state.sido);
    head.textContent = '';
    var back = el('button', { type: 'button', 'class': 'rmap-back', 'data-rmap-back': '' }, '← 전국');
    back.addEventListener('click', function () { selectSido(null, true, state.sido); });
    head.appendChild(back);
    head.appendChild(el('h2', { 'class': 'rmap-panel-title', 'data-rmap-sido-title': '' }, s.name));
    // 시·도 화면은 기초 기준. 세종·제주는 그 한 면이 곧 광역이다
    var tier = s.whole ? (state.target === 'council' ? '광역의회' : '광역') : (state.target === 'council' ? '기초의회' : '기초 ' + noun());
    renderSummary(label(data.families, state.family) + ' 도입 · ' + tier, s.adopted, s.total);
    body.textContent = '';

    if (!s.whole) {  // 세종·제주는 광역 기관이 곧 그 면이라 '도입한 곳'에만 둔다(리뷰 24)
      var wide = section(state.target === 'council' ? '광역의회' : '광역 기관');
      var w = el('div', { 'class': 'rmap-wide', 'data-rmap-wide': '' });
      // 광역 상태 카드(spec v4 1-D): 도입한 광역 기관마다 한 장, 빈 칸(전남광주 2칸 중 1칸 등)은 '미도입' 카드
      s.wide_orgs.slice(0, s.wide_slots).forEach(function (o) { w.appendChild(wideCard(o, true)); });
      for (var i = Math.min(s.wide_orgs.length, s.wide_slots); i < s.wide_slots; i++) {
        w.appendChild(wideCard({ name: s.name + (state.target === 'council' ? '의회' : '') }, false));
      }
      s.wide_facilities.forEach(function (o) {
        var b = el('button', { type: 'button', 'class': 'rmap-chip', 'data-org': o.id, 'data-fac': '' });
        b.appendChild(facDot());
        b.appendChild(document.createTextNode(o.name));
        b.addEventListener('click', function () { openOrgsCard(b, s.name + ' 시설·공기업', [o]); });
        w.appendChild(b);
      });
      wide.appendChild(w);
      body.appendChild(wide);
    }

    var miss = section('빠진 곳', s.missing.length);
    if (s.missing.length) {
      var ul = el('ul', { 'class': 'rmap-chips', 'data-rmap-missing': '' });
      s.missing.forEach(function (code) {
        var li = el('li', { 'data-unit': code });
        var b = el('button', { type: 'button', 'class': 'rmap-chip' });
        b.appendChild(el('span', { 'data-unit-name': '' }, unitLabel(code)));
        if (c.units[code] && c.units[code].facilities.length) b.appendChild(facDot());
        b.addEventListener('click', function () { openCardFrom(b, code); });
        li.appendChild(b);
        ul.appendChild(li);
      });
      miss.appendChild(ul);
    } else {
      miss.appendChild(el('p', { 'class': 'rmap-empty-note' }, '빠진 곳이 없습니다.'));
    }

    var items = [];
    s.adopted_units.forEach(function (code) {
      (c.units[code] ? c.units[code].orgs : []).forEach(function (o) { items.push([o, code]); });
    });
    var done = section('도입한 곳', items.length);  // 숫자와 목록 줄 수를 기관 수로 맞춘다(리뷰 25)
    if (items.length) {
      var ol = el('ul', { 'class': 'rmap-orgs', 'data-rmap-adopted': '' });
      items.forEach(function (it) { ol.appendChild(orgItem(it[0], it[1])); });
      done.appendChild(ol);
    } else {
      done.appendChild(el('p', { 'class': 'rmap-empty-note' }, '아직 도입한 곳이 없습니다.'));
    }
    body.appendChild(done);  // 도입한 곳을 빠진 곳보다 위에(19:50 형우)
    body.appendChild(miss);
  }

  function paint() {
    if (!svg) return;
    var c = combo();
    svg.querySelectorAll('.rmap-unit').forEach(function (p) {
      var slot = c.units[p.dataset.code];
      // 광역 보기(17:34): 시·도 전체 면을 광역 도입으로 칠한다. 전남광주처럼 2칸 중 1칸이면 흐리게(is-part)
      if (state.tier === 'wide') {
        var w = sidoRow(p.dataset.sido);
        p.classList.toggle('is-in', w.wide_count >= w.wide_slots);
        p.classList.toggle('is-part', w.wide_count > 0 && w.wide_count < w.wide_slots);
      } else {
        p.classList.toggle('is-in', !!(slot && slot.state === 'in'));
        p.classList.remove('is-part');
      }
      p.classList.toggle('is-dim', !!state.sido && p.dataset.sido !== state.sido);
    });
    svg.querySelectorAll('.rmap-sido').forEach(function (p) {
      p.classList.toggle('is-selected', p.dataset.code === state.sido);
    });
    liftSido();
    drawMarkers();
    drawBadges();
    if (root.dataset.zoom !== 'moving') drawLabels();
  }

  /* 광역 기관 짧은 이름: 서울특별시 → 서울시, 충청남도 → 충남도, 강원특별자치도 → 강원도, 전남광주통합특별시 → 전남광주. 의회는 + 의회 */
  function wideName(code) {
    var info = sidoInfo(code), name = info.name, short = info.short;
    var base = code === '12' ? short : /도$/.test(name) ? short + '도' : short + '시';
    return base + (state.target === 'council' ? '의회' : '');
  }
  /* 광역 배지(spec v4 1-A, 17:17 수정): 유리 알약 + 광역(의회) 기관 이름. 점 채움 = 도입. 세종·제주도 표시.
     전국 크기에서만 보이고, 시·도를 고르거나 확대하면 사라진다(그때는 광역 상태 카드로 본다).
     글자 크기가 확대와 무관하게 같도록 SVG 밖 HTML 층에 두고, 화면 좌표로 옮긴다 */
  /* 고른 시·도는 테두리 대신 그림자(19:50 형우). 그 시·도 면들을 다른 면 위 묶음으로 옮기고, 바로 밑에 외곽선 모양 그림자를 깐다 */
  var liftedSido = null;
  function liftSido() {
    if (!svg || liftedSido === state.sido) { if (svg && state.sido) shadowPath.setAttribute('d', sidoOutline(state.sido)); return; }
    while (selLayer.firstChild) unitLayer.appendChild(selLayer.firstChild);
    liftedSido = state.sido;
    shadowPath.style.display = state.sido ? '' : 'none';
    if (!state.sido) return;
    unitLayer.querySelectorAll('.rmap-unit[data-sido="' + state.sido + '"]').forEach(function (p) { selLayer.appendChild(p); });
    shadowPath.setAttribute('d', sidoOutline(state.sido));
  }
  function sidoOutline(code) { var o = svg.querySelector('.rmap-sido[data-code="' + code + '"]'); return o ? o.getAttribute('d') : ''; }
  function drawBadges() {
    var c = combo();
    badgeLayer.textContent = '';
    c.sido.forEach(function (s) {
      var info = sidoInfo(s.code);
      if (!info.label) return;
      var full = s.wide_count >= s.wide_slots, part = s.wide_count > 0 && !full;
      // 19:50 형우: 점 없이 배지를 색으로 채움(도입)/안 채움(미도입). 누르면 광역 기관 카드
      var name = wideName(s.code) + (s.wide_slots > 1 ? ' ' + s.wide_count + '/' + s.wide_slots : '');
      var b = el('span', { role: 'button', tabindex: '0', 'class': 'rmap-badge' + (full ? ' is-in' : part ? ' is-part' : ''),
                           'data-sido': s.code, 'data-state': full ? 'in' : part ? 'part' : 'out',
                           'aria-label': name + ' ' + (full ? '도입' : part ? '일부 도입' : '미도입') + ', 누르면 광역 기관 카드' }, name);
      b.addEventListener('click', function (ev) {
        ev.stopPropagation();
        if (suppressClick) { suppressClick = false; return; }  // 배지 위에서 시작해 끈 것은 누름이 아니다
        openWideCard(s.code, b);
      });
      b.addEventListener('keydown', function (ev) { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); openWideCard(s.code, b); } });
      badgeLayer.appendChild(b);
    });
    badgeLayer.hidden = !!state.sido || zoomedIn();
    placeBadges();
  }
  /* 전국 보기보다 1.3배 넘게 확대했는지(자유 확대 대비) */
  function zoomedIn() { return !!(geo && viewBox && svg) && viewBox[2] < nationalBox()[2] / 1.3; }
  function placeBadges() {
    if (!svg || !badgeLayer.firstChild) return;
    badgeLayer.hidden = !!state.sido || zoomedIn();
    if (badgeLayer.hidden) return;
    var m = svg.getScreenCTM(), cr = canvas.getBoundingClientRect(), pt = svg.createSVGPoint();
    if (!m) return;
    var items = [];
    badgeLayer.querySelectorAll('.rmap-badge').forEach(function (b) {
      var l = sidoInfo(b.dataset.sido).label;
      pt.x = l[0]; pt.y = l[1];
      var q = pt.matrixTransform(m);
      items.push({ el: b, x: q.x - cr.left, y: q.y - cr.top, w: b.offsetWidth, h: b.offsetHeight });
    });
    // 화면 크기에 따라 배지끼리 겹치면(서울·인천, 세종·충남 등) 위아래로 조금씩 밀어 떼어 놓는다
    for (var round = 0; round < 12; round++) {
      var moved = false;
      for (var i = 0; i < items.length; i++) {
        for (var j = i + 1; j < items.length; j++) {
          var A = items[i], B = items[j], gap = 3;
          if (Math.abs(A.x - B.x) >= (A.w + B.w) / 2 + gap) continue;
          var need = (A.h + B.h) / 2 + gap - Math.abs(A.y - B.y);
          if (need <= 0) continue;
          var up = A.y <= B.y ? A : B, down = up === A ? B : A;
          up.y -= need / 2; down.y += need / 2; moved = true;
        }
      }
      if (!moved) break;
    }
    items.forEach(function (it) { it.el.style.left = it.x + 'px'; it.el.style.top = it.y + 'px'; });
  }

  function update() {
    closeCard(false);
    hideTip();
    syncSwitches();
    if (state.sido) { renderSido(); } else { renderNational(); }
    paint();
    root.dataset.combo = state.family + ':' + state.target;
    root.dataset.family = state.family;  // 제품군 색(도청 파랑 / 불법촬영 코랄)은 CSS가 이 값으로 바꾼다
    root.dataset.sido = state.sido || '';
    layout();
  }

  /* ---------- 시설·공기업 표시 ---------- */
  function center(code) {
    if (!centers[code]) {
      var b = svg.querySelector('.rmap-unit[data-code="' + code + '"]').getBBox();
      centers[code] = [b.x + b.width / 2, b.y + b.height / 2];
    }
    return centers[code];
  }
  /* 화면에서 반지름이 7px보다 작아지지 않게 한다(리뷰 23) */
  function markerRadius() {
    var w = svg.clientWidth || 1, h = svg.clientHeight || 1;
    var perPx = Math.max(viewBox[2] / w, viewBox[3] / h);
    // 화면에서 늘 반지름 7px(18:03 형우: 11d에서 지도를 화면 전체로 넓히며 viewBox 기준 크기가 커지던 것을 고침)
    return 7 * perPx;
  }
  function drawMarkers() {
    var c = combo();
    var any = c.sido.some(function (s) { return s.wide_facilities.length; });
    facLayer.textContent = '';
    var r = markerRadius();
    Object.keys(c.units).forEach(function (code) {
      if (!c.units[code].facilities.length) return;
      any = true;
      var xy = center(code);
      var m = document.createElementNS(SVG, 'circle');
      m.setAttribute('cx', xy[0]); m.setAttribute('cy', xy[1]); m.setAttribute('r', r);
      m.setAttribute('class', 'rmap-fac' + (state.sido && data.units[code].sido !== state.sido ? ' is-dim' : ''));
      m.dataset.code = code;
      facLayer.appendChild(m);
    });
    legendFac.hidden = !any;
  }

  /* ---------- 말풍선(마우스) ---------- */
  function place(box, x, y) {
    var r = stage.getBoundingClientRect(), w = box.offsetWidth, h = box.offsetHeight;
    var left = x - r.left + 14, top = y - r.top + 14;
    if (left > r.width - w - 8) left = x - r.left - w - 14;
    if (top > r.height - h - 8) top = y - r.top - h - 14;
    box.style.left = Math.max(8, left) + 'px';
    box.style.top = Math.max(8, top) + 'px';
  }
  function showTip(code, x, y, onMarker) {
    var c = combo(), slot = c.units[code], isIn = !!(slot && slot.state === 'in');
    tip.textContent = '';
    if (onMarker && slot && slot.facilities.length) {  // 시설 표시 위: 시설·공기업 목록(리뷰 11)
      tip.appendChild(el('strong', {}, data.units[code].name + ' 시설·공기업'));
      slot.facilities.forEach(function (o) {
        var line = el('span', { 'class': 'rmap-tip-line' }, o.name + ' ');
        line.appendChild(marks(o));
        line.appendChild(document.createTextNode(' ' + o.year));
        tip.appendChild(line);
      });
    } else {
      tip.appendChild(el('strong', {}, unitLabel(code)));
      tip.appendChild(el('span', { 'class': isIn ? 'is-in' : 'is-out' }, isIn ? '도입' : '미도입'));
      if (slot && slot.facilities.length) tip.appendChild(el('span', { 'class': 'is-out' }, ' · 시설·공기업 ' + slot.facilities.length + '곳'));
    }
    tip.hidden = false;
    tip.dataset.unit = code;
    place(tip, x, y);
  }
  function hideTip() { tip.hidden = true; tip.dataset.unit = ''; }

  /* ---------- 기관 카드 ---------- */
  function cardOrg(org) {
    var box = el('div', { 'class': 'rmap-card-org', 'data-org': org.id });
    box.appendChild(symbol(org));
    var t = el('div');
    t.appendChild(el('p', { 'class': 'rmap-card-name', 'data-field': 'name' }, org.name));
    t.appendChild(el('p', { 'class': 'rmap-card-family', 'data-field': 'family' }, label(data.families, state.family)));
    box.appendChild(t);
    var cells = el('dl', { 'class': 'rmap-card-cells' });
    var a = el('div'); a.appendChild(el('dt', {}, '제품'));
    var dd = el('dd', { 'data-field': 'marks' }); dd.appendChild(marks(org)); a.appendChild(dd);
    var b = el('div'); b.appendChild(el('dt', {}, '도입 연도')); b.appendChild(el('dd', { 'data-field': 'year' }, org.year));
    cells.appendChild(a); cells.appendChild(b);
    box.appendChild(cells);
    return box;
  }
  function cardShell() {
    hideTip();
    card.textContent = '';
    var close = el('button', { type: 'button', 'class': 'rmap-card-close', 'aria-label': '닫기', 'data-rmap-card-close': '' }, '×');
    close.addEventListener('click', function () { closeCard(true); });
    card.appendChild(close);
    return close;
  }
  function showCard(close, x, y) {
    card.hidden = false;
    if (narrow.matches) { setSheet(false); } else { place(card, x, y); }  // 좁은 화면은 아래에 고정(CSS)
    close.focus({ preventScroll: true });
  }
  /* 누른 시군구는 카드가 열려 있는 동안 마우스를 올렸을 때 색을 유지한다(20:20 형우) */
  function setPicked(code) {
    if (!svg) return;
    svg.querySelectorAll('.rmap-unit.is-picked').forEach(function (p) { p.classList.remove('is-picked'); });
    if (code) { var u = svg.querySelector('.rmap-unit[data-code="' + code + '"]'); if (u) u.classList.add('is-picked'); }
  }
  function openCard(code, x, y) {
    setPicked(code);
    var c = combo(), slot = c.units[code] || { state: 'out', orgs: [], facilities: [] }, u = data.units[code];
    var close = cardShell();
    if (slot.state === 'in') {
      card.appendChild(el('p', { 'class': 'rmap-card-unit' }, u.whole ? u.name : sidoInfo(u.sido).short + ' ' + u.name));
      slot.orgs.forEach(function (o) { card.appendChild(cardOrg(o)); });
    } else {
      var out = el('p', { 'class': 'rmap-card-out', 'data-field': 'name' }, unitLabel(code));
      out.appendChild(el('span', { 'data-field': 'status' }, '미도입'));
      card.appendChild(out);
    }
    if (slot.facilities.length) {
      var fac = el('div', { 'class': 'rmap-card-fac', 'data-rmap-card-fac': '' });
      var ft = el('p', { 'class': 'rmap-card-fac-title' });
      ft.appendChild(facDot());
      ft.appendChild(document.createTextNode('시설·공기업 도입'));
      fac.appendChild(ft);
      slot.facilities.forEach(function (o) { fac.appendChild(cardOrg(o)); });
      card.appendChild(fac);
    }
    card.dataset.unit = code;
    showCard(close, x, y);
  }
  /* 목록에서 연 카드는 패널 오른쪽(패널이 왼쪽에 있다), 누른 줄 높이에 띄운다. place()가 14px를 더한다 */
  function besidePanel(opener) {
    var r = panel.getBoundingClientRect(), b = opener.getBoundingClientRect();
    return [r.right + 2, b.top];
  }
  /* 광역 배지를 누르면: 그 시·도의 광역 기관(세종·제주는 그 면의 기관) 카드. 빈 칸은 미도입 */
  function openWideCard(code, opener) {
    var c = combo(), s = sidoRow(code), council = state.target === 'council';
    var orgs = s.whole ? ((c.units[s.adopted_units.concat(s.missing)[0]] || {}).orgs || []) : s.wide_orgs;
    var close = cardShell();
    card.appendChild(el('p', { 'class': 'rmap-card-unit' }, s.name + (council ? ' 광역의회' : ' 광역 기관')));
    orgs.slice(0, s.wide_slots).forEach(function (o) { card.appendChild(cardOrg(o)); });
    for (var i = Math.min(orgs.length, s.wide_slots); i < s.wide_slots; i++) {
      var out = el('p', { 'class': 'rmap-card-out', 'data-field': 'name' }, wideName(code));
      out.appendChild(el('span', { 'data-field': 'status' }, '미도입'));
      card.appendChild(out);
    }
    card.dataset.unit = '';
    card.dataset.wide = code;
    var r = opener.getBoundingClientRect();
    showCard(close, r.left + r.width / 2 - 14, r.bottom - 6);
    cardOpener = opener;
  }
  function openOrgsCard(opener, title, orgs) {
    var close = cardShell(), at = besidePanel(opener);
    cardOpener = opener;
    card.appendChild(el('p', { 'class': 'rmap-card-unit' }, title));
    orgs.forEach(function (o) { card.appendChild(cardOrg(o)); });
    card.dataset.unit = '';
    showCard(close, at[0], at[1]);
  }
  function openCardFrom(opener, code) {
    var at = besidePanel(opener);
    openCard(code, at[0], at[1]);
    cardOpener = opener;  // 닫으면 누른 줄로 포커스를 돌려준다(리뷰 19 일부)
  }
  function closeCard(returnFocus) {
    if (card.hidden) return;
    card.hidden = true;
    card.dataset.unit = '';
    card.dataset.wide = '';
    setPicked(null);
    card.style.transform = ''; card.style.opacity = '';
    if (returnFocus && cardOpener && document.body.contains(cardOpener)) cardOpener.focus({ preventScroll: true });
    cardOpener = null;
  }

  /* ---------- 확대 ---------- */
  function setViewBox(vb) {
    viewBox = vb;
    svg.setAttribute('viewBox', vb.map(function (n) { return n.toFixed(1); }).join(' '));
    if (facLayer) {
      var r = markerRadius();
      facLayer.querySelectorAll('circle').forEach(function (m) { m.setAttribute('r', r); });
    }
    placeBadges();
    var z = zoomedIn();
    root.dataset.zoomed = z ? '1' : '';
    // 전국 크기에서는 한 손가락으로 페이지가 스크롤되게(pan-y), 확대했으면 지도가 손가락을 받는다
    svg.style.touchAction = 'none';  // 20:07 형우: 전국 크기에서도 끌어서 지도를 옮긴다(지도 위 한 손가락 = 지도 이동)
  }
  /* 지도는 화면 전체(패널·상단 띠 밑까지)에 그리고, 보여줄 범위 b는 패널·띠를 뺀 빈 곳(캔버스 안쪽 여백 안)에 맞춘다.
     그래서 확대·이동하면 지도가 유리 패널 밑으로 지나간다 */
  function fitBox(b) {
    var W = svg.clientWidth || 1, H = svg.clientHeight || 1, cs = getComputedStyle(canvas);
    var pl = parseFloat(cs.paddingLeft) || 0, pr = parseFloat(cs.paddingRight) || 0;
    var pt = parseFloat(cs.paddingTop) || 0, pb = parseFloat(cs.paddingBottom) || 0;
    var fw = Math.max(80, W - pl - pr), fh = Math.max(80, H - pt - pb), k = Math.min(fw / b[2], fh / b[3]);
    return [b[0] + b[2] / 2 - (pl + fw / 2) / k, b[1] + b[3] / 2 - (pt + fh / 2) / k, W / k, H / k];
  }
  /* 전국 보기 범위: 데스크톱은 울릉·독도까지 넣은 전체(19:50 형우: 데스크톱은 원래대로).
     폰은 본토(울릉·독도 뺀 0~884)를 화면 가운데 쯤에 둔다(19:50: 왼쪽으로 쏠려 보임 → 20:05: 너무 오른쪽, 살짝 왼쪽으로).
     서해 섬들이 왼쪽 끝을 넓혀 정가운데면 오른쪽으로 보이므로 범위를 64만큼 오른쪽으로 잡아 지도를 약 26px 왼쪽으로(20:07: 10px 더). 울릉·독도는 옮기면 보인다 */
  var MAINLAND = [64, 0, 884, 1210];
  var natCache = null;  // 손가락이 움직일 때마다 화면 배치를 다시 재지 않도록, 배치가 바뀔 때(layout)만 새로 잰다
  function nationalBox() {
    if (!natCache) natCache = fitBox(narrow.matches ? MAINLAND : geo.viewBox);
    return natCache.slice();
  }
  function targetBox(code) {
    if (!code) return nationalBox();
    var b = sidoBox[code], w = b[2] - b[0], h = b[3] - b[1], pad = Math.max(w, h) * 0.08 + 6;
    return fitBox([b[0] - pad, b[1] - pad, w + pad * 2, h + pad * 2]);
  }
  function zoomTo(vb) {
    if (anim) cancelAnimationFrame(anim);
    // 움직임 줄이기 설정이거나 화면이 보이지 않을 때(애니메이션 프레임이 멈춤)는 바로 이동한다
    if (reduceMotion || document.visibilityState !== 'visible') { setViewBox(vb); root.dataset.zoom = 'done'; afterView(true); return; }
    root.dataset.zoom = 'moving';  // 검사와 확대 중 판단에 쓴다
    labelLayer.hidden = true;
    var from = viewBox.slice(), start = null, dur = 420;
    function step(t) {
      if (start === null) start = t;
      var k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
      setViewBox(from.map(function (f, i) { return f + (vb[i] - f) * e; }));
      if (k < 1) { anim = requestAnimationFrame(step); } else { anim = null; root.dataset.zoom = 'done'; afterView(true); }
    }
    anim = requestAnimationFrame(step);
  }
  function loadDetail(code) {
    if (detailLoaded[code]) return;
    detailLoaded[code] = true;
    fetch(root.dataset.sidoBase + code + '.json', { credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        d.units.forEach(function (u) {
          var p = svg.querySelector('.rmap-unit[data-code="' + u.code + '"]');
          if (p) p.setAttribute('d', u.d);
          delete centers[u.code];
        });
        var o = svg.querySelector('.rmap-sido[data-code="' + code + '"]');
        if (o) o.setAttribute('d', d.outline);
        if (state.sido === code) shadowPath.setAttribute('d', d.outline);
        drawMarkers();
        root.dataset.detail = (root.dataset.detail ? root.dataset.detail + ',' : '') + code;
      })
      .catch(function () { detailLoaded[code] = false; /* 전국용 경계로 계속 보여준다 */ });
  }
  /* keepView: 자유 확대 중에 면을 누르면 패널만 그 시·도로 바꾸고 보기는 그대로 둔다(확대는 보기만, 패널은 누른 것만) */
  function selectSido(code, moveFocus, fromSido, keepView) {
    state.sido = code;
    if (code) state.tier = 'all';  // 시·도 화면은 기초 기준이라 광역 보기를 끈다
    if (narrow.matches) setSheet(false);  // 확대한 지도가 시트에 가리지 않게(리뷰 2)
    update();
    if (svg) {
      if (!keepView) zoomTo(targetBox(code)); else afterView(true);
      if (code) loadDetail(code);
    }
    if (moveFocus) {  // 키보드로 오갈 때 포커스를 잃지 않게(리뷰 18)
      var target = code ? $('[data-rmap-back]') : (fromSido ? $('.rmap-sido-row[data-sido="' + fromSido + '"]') : null);
      if (target) target.focus({ preventScroll: true });
    }
  }

  /* ---------- 자유 확대(11d): 휠·끌기·두 손가락·−/+·전국 ---------- */
  function toSvgPoint(x, y) {
    var pt = svg.createSVGPoint(); pt.x = x; pt.y = y;
    return pt.matrixTransform(svg.getScreenCTM().inverse());
  }
  /* 전국보다 넓게는 못 줄이고, 14배보다 크게는 못 키운다. 가운데는 전국 범위 안에 둔다 */
  function clampBox(vb) {
    var N = nationalBox(), g = geo.viewBox, k = vb[2] / N[2], w = vb[2], h = vb[3];
    if (k > 1.001) return N;  // 전국 크기보다 줄이면 전국 보기로(전국 크기에서 끌어 옮기는 것은 아래에서 허용, 20:07)
    if (k < 1 / MAX_ZOOM) { w *= 1 / (MAX_ZOOM * k); h *= 1 / (MAX_ZOOM * k); }
    var cx = Math.min(g[0] + g[2], Math.max(g[0], vb[0] + vb[2] / 2));
    var cy = Math.min(g[1] + g[3], Math.max(g[1], vb[1] + vb[3] / 2));
    return [cx - w / 2, cy - h / 2, w, h];
  }
  /* 확대했거나, 전국 크기라도 끌어서 옮겼으면 true(바다 누르기·Esc로 제자리) */
  function awayFromNational() {
    var N = nationalBox();
    return zoomedIn() || Math.abs(viewBox[0] - N[0]) > 1 || Math.abs(viewBox[1] - N[1]) > 1;
  }
  function zoomAt(factor, x, y) {
    if (!svg) return;
    if (anim) { cancelAnimationFrame(anim); anim = null; root.dataset.zoom = 'done'; }
    var p = toSvgPoint(x, y), vb = viewBox;
    setViewBox(clampBox([p.x - (p.x - vb[0]) / factor, p.y - (p.y - vb[1]) / factor, vb[2] / factor, vb[3] / factor]));
    viewChanged();
  }
  function panBy(dx, dy) {
    var m = svg.getScreenCTM(), vb = viewBox;
    setViewBox(clampBox([vb[0] - dx / m.a, vb[1] - dy / m.d, vb[2], vb[3]]));
    viewChanged();
  }
  /* 보기가 바뀌는 동안은 이름을 숨기고, 멈추면 다시 그린다 */
  function viewChanged() {
    closeCard(false); hideTip();
    labelLayer.hidden = true;
    clearTimeout(viewTimer);
    viewTimer = setTimeout(function () { afterView(true); }, 160);
  }
  function afterView(now) {
    if (!svg) return;
    if (!now) { clearTimeout(viewTimer); viewTimer = setTimeout(function () { afterView(true); }, 160); return; }
    // 많이 확대한 곳의 시·도는 세밀한 경계로 바꾼다
    if (viewBox[2] < nationalBox()[2] / 2) {
      Object.keys(sidoBox).forEach(function (code) {
        var b = sidoBox[code];
        if (b[2] > viewBox[0] && b[0] < viewBox[0] + viewBox[2] && b[3] > viewBox[1] && b[1] < viewBox[1] + viewBox[3]) loadDetail(code);
      });
    }
    drawLabels();
  }
  function bindZoom() {
    canvas.addEventListener('wheel', function (ev) {
      if (!svg) return;
      ev.preventDefault();
      var unit = ev.deltaMode === 1 ? 0.05 : 0.0018;
      zoomAt(Math.exp(-ev.deltaY * unit), ev.clientX, ev.clientY);
    }, { passive: false });
    /* 20:10 형우(폰에서 확대할 때 오류) 점검 뒤 고침:
       - 손가락을 지도 영역 어디(배지·이름 위 포함)에 대도 지도가 받는다. 전엔 배지 위에서 시작하면 브라우저가 페이지 전체를 확대했다
       - 움직임은 화면 한 번 그릴 때(프레임) 한 번만 반영하고, 손가락 수가 바뀌면 기준을 다시 잡아 튀지 않게 한다 */
    var gest = null, frameReq = null;
    function snapshot() {
      var ids = Object.keys(pointers);
      if (ids.length >= 2) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        return { n: 2, d: Math.hypot(a.x - b.x, a.y - b.y), mx: (a.x + b.x) / 2, my: (a.y + b.y) / 2 };
      }
      if (ids.length === 1) { var p0 = pointers[ids[0]]; return { n: 1, x: p0.x, y: p0.y }; }
      return null;
    }
    function applyGesture() {
      frameReq = null;
      var now = snapshot();
      if (!now || !gest || now.n !== gest.n) { gest = now; return; }
      if (now.n === 2) {
        dragMoved = true;
        if (gest.d > 0 && now.d > 0) zoomAt(now.d / gest.d, now.mx, now.my);
        panBy(now.mx - gest.mx, now.my - gest.my);
      } else {
        var me = pointers[Object.keys(pointers)[0]];
        if (!dragMoved && Math.hypot(me.x - me.sx, me.y - me.sy) < 5) return;  // 손떨림은 누름으로 본다(기준은 그대로)
        dragMoved = true;
        root.dataset.dragging = '1';
        panBy(now.x - gest.x, now.y - gest.y);
      }
      gest = now;
    }
    function flush() { if (frameReq) { cancelAnimationFrame(frameReq); applyGesture(); } }
    canvas.addEventListener('pointerdown', function (ev) {
      if (ev.pointerType === 'mouse' && ev.button !== 0) return;
      if (ev.target.closest('.rmap-zoom, .rmap-error')) return;
      flush();
      pointers[ev.pointerId] = { x: ev.clientX, y: ev.clientY, sx: ev.clientX, sy: ev.clientY, type: ev.pointerType };
      if (Object.keys(pointers).length === 1) dragMoved = false;
      gest = snapshot();
    });
    window.addEventListener('pointermove', function (ev) {
      var me = pointers[ev.pointerId];
      if (!me) return;
      me.x = ev.clientX; me.y = ev.clientY;
      if (!frameReq) frameReq = requestAnimationFrame(applyGesture);
    });
    function release(ev) {
      if (!pointers[ev.pointerId]) return;
      flush();
      delete pointers[ev.pointerId];
      gest = snapshot();
      if (!Object.keys(pointers).length) {
        root.dataset.dragging = '';
        if (dragMoved) { suppressClick = true; setTimeout(function () { suppressClick = false; }, 0); }
      }
    }
    window.addEventListener('pointerup', release);
    window.addEventListener('pointercancel', release);
    // iOS 사파리: 지도 위 두 손가락은 페이지 확대가 아니라 지도 확대로
    ['gesturestart', 'gesturechange'].forEach(function (t) {
      stage.addEventListener(t, function (ev) { ev.preventDefault(); }, { passive: false });
    });
  }
  function zoomControls() {
    zoomBox = el('div', { 'class': 'rmap-zoom', role: 'group', 'aria-label': '지도 확대' });
    [['+', '확대', function () { var r = svg.getBoundingClientRect(); zoomAt(1.6, r.left + r.width / 2, r.top + r.height / 2); }],
     ['−', '축소', function () { var r = svg.getBoundingClientRect(); zoomAt(1 / 1.6, r.left + r.width / 2, r.top + r.height / 2); }],
     ['전국', '전국 보기', function () { if (state.sido) { selectSido(null, false, state.sido); } else { zoomTo(nationalBox()); } }]
    ].forEach(function (b) {
      var btn = el('button', { type: 'button', 'aria-label': b[1], 'data-rmap-zoom': b[1] }, b[0]);
      btn.addEventListener('click', b[2]);
      zoomBox.appendChild(btn);
    });
    return zoomBox;
  }

  /* 시군구 이름(17:49 데스크톱, 18:13 모바일도): 시·도를 고르거나 확대했을 때만. 화면에서 면이 이름보다 작으면 숨기고 서로 겹치지 않게 한다.
     패널(아래 시트)·상단 띠·확대 버튼에 가리는 자리는 처음부터 비워 둔다. 글씨 크기는 CSS(폰 11px) */
  function drawLabels() {
    labelLayer.textContent = '';
    var show = svg && (state.sido || zoomedIn()) && root.dataset.zoom !== 'moving';
    labelLayer.hidden = !show;
    if (!show) return;
    // 글씨 크기는 확대 정도를 따라 10~16px(폰은 1px 작게). 2배 확대마다 2px씩(19:32 형우)
    var z = nationalBox()[2] / viewBox[2];
    var fs = Math.max(10, Math.min(16, 10 + 2 * Math.log2(Math.max(1, z)))) - (narrow.matches ? 1 : 0);
    labelLayer.style.fontSize = fs.toFixed(1) + 'px';
    var m = svg.getScreenCTM(), cr = canvas.getBoundingClientRect(), pt = svg.createSVGPoint(), vb = viewBox;
    var placed = [panel, bar, zoomBox].filter(Boolean).map(function (n) {
      var r = n.getBoundingClientRect();
      return { l: r.left - cr.left, r: r.right - cr.left, t: r.top - cr.top, b: r.bottom - cr.top };
    });
    Object.keys(data.units).forEach(function (code) {
      var u = data.units[code];
      if (!u.lp || (state.sido && u.sido !== state.sido)) return;
      if (u.lp[0] < vb[0] || u.lp[0] > vb[0] + vb[2] || u.lp[1] < vb[1] || u.lp[1] > vb[1] + vb[3]) return;
      var r = svg.querySelector('.rmap-unit[data-code="' + code + '"]').getBoundingClientRect();
      var span = el('span', { 'class': 'rmap-label', 'data-unit': code }, u.name);
      labelLayer.appendChild(span);
      var w = span.offsetWidth, h = span.offsetHeight;
      pt.x = u.lp[0]; pt.y = u.lp[1];
      var q = pt.matrixTransform(m), x = q.x - cr.left, y = q.y - cr.top;
      var box = { l: x - w / 2 - 2, r: x + w / 2 + 2, t: y - h / 2 - 1, b: y + h / 2 + 1 };
      var fits = r.width >= w * 1.05 && r.height >= h * 1.4 && box.l > 0 && box.t > 0 && box.r < cr.width && box.b < cr.height &&
        !placed.some(function (o) { return box.l < o.r && o.l < box.r && box.t < o.b && o.t < box.b; });
      if (!fits) { labelLayer.removeChild(span); return; }
      span.style.left = x + 'px'; span.style.top = y + 'px';
      placed.push(box);
    });
  }

  function draw(g) {
    geo = g;
    g.sido.forEach(function (s) { sidoBox[s.code] = s.bbox; });
    svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '시군구 지도. 목록에서 시·도와 기관을 고를 수 있습니다.');
    var units = unitLayer = document.createElementNS(SVG, 'g');
    g.units.forEach(function (u) {
      var p = document.createElementNS(SVG, 'path');
      p.setAttribute('d', u.d);
      p.setAttribute('class', 'rmap-unit');
      p.dataset.code = u.code;
      p.dataset.sido = u.sido;
      units.appendChild(p);
    });
    var sido = document.createElementNS(SVG, 'g');
    g.sido.forEach(function (s) {
      var p = document.createElementNS(SVG, 'path');
      p.setAttribute('d', s.d);
      p.setAttribute('class', 'rmap-sido');
      p.dataset.code = s.code;
      sido.appendChild(p);
    });
    facLayer = document.createElementNS(SVG, 'g');
    facLayer.setAttribute('class', 'rmap-facs');
    // 그림자는 SVG 필터로 그린다(20:20 형우: 폰에서 안 보임 — 아이폰 사파리는 SVG 도형에 CSS drop-shadow를 그리지 않는다)
    var defs = document.createElementNS(SVG, 'defs');
    defs.innerHTML = '<filter id="rmap-shadow" x="-20%" y="-20%" width="140%" height="140%">' +
      '<feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#122644" flood-opacity="0.35"/></filter>';
    svg.appendChild(defs);
    shadowPath = document.createElementNS(SVG, 'path');
    shadowPath.setAttribute('class', 'rmap-sido-shadow');
    shadowPath.setAttribute('filter', 'url(#rmap-shadow)');
    shadowPath.style.display = 'none';
    selLayer = document.createElementNS(SVG, 'g');
    selLayer.setAttribute('class', 'rmap-selected');
    svg.appendChild(units); svg.appendChild(shadowPath); svg.appendChild(selLayer); svg.appendChild(sido); svg.appendChild(facLayer);
    function hit(target) {
      var n = target.closest('.rmap-unit, .rmap-fac');
      return n ? { code: n.dataset.code, marker: n.classList.contains('rmap-fac') } : null;
    }
    svg.addEventListener('click', function (ev) {
      if (suppressClick) { suppressClick = false; return; }  // 끌어서 옮긴 뒤 손을 뗀 것은 누름이 아니다
      var h = hit(ev.target);
      if (!h) {  // 바다를 누르면 전국으로(17:00 형우)
        closeCard(false);
        if (state.sido) { selectSido(null, false, state.sido); } else if (awayFromNational()) { zoomTo(nationalBox()); }
        return;
      }
      var sidoCode = data.units[h.code].sido;
      if (state.sido !== sidoCode) {
        if (zoomedIn() && !state.sido) { selectSido(sidoCode, false, null, true); openCard(h.code, ev.clientX, ev.clientY); cardOpener = null; }
        else { selectSido(sidoCode); }
        return;
      }
      openCard(h.code, ev.clientX, ev.clientY);
      cardOpener = null;
    });
    bindZoom();
    svg.addEventListener('pointermove', function (ev) {
      if (ev.pointerType !== 'mouse') return;
      var h = hit(ev.target);
      if (!h) { hideTip(); return; }
      showTip(h.code, ev.clientX, ev.clientY, h.marker);
    });
    svg.addEventListener('pointerleave', hideTip);
    canvas.appendChild(svg);
    canvas.appendChild(badgeLayer);
    canvas.appendChild(labelLayer);
    canvas.appendChild(zoomControls());
    setViewBox(targetBox(state.sido));
    paint();
    layout();
    root.dataset.ready = '1';
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    if (!card.hidden) { closeCard(true); return; }   // 카드가 열려 있으면 카드만 닫는다
    if (state.sido) { selectSido(null, true, state.sido); } else if (awayFromNational()) { zoomTo(nationalBox()); }
  });
  document.addEventListener('pointerdown', function (ev) {
    if (card.hidden || card.contains(ev.target) || (svg && svg.contains(ev.target)) || panel.contains(ev.target)) return;
    closeCard(false);
  });
  window.addEventListener('resize', function () {
    layout();
    if (svg) { setViewBox(zoomedIn() && !state.sido ? viewBox : targetBox(state.sido)); afterView(); }
  });
  if (narrow.addEventListener) narrow.addEventListener('change', function () { setSheet(false); update(); });

  setSheet(false);
  update();
  fetch(root.dataset.mapUrl, { credentials: 'same-origin' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () { errorBox.hidden = false; root.dataset.ready = 'error'; });
})();
