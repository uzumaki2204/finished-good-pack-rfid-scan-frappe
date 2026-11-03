(() => {
  'use strict';
  const catalog = window.FinishedGoodRfidCatalog || {};
  let savedLanguage;
  try { savedLanguage = localStorage.getItem('finished_good_rfid_language'); } catch { savedLanguage = null; }
  let language = savedLanguage || document.documentElement.lang || 'vi';
  if (!catalog[language]) language = 'vi';
  const text = (key, values = {}) => {
    const template = (catalog[language] || {})[key] || (catalog.vi || {})[key];
    if (template === undefined) throw new Error(`Missing RFID catalog key: ${key}`);
    return template.replace(/\{([a-zA-Z_]+)\}/g, (_, name) => String(values[name] ?? ''));
  };
  const render = () => {
    document.documentElement.lang = language;
    document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = text(node.dataset.i18n); });
    document.querySelectorAll('[data-i18n-aria]').forEach(node => { node.setAttribute('aria-label', text(node.dataset.i18nAria)); });
  };
  const setLanguage = value => {
    if (!catalog[value]) return;
    language = value;
    try { localStorage.setItem('finished_good_rfid_language', value); } catch { /* Language still changes for this page. */ }
    render();
    document.dispatchEvent(new CustomEvent('rfid:language'));
  };
  window.RfidI18n = { text, render, setLanguage, get language() { return language; } };
})();
