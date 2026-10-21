'use strict';
(() => {
document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); }));
 document.querySelectorAll('.symbol img').forEach(img => img.addEventListener('error', () => { img.hidden = true; const fallback = img.parentElement.querySelector('.fallback'); if (fallback) fallback.hidden = false; }));
 const presentation = document.querySelector('[data-presentation-form]');
 if (presentation) {
  const category = presentation.querySelector('[name="category"]');
  const visibility = presentation.querySelector('[name="partner_public"]');
  const note = presentation.querySelector('[data-category-note]');
  const update = () => { note.hidden = !(presentation.dataset.originalCategory && category.value !== presentation.dataset.originalCategory); };
  category.addEventListener('change', () => {visibility.value = 'default'; update();}); update();
 }
 const form = document.querySelector('[data-contract-form]'); if (!form) return;
 const metadata = JSON.parse(document.getElementById('site-metadata').textContent);
 const selectedProducts = () => new Set(Array.from(form.querySelectorAll('[data-product-row]:not([hidden]) select[name$="-product"]')).map(e => e.value).filter(Boolean));
 const updateProducts = () => { const ids = selectedProducts(); form.querySelectorAll('[data-site-row] .field-products input[type="checkbox"]').forEach(input => {input.disabled = !ids.has(input.value); input.closest('label').classList.toggle('unavailable', input.disabled);}); };
 const setupSite = row => {
  const select = row.querySelector('[name$="-existing_site"]');
  const override = row.querySelector('[name$="-update_display"]');
  const lock = () => {
   const existing = metadata[select.value];
   if (existing && !override.checked) Object.entries(existing).forEach(([key,value]) => {const input=row.querySelector(`[name$="-${key}"]`);if(input){if(input.type==='checkbox')input.checked=value;else input.value=value;}});
   row.querySelector('[data-override-control]').hidden = !existing;
   row.querySelectorAll('[data-display-fields] input,[data-display-fields] select').forEach(input => {input.disabled = Boolean(existing) && !override.checked;});
  };
  select.addEventListener('change', () => {
   const data = metadata[select.value];
   if (data) Object.entries(data).forEach(([key,value]) => {const input=row.querySelector(`[name$="-${key}"]`);if(input){if(input.type==='checkbox')input.checked=value;else input.value=value;}});
   override.checked = false; lock();
  }); override.addEventListener('change', lock); lock();
 };
 form.querySelectorAll('[data-site-row]').forEach(setupSite);
 form.addEventListener('change', updateProducts);
 form.querySelectorAll('[data-add-form]').forEach(button => button.addEventListener('click', () => {
  const name = button.dataset.addForm; const total = document.getElementById(`id_${name}-TOTAL_FORMS`); const index = Number(total.value);
  const fragment = document.getElementById(`${name}-template`).content.cloneNode(true);
  fragment.querySelectorAll('*').forEach(node => ['name','id','for'].forEach(attr => {if(node.hasAttribute(attr))node.setAttribute(attr,node.getAttribute(attr).replaceAll('__prefix__',String(index)));}));
  const row = fragment.querySelector('[data-site-row],[data-product-row]'); form.querySelector(`[data-formset="${name}"]`).append(fragment); total.value = index+1;
  if(name==='sites')setupSite(row); updateProducts(); row.querySelector('select,input:not([type=hidden])')?.focus();
 }));
 form.addEventListener('click', event => {const button=event.target.closest('[data-remove-row]');if(!button)return;const row=button.closest('[data-product-row],[data-site-row]');row.querySelector('[name$="-DELETE"]').checked=true;row.hidden=true;updateProducts();});
 const party = form.querySelector('[name="party_mode"]'); const updateParty=()=>form.querySelectorAll('[data-party-mode]').forEach(section=>section.hidden=section.dataset.partyMode!==party.value);party.addEventListener('change',updateParty);updateParty();updateProducts();
})();
