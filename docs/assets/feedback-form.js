/* feedback-relay SDK — готовая форма-оверлей (M3, issue #3).
 *
 * Опциональная надстройка над headless-ядром feedback.js: кнопка + модальный
 * оверлей (textarea + опц. имя) из коробки — для проектов без своего UI. unevie
 * её НЕ подключает: у него свой стилизованный диалог поверх только ядра
 * (DESIGN.md §2 п.4). Порядок подключения — ядро, затем надстройка:
 *
 *   <script src="feedback.js"></script>       // ядро: FeedbackRelay.send
 *   <script src="feedback-form.js"></script>  // надстройка: FeedbackRelay.mount
 *   <script>
 *     var handle = FeedbackRelay.mount({ endpoint: ENDPOINT, project: 'demo' });
 *     // handle = { open, close, destroy } — для button:false / своего триггера
 *   </script>
 *
 * Без зависимостей, один вшитый <style> (light/dark по prefers-color-scheme +
 * явный theme-override в обе стороны), вместе с ядром ≤10 КБ. Доставка — через
 * FeedbackRelay.send ядра, поэтому таймаут/коды ошибок/контракт — те же.
 */
(function (global) {
  'use strict';

  /* Держится равным LIMITS.MAX_TEXT воркера (`worker/worker.js:34`). Сервер
     режет текст на 4000 символах и отвечает 413 — то есть длинный вдумчивый
     отзыв терялся целиком в момент отправки, а это ровно то, ради чего канал
     существует (#42). Дублирование числа здесь неизбежно: SDK статичен и
     воркера ни о чём не спрашивает, поэтому оно названо, а не спрятано в
     разметке. */
  var MAX_TEXT = 4000;

  /* Дефолтные подписи: два встроенных набора (ru/en), любой ключ переопределяется
     через opts.labels. Тексты — данные автора страницы, не пользовательский ввод. */
  var DEFAULT_LABELS = {
    ru: {
      button: 'Оставить отзыв',
      title: 'Обратная связь',
      placeholder: 'Что можно улучшить? Что понравилось?',
      name: 'Имя (необязательно)',
      submit: 'Отправить',
      sending: 'Отправляем…',
      close: 'Закрыть',
      // Одной фразы достаточно: согласия/чекбокса issue #42 не требует —
      // требуется, чтобы человек знал, куда уходит текст, ДО отправки.
      privacy: 'Текст уходит в рабочий чат команды; имя указывать не обязательно.',
      remaining: 'осталось символов: {n}',
      success: 'Спасибо! Отзыв отправлен.',
      empty: 'Напишите пару слов.',
      rate: 'Слишком часто — попробуйте через минуту.',
      error: 'Не отправилось. Попробуйте позже.',
    },
    en: {
      button: 'Send feedback',
      title: 'Feedback',
      placeholder: 'What can we improve? What did you like?',
      name: 'Name (optional)',
      submit: 'Send',
      sending: 'Sending…',
      close: 'Close',
      privacy: 'Your message goes to the team chat; the name field is optional.',
      remaining: '{n} characters left',
      success: 'Thanks! Your feedback was sent.',
      empty: 'Please write a few words.',
      rate: 'Too many requests — try again in a minute.',
      error: "Couldn't send. Please try again later.",
    },
  };

  /* Выбор языка встроенных подписей: явный opts.lang → <html lang> → ru.
     Чистая функция (document читается только при отсутствии явного значения). */
  function pickLang(explicit) {
    if (explicit === 'ru' || explicit === 'en') return explicit;
    if (typeof document !== 'undefined' && document.documentElement) {
      var l = (document.documentElement.lang || '').toLowerCase();
      if (l.indexOf('en') === 0) return 'en';
    }
    return 'ru';
  }

  /* Встроенный набор языка + пользовательские переопределения поверх. */
  function resolveLabels(userLabels, lang) {
    var base = DEFAULT_LABELS[lang] || DEFAULT_LABELS.ru;
    var out = {};
    for (var k in base) if (Object.prototype.hasOwnProperty.call(base, k)) out[k] = base[k];
    if (userLabels) for (var u in userLabels) {
      if (Object.prototype.hasOwnProperty.call(userLabels, u) && userLabels[u] != null) out[u] = String(userLabels[u]);
    }
    return out;
  }

  /* Код ошибки send() → подпись для пользователя. 'rate' различаем явно
     (DESIGN.md §8: «отправлено / слишком часто / не дошло»); остальное — generic. */
  function errorText(code, L) {
    if (code === 'client_empty') return L.empty;
    if (code === 'rate') return L.rate;
    return L.error;
  }

  var STYLE_ID = 'fr-form-style';
  var mountSeq = 0;

  /* Один вшитый <style>, инжектится единожды. Палитра — CSS-переменные: дефолт
     светлый, тёмный по prefers-color-scheme, плюс явный [data-fr-theme] в обе
     стороны (override побеждает медиазапрос). */
  var CSS =
    '.fr-overlay,.fr-trigger{--fr-bg:#fff;--fr-fg:#1a1a1a;--fr-muted:#5b6470;' +
    '--fr-border:#d3d8de;--fr-field:#fff;--fr-accent:#2b6cb0;--fr-accent-fg:#fff;' +
    '--fr-backdrop:rgba(16,20,26,.5);--fr-err:#c0392b;--fr-ok:#1f7a4d;' +
    "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;box-sizing:border-box}" +
    '@media (prefers-color-scheme:dark){.fr-overlay,.fr-trigger{--fr-bg:#20242b;' +
    '--fr-fg:#eceff3;--fr-muted:#9aa4b0;--fr-border:#39414c;--fr-field:#171a20;' +
    '--fr-accent:#4c9be8;--fr-accent-fg:#0b0e12;--fr-backdrop:rgba(0,0,0,.6)}}' +
    '.fr-overlay[data-fr-theme=dark],.fr-trigger[data-fr-theme=dark]{--fr-bg:#20242b;' +
    '--fr-fg:#eceff3;--fr-muted:#9aa4b0;--fr-border:#39414c;--fr-field:#171a20;' +
    '--fr-accent:#4c9be8;--fr-accent-fg:#0b0e12;--fr-backdrop:rgba(0,0,0,.6)}' +
    '.fr-overlay[data-fr-theme=light],.fr-trigger[data-fr-theme=light]{--fr-bg:#fff;' +
    '--fr-fg:#1a1a1a;--fr-muted:#5b6470;--fr-border:#d3d8de;--fr-field:#fff;' +
    '--fr-accent:#2b6cb0;--fr-accent-fg:#fff;--fr-backdrop:rgba(16,20,26,.5)}' +
    '.fr-trigger{position:fixed;right:18px;bottom:18px;z-index:2147483000;' +
    'padding:10px 16px;border:0;border-radius:999px;background:var(--fr-accent);' +
    'color:var(--fr-accent-fg);font-size:14px;font-weight:600;cursor:pointer;' +
    'box-shadow:0 3px 12px rgba(0,0,0,.25)}' +
    '.fr-trigger:hover{filter:brightness(1.06)}' +
    '.fr-overlay{position:fixed;inset:0;z-index:2147483001;display:flex;' +
    'align-items:center;justify-content:center;padding:16px;' +
    'background:var(--fr-backdrop)}' +
    '.fr-overlay[hidden]{display:none}' +
    '.fr-dialog{background:var(--fr-bg);color:var(--fr-fg);width:100%;' +
    'max-width:420px;border-radius:12px;padding:20px;position:relative;' +
    'box-shadow:0 12px 40px rgba(0,0,0,.35);max-height:calc(100vh - 32px);overflow:auto}' +
    '.fr-title{margin:0 0 12px;font-size:18px;font-weight:700}' +
    '.fr-close{position:absolute;top:10px;right:10px;width:32px;height:32px;' +
    'border:0;border-radius:8px;background:transparent;color:var(--fr-muted);' +
    'font-size:22px;line-height:1;cursor:pointer}' +
    '.fr-close:hover{background:rgba(127,127,127,.15)}' +
    '.fr-text,.fr-name{width:100%;box-sizing:border-box;margin:0 0 10px;' +
    'padding:10px;border:1px solid var(--fr-border);border-radius:8px;' +
    'background:var(--fr-field);color:var(--fr-fg);font:inherit;font-size:14px}' +
    '.fr-text{min-height:96px;resize:vertical}' +
    '.fr-text:focus,.fr-name:focus,.fr-submit:focus-visible,.fr-close:focus-visible,' +
    '.fr-trigger:focus-visible{outline:2px solid var(--fr-accent);outline-offset:2px}' +
    '.fr-actions{display:flex;align-items:center;gap:12px;margin-top:4px}' +
    '.fr-submit{padding:9px 18px;border:0;border-radius:8px;' +
    'background:var(--fr-accent);color:var(--fr-accent-fg);font-size:14px;' +
    'font-weight:600;cursor:pointer}' +
    '.fr-submit[disabled]{opacity:.6;cursor:default}' +
    '.fr-status{font-size:13px;min-height:18px;color:var(--fr-muted)}' +
    '.fr-privacy{font-size:12px;line-height:1.4;margin:0 0 10px;color:var(--fr-muted)}' +
    '.fr-counter{font-size:12px;text-align:right;margin:-6px 0 10px;color:var(--fr-muted)}' +
    '.fr-status.fr-err{color:var(--fr-err)}.fr-status.fr-ok{color:var(--fr-ok)}';

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;
    var s = document.createElement('style');
    s.id = STYLE_ID;
    s.textContent = CSS;
    (document.head || document.documentElement).appendChild(s);
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  var FOCUSABLE =
    'a[href],button:not([disabled]),textarea:not([disabled]),input:not([disabled]),' +
    'select:not([disabled]),[tabindex]:not([tabindex="-1"])';

  /* Готовая форма-оверлей. Возвращает { open, close, destroy }. */
  function mount(opts) {
    opts = opts || {};
    if (typeof document === 'undefined')
      throw new Error('feedback-relay: mount() требует DOM (только браузер)');
    if (!opts.endpoint || !opts.project)
      throw new Error('feedback-relay: mount() требует { endpoint, project }');

    var endpoint = opts.endpoint;
    var project = opts.project;
    var L = resolveLabels(opts.labels, pickLang(opts.lang));
    var theme = opts.theme === 'light' || opts.theme === 'dark' ? opts.theme : null; // null = auto
    var getContext = typeof opts.context === 'function' ? opts.context : null;
    var sendOpts = opts.timeoutMs ? { timeoutMs: opts.timeoutMs } : undefined;

    injectStyle();
    var titleId = 'fr-title-' + (++mountSeq);

    var overlay = el('div', 'fr-overlay');
    overlay.hidden = true;
    if (theme) overlay.setAttribute('data-fr-theme', theme);

    var dialog = el('div', 'fr-dialog');
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', titleId);

    var closeBtn = el('button', 'fr-close', '×');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', L.close);

    var title = el('h2', 'fr-title', L.title);
    title.id = titleId;

    var form = el('form', 'fr-form');
    var textarea = el('textarea', 'fr-text');
    textarea.setAttribute('placeholder', L.placeholder);
    textarea.setAttribute('aria-label', L.title);
    textarea.required = true;
    textarea.setAttribute('maxlength', String(MAX_TEXT));
    var nameInput = el('input', 'fr-name');
    nameInput.type = 'text';
    nameInput.setAttribute('placeholder', L.name);
    nameInput.setAttribute('aria-label', L.name);
    var status = el('div', 'fr-status');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    var privacy = el('div', 'fr-privacy', L.privacy);
    var counter = el('div', 'fr-counter');
    function updateCounter() {
      var left = MAX_TEXT - textarea.value.length;
      counter.textContent = L.remaining.replace('{n}', String(left));
    }
    textarea.addEventListener('input', updateCounter);
    updateCounter();
    var actions = el('div', 'fr-actions');
    var submitBtn = el('button', 'fr-submit', L.submit);
    submitBtn.type = 'submit';

    actions.appendChild(submitBtn);
    form.appendChild(textarea);
    form.appendChild(counter);
    form.appendChild(nameInput);
    form.appendChild(privacy);
    form.appendChild(status);
    form.appendChild(actions);
    dialog.appendChild(closeBtn);
    dialog.appendChild(title);
    dialog.appendChild(form);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    var previouslyFocused = null;
    var closeTimer = null;

    function setStatus(msg, kind) {
      status.textContent = msg || '';
      status.className = 'fr-status' + (kind ? ' fr-' + kind : '');
    }

    function resetForm() {
      textarea.value = '';
      nameInput.value = '';
      submitBtn.disabled = false;
      setStatus('', '');
    }

    function trapTab(e) {
      var f = Array.prototype.slice
        .call(dialog.querySelectorAll(FOCUSABLE))
        .filter(function (n) { return n.offsetParent !== null || n === document.activeElement; });
      if (!f.length) return;
      var first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }

    function onKey(e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      else if (e.key === 'Tab') trapTab(e);
    }

    function open() {
      if (!overlay.hidden) return;
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
      previouslyFocused = document.activeElement;
      resetForm();
      overlay.hidden = false;
      overlay.addEventListener('keydown', onKey);
      textarea.focus();
    }

    function close() {
      if (overlay.hidden) return;
      if (closeTimer) { clearTimeout(closeTimer); closeTimer = null; }
      overlay.hidden = true;
      overlay.removeEventListener('keydown', onKey);
      if (previouslyFocused && typeof previouslyFocused.focus === 'function' &&
          document.contains(previouslyFocused)) previouslyFocused.focus();
    }

    function submit(e) {
      e.preventDefault();
      var text = textarea.value;
      if (!text.trim()) { setStatus(L.empty, 'err'); textarea.focus(); return; }
      submitBtn.disabled = true;
      setStatus(L.sending, '');

      var payload = { text: text };
      if (nameInput.value.trim()) payload.name = nameInput.value;
      if (getContext) {
        /* контекст собирается в момент отправки (актуальное состояние); ошибку
           в коллекторе проекта не даём заблокировать отправку отзыва */
        try {
          var ctx = getContext();
          if (ctx && typeof ctx === 'object') payload.context = ctx;
        } catch (err) { /* контекст пропускаем */ }
      }

      var relay = global.FeedbackRelay;
      if (!relay || typeof relay.send !== 'function') {
        submitBtn.disabled = false;
        setStatus(L.error, 'err');
        throw new Error('feedback-relay: mount() требует загруженное ядро feedback.js (FeedbackRelay.send)');
      }

      relay.send(endpoint, project, payload, sendOpts).then(function () {
        setStatus(L.success, 'ok');
        textarea.value = '';
        nameInput.value = '';
        closeTimer = setTimeout(close, 1400);
      }).catch(function (err) {
        submitBtn.disabled = false;
        setStatus(errorText(err && err.code, L), 'err');
        textarea.focus();
      });
    }

    form.addEventListener('submit', submit);
    closeBtn.addEventListener('click', close);
    /* клик по подложке (вне диалога) закрывает; клик внутри диалога — нет */
    overlay.addEventListener('click', function (e) { if (e.target === overlay) close(); });

    /* Триггер: false → без кнопки (свой вызов open()); Element/селектор →
       привязка к существующему элементу; иначе — плавающая кнопка. */
    var trigger = null;
    var ownsTrigger = false;
    if (opts.button === false) {
      trigger = null;
    } else if (opts.button && opts.button.nodeType === 1) {
      trigger = opts.button;
    } else if (typeof opts.button === 'string') {
      trigger = document.querySelector(opts.button);
      if (!trigger && typeof console !== 'undefined' && console.warn)
        console.warn('feedback-relay: селектор кнопки не найден:', opts.button);
    }
    if (!trigger && opts.button !== false) {
      trigger = el('button', 'fr-trigger', L.button);
      trigger.type = 'button';
      if (theme) trigger.setAttribute('data-fr-theme', theme);
      document.body.appendChild(trigger);
      ownsTrigger = true;
    }
    if (trigger) trigger.addEventListener('click', open);

    function destroy() {
      close();
      if (trigger) trigger.removeEventListener('click', open);
      if (ownsTrigger && trigger && trigger.parentNode) trigger.parentNode.removeChild(trigger);
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
    }

    return { open: open, close: close, destroy: destroy };
  }

  /* Надстройка над тем же объектом, что создаёт ядро (feedback.js): один
     FeedbackRelay c .send и .mount. Ядро должно грузиться первым. */
  var host = global.FeedbackRelay || (global.FeedbackRelay = {});
  host.mount = mount;

  /* CommonJS — для node:test чистых функций (mount требует DOM и тут не гоняется) */
  if (typeof module !== 'undefined' && module.exports)
    module.exports = { mount: mount, resolveLabels: resolveLabels, errorText: errorText, pickLang: pickLang, DEFAULT_LABELS: DEFAULT_LABELS };
})(typeof globalThis !== 'undefined' ? globalThis : this);
