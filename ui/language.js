'use strict';
// Language is scoped to the URL; projects and settings share the same local store.
(() => {
  const english = document.documentElement.lang === 'en';
  const catalog = /* ENGLISH_CATALOG */ {};
  window.DraftLanguage = {systemText(text) {
    if (!english || typeof text !== 'string') return text;
    if (catalog[text]) return catalog[text];
    const round = text.match(/^Gemini 第 (\d+) 轮生成 · 已调用 (\d+(?:\/\d+)?) 个工具$/);
    if (round) return `Gemini generation round ${round[1]} · ${round[2]} tools used`;
    if (text.startsWith('开始：')) {
      const [label, ...detail] = text.slice(3).split(' · ');
      return 'Starting: ' + (catalog[label] || label) + (detail.length ? ' · ' + detail.join(' · ') : '');
    }
    return text;
  }};
  const button = document.getElementById('language-switch');
  button.textContent = english ? 'Chinese' : 'English';
  button.setAttribute('aria-label', english ? 'Switch to Chinese' : 'Switch to English');
  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    if (english && url.origin === location.origin && url.pathname.startsWith('/api/')) {
      const headers = new Headers(input instanceof Request ? input.headers : undefined);
      new Headers(options.headers).forEach((value, key) => headers.set(key, value));
      headers.set('X-Draft-Language', 'en');
      options = {...options, headers};
    }
    return originalFetch(input, options);
  };
  button.onclick = async () => {
    if (typeof busy !== 'undefined' && (busy || loadingFile)) {
      status(english ? 'Wait for the current operation to finish before switching languages.' : '请等待当前操作完成后切换语言。');
      return;
    }
    // Dialogs can contain unsaved source, rule, or configuration edits.
    if (document.querySelector('dialog[open]')) {
      status(english ? 'Save or close the open dialog before switching languages.' : '请先保存或关闭当前弹窗，再切换语言。');
      return;
    }
    button.disabled = true;
    try {
      if (typeof project !== 'undefined' && project) {
        clearTimeout(inputTimer);
        if (active()) active().input = document.getElementById('prompt').value;
        if (!await persist()) return;
      }
      location.assign(english ? '/' : '/en/');
    } finally { button.disabled = false; }
  };
})();
