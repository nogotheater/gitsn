/* List conditions live in the URL and are validated by the server; this only adds convenience. */
(() => {
  'use strict';
  const root = document.querySelector('[data-performance-page]');
  if (!root) return;

  // Category tabs: one row that scrolls sideways, with edge fades and step buttons when it overflows.
  const tabs = root.querySelector('[data-category-tabs]');
  if (tabs) {   // 2026-10-22: 탭 줄은 없앴다(분류 칸이 대신). 다른 화면에서 다시 쓸 수 있게 코드는 남긴다.
  const track = tabs.querySelector('[data-tabs-track]');
  const steppers = Array.from(tabs.querySelectorAll('[data-tabs-scroll]'));
  function syncTabs() {
    const max = track.scrollWidth - track.clientWidth;
    const overflow = max > 4;
    tabs.classList.toggle('has-overflow', overflow);
    tabs.classList.toggle('at-start', track.scrollLeft <= 4);
    tabs.classList.toggle('at-end', track.scrollLeft >= max - 4);
    steppers.forEach(button => { button.hidden = !overflow; });
  }
  steppers.forEach(button => button.addEventListener('click', () => {
    track.scrollBy({ left: Number(button.dataset.tabsScroll) * Math.max(120, track.clientWidth * 0.7), behavior: 'smooth' });
  }));
  track.addEventListener('scroll', syncTabs, { passive: true });
  window.addEventListener('resize', syncTabs);
  const activeTab = track.querySelector('.is-active');
  if (activeTab) track.scrollLeft = Math.max(0, activeTab.offsetLeft - (track.clientWidth - activeTab.offsetWidth) / 2);
  syncTabs();
  }

  // Desktop product panel: an inline panel whose open state survives the reload each chip causes.
  const PANEL_KEY = 'gitsn-product-panel';
  const panel = root.querySelector('[data-product-panel]');
  const panelToggle = root.querySelector('[data-product-panel-toggle]');
  function setPanel(open, remember) {
    panel.hidden = !open;
    panelToggle.setAttribute('aria-expanded', String(open));
    if (remember) { try { sessionStorage.setItem(PANEL_KEY, open ? '1' : '0'); } catch (error) { /* storage unavailable */ } }
  }
  panelToggle.setAttribute('aria-expanded', String(!panel.hidden));
  panelToggle.addEventListener('click', () => setPanel(panel.hidden, true));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !panel.hidden) setPanel(false, true); });

  // Mobile bottom sheet: a draft that only applies with the button; closing discards changes.
  const sheet = root.querySelector('#product-sheet');
  const sheetForm = sheet.querySelector('form');
  const boxes = Array.from(sheetForm.querySelectorAll('input[name="products"]'));
  const paintBoxes = () => boxes.forEach(box => box.closest('.product-chip').classList.toggle('is-active', box.checked));
  boxes.forEach(box => box.addEventListener('change', paintBoxes));
  sheetForm.querySelector('[data-sheet-clear]').addEventListener('click', () => { boxes.forEach(box => { box.checked = false; }); paintBoxes(); });
  if (typeof sheet.showModal === 'function') {
    let snapshot = [];
    let submitting = false;
    root.querySelectorAll('[data-sheet-open]').forEach(button => button.addEventListener('click', () => {
      snapshot = boxes.map(box => box.checked);
      sheet.showModal();
      document.body.classList.add('filter-panel-open');
    }));
    sheet.querySelector('[data-sheet-close]').addEventListener('click', () => sheet.close());
    sheet.addEventListener('click', event => {
      if (event.target !== sheet) return;
      const rect = sheetForm.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) sheet.close();
    });
    sheetForm.addEventListener('submit', () => { submitting = true; });
    sheet.addEventListener('close', () => {
      document.body.classList.remove('filter-panel-open');
      if (!submitting) { boxes.forEach((box, index) => { box.checked = snapshot[index]; }); paintBoxes(); }
    });
  }

  // 섹션 접기 단위(2026-10-22 형우): 처음 카드 두 줄·리스트 다섯 줄, '더 보기'마다 카드 두 줄·리스트 열 줄씩.
  // setView가 처음부터 접기를 다시 계산하므로 맨 앞에 둔다.
  const FOLD = { card: { first: 2, step: 2 }, list: { first: 5, step: 10 } };

  // Card/list view: a per-browser preference. Default follows the device (cards on desktop, list on phones).
  const VIEW_KEY = 'gitsn-performance-view';
  let viewRoot = root.querySelector('[data-view-root]');
  const viewButtons = Array.from(root.querySelectorAll('[data-view]'));
  function setView(view, remember) {
    viewRoot.classList.toggle('view-list', view === 'list');
    viewRoot.classList.toggle('view-card', view === 'card');
    viewButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === view)));
    if (remember) { try { localStorage.setItem(VIEW_KEY, view); } catch (error) { /* storage unavailable */ } }
    if (typeof syncMore === 'function') syncMore();
  }
  let storedView = null;
  try { storedView = localStorage.getItem(VIEW_KEY); } catch (error) { /* storage unavailable */ }
  // 2026-10-22 형우: 폰은 항상 리스트로 시작한다(폰에서 바꾼 보기는 저장하지 않음). PC·태블릿은 고른 보기를 기억한다.
  const narrow = () => window.matchMedia('(max-width: 639px)').matches;
  setView(narrow() ? 'list' : (storedView === 'list' || storedView === 'card' ? storedView : 'card'), false);
  viewButtons.forEach(button => button.addEventListener('click', () => setView(button.dataset.view, !narrow())));

  // 분류 칸 = 분류 버튼(2026-10-22 형우). 누르면 새로고침 없이 그 자리에서 바뀐다(주소·뒤로 가기는 그대로 동작).
  // 서버가 그린 같은 화면을 받아 바뀌는 부분(data-live-region)만 갈아 끼운다. 실패하면 보통 이동으로 넘어간다.
  const status = root.querySelector('[data-live-status]');
  let bandObserver = null;
  function watchBand() {
    if (bandObserver) bandObserver.disconnect();
    const band = root.querySelector('[data-category-band]');
    const chipsBox = root.querySelector('[data-category-chips]');
    if (!band || !chipsBox || !('IntersectionObserver' in window)) return;
    bandObserver = new IntersectionObserver(([entry]) => {
      bandPast = !entry.isIntersecting && entry.boundingClientRect.top <= 0;
      applyBand();
    });
    bandObserver.observe(chipsBox);
  }
  // 띠는 분류 칸이 화면 밖으로 나가면 보인다. PC 띠 검색칸에 커서가 있는 동안은 결과가 짧아져도 띠를 그대로 둔다.
  let bandPast = false;
  function bandPinned() {
    // 띠 검색칸에 커서가 있거나 띠 필터 패널이 열려 있는 동안(PC)은, 결과가 짧아져도 띠를 그대로 둔다(2026-10-22 형우: 변화 없이).
    if (narrow()) return false;
    const inline = root.querySelector('[data-band-inline-input]');
    return (Boolean(inline) && document.activeElement === inline) || filterOpen;
  }
  function applyBand() {
    const band = root.querySelector('[data-category-band]');
    const tools = root.querySelector('[data-float-tools]');
    if (!band) return;
    const show = bandPast || bandPinned();
    if (band.hidden === show) band.hidden = !show;
    // 폰 검색창이 열려 있는 동안은 알약을 그대로 둔다 — 🔍를 다시 눌러 닫을 수 있게(2026-10-22 형우)
    const phoneSearch = root.querySelector('[data-band-search]');
    if (tools) tools.hidden = !(bandPast || (narrow() && phoneSearch && !phoneSearch.hidden));
    if (show) syncBand();
    if (!bandPast) { closeIndex(); if (!bandPinned()) closeFilter(); }
  }
  function currentView() { return viewRoot && viewRoot.classList.contains('view-list') ? 'list' : 'card'; }
  let ticket = 0;
  async function live(url, { push = true, focusKey = null, keepList = false } = {}) {
    const mine = ++ticket;
    const list = root.querySelector('[data-view-root]');
    if (list && !keepList) list.setAttribute('aria-busy', 'true');
    let fresh;
    try {
      const response = await fetch(url, { credentials: 'same-origin', headers: { Accept: 'text/html' } });
      if (!response.ok) throw new Error(String(response.status));
      fresh = new DOMParser().parseFromString(await response.text(), 'text/html').querySelector('[data-performance-page]');
      if (!fresh) throw new Error('page');
    } catch (error) { window.location.href = url; return; }
    if (mine !== ticket) return;
    const view = currentView();
    const oldRegions = Array.from(root.querySelectorAll('[data-live-region]'));
    const newRegions = new Map(Array.from(fresh.querySelectorAll('[data-live-region]'), el => [el.dataset.liveRegion, el]));
    if (oldRegions.length !== newRegions.size || oldRegions.some(el => !newRegions.has(el.dataset.liveRegion))) { window.location.href = url; return; }
    // keepList: 목록은 이미 그 자리에서 바꿨다(분류 칩 즉시 전환) — 나머지(주소가 든 링크·숨은 칸 등)만 서버 것으로 맞춘다
    oldRegions.forEach(el => {
      if (keepList && (el.dataset.liveRegion === 'list' || el.dataset.liveRegion === 'pages')) return;
      el.replaceWith(document.importNode(newRegions.get(el.dataset.liveRegion), true));
    });
    if (!keepList) primeFull(url, fresh);
    viewRoot = root.querySelector('[data-view-root]');
    setView(view, false);
    // 바꾸지 않고 값만 맞추는 곳: 폰 필터 시트의 제품 체크(이벤트가 걸려 있다), 검색창 글자
    const freshIds = new Set(Array.from(fresh.querySelectorAll('#product-sheet input[name="products"]:checked'), box => box.value));
    boxes.forEach(box => { box.checked = freshIds.has(box.value); });
    paintBoxes();
    const freshSearch = fresh.querySelector('#performance-search');
    if (freshSearch) mirrorSearch(freshSearch.value, document.activeElement);   // 치고 있는 칸은 건드리지 않는다
    // 2026-10-22 형우: 칩을 여러 번 눌러도 뒤로 가기 한 번이면 이 화면을 나간다(주소만 바꾸고 기록은 쌓지 않음)
    if (push) history.replaceState({ performanceLive: true }, '', url);
    watchBand();
    syncMore();
    if (filterOpen) openFilter(false);
    const total = root.querySelector('[data-testid="total-count"]');
    const picked = Array.from(root.querySelectorAll('[data-category-chips] .is-active span:first-child'), el => el.textContent);
    if (status && total) status.textContent = `${picked.length ? picked.join(', ') : '전체'} ${total.textContent}곳`;
    const again = focusKey && root.querySelector(`[data-live-key="${focusKey}"]`);
    if (again) again.focus({ preventScroll: true });
  }
  // 칩은 누르는 즉시(2026-10-22 형우: 분류 칩도 제품 칩도 '누르고 1~2초 뒤에 바뀐다' → 바로).
  // 제품·분류를 안 고른 '전체 목록'과 집계표(#count-index: 분류·권역·공개 여부·제품만, 이름 없음)를 한 벌 들고 있다가
  // 누르면 그 안에서 고르고 숫자를 다시 센다. 링크·숨은 칸·인쇄 주소 등 나머지는 뒤에서 서버 응답으로 조용히 맞춘다.
  const fullReady = new Map();   // 검색어 → { list, index }
  const fullPending = new Set();
  const partner = root.hasAttribute('data-partner');
  function readState(url) {
    const u = new URL(url, window.location.href);
    return { path: u.pathname, products: u.searchParams.getAll('products'), categories: u.searchParams.getAll('category'), q: u.searchParams.get('q') || '' };
  }
  function buildUrl(path, products, categories, q) {
    const p = new URLSearchParams();
    products.forEach(v => p.append('products', v));
    categories.forEach(v => p.append('category', v));
    if (q) p.set('q', q);
    const qs = p.toString();
    return qs ? `${path}?${qs}` : path;
  }
  function storeFull(q, list, indexEl) {
    let index = null;
    try { index = indexEl ? JSON.parse(indexEl.textContent) : null; } catch (error) { index = null; }
    if (!list || !index) return;
    const copy = list.cloneNode(true);
    copy.removeAttribute('aria-busy');
    copy.querySelectorAll('.is-cut').forEach(card => card.classList.remove('is-cut'));
    copy.querySelectorAll('.performance-category').forEach(section => { delete section.dataset.rowsCard; delete section.dataset.rowsList; });
    fullReady.set(q, { list: copy, index });
    root.dataset.quickReady = '1';   // 검사용 표시: 즉시 바꿀 준비가 됐다
    if (fullReady.size > 4) fullReady.delete(fullReady.keys().next().value);
  }
  // 지금 화면이 아무것도 안 고른 전체 목록이면 그대로 담고, 아니면 전체 목록을 뒤에서 한 번 받아 둔다.
  function primeFull(url, doc) {
    const state = readState(url);
    if (fullReady.has(state.q) || fullPending.has(state.q)) return;
    const src = doc || root;
    if (!state.products.length && !state.categories.length) {
      storeFull(state.q, src.querySelector('[data-live-region="list"]'), src.querySelector('#count-index'));
      return;
    }
    fullPending.add(state.q);
    const go = () => fetch(buildUrl(state.path, [], [], state.q), { credentials: 'same-origin', headers: { Accept: 'text/html' } })
      .then(response => response.ok ? response.text() : Promise.reject(response.status))
      .then(html => {
        const page = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-performance-page]');
        if (page) storeFull(state.q, page.querySelector('[data-live-region="list"]'), page.querySelector('#count-index'));
      })
      .catch(() => {})
      .finally(() => fullPending.delete(state.q));
    if ('requestIdleCallback' in window) requestIdleCallback(go, { timeout: 1500 }); else setTimeout(go, 300);
  }
  function markCard(card, mask) {
    const box = card.querySelector('.badges');
    if (!box) return;
    const marks = Array.from(box.children);
    marks.forEach(mark => {
      const on = ((Number(mark.dataset.p) || 0) & mask) !== 0;
      mark.classList.toggle('is-selected', on);
      mark.classList.toggle('is-subdued', !on);
      if (on) mark.title += ' · 선택 제품';
    });
    marks.filter(mark => mark.classList.contains('is-subdued')).forEach(mark => box.appendChild(mark));   // 고른 제품 먼저(서버와 같은 순서)
  }
  // 서버 확인이 오기 전에 눌러도 맞게: 인쇄 주소·조건 칩·숨은 칸·검색 지우기 주소를 바로 맞춘다(2026-10-23, 검사가 찾은 1초 틈)
  function syncLinks(want, labels) {
    const printQuery = buildUrl('', want.products, want.categories, '').replace(/^\?/, '');
    root.querySelectorAll('[data-live-region="print-top"], [data-live-region="print-bottom"]').forEach(link => {
      link.href = `${new URL(link.href, window.location.href).pathname}?${printQuery}`;
    });
    const clearSearch = buildUrl(want.path, want.products, want.categories, '');
    const clearInField = root.querySelector('[data-live-region="search-clear"] a');
    if (clearInField) clearInField.href = clearSearch;
    const hidden = (name, value) => { const input = document.createElement('input'); input.type = 'hidden'; input.name = name; input.value = value; return input; };
    const searchHidden = root.querySelector('[data-live-region="search-hidden"]');
    if (searchHidden) searchHidden.replaceChildren(...want.products.map(v => hidden('products', v)), ...want.categories.map(v => hidden('category', v)));
    const sheetHidden = root.querySelector('[data-live-region="sheet-hidden"]');
    if (sheetHidden) sheetHidden.replaceChildren(...want.categories.map(v => hidden('category', v)), ...(want.q ? [hidden('q', want.q)] : []));
    // 위쪽 조건 줄: 분류 이름 · 고른 제품(× 해제) · 검색 · 모두 해제
    const active = root.querySelector('[data-live-region="active"]');
    if (!active) return;
    const parts = [];
    const span = (cls, text) => { const node = document.createElement('span'); node.className = cls; node.textContent = text; return node; };
    const names = labels.filter(([code]) => want.categories.includes(code)).map(([, label]) => label);
    if (names.length) parts.push(span('active-label', '분류'), span('active-text', names.join(', ')));
    root.querySelectorAll('[data-live-region="panel-chips"] a.product-chip').forEach(chip => {
      const id = chip.dataset.liveKey.replace(/^prod-/, '');
      if (!want.products.includes(id)) return;
      const link = document.createElement('a');
      link.className = 'active-chip';
      link.dataset.live = '';
      link.href = buildUrl(want.path, want.products.filter(v => v !== id), want.categories, want.q);
      link.setAttribute('aria-label', `${chip.textContent} 조건 해제`);
      const mark = span('product-mark', chip.dataset.mark || '');
      mark.style.setProperty('--product-color', chip.dataset.color || '');
      link.append(mark, document.createTextNode(chip.textContent), span('active-remove', '×'));
      link.lastChild.setAttribute('aria-hidden', 'true');
      parts.push(link);
    });
    if (want.q) {
      const link = document.createElement('a');
      link.className = 'active-chip';
      link.dataset.live = '';
      link.href = clearSearch;
      link.setAttribute('aria-label', '검색 조건 해제');
      link.append(document.createTextNode(`검색 “${want.q}”`), span('active-remove', '×'));
      link.lastChild.setAttribute('aria-hidden', 'true');
      parts.push(link);
    }
    if (want.products.length || want.categories.length || want.q) {
      const link = document.createElement('a');
      link.className = 'clear-all';
      link.dataset.live = '';
      link.href = want.path;
      link.textContent = '모두 해제';
      parts.push(link);
    }
    active.replaceChildren(...parts);
  }
  function quickApply(url, focusKey) {
    const want = readState(url);
    const now = readState(window.location.href);
    const full = fullReady.get(want.q);
    const nav = root.querySelector('[data-category-chips]');
    if (want.path !== now.path || want.q !== now.q || !full || !nav) return false;
    const index = full.index;
    let mask = 0;
    for (const id of want.products) {
      const at = index.products.indexOf(id);
      if (at < 0) return false;
      mask |= 1 << at;
    }
    const hit = m => !mask || (m & mask) !== 0;
    const catOn = code => !want.categories.length || want.categories.includes(code);
    // 숫자: 분류 칸은 분류 선택과 상관없이 각자, 섹션·총수는 고른 분류 안에서(서버와 같은 센 법)
    const byCat = {}, bySection = {}, privateBySection = {};
    let total = 0;
    index.rows.forEach(([section, category, isPublic, m]) => {
      if (!hit(m)) return;
      byCat[category] = (byCat[category] || 0) + 1;
      if (!catOn(category)) return;
      total += 1;
      const key = index.sections[section];
      bySection[key] = (bySection[key] || 0) + 1;
      if (!isPublic) privateBySection[key] = (privateBySection[key] || 0) + 1;
    });
    const collapse = !want.categories.length && !want.q;
    const list = full.list.cloneNode(true);
    let shown = 0;
    list.querySelectorAll('.performance-category').forEach(section => {
      if (!catOn(section.dataset.category)) { section.remove(); return; }
      const key = section.id.replace(/^section-/, '');
      const count = bySection[key] || 0;
      const privateCount = privateBySection[key] || 0;
      const grid = section.querySelector('.performance-grid');
      let cards = 0;
      if (grid) grid.querySelectorAll('.customer-card').forEach(card => {
        if (!hit(Number(card.dataset.pm) || 0)) { card.remove(); return; }
        cards += 1;
        if (mask) markCard(card, mask);
      });
      if (!cards && !(count && !want.q)) { section.remove(); return; }
      if (!cards) {
        // 카드는 없고 숫자만 남은 섹션: 서버와 같은 문구
        section.querySelectorAll('.performance-grid, [data-more-row]').forEach(node => node.remove());
        let note = section.querySelector('.category-empty');
        if (!note) { note = document.createElement('p'); note.className = 'category-empty hint'; section.appendChild(note); }
        note.textContent = partner && privateCount ? '비공개 고객사는 숫자에만 포함하며 개별 정보는 표시하지 않습니다.' : '집계에 포함되며 목록에는 표시하지 않는 고객사입니다.';
      }
      const totalEl = section.querySelector('.category-total');
      if (totalEl) totalEl.textContent = `${count}곳`;
      if (partner) {
        let small = section.querySelector('.category-private-note');
        if (privateCount) {
          if (!small) { small = document.createElement('small'); small.className = 'category-private-note'; small.dataset.testid = 'category-private-count'; section.querySelector('.performance-category-heading').appendChild(small); }
          small.textContent = `비공개 ${privateCount}곳 포함`;
        } else if (small) small.remove();
      }
      if (!collapse) {
        section.classList.remove('is-collapsible');
        section.querySelectorAll('.section-fold, [data-more-row]').forEach(node => node.remove());
      }
      shown += 1;
    });
    if (!shown) return false;   // 빈 화면 문구는 서버가 그린다
    const view = currentView();
    root.querySelector('[data-view-root]').replaceWith(list);
    viewRoot = list;
    setView(view, false);
    // 분류 칸: 숫자·모양·다음에 누를 주소
    const labels = Array.from(nav.querySelectorAll('[data-category]'), chip => [chip.dataset.category, chip.querySelector('span').textContent]);
    const order = labels.map(([code]) => code);
    const chips = labels.map(([code, label]) => {
      const count = byCat[code] || 0;
      const on = want.categories.includes(code);
      let chip;
      if (count || on) {
        chip = document.createElement('a');
        chip.className = 'category-chip' + (on ? ' is-active' : want.categories.length ? ' is-dim' : '');
        chip.href = buildUrl(want.path, want.products, order.filter(v => want.categories.includes(v) !== (v === code)), want.q);
        chip.dataset.category = code;
        chip.dataset.live = '';
        chip.dataset.liveKey = `cat-${code}`;
        if (on) { chip.setAttribute('aria-current', 'true'); chip.title = '다시 누르면 선택 해제'; }
      } else {
        chip = document.createElement('span');
        chip.className = 'category-chip is-empty';
        chip.dataset.category = code;
        chip.setAttribute('aria-disabled', 'true');
        chip.title = '조건에 맞는 고객사가 없습니다';
      }
      const name = document.createElement('span');
      name.textContent = label;
      const number = document.createElement('strong');
      number.textContent = String(count);
      const unit = document.createElement('small');
      unit.textContent = '곳';
      number.appendChild(unit);
      chip.append(name, number);
      return chip;
    });
    nav.replaceChildren(...chips);
    const totalEl = root.querySelector('[data-testid="total-count"]');
    if (totalEl) totalEl.textContent = String(total);
    // 제품 칩·필터 숫자 배지·폰 필터 체크
    root.querySelectorAll('[data-live-region="panel-chips"] a.product-chip, [data-live-region="band-chips"] a.product-chip').forEach(chip => {
      const id = (chip.dataset.liveKey || '').replace(/^(band)?prod-/, '');
      const on = want.products.includes(id);
      chip.classList.toggle('is-active', on);
      if (on) chip.setAttribute('aria-current', 'true'); else chip.removeAttribute('aria-current');
      chip.href = buildUrl(want.path, on ? want.products.filter(v => v !== id) : [...want.products, id], want.categories, want.q);
    });
    ['badge-top', 'band-badge', 'badge-bottom'].forEach(name => {
      const holder = root.querySelector(`[data-live-region="${name}"]`);
      if (holder) holder.innerHTML = want.products.length ? `<span class="filter-badge">${want.products.length}</span>` : '';
    });
    boxes.forEach(box => { box.checked = want.products.includes(box.value); });
    paintBoxes();
    syncLinks(want, labels);
    history.replaceState({ performanceLive: true }, '', url);
    syncMore();
    syncBand();
    const again = focusKey && root.querySelector(`[data-live-key="${focusKey}"]`);
    if (again) again.focus({ preventScroll: true });
    live(url, { push: false, focusKey, keepList: true });
    return true;
  }
  root.addEventListener('click', event => {
    // 분류 칸·제품 칩·조건 해제 칩·모두 해제: 새로고침 없이 바꾼다(새 탭 열기 등 보조키 클릭은 그대로).
    // 들고 있는 전체 목록으로 바로 바꿀 수 있으면 즉시, 아니면 서버에서 받아 바꾼다.
    const link = event.target.closest('a[data-live]');
    if (link && !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button)) {
      event.preventDefault();
      const focusKey = link.dataset.liveKey || null;
      if (!quickApply(link.href, focusKey)) live(link.href, { focusKey });
      return;
    }
    if (event.target.closest('[data-band-toggle]')) { closeFilter(); toggleIndex(); return; }
    if (event.target.closest('[data-band-filter]')) { closeIndex(); if (filterOpen) closeFilter(); else openFilter(event.detail === 0); return; }
    if (event.target.closest('[data-float-search]')) { floatSearch(); return; }
    if (event.target.closest('[data-band-search-close]')) { closeSearch(true); return; }
    if (event.target.closest('[data-band-inline-clear]')) { clearInline(); return; }
    const jump = event.target.closest('[data-section-jump]');
    if (jump) { closeIndex(); goTo(document.getElementById(jump.dataset.sectionJump)); return; }
    if (event.target.closest('[data-band-chips]')) {
      closeIndex();
      const chipsBox = root.querySelector('[data-category-chips]');
      goTo(chipsBox, chipsBox && (chipsBox.querySelector('.is-active') || chipsBox.querySelector('a')));
      return;
    }
    if (event.target.closest('[data-to-top]')) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
      const title = root.querySelector('.page-head h1');
      if (title) { title.setAttribute('tabindex', '-1'); title.focus({ preventScroll: true }); }
      return;
    }
    const more = event.target.closest('[data-section-more]');
    if (more) { showMore(more.closest('.performance-category')); return; }
    const fold = event.target.closest('[data-section-fold]');
    if (fold) collapse(fold.closest('.performance-category'));
  });

  // 섹션 더 보기·접기(2026-10-22 형우): '더 보기'는 한꺼번에가 아니라 조금씩(카드 두 줄씩, 리스트 열 줄씩).
  // 다 보이면 '접기 ▴'. 펼친 섹션은 제목 옆에도 '접기 ▴'. 접으면 그 섹션 제목이 화면 위로 오게 올린다.
  function rowsKey() { return currentView() === 'list' ? 'rowsList' : 'rowsCard'; }
  function columns(section) {
    const grid = section.querySelector('.performance-grid');
    return grid ? Math.max(1, getComputedStyle(grid).gridTemplateColumns.split(' ').filter(Boolean).length) : 1;
  }
  function showMore(section) {
    if (!section) return;
    const cards = Array.from(section.querySelectorAll('.customer-card'));
    const rule = FOLD[currentView()];
    const rows = Number(section.dataset[rowsKey()]) || rule.first;
    if (rows * columns(section) >= cards.length) { collapse(section); return; }
    const firstNew = cards[rows * columns(section)];
    section.dataset[rowsKey()] = String(rows + rule.step);
    syncMore();
    if (firstNew) firstNew.focus({ preventScroll: true });
  }
  function collapse(section) {
    if (!section) return;
    delete section.dataset[rowsKey()];
    syncMore();
    const more = section.querySelector('[data-section-more]');
    if (section.getBoundingClientRect().top < BAND_OFFSET) goTo(section, more);
    else if (more) more.focus({ preventScroll: true });
  }

  // 섹션 바로가기(2026-10-22 형우): 띠의 '목차 ▾' → 분류 8줄, 지자체·의회는 권역 칩 한 줄. 지금 보는 곳에 ▸.
  const BAND_OFFSET = 72;
  function goTo(target, focusTarget) {
    if (!target) return;
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: Math.max(0, target.getBoundingClientRect().top + window.scrollY - BAND_OFFSET), behavior: reduce ? 'auto' : 'smooth' });
    const f = focusTarget || target.querySelector('h2');
    if (f) { if (f.tagName === 'H2' && !f.hasAttribute('tabindex')) f.setAttribute('tabindex', '-1'); f.focus({ preventScroll: true }); }
  }
  function currentSection() {
    const sections = root.querySelectorAll('.performance-category');
    // 맨 아래까지 내려왔으면 마지막 섹션(짧아서 위까지 못 올라오는 경우)
    if (sections.length && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) return sections[sections.length - 1];
    let current = null;
    sections.forEach(section => { if (section.getBoundingClientRect().top - BAND_OFFSET - 8 <= 0) current = section; });
    return current;
  }
  function sectionName(section) {
    const heading = section.querySelector('h2');
    return heading ? heading.firstChild.textContent.trim() : '';
  }
  function sectionCount(section) {
    const total = section.querySelector('.category-total');
    return total ? total.textContent.trim() : '';
  }
  function closeIndex() {
    const panel = root.querySelector('[data-band-panel]');
    const toggle = root.querySelector('[data-band-toggle]');
    if (panel) panel.hidden = true;
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  }
  function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text) node.textContent = text; return node; }
  function toggleIndex() {
    const panel = root.querySelector('[data-band-panel]');
    const toggle = root.querySelector('[data-band-toggle]');
    if (!panel || !toggle) return;
    if (!panel.hidden) { closeIndex(); return; }
    const here = currentSection();
    const groups = new Map();   // 분류 코드 → 섹션들(화면 순서)
    root.querySelectorAll('.performance-category').forEach(section => {
      const code = section.dataset.category;
      if (!groups.has(code)) groups.set(code, []);
      groups.get(code).push(section);
    });
    const list = document.createElement('ul');
    groups.forEach(sections => {
      const item = document.createElement('li');
      const regional = sections.length > 1 || sections[0].dataset.region;
      const head = el('button');
      head.type = 'button';
      head.dataset.sectionJump = sections[0].id;
      const name = regional ? sectionName(sections[0]).replace(/\(.*\)$/, '') : sectionName(sections[0]);
      const sum = regional ? sections.reduce((n, s) => n + (parseInt(sectionCount(s), 10) || 0), 0) + '곳' : sectionCount(sections[0]);
      if (sections.includes(here)) { head.classList.add('is-here'); head.setAttribute('aria-current', 'location'); }
      head.append(el('span', '', name), el('span', 'band-panel-count', sum));
      item.append(head);
      if (regional) {
        const chips = el('div', 'band-panel-regions');
        sections.forEach(section => {
          const match = sectionName(section).match(/\(([^)]+)\)$/);
          const chip = el('button', 'band-region', match ? match[1] : sectionName(section));
          chip.type = 'button';
          chip.dataset.sectionJump = section.id;
          chip.setAttribute('aria-label', `${sectionName(section)} ${sectionCount(section)}`);
          if (section === here) { chip.classList.add('is-here'); chip.setAttribute('aria-current', 'location'); }
          chips.append(chip);
        });
        item.append(chips);
      }
      list.append(item);
    });
    const change = el('button', 'band-panel-chips', '분류 바꾸기 ↑');
    change.type = 'button';
    change.dataset.bandChips = '';
    panel.replaceChildren(list, change);
    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    const focusTarget = panel.querySelector('.band-region.is-here') || panel.querySelector('.is-here') || panel.querySelector('button');
    if (focusTarget) { focusTarget.focus({ preventScroll: true }); focusTarget.scrollIntoView({ block: 'nearest' }); }
  }
  // 띠 필터(PC, 2026-10-22 형우): 띠 아래로 제품 칩. 고르면 그 자리에서 바뀌고 패널은 열린 채로.
  let filterOpen = false;
  function openFilter(focus) {
    const panel = root.querySelector('[data-band-filter-panel]');
    const button = root.querySelector('[data-band-filter]');
    if (!panel || !button) return;
    filterOpen = true;
    panel.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    if (focus) { const first = panel.querySelector('a'); if (first) first.focus({ preventScroll: true }); }
  }
  function closeFilter() {
    const was = filterOpen;
    filterOpen = false;
    const panel = root.querySelector('[data-band-filter-panel]');
    const button = root.querySelector('[data-band-filter]');
    if (panel) panel.hidden = true;
    if (button) button.setAttribute('aria-expanded', 'false');
    if (was) applyBand();   // 패널을 닫으면 띠가 지금 있어야 하는지 다시 본다
  }

  // 검색(2026-10-22 형우): 맨 위 검색창·띠 검색창 모두 치는 대로 바로 걸러진다(새로고침 없이).
  // 아래 떠 있는 🔍를 누르면 위쪽 띠 자리가 검색창으로 바뀐다(폰 키보드에 가리지 않게).
  const topSearch = root.querySelector('#performance-search');
  const bandSearch = root.querySelector('[data-band-search]');
  const bandInput = root.querySelector('[data-band-search-input]');
  let searchTimer = null;
  function searchUrl(text) {
    const params = new URLSearchParams(window.location.search);
    params.delete('page');
    if (text.trim()) params.set('q', text.trim()); else params.delete('q');
    const query = params.toString();
    return window.location.pathname + (query ? `?${query}` : '');
  }
  async function runSearch(text) {
    clearTimeout(searchTimer);
    const url = searchUrl(text);
    if (url === window.location.pathname + window.location.search) return;
    await live(url);
    const list = root.querySelector('[data-view-root]');
    if (list && list.getBoundingClientRect().top < BAND_OFFSET) window.scrollTo({ top: Math.max(0, list.getBoundingClientRect().top + window.scrollY - BAND_OFFSET - 8) });
  }
  function searchSoon(text) { clearTimeout(searchTimer); searchTimer = setTimeout(() => runSearch(text), 300); }
  const inlineInput = root.querySelector('[data-band-inline-input]');
  function mirrorSearch(value, except) {
    [topSearch, bandInput, inlineInput].forEach(el => { if (el && el !== except) el.value = value; });
    const clear = root.querySelector('[data-band-inline-clear]');
    if (clear) clear.hidden = !(inlineInput && inlineInput.value);
  }
  if (topSearch) {
    topSearch.addEventListener('input', () => { mirrorSearch(topSearch.value, topSearch); searchSoon(topSearch.value); });
    topSearch.closest('form').addEventListener('submit', event => { event.preventDefault(); runSearch(topSearch.value); });
  }
  // PC(2026-10-22 형우): 검색은 띠 한 줄 안(필터 | 검색 | 지금 섹션·목차). 🔍는 그 칸으로 커서를 옮긴다.
  if (inlineInput) {
    inlineInput.addEventListener('input', () => { mirrorSearch(inlineInput.value, inlineInput); searchSoon(inlineInput.value); });
    inlineInput.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); runSearch(inlineInput.value); }
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); inlineInput.blur(); if (inlineInput.value) { mirrorSearch('', null); runSearch(''); } }
    });
    inlineInput.addEventListener('focus', () => { closeIndex(); });
    inlineInput.addEventListener('blur', () => { setTimeout(applyBand, 0); });
  }
  function clearInline() {
    if (!inlineInput) return;
    mirrorSearch('', null);
    inlineInput.focus();
    runSearch('');
  }
  // 폰(2026-10-22 형우): 🔍를 다시 누르거나 키보드를 내리면 검색창이 닫힌다. 걸러진 결과는 그대로(지우기는 ×).
  function floatSearch() {
    if (!narrow() && inlineInput) { inlineInput.focus(); inlineInput.select(); return; }
    if (bandSearch && !bandSearch.hidden) { closeSearch(false); return; }
    openSearch();
  }
  // 열린 검색창에서 🔍·×를 누를 때 입력칸이 먼저 포커스를 잃어 닫히지 않게(누른 버튼이 처리한다)
  root.addEventListener('mousedown', event => {
    if (bandSearch && !bandSearch.hidden && event.target.closest('[data-float-search]')) event.preventDefault();
  });
  let keyboardBase = 0;
  let keyboardSeen = false;
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', () => {
      if (!bandSearch || bandSearch.hidden || !narrow()) return;
      const height = window.visualViewport.height;
      if (height < keyboardBase - 120) keyboardSeen = true;
      else if (keyboardSeen && height > keyboardBase - 60) { if (bandInput) bandInput.blur(); closeSearch(false); }
    });
  }
  function openSearch() {
    if (!bandSearch || !bandInput) return;
    keyboardBase = window.visualViewport ? window.visualViewport.height : window.innerHeight;
    keyboardSeen = false;
    closeIndex(); closeFilter();
    bandInput.value = topSearch ? topSearch.value : '';
    bandSearch.hidden = false;
    applyBand();
    bandInput.focus();
  }
  function closeSearch(clear) {
    if (!bandSearch || bandSearch.hidden) return;
    bandSearch.hidden = true;
    applyBand();
    if (clear && bandInput && bandInput.value) { mirrorSearch('', null); runSearch(''); }
    const button = root.querySelector('[data-float-search]');
    if (button && !button.closest('[hidden]')) button.focus({ preventScroll: true });
  }
  if (bandInput) {
    bandInput.addEventListener('input', () => { mirrorSearch(bandInput.value, bandInput); searchSoon(bandInput.value); });
    bandInput.addEventListener('blur', () => { if (narrow()) closeSearch(false); });   // 키보드 '완료'·바깥 누름
    bandSearch.addEventListener('mousedown', event => { if (event.target.closest('[data-band-search-close]')) event.preventDefault(); });
    bandInput.addEventListener('keydown', event => {
      if (event.key === 'Enter') { event.preventDefault(); runSearch(bandInput.value); }
      if (event.key === 'Escape') { event.preventDefault(); closeSearch(true); }
    });
  }

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    if (filterOpen) { closeFilter(); const b = root.querySelector('[data-band-filter]'); if (b) b.focus(); return; }
    const panel = root.querySelector('[data-band-panel]');
    if (panel && !panel.hidden) { closeIndex(); const t = root.querySelector('[data-band-toggle]'); if (t) t.focus(); }
  });
  document.addEventListener('click', event => {
    const band = root.querySelector('[data-category-band]');
    if (band && !band.contains(event.target)) { closeIndex(); closeFilter(); }
  });

  // 띠에 지금 보는 섹션(2026-10-22 형우): 스크롤에 따라 '공공기관 85곳 · 목차 ▾'
  let bandFrame = 0;
  function syncBand() {
    bandFrame = 0;
    const band = root.querySelector('[data-category-band]');
    if (!band || band.hidden) return;
    const section = currentSection() || root.querySelector('.performance-category');
    if (!section) return;
    const value = band.querySelector('.band-value');
    const count = band.querySelector('.band-count');
    const label = band.querySelector('.band-label');
    if (label) label.textContent = '지금';
    if (value && value.dataset.section !== section.id) { value.textContent = sectionName(section); value.dataset.section = section.id; }
    if (count) count.textContent = sectionCount(section);
  }
  window.addEventListener('scroll', () => { if (!bandFrame) bandFrame = requestAnimationFrame(syncBand); }, { passive: true });

  // 섹션 접기(2026-10-22 형우): 전체 보기에서는 섹션마다 카드 두 줄·리스트 다섯 줄. 버튼은 '더 보기 ▾' / 다 보이면 '접기 ▴'.
  function syncMore() {
    root.querySelectorAll('.performance-category.is-collapsible').forEach(section => {
      const more = section.querySelector('[data-section-more]');
      const fold = section.querySelector('.section-fold');
      const foldBottom = section.querySelector('[data-fold-bottom]');
      const row = section.querySelector('[data-more-row]');
      if (!more) return;
      const cards = Array.from(section.querySelectorAll('.customer-card'));
      const rule = FOLD[currentView()];
      const cols = columns(section);
      const rows = Number(section.dataset[rowsKey()]) || rule.first;
      const limit = rows * cols;
      cards.forEach((card, index) => card.classList.toggle('is-cut', index >= limit));
      const foldable = cards.length > rule.first * cols;
      const all = limit >= cards.length;
      if (row) row.hidden = !foldable; else more.hidden = !foldable;
      more.textContent = all ? '접기' : '더 보기';
      more.dataset.dir = all ? 'up' : 'down';   // 화살표는 CSS로 같은 모양(2026-10-22 형우: 더 보기·접기 화살표·글꼴 통일)
      more.setAttribute('aria-expanded', String(all));
      if (fold) fold.hidden = !(foldable && rows > rule.first);
      // 일부만 펼쳤을 때는 아래 '더 보기' 옆에도 '접기'(2026-10-22 형우). 다 펼치면 '더 보기' 자리가 '접기'가 된다.
      if (foldBottom) foldBottom.hidden = !(foldable && rows > rule.first && !all);
    });
  }
  let moreTimer = null;
  window.addEventListener('resize', () => { clearTimeout(moreTimer); moreTimer = setTimeout(syncMore, 120); });
  primeFull(window.location.href);
  syncMore();
  window.addEventListener('popstate', () => live(window.location.href, { push: false }));
  watchBand();

  // 폰 머리띠(D, 2026-10-21 형우: 지역 현황과 같은 ☰ 한 줄). 메뉴·로그아웃을 ☰ 안에 접는다. 보이는 폭은 CSS가 정한다.
  const topbar = document.querySelector('.topbar-inner');
  if (topbar && topbar.querySelector('nav, form')) {
    const menu = document.createElement('button');
    menu.type = 'button';
    menu.className = 'look-menu-btn';
    menu.setAttribute('aria-expanded', 'false');
    menu.setAttribute('aria-label', '메뉴 열기');
    menu.innerHTML = '<span aria-hidden="true"></span>';
    menu.addEventListener('click', () => {
      const open = document.body.classList.toggle('look-menu-open');
      menu.setAttribute('aria-expanded', String(open));
      menu.setAttribute('aria-label', open ? '메뉴 닫기' : '메뉴 열기');
    });
    topbar.appendChild(menu);
  }
})();
