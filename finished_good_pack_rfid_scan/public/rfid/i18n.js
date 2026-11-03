(() => {
  'use strict';
  const catalog = window.FinishedGoodRfidCatalog || {};
  let language = document.documentElement.lang || 'vi';
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
    document.querySelectorAll('[data-i18n-title]').forEach(node => { node.setAttribute('title', text(node.dataset.i18nTitle)); });
    document.querySelectorAll('[data-i18n-placeholder]').forEach(node => { node.setAttribute('placeholder', text(node.dataset.i18nPlaceholder)); });
  };
  window.RfidI18n = { text, render, get language() { return language; } };
})();
