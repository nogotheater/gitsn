/* 지역 현황 지도(8단계). 외부 라이브러리 없이 인라인 SVG로 그린다.
   데이터: #rmap-data(서버 계산 결과, 네 조합), 경계: korea-lite.json(전국, SVG 경로, 1단위=500m),
   sido/<코드>.json(시·도 세밀 경계, 확대할 때만 불러옴. 같은 좌표계). */
(function () {
  'use strict';
  var root = document.querySelector('[data-rmap]');
  if (!root) return;
  var data = JSON.parse(document.getElementById('rmap-data').textContent);
  var state = { family: data.families[0].key, target: data.targets[0].key, sido: null };
  var SVG = 'http://www.w3.org/2000/svg';
  var canvas = root.querySelector('[data-rmap-canvas]');
  var errorBox = root.querySelector('[data-rmap-error]');
  var head = root.querySelector('[data-rmap-panel-head]');
  var summary = root.querySelector('[data-rmap-summary]');
  var body = root.querySelector('[data-rmap-panel-body]');
  var stage = root.querySelector('[data-rmap-stage]');
  var tip = root.querySelector('[data-rmap-tip]');
  var card = root.querySelector('[data-rmap-card]');
  var legendFac = root.querySelector('[data-rmap-legend-fac]');
  var facLayer = null, centers = {};
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var geo = null, svg = null, viewBox = null, sidoBox = {}, detailLoaded = {}, anim = null;

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
  function meter(adopted, total) {
    var m = el('span', { 'class': 'rmap-meter', 'aria-hidden': 'true' });
    var bar = el('i');
    bar.style.width = (total ? Math.round(adopted / total * 1000) / 10 : 0) + '%';
    m.appendChild(bar);
    return m;
  }
  function symbol(org) {
    var s = el('span', { 'class': 'rmap-symbol', 'aria-hidden': 'true' });
    if (org.logo) { s.appendChild(el('img', { src: org.logo, alt: '' })); } else { s.textContent = org.initial; }
    return s;
  }
  function orgRow(org) {
    var li = el('li', { 'class': 'rmap-org', 'data-org': org.id });
    li.appendChild(symbol(org));
    var t = el('div');
    t.appendChild(el('p', { 'class': 'rmap-org-name' }, org.name));
    t.appendChild(el('p', { 'class': 'rmap-org-meta' }, org.products + ' · ' + org.year));
    li.appendChild(t);
    return li;
  }
  function section(title, count) {
    var sec = el('section', { 'class': 'rmap-section' });
    var h = el('h2', { 'class': 'rmap-section-title' }, title);
    if (count != null) h.appendChild(el('span', {}, count + '곳'));
    sec.appendChild(h);
    return sec;
  }

  function renderSwitches() {
    [['family', data.families], ['target', data.targets]].forEach(function (pair) {
      var box = root.querySelector('[data-rmap-switch="' + pair[0] + '"]');
      box.textContent = '';
      pair[1].forEach(function (opt) {
        var b = el('button', { type: 'button', 'aria-pressed': String(state[pair[0]] === opt.key), 'data-value': opt.key }, opt.label);
        b.addEventListener('click', function () { state[pair[0]] = opt.key; update(); });
        box.appendChild(b);
      });
    });
  }

  function renderSummary(adopted, total) {
    summary.textContent = '';
    summary.appendChild(el('p', { 'class': 'rmap-summary-label' }, label(data.families, state.family) + ' 도입 ' + noun()));
    var v = el('p', { 'class': 'rmap-summary-value', 'data-rmap-national': '' });
    v.appendChild(el('strong', {}, String(adopted)));
    v.appendChild(el('span', {}, '/ ' + total));
    summary.appendChild(v);
    var bar = meter(adopted, total);
    bar.classList.add('rmap-summary-bar');
    summary.appendChild(bar);
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
      row.addEventListener('click', function () { selectSido(s.code); });
      li.appendChild(row);
      list.appendChild(li);
    });
    body.appendChild(list);
  }

  function renderSido() {
    var c = combo();
    var s = sidoRow(state.sido);
    head.textContent = '';
    var back = el('button', { type: 'button', 'class': 'rmap-back', 'data-rmap-back': '' }, '← 전국');
    back.addEventListener('click', function () { selectSido(null); });
    head.appendChild(back);
    head.appendChild(el('h2', { 'class': 'rmap-panel-title', 'data-rmap-sido-title': '' }, s.name));
    renderSummary(s.adopted, s.total);
    body.textContent = '';

    var wide = section(state.target === 'council' ? '광역의회' : '광역 기관');
    var w = el('p', { 'class': 'rmap-wide', 'data-rmap-wide': '' });
    if (s.wide_orgs.length) {
      s.wide_orgs.forEach(function (o) { w.appendChild(el('span', { 'data-org': o.id }, o.name + ' · 도입')); });
    } else {
      w.appendChild(el('span', { 'class': 'is-none' }, '미도입'));
    }
    s.wide_facilities.forEach(function (o) {
      var f = el('span', { 'data-org': o.id, 'data-fac': '' });
      f.appendChild(el('span', { 'class': 'rmap-fac-dot', 'aria-hidden': 'true' }));
      f.appendChild(document.createTextNode(' ' + o.name));
      w.appendChild(f);
    });
    wide.appendChild(w);
    body.appendChild(wide);

    var miss = section('빠진 곳', s.missing.length);
    if (s.missing.length) {
      var ul = el('ul', { 'class': 'rmap-missing', 'data-rmap-missing': '' });
      s.missing.forEach(function (code) {
        var li = el('li', { 'data-unit': code }, data.units[code].name);
        if (c.units[code] && c.units[code].facilities.length) {
          li.appendChild(el('span', { 'class': 'rmap-fac-dot', title: '시설·공기업 도입 있음', 'data-fac': '' }));
        }
        ul.appendChild(li);
      });
      miss.appendChild(ul);
    } else {
      miss.appendChild(el('p', { 'class': 'rmap-empty-note' }, '빠진 곳이 없습니다.'));
    }
    body.appendChild(miss);

    var orgs = [];
    s.adopted_units.forEach(function (code) { (c.units[code] ? c.units[code].orgs : []).forEach(function (o) { orgs.push(o); }); });
    var done = section('도입한 곳', s.adopted);
    if (orgs.length) {
      var ol = el('ul', { 'class': 'rmap-orgs', 'data-rmap-adopted': '' });
      orgs.forEach(function (o) { ol.appendChild(orgRow(o)); });
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

  /* ---------- 시설·공기업 표시 ---------- */
  function center(code) {
    if (!centers[code]) {
      var p = svg.querySelector('.rmap-unit[data-code="' + code + '"]');
      var b = p.getBBox();
      centers[code] = [b.x + b.width / 2, b.y + b.height / 2];
    }
    return centers[code];
  }
  function markerRadius() { return Math.max(viewBox[2], viewBox[3]) / 150; }
  function drawMarkers() {
    var c = combo();
    var any = c.sido.some(function (s) { return s.wide_facilities.length; });
    facLayer.textContent = '';
    Object.keys(c.units).forEach(function (code) {
      if (!c.units[code].facilities.length) return;
      any = true;
      var xy = center(code);
      var m = document.createElementNS(SVG, 'circle');
      m.setAttribute('cx', xy[0]); m.setAttribute('cy', xy[1]); m.setAttribute('r', markerRadius());
      m.setAttribute('class', 'rmap-fac' + (state.sido && data.units[code].sido !== state.sido ? ' is-dim' : ''));
      m.dataset.code = code;
      facLayer.appendChild(m);
    });
    legendFac.hidden = !any;
  }

  /* ---------- 말풍선(마우스) ---------- */
  function place(box, x, y, w, h) {
    var r = stage.getBoundingClientRect();
    var left = x - r.left + 14, top = y - r.top + 14;
    var maxX = r.width - w - 8, maxY = r.height - h - 8;
    if (left > maxX) left = x - r.left - w - 14;
    if (top > maxY) top = y - r.top - h - 14;
    box.style.left = Math.max(8, left) + 'px';
    box.style.top = Math.max(8, top) + 'px';
  }
  function showTip(code, x, y) {
    var c = combo(), slot = c.units[code], u = data.units[code];
    var isIn = !!(slot && slot.state === 'in');
    tip.textContent = '';
    tip.appendChild(el('strong', {}, u.name));
    tip.appendChild(el('span', { 'class': isIn ? 'is-in' : 'is-out' }, isIn ? '도입' : '미도입'));
    if (slot && slot.facilities.length) tip.appendChild(el('span', { 'class': 'is-out' }, ' · 시설·공기업 ' + slot.facilities.length + '곳'));
    tip.hidden = false;
    tip.dataset.unit = code;
    place(tip, x, y, tip.offsetWidth, tip.offsetHeight);
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
  function openCard(code, x, y) {
    hideTip();
    var c = combo(), slot = c.units[code] || { state: 'out', orgs: [], facilities: [] }, u = data.units[code];
    card.textContent = '';
    var close = el('button', { type: 'button', 'class': 'rmap-card-close', 'aria-label': '닫기', 'data-rmap-card-close': '' }, '×');
    close.addEventListener('click', closeCard);
    card.appendChild(close);
    if (slot.state === 'in') {
      card.appendChild(el('p', { 'class': 'rmap-card-unit' }, data.sido.filter(function (s) { return s.code === u.sido; })[0].short + ' ' + u.name));
      slot.orgs.forEach(function (o) { card.appendChild(cardOrg(o)); });
    } else {
      var out = el('p', { 'class': 'rmap-card-out', 'data-field': 'name' }, u.name);
      out.appendChild(el('span', { 'data-field': 'status' }, '미도입'));
      card.appendChild(out);
    }
    if (slot.facilities.length) {
      var fac = el('div', { 'class': 'rmap-card-fac', 'data-rmap-card-fac': '' });
      var ft = el('p', { 'class': 'rmap-card-fac-title' });
      ft.appendChild(el('span', { 'class': 'rmap-fac-dot', 'aria-hidden': 'true' }));
      ft.appendChild(document.createTextNode('시설·공기업 도입'));
      fac.appendChild(ft);
      slot.facilities.forEach(function (o) { fac.appendChild(cardOrg(o)); });
      card.appendChild(fac);
    }
    card.hidden = false;
    card.dataset.unit = code;
    place(card, x, y, card.offsetWidth, card.offsetHeight);
    close.focus({ preventScroll: true });
  }
  function closeCard() { card.hidden = true; card.dataset.unit = ''; }

  function update() {
    closeCard();
    hideTip();
    renderSwitches();
    if (state.sido) { renderSido(); } else { renderNational(); }
    paint();
    root.dataset.combo = state.family + ':' + state.target;
    root.dataset.sido = state.sido || '';
  }

  /* ---------- 확대 ---------- */
  function setViewBox(vb) {
    viewBox = vb;
    svg.setAttribute('viewBox', vb.map(function (n) { return n.toFixed(1); }).join(' '));
    if (facLayer) { var r = markerRadius(); facLayer.querySelectorAll('circle').forEach(function (m) { m.setAttribute('r', r); }); }
  }
  function targetBox(code) {
    if (!code) return geo.viewBox.slice();
    var b = sidoBox[code];
    var w = b[2] - b[0], h = b[3] - b[1], pad = Math.max(w, h) * 0.08 + 6;
    return [b[0] - pad, b[1] - pad, w + pad * 2, h + pad * 2];
  }
  function zoomTo(vb) {
    if (anim) cancelAnimationFrame(anim);
    // 움직임 줄이기 설정이거나 화면이 보이지 않을 때(애니메이션 프레임이 멈춤)는 바로 이동한다
    if (reduceMotion || document.visibilityState !== 'visible') { setViewBox(vb); return; }
    var from = viewBox.slice(), start = null, dur = 420;
    function step(t) {
      if (start === null) start = t;
      var k = Math.min(1, (t - start) / dur), e = 1 - Math.pow(1 - k, 3);
      setViewBox(from.map(function (f, i) { return f + (vb[i] - f) * e; }));
      if (k < 1) { anim = requestAnimationFrame(step); } else { anim = null; }
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
        drawMarkers();
        var o = svg.querySelector('.rmap-sido[data-code="' + code + '"]');
        if (o) o.setAttribute('d', d.outline);
        root.dataset.detail = (root.dataset.detail ? root.dataset.detail + ',' : '') + code;
      })
      .catch(function () { detailLoaded[code] = false; /* 전국용 경계로 계속 보여준다 */ });
  }
  function selectSido(code) {
    state.sido = code;
    update();
    if (svg) { zoomTo(targetBox(code)); if (code) loadDetail(code); }
  }

  function draw(g) {
    geo = g;
    g.sido.forEach(function (s) { sidoBox[s.code] = s.bbox; });
    svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '시군구 지도');
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
    svg.appendChild(units);
    svg.appendChild(sido);
    svg.appendChild(facLayer);
    function codeOf(target) {
      var n = target.closest('.rmap-unit, .rmap-fac');
      return n ? n.dataset.code : null;
    }
    svg.addEventListener('click', function (ev) {
      var code = codeOf(ev.target);
      if (!code) { closeCard(); return; }
      var sidoCode = data.units[code].sido;
      if (state.sido !== sidoCode) { selectSido(sidoCode); return; }
      openCard(code, ev.clientX, ev.clientY);
    });
    svg.addEventListener('pointermove', function (ev) {
      if (ev.pointerType !== 'mouse') return;
      var code = codeOf(ev.target);
      if (!code) { hideTip(); return; }
      showTip(code, ev.clientX, ev.clientY);
    });
    svg.addEventListener('pointerleave', hideTip);
    canvas.appendChild(svg);
    setViewBox(targetBox(state.sido));
    paint();
    root.dataset.ready = '1';
  }

  document.addEventListener('keydown', function (ev) {
    if (ev.key !== 'Escape') return;
    if (!card.hidden) { closeCard(); return; }   // 카드가 열려 있으면 카드만 닫는다
    if (state.sido) selectSido(null);
  });
  document.addEventListener('pointerdown', function (ev) {
    if (card.hidden || card.contains(ev.target) || (svg && svg.contains(ev.target))) return;
    closeCard();
  });

  update();
  fetch(root.dataset.mapUrl, { credentials: 'same-origin' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () { errorBox.hidden = false; root.dataset.ready = 'error'; });
})();
