/* List conditions live in the URL and are validated by the server; this only adds convenience. */
(() => {
  'use strict';
  const root = document.querySelector('[data-performance-page]');
  if (!root) return;

  // Category tabs: one row that scrolls sideways, with edge fades and step buttons when it overflows.
  const tabs = root.querySelector('[data-category-tabs]');
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

  // Card/list view: a per-browser preference. Default follows the device (cards on desktop, list on phones).
  const VIEW_KEY = 'gitsn-performance-view';
  const viewRoot = root.querySelector('[data-view-root]');
  const viewButtons = Array.from(root.querySelectorAll('[data-view]'));
  function setView(view, remember) {
    viewRoot.classList.toggle('view-list', view === 'list');
    viewRoot.classList.toggle('view-card', view === 'card');
    viewButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.view === view)));
    if (remember) { try { localStorage.setItem(VIEW_KEY, view); } catch (error) { /* storage unavailable */ } }
  }
  let storedView = null;
  try { storedView = localStorage.getItem(VIEW_KEY); } catch (error) { /* storage unavailable */ }
  const defaultView = window.matchMedia('(max-width: 639px)').matches ? 'list' : 'card';
  setView(storedView === 'list' || storedView === 'card' ? storedView : defaultView, false);
  viewButtons.forEach(button => button.addEventListener('click', () => setView(button.dataset.view, true)));

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
