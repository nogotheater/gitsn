/* 지역 현황 지도(8단계). 외부 라이브러리 없이 인라인 SVG로 그린다.
   데이터: #rmap-data(서버 계산 결과), 경계: korea-lite.json(SVG 경로, 1단위=500m). */
(function () {
  'use strict';
  var root = document.querySelector('[data-rmap]');
  if (!root) return;
  var data = JSON.parse(document.getElementById('rmap-data').textContent);
  var state = { family: 'eavesdrop', target: 'local' };
  var SVG = 'http://www.w3.org/2000/svg';
  var canvas = root.querySelector('[data-rmap-canvas]');
  var errorBox = root.querySelector('[data-rmap-error]');

  function combo() { return data.combos[state.family + ':' + state.target]; }

  function paint() {
    var c = combo();
    canvas.querySelectorAll('.rmap-unit').forEach(function (p) {
      var slot = c.units[p.dataset.code];
      p.classList.toggle('is-in', !!(slot && slot.state === 'in'));
    });
  }

  function draw(geo) {
    var svg = document.createElementNS(SVG, 'svg');
    svg.setAttribute('viewBox', geo.viewBox.join(' '));
    svg.setAttribute('data-rmap-svg', '');
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

  fetch(root.dataset.mapUrl, { credentials: 'same-origin' })
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(draw)
    .catch(function () { errorBox.hidden = false; root.dataset.ready = 'error'; });
})();
