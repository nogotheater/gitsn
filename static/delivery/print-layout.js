(function () {
  'use strict';
  let preparation;
  // 화면 폭에 맞춰 A4 쪽을 줄여 보인다. 문서가 넘친 뒤의 넓어진 폭이 아니라 실제 보이는 폭을 기준으로(2026-10-22 형우: 폰에서 잘림).
  function fitPreview() {
    const root = document.getElementById('print-document');
    const width = Math.min(window.innerWidth, document.documentElement.clientWidth || window.innerWidth);
    const scale = String(Math.min(1, Math.max(0.1, (width - 24) / (210 * 96 / 25.4))));
    document.documentElement.style.setProperty('--preview-scale', scale);
    if (root) root.style.setProperty('--preview-scale', scale);
  }
  async function paginate() {
    const root = document.getElementById('print-document');
    if (!root) throw new Error('Print document unavailable');
    const fonts = await document.fonts.load('550 11pt "Freesentation VF"', '가나다ABC');
    await document.fonts.ready;
    if (!fonts.length || !document.fonts.check('550 11pt "Freesentation VF"')) throw new Error('Print font unavailable');
    await Promise.all(Array.from(root.querySelectorAll('img'), image => image.decode()));
    const header = root.querySelector('.document-head'), summary = root.querySelector('.summary');
    const conditions = root.querySelector('.conditions'), footer = root.querySelector('.document-footer');
    const empty = root.querySelector('.empty-output');
    const groups = Array.from(root.querySelectorAll('.category-group'), group => ({heading: group.querySelector('h2').textContent, rows: Array.from(group.querySelectorAll('.card-row'))}));
    const repeat = document.getElementById('repeat-header').content;
    root.replaceChildren(); root.classList.add('is-paginated'); root.style.setProperty('--preview-scale', '1');
    const pages = [];
    function newPage(first = false) {
      const page = document.createElement('section'); page.className = 'print-page';
      const body = document.createElement('div'); body.className = 'page-body';
      const content = document.createElement('div'); content.className = 'page-content';
      body.append(content, footer.cloneNode(true)); page.append(body); root.append(page);
      if (first) { content.append(header, summary); if (conditions) content.append(conditions); }
      else content.append(repeat.cloneNode(true));
      const item = {page, body, content}; pages.push(item); return item;
    }
    function fits(page) {
      const reserved = page.body.querySelector('.document-footer').offsetHeight + 8;
      return page.content.offsetHeight <= page.body.clientHeight - reserved;
    }
    function addGroup(page, label, continued) {
      const group = document.createElement('section'); group.className = 'category-group';
      const heading = document.createElement('h2'); heading.textContent = label + (continued ? ' - 계속' : '');
      const rows = document.createElement('div'); rows.className = 'card-rows';
      group.append(heading, rows); page.content.append(group); return {group, rows};
    }
    let page = newPage(true);
    if (!fits(page)) throw new Error('Print heading exceeds page');
    for (const source of groups) {
      let group = addGroup(page, source.heading, false);
      for (let index = 0; index < source.rows.length; index++) {
        const row = source.rows[index]; group.rows.append(row);
        if (!fits(page)) {
          row.remove(); if (!group.rows.children.length) group.group.remove();
          page = newPage(); group = addGroup(page, source.heading, index > 0); group.rows.append(row);
          if (!fits(page)) throw new Error('Print row exceeds page');
        }
      }
    }
    if (empty) { page.content.append(empty); if (!fits(page)) throw new Error('Print notice exceeds page'); }
    pages.forEach((item, index) => { item.body.querySelector('.page-number').textContent = (index + 1) + ' / ' + pages.length; });
    root.dataset.ready = 'true'; root.dataset.pageCount = String(pages.length); fitPreview(); return pages.length;
  }
  window.GitsnPrint = {prepare() { if (!preparation) preparation = paginate(); return preparation; }};
  window.addEventListener('resize', fitPreview);
  fitPreview();
})();
