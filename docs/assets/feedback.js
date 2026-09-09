/* feedback-relay SDK — headless-ядро отправки фидбека.
 *
 * Классический скрипт без зависимостей: работает и с хостинга, и из офлайн-файла
 * (file://), и как CommonJS-модуль в тестах. Подключение:
 *
 *   <script src="feedback.js"></script>
 *   FeedbackRelay.send(ENDPOINT, 'unevie', { text, name, context })
 *     .then(() => ui.thanks())
 *     .catch((e) => ui.sorry(e.code));
 *
 * ENDPOINT — базовый URL воркера БЕЗ пути (https://feedback-relay.<acc>.workers.dev).
 * Готовая форма-оверлей (FeedbackRelay.mount) — этап M3, см. DESIGN.md.
 */
(function (global) {
  'use strict';

  var VERSION = '0.1.0';
  var DEFAULT_TIMEOUT_MS = 8000;

  /* Коды ошибок (e.code): совпадают с error-полем воркера, плюс клиентские
     'timeout' | 'network' | 'client_empty'. Текст для пользователя проект
     подбирает сам — SDK не навязывает формулировки. */
  function fail(code, status) {
    var e = new Error('feedback-relay: ' + code);
    e.code = code;
    if (status) e.status = status;
    return e;
  }

  function send(endpoint, projectId, payload, opts) {
    payload = payload || {};
    opts = opts || {};
    var text = String(payload.text == null ? '' : payload.text).trim();
    /* быстрая клиентская проверка — не гонять пустышку по сети */
    if (!text) return Promise.reject(fail('client_empty'));

    var url = String(endpoint).replace(/\/+$/, '') + '/v1/f/' + encodeURIComponent(projectId);
    var body = { text: text, sdk: VERSION };
    if (payload.name) body.name = String(payload.name);
    if (payload.context && typeof payload.context === 'object') body.context = payload.context;

    var ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = ctrl && setTimeout(function () { ctrl.abort(); }, opts.timeoutMs || DEFAULT_TIMEOUT_MS);

    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl ? ctrl.signal : undefined,
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (data) {
        if (r.ok && data.ok === true) return { ok: true };
        throw fail(data.error || ('http_' + r.status), r.status);
      });
    }).catch(function (e) {
      if (e && e.code) throw e;                                  // уже наш fail()
      throw fail(e && e.name === 'AbortError' ? 'timeout' : 'network');
    }).finally(function () {
      if (timer) clearTimeout(timer);
    });
  }

  var api = { version: VERSION, send: send };
  global.FeedbackRelay = api;
  /* CommonJS — для node:test; в браузере ветка не выполняется */
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
