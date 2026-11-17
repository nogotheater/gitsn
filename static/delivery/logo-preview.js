// 심볼 미리보기(2026-11-17 형우: 팀원이 올려도 크기·여백이 통일되게).
// 파일을 고르거나 크기·배경을 바꾸면 서버가 실제로 정리한 모습을 받아 카드 크기로 보여 준다(저장은 '저장' 버튼으로).
(() => {
  const box = document.querySelector('[data-logo-preview]');
  if (!box) return;
  const form = box.closest('form');
  const input = form.querySelector('[data-logo-input]');
  const image = box.querySelector('[data-logo-preview-img]');
  const zoom = box.querySelector('[data-logo-preview-zoom]');
  const list = box.querySelector('[data-logo-warnings]');
  let ticket = 0;
  let timer = 0;
  const checked = name => { const field = form.querySelector(`[name="${name}"]:checked`); return field ? field.value : ''; };
  async function refresh() {
    const file = input && input.files && input.files[0];
    if (!file && !box.dataset.id) { box.hidden = true; return; }
    box.hidden = false;
    const data = new FormData();
    data.append('csrfmiddlewaretoken', form.querySelector('[name="csrfmiddlewaretoken"]').value);
    if (file) data.append('logo', file);
    else { data.append('kind', box.dataset.kind); data.append('id', box.dataset.id); }
    data.append('logo_size', checked('logo_size'));
    data.append('logo_background', checked('logo_background'));
    const auto = form.querySelector('[name="logo_auto"]');
    if (auto && auto.checked) data.append('logo_auto', '1');
    const mine = ++ticket;
    box.setAttribute('aria-busy', 'true');
    try {
      const response = await fetch(box.dataset.url, { method: 'POST', body: data, credentials: 'same-origin' });
      const result = await response.json();
      if (mine !== ticket) return;
      [image, zoom].forEach(node => { node.src = result.image || ''; node.hidden = !result.image; });
      list.replaceChildren(...(result.warnings || []).map(text => { const item = document.createElement('li'); item.textContent = text; return item; }));
      // 크기·배경은 자동 정리할 때만 의미가 있다(다듬어 올린 그대로 쓰는 기존 심볼은 '새 기준으로 자동 정리'를 켜면 보인다)
      box.querySelectorAll('[data-logo-auto-only]').forEach(node => { node.hidden = result.fit !== 'auto'; });
    } catch (error) {
      if (mine === ticket) list.replaceChildren(Object.assign(document.createElement('li'), { textContent: '미리보기를 불러오지 못했습니다. 저장하면 그대로 반영됩니다.' }));
    } finally {
      if (mine === ticket) box.removeAttribute('aria-busy');
    }
  }
  form.addEventListener('change', event => {
    if (event.target === input || event.target.matches('[data-logo-option]')) { clearTimeout(timer); timer = setTimeout(refresh, 120); }
  });
  refresh();
})();
