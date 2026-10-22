/* 고객사 소재지·기관 유형 입력(4단계, 2026-10-22 형우 확정).
   - 지자체·의회에서만 칸을 보인다.
   - 명칭·분류·지역을 바꾸면 서버(guess_location)에 바로 제안을 받아 채운다.
     단, 비어 있거나 제안으로 채운 값일 때만 덮어쓴다. 직접 고른 값·저장된 값은 '명칭 기준 제안 [적용]'만 보여준다.
   - 시·도를 고르면 그 시·도의 시군구만 보이고, 지역(권역)이 소재지를 따라간다. */
(() => {
  'use strict';
  const box = document.querySelector('[data-location-fields]');
  const dataNode = document.getElementById('location-data');
  if (!box || !dataNode) return;
  const data = JSON.parse(dataNode.textContent);
  const form = box.closest('form');
  const name = form.querySelector('[name="official_name"]');
  const category = form.querySelector('[name="category"]');
  const region = form.querySelector('[name="region"]');
  const sido = form.querySelector('[name="location_sido"]');
  const unit = form.querySelector('[name="location_unit"]');
  const types = Array.from(form.querySelectorAll('[name="institution_type"]'));
  const hint = box.querySelector('[data-location-hint]');
  const TYPE_LABEL = {admin: '행정기관', facility: '시설·공기업'};

  let source = sido.value ? 'saved' : 'empty';   // empty | suggested | manual | saved
  let regionAuto = false;
  let ticket = 0;
  let timer = null;

  function fillUnits(code, keep) {
    const first = new Option('(시·도 전체)', '');
    unit.replaceChildren(first);
    (data.units[code] || []).forEach(([value, label]) => unit.add(new Option(label, value)));
    unit.value = (data.units[code] || []).some(([value]) => value === keep) ? keep : '';
    unit.disabled = !code || !(data.units[code] || []).length;
  }
  function setType(value) { types.forEach(input => { input.checked = input.value === value; }); }
  function followRegion() {
    const r = data.regionOfSido[sido.value];
    if (r && region.value !== r) { region.value = r; regionAuto = true; }
  }
  function currentCode() { return unit.value || sido.value; }
  function say(text, action) {
    hint.replaceChildren();
    if (!text) { hint.hidden = true; return; }
    hint.hidden = false;
    hint.append(document.createTextNode(text));
    if (action) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'button text location-apply'; b.textContent = '적용';
      b.addEventListener('click', action);
      hint.append(' ', b);
    }
  }
  function apply(s) {
    sido.value = s.sido; fillUnits(s.sido, s.unit); setType(s.institution_type);
    if (s.region) { region.value = s.region; regionAuto = true; }
    source = 'suggested';
    say(`명칭 기준으로 채웠어요: ${s.label} · ${TYPE_LABEL[s.institution_type] || ''}. 다르면 고쳐 주세요.`);
  }
  const regionField = form.querySelector('[data-region-field]');
  const categoryRow = form.querySelector('[data-category-row]');
  function visible() {
    const on = data.categories.includes(category.value);
    box.hidden = !on;
    // 지역(권역)도 지자체·의회에서만(2026-10-22 형우). 다른 분류는 분류 칸이 한 줄을 다 쓴다.
    if (regionField) regionField.hidden = !on;
    if (categoryRow) categoryRow.classList.toggle('is-single', !on);
    return on;
  }
  async function suggest() {
    if (!visible()) return;
    const text = name.value.trim();
    if (!text) { if (source === 'suggested') say(''); return; }
    const mine = ++ticket;
    const query = new URLSearchParams({name: text, category: category.value, region: regionAuto ? '' : region.value});
    let s;
    try {
      const response = await fetch(`${box.dataset.guessUrl}?${query}`, {headers: {Accept: 'application/json'}, credentials: 'same-origin'});
      if (!response.ok) return;
      s = await response.json();
    } catch (error) { return; }
    if (mine !== ticket) return;   // 더 새로운 요청이 있다
    if (!s.location) {
      if (source === 'empty' || source === 'suggested') {
        sido.value = ''; fillUnits('', ''); setType(''); source = 'empty';
        if (regionAuto) { region.value = ''; regionAuto = false; }   // 제안으로 맞췄던 지역도 되돌린다
        say(`소재지 선택 필요 — ${s.reason || '명칭으로 위치를 찾지 못했어요'}`);
      }
      return;
    }
    if (source === 'empty' || source === 'suggested') { apply(s); return; }
    if (s.location !== currentCode() || (s.institution_type && !types.some(i => i.checked && i.value === s.institution_type))) {
      say(`명칭 기준 제안: ${s.label} · ${TYPE_LABEL[s.institution_type] || ''}`, () => apply(s));
    } else {
      say('');
    }
  }
  function later() { clearTimeout(timer); timer = setTimeout(suggest, 300); }

  fillUnits(sido.value, unit.value);
  say('');
  name.addEventListener('input', later);
  category.addEventListener('change', () => { if (visible()) suggest(); });
  visible();
  region.addEventListener('change', () => { regionAuto = false; later(); });
  sido.addEventListener('change', () => { source = 'manual'; fillUnits(sido.value, ''); followRegion(); say(''); });
  unit.addEventListener('change', () => { source = 'manual'; say(''); });
  types.forEach(input => input.addEventListener('change', () => { source = 'manual'; say(''); }));
  if (visible() && name.value.trim()) suggest();
})();
