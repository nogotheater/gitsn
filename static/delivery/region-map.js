/* 지역 현황 지도(8단계). 외부 라이브러리 없이 인라인 SVG로 그린다.
   데이터: #rmap-data(서버 계산 결과, 네 조합), 경계: korea-lite.json(전국, SVG 경로, 1단위=500m),
   sido/<코드>.json(시·도 세밀 경계, 확대할 때만 불러옴. 같은 좌표계). */
(function () {
  'use strict';
  var root = document.querySelector('[data-rmap]');
  var dataEl = document.getElementById('rmap-data');
  if (!root || !dataEl) return;
  var data = JSON.parse(dataEl.textContent);
  var state = { family: data.families[0].key, target: data.targets[0].key, sido: null };
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
  var facLayer = null, centers = {}, cardOpener = null;

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
  function facDot() { return el('span', { 'class': 'rmap-fac-dot', 'aria-hidden': 'true', 'data-fac': '' }); }
  function whenVisible(fn) {
    if (document.visibilityState === 'visible') requestAnimationFrame(fn); else fn();
  }

  /* ---------- 배치 재기(리뷰 1·4·16·29) ---------- */
  function layout() {
    root.style.setProperty('--rmap-sbw', (window.innerWidth - document.documentElement.clientWidth) + 'px');
    if (narrow.matches) {
      root.style.removeProperty('--rmap-bar-h');
      root.style.removeProperty('--rmap-stage-h');
      var h = panel.offsetHeight;
      root.style.setProperty('--rmap-sheet-h', h + 'px');
      document.body.style.paddingBottom = h + 'px';  // 바닥글이 접힌 시트 뒤에 가려지지 않게
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

  /* ---------- 아래 시트 ---------- */
  function setSheet(open) {
    root.dataset.sheet = open ? 'open' : 'closed';
    sheetToggle.setAttribute('aria-expanded', String(open));
    sheetToggle.setAttribute('aria-label', open ? '목록 접기' : '목록 펼치기');
    if (narrow.matches) whenVisible(layout);
  }
  sheetToggle.addEventListener('click', function () { setSheet(root.dataset.sheet !== 'open'); });

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
  }

  /* ---------- 패널 ---------- */
  function renderSummary(adopted, total) {
    summary.textContent = '';
    summary.appendChild(el('p', { 'class': 'rmap-summary-label' }, label(data.families, state.family) + ' 도입 ' + noun()));
    var v = el('p', { 'class': 'rmap-summary-value', 'data-rmap-national': '' });
    v.appendChild(el('strong', {}, String(adopted)));
    v.appendChild(el('span', {}, '/ ' + total));
    summary.appendChild(v);
    var m = meter(adopted, total);
    m.classList.add('rmap-summary-bar');
    summary.appendChild(m);
  }

  function renderNational() {
    var c = combo();
    head.textContent = '';
    renderSummary(c.national.adopted, c.national.total);
    body.textContent = '';
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
    t.appendChild(el('span', { 'class': 'rmap-org-meta' }, org.products + ' · ' + org.year));
    row.appendChild(t);
    li.appendChild(row);
    return li;
  }

  function renderSido() {
    var c = combo();
    var s = sidoRow(state.sido);
    head.textContent = '';
    var back = el('button', { type: 'button', 'class': 'rmap-back', 'data-rmap-back': '' }, '← 전국');
    back.addEventListener('click', function () { selectSido(null, true, state.sido); });
    head.appendChild(back);
    head.appendChild(el('h2', { 'class': 'rmap-panel-title', 'data-rmap-sido-title': '' }, s.name));
    renderSummary(s.adopted, s.total);
    body.textContent = '';

    if (!s.whole) {  // 세종·제주는 광역 기관이 곧 그 면이라 '도입한 곳'에만 둔다(리뷰 24)
      var wide = section(state.target === 'council' ? '광역의회' : '광역 기관');
      var w = el('div', { 'class': 'rmap-wide', 'data-rmap-wide': '' });
      if (s.wide_orgs.length) {
        s.wide_orgs.forEach(function (o) { w.appendChild(el('span', { 'data-org': o.id }, o.name + ' · 도입')); });
      } else {
        w.appendChild(el('span', { 'class': 'is-none' }, '미도입'));
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
    body.appendChild(miss);

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
    body.appendChild(done);
  }

  function paint() {
    if (!svg) return;
    var c = combo();
    svg.querySelectorAll('.rmap-unit').forEach(function (p) {
      var slot = c.units[p.dataset.code];
      p.classList.toggle('is-in', !!(slot && slot.state === 'in'));
      p.classList.toggle('is-dim', !!state.sido && p.dataset.sido !== state.sido);
    });
    svg.querySelectorAll('.rmap-sido').forEach(function (p) {
      p.classList.toggle('is-selected', p.dataset.code === state.sido);
    });
    drawMarkers();
  }

  function update() {
    closeCard(false);
    hideTip();
    syncSwitches();
    if (state.sido) { renderSido(); } else { renderNational(); }
    paint();
    root.dataset.combo = state.family + ':' + state.target;
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
    return Math.max(Math.max(viewBox[2], viewBox[3]) / 150, 7 * perPx);
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
        tip.appendChild(el('span', { 'class': 'rmap-tip-line' }, o.name + ' · ' + o.products + ' · ' + o.year));
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
    var a = el('div'); a.appendChild(el('dt', {}, '제품')); a.appendChild(el('dd', { 'data-field': 'products' }, org.products));
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
  function openCard(code, x, y) {
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
  /* 목록에서 연 카드는 패널 왼쪽, 누른 줄 높이에 띄운다 */
  function besidePanel(opener) {
    var r = panel.getBoundingClientRect(), b = opener.getBoundingClientRect();
    return [r.left - 296 - 40, b.top];
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
  }
  function targetBox(code) {
    if (!code) return geo.viewBox.slice();
    var b = sidoBox[code], w = b[2] - b[0], h = b[3] - b[1], pad = Math.max(w, h) * 0.08 + 6;
    return [b[0] - pad, b[1] - pad, w + pad * 2, h + pad * 2];
  }
  function zoomTo(vb) {
    if (anim) cancelAnimationFrame(anim);
    // 움직임 줄이기 설정이거나 화면이 보이지 않을 때(애니메이션 프레임이 멈춤)는 바로 이동한다
    if (reduceMotion || document.visibilityState !== 'visible') { setViewBox(vb); root.dataset.zoom = 'done'; return; }
    root.dataset.zoom = 'moving';  // 검사와 확대 중 판단에 쓴다
    var from = viewBox.slice(), start = null, dur = 420;
    function step(t) {
      if (start === null) start = t;
      var k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
      setViewBox(from.map(function (f, i) { return f + (vb[i] - f) * e; }));
      if (k < 1) { anim = requestAnimationFrame(step); } else { anim = null; root.dataset.zoom = 'done'; }
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
        drawMarkers();
        root.dataset.detail = (root.dataset.detail ? root.dataset.detail + ',' : '') + code;
      })
      .catch(function () { detailLoaded[code] = false; /* 전국용 경계로 계속 보여준다 */ });
  }
  function selectSido(code, moveFocus, fromSido) {
    state.sido = code;
    if (narrow.matches) setSheet(false);  // 확대한 지도가 시트에 가리지 않게(리뷰 2)
    update();
    if (svg) { zoomTo(targetBox(code)); if (code) loadDetail(code); }
    if (moveFocus) {  // 키보드로 오갈 때 포커스를 잃지 않게(리뷰 18)
      var target = code ? $('[data-rmap-back]') : (fromSido ? $('.rmap-sido-row[data-sido="' + fromSido + '"]') : null);
      if (target) target.focus({ preventScroll: true });
    }
  }

  function draw(g) {
    geo = g;
    g.sido.forEach(function (s) { sidoBox[s.code] = s.bbox; });
    svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '시군구 지도. 목록에서 시·도와 기관을 고를 수 있습니다.');
    var units = document.createElementNS(SVG, 'g');
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
    svg.appendChild(units); svg.appendChild(sido); svg.appendChild(facLayer);
    function hit(target) {
      var n = target.closest('.rmap-unit, .rmap-fac');
      return n ? { code: n.dataset.code, marker: n.classList.contains('rmap-fac') } : null;
    }
    svg.addEventListener('click', function (ev) {
      var h = hit(ev.target);
      if (!h) { closeCard(false); return; }
      var sidoCode = data.units[h.code].sido;
      if (state.sido !== sidoCode) { selectSido(sidoCode); return; }
      openCard(h.code, ev.clientX, ev.clientY);
      cardOpener = null;
    });
    svg.addEventListener('pointermove', function (ev) {
      if (ev.pointerType !== 'mouse') return;
      var h = hit(ev.target);
      if (!h) { hideTip(); return; }
      showTip(h.code, ev.clientX, ev.clientY, h.marker);
    });
    svg.addEventListener('pointerleave', hideTip);
    canvas.appendChild(svg);
    setViewBox(targetBox(state.sido));
    paint();
    layout();
    root.dataset.ready = '1';
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    if (!card.hidden) { closeCard(true); return; }   // 카드가 열려 있으면 카드만 닫는다
    if (state.sido) selectSido(null, true, state.sido);
  });
  document.addEventListener('pointerdown', function (ev) {
    if (card.hidden || card.contains(ev.target) || (svg && svg.contains(ev.target)) || panel.contains(ev.target)) return;
    closeCard(false);
  });
  window.addEventListener('resize', function () { layout(); if (svg) setViewBox(viewBox); });
  if (narrow.addEventListener) narrow.addEventListener('change', function () { setSheet(false); update(); });

  setSheet(false);
  update();
  fetch(root.dataset.mapUrl, { credentials: 'same-origin' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () { errorBox.hidden = false; root.dataset.ready = 'error'; });
})();
