/* 지역 현황 지도(8단계). 외부 라이브러리 없이 인라인 SVG로 그린다.
   데이터: #rmap-data(서버 계산 결과, 네 조합), 경계: korea-lite.json(SVG 경로, 1단위=500m). */
(function () {
  'use strict';
  var root = document.querySelector('[data-rmap]');
  if (!root) return;
  var data = JSON.parse(document.getElementById('rmap-data').textContent);
  var state = { family: data.families[0].key, target: data.targets[0].key };
  var SVG = 'http://www.w3.org/2000/svg';
  var canvas = root.querySelector('[data-rmap-canvas]');
  var errorBox = root.querySelector('[data-rmap-error]');
  var summary = root.querySelector('[data-rmap-summary]');
  var sidoList = root.querySelector('[data-rmap-sido-list]');

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (text != null) n.textContent = text;
    return n;
  }
  function combo() { return data.combos[state.family + ':' + state.target]; }
  function label(list, key) { return list.filter(function (x) { return x.key === key; })[0].label; }
  function meter(adopted, total) {
    var m = el('span', { 'class': 'rmap-meter', 'aria-hidden': 'true' });
    var bar = el('i');
    bar.style.width = (total ? Math.round(adopted / total * 1000) / 10 : 0) + '%';
    m.appendChild(bar);
    return m;
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

  function renderPanel() {
    var c = combo();
    var noun = state.target === 'council' ? '의회' : '지자체';
    summary.textContent = '';
    summary.appendChild(el('p', { 'class': 'rmap-summary-label' }, label(data.families, state.family) + ' 도입 ' + noun));
    var v = el('p', { 'class': 'rmap-summary-value', 'data-rmap-national': '' });
    v.appendChild(el('strong', {}, String(c.national.adopted)));
    v.appendChild(el('span', {}, '/ ' + c.national.total));
    summary.appendChild(v);
    var bar = meter(c.national.adopted, c.national.total);
    bar.classList.add('rmap-summary-bar');
    summary.appendChild(bar);

    sidoList.textContent = '';
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
      li.appendChild(row);
      sidoList.appendChild(li);
    });
  }

  function paint() {
    var c = combo();
    canvas.querySelectorAll('.rmap-unit').forEach(function (p) {
      var slot = c.units[p.dataset.code];
      p.classList.toggle('is-in', !!(slot && slot.state === 'in'));
    });
  }

  function update() {
    renderSwitches();
    renderPanel();
    paint();
    root.dataset.combo = state.family + ':' + state.target;
  }

  function draw(geo) {
    var svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', geo.viewBox.join(' '));
    svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '시군구 지도');
    var units = document.createElementNS(SVG, 'g');
    geo.units.forEach(function (u) {
      var p = document.createElementNS(SVG, 'path');
      p.setAttribute('d', u.d);
      p.setAttribute('class', 'rmap-unit');
      p.dataset.code = u.code;
      p.dataset.sido = u.sido;
      units.appendChild(p);
    });
    var sido = document.createElementNS(SVG, 'g');
    geo.sido.forEach(function (s) {
      var p = document.createElementNS(SVG, 'path');
      p.setAttribute('d', s.d);
      p.setAttribute('class', 'rmap-sido');
      p.dataset.code = s.code;
      sido.appendChild(p);
    });
    svg.appendChild(units);
    svg.appendChild(sido);
    canvas.appendChild(svg);
    paint();
    root.dataset.ready = '1';
  }

  update();
  fetch(root.dataset.mapUrl, { credentials: 'same-origin' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () { errorBox.hidden = false; root.dataset.ready = 'error'; });
})();
