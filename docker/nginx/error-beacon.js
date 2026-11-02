/*
 * MrMap frontend error beacon.
 *
 * Reports browser side errors to `POST /api/system/error` so they land in the
 * central log stack (see `system.views.FrontendErrorView`). It is deliberately
 * a plain script injected into the built `index.html` instead of app code, so
 * it also catches failures of the app bundle itself:
 *
 *   - uncaught exceptions        (window error)
 *   - unhandled promise rejections (unhandledrejection)
 *   - failed resource loads      (script/img/css, via capturing error listener)
 *   - same origin /api/ calls answering 5xx (fetch + XMLHttpRequest)
 *
 * Nothing here may ever break the page: everything is wrapped, every report is
 * size limited, deduplicated and capped per page load.
 */
(function () {
  'use strict';

  var ENDPOINT = '/api/system/error';
  var MAX_REPORTS = 30;          // hard cap per page load
  var DEDUP_WINDOW_MS = 30000;   // identical reports inside this window drop
  var MAX_MSG = 1000;
  var MAX_STACK = 4000;

  var sent = 0;
  var seen = Object.create(null);

  function truncate(value, max) {
    value = value == null ? '' : String(value);
    return value.length > max ? value.slice(0, max) : value;
  }

  function report(entry) {
    try {
      if (sent >= MAX_REPORTS) return;
      var key = entry.source + '|' + truncate(entry.message, 200) + '|' + (entry.status || '');
      var now = Date.now();
      if (seen[key] && now - seen[key] < DEDUP_WINDOW_MS) return;
      seen[key] = now;
      sent++;

      entry.message = truncate(entry.message, MAX_MSG);
      entry.stack = truncate(entry.stack, MAX_STACK);
      entry.url = truncate(entry.url, 500);
      entry.page = window.location.href;
      entry.user_agent = navigator.userAgent;

      var body = JSON.stringify(entry);
      if (body.length > 7000) {
        // stack is the bulkiest field, sacrifice it first
        entry.stack = truncate(entry.stack, 500);
        body = JSON.stringify(entry);
      }
      fetch(ENDPOINT, {
        method: 'POST',
        body: body,
        headers: { 'Content-Type': 'application/json' },
        credentials: 'omit',
        keepalive: true
      }).catch(function () { /* reporting failure must stay silent */ });
    } catch (e) { /* reporting failure must stay silent */ }
  }

  // runtime errors and, with capture, resource load failures
  window.addEventListener('error', function (ev) {
    try {
      var target = ev.target;
      if (target && target !== window && target.tagName) {
        var src = target.src || target.href || '';
        if (src.indexOf('/system/error') !== -1) return;
        report({
          source: 'resource',
          message: target.tagName + ' failed to load: ' + truncate(src, 300)
        });
        return;
      }
      var where = ev.filename || '';
      if (ev.lineno) where += ':' + ev.lineno + ':' + ev.colno;
      report({
        source: 'error',
        message: ev.message || String(ev.error || 'unknown error'),
        stack: ev.error && ev.error.stack,
        url: where
      });
    } catch (e) { /* reporting failure must stay silent */ }
  }, true);

  window.addEventListener('unhandledrejection', function (ev) {
    try {
      var reason = ev.reason;
      report({
        source: 'rejection',
        message: (reason && reason.message) || String(reason),
        stack: reason && reason.stack
      });
    } catch (e) { /* reporting failure must stay silent */ }
  });

  // same origin API calls that answer server side
  var originFetch = window.fetch;
  if (originFetch) {
    window.fetch = function (input, init) {
      var promise = originFetch.apply(this, arguments);
      try {
        var url = typeof input === 'string' ? input : (input && input.url) || '';
        var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
        if (url.indexOf('/api/') !== -1 && url.indexOf('/system/error') === -1) {
          promise.then(function (response) {
            if (response.status >= 500) {
              report({
                source: 'http',
                message: method + ' ' + url + ' -> ' + response.status,
                url: url,
                status: String(response.status)
              });
            }
          }, function () { /* network errors are not server errors */ });
        }
      } catch (e) { /* reporting failure must stay silent */ }
      return promise;
    };
  }

  var XHR = window.XMLHttpRequest;
  if (XHR) {
    var origOpen = XHR.prototype.open;
    XHR.prototype.open = function (method, url) {
      try {
        if (url && String(url).indexOf('/api/') !== -1 &&
            String(url).indexOf('/system/error') === -1) {
          this._mrmapReq = String(method).toUpperCase() + ' ' + url;
          this._mrmapUrl = String(url);
        }
      } catch (e) { /* reporting failure must stay silent */ }
      return origOpen.apply(this, arguments);
    };
    var origSend = XHR.prototype.send;
    XHR.prototype.send = function () {
      var xhr = this;
      if (xhr._mrmapReq) {
        xhr.addEventListener('load', function () {
          try {
            if (xhr.status >= 500) {
              report({
                source: 'http',
                message: xhr._mrmapReq + ' -> ' + xhr.status,
                url: xhr._mrmapUrl,
                status: String(xhr.status)
              });
            }
          } catch (e) { /* reporting failure must stay silent */ }
        });
      }
      return origSend.apply(this, arguments);
    };
  }
})();
