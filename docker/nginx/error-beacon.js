/*
 * MrMap frontend error beacon.
 *
 * Reports browser side errors to `POST /api/system/error`, which nginx answers
 * on its own (see `docker/nginx/mrmap.conf`): the fields of a report travel in
 * the query string, nginx writes one line into its `mrmap_frontend_error` log
 * and answers with an empty body. Django never sees a report, so there is no
 * endpoint that has to be kept free of credentials and no request body that a
 * report could cost anything more than a log line.
 *
 * Injected into the built `index.html` *before* the app bundle, and plain JS
 * instead of app code, so that it also catches the app bundle failing:
 *
 *   - uncaught exceptions          (window error)
 *   - unhandled promise rejections (unhandledrejection)
 *   - failed resource loads        (script/img/css, via the capturing listener)
 *
 * Failing same origin API calls are deliberately NOT reported from here: the
 * access log of this very nginx records every status code of every call
 * already, and a browser side report would have the beacon POST at exactly the
 * API that is down.
 *
 * One report is one request line and nginx accepts 8k of it, so the payload is
 * bounded here rather than answered 414 there. Nothing in this file may ever
 * break the page: every field is truncated, identical reports within a window
 * drop, a page load reports at most MAX_REPORTS times, and every failure path
 * is swallowed.
 */
(function () {
  'use strict';

  var ENDPOINT = '/api/system/error';
  var SELF = 'error-beacon.js';     // the beacon never reports itself
  var MAX_REPORTS = 20;             // hard cap per page load
  var DEDUP_WINDOW_MS = 30000;      // identical reports inside this window drop
  var MAX_QUERY = 3000;             // of the 8k nginx takes for a request line
  var MAX_MSG = 500;
  var MAX_STACK = 1000;
  var MAX_URL = 200;
  var MAX_PAGE = 300;

  var sent = 0;
  var seen = Object.create(null);

  function truncate(value, max) {
    value = value == null ? '' : String(value);
    return value.length > max ? value.slice(0, max) : value;
  }

  // encodeURIComponent leaves the sub-delimiters !'()* alone, and those are the
  // characters a strict reverse proxy is most likely to refuse in a query.
  // Nothing of a report needs them, so they go too: what travels is unreserved
  // characters and the separators of the query itself, and the log line reads
  // as percent encoded text, which is what an access log looks like anyway
  function encode(value) {
    return encodeURIComponent(value).replace(
      /[!'()*]/g,
      function (c) { return '%' + c.charCodeAt(0).toString(16).toUpperCase(); }
    );
  }

  // the values stay encoded, nginx hands them to the log line as they arrived
  function query(entry, withStack) {
    var parts = [
      'source=' + encode(entry.source),
      'msg=' + encode(entry.message),
      'url=' + encode(entry.url),
      'page=' + encode(entry.page)
    ];
    if (withStack && entry.stack) {
      parts.push('stack=' + encode(entry.stack));
    }
    return parts.join('&');
  }

  function send(url) {
    // a beacon survives the page going away, which is when a load failure is
    // worth most, and it cannot set headers — so a report needs none
    if (navigator.sendBeacon) {
      try {
        if (navigator.sendBeacon(url, '')) {
          return;
        }
      } catch (e) { /* fall through to fetch */ }
    }
    if (window.fetch) {
      try {
        window.fetch(url, { method: 'POST', keepalive: true })
          .catch(function () { /* reporting failure must stay silent */ });
      } catch (e) { /* reporting failure must stay silent */ }
    }
  }

  function report(source, message, stack, url) {
    try {
      if (sent >= MAX_REPORTS) {
        return;
      }
      var entry = {
        source: source,
        message: truncate(message, MAX_MSG) || 'unspecified frontend error',
        stack: truncate(stack, MAX_STACK),
        url: truncate(url, MAX_URL),
        page: truncate(window.location.href, MAX_PAGE)
      };

      var key = source + '|' + entry.message;
      var now = Date.now();
      if (seen[key] && now - seen[key] < DEDUP_WINDOW_MS) {
        return;
      }
      seen[key] = now;

      // the stack is the bulkiest field, so it goes first, then the rest of
      // what a request line has no room for
      var encoded = query(entry, true);
      if (encoded.length > MAX_QUERY) {
        encoded = query(entry, false);
      }
      if (encoded.length > MAX_QUERY) {
        encoded = query({
          source: entry.source,
          message: entry.message,
          url: '',
          page: entry.page
        }, false);
      }
      if (encoded.length > MAX_QUERY) {
        return;
      }

      sent++;
      send(ENDPOINT + '?' + encoded);
    } catch (e) { /* reporting failure must stay silent */ }
  }

  // runtime errors and, with capture, resource load failures
  window.addEventListener('error', function (ev) {
    try {
      var target = ev.target;
      if (target && target !== window && target.tagName) {
        var src = target.src || target.href || '';
        if (src.indexOf(SELF) !== -1) {
          return;
        }
        report('resource',
               target.tagName + ' failed to load: ' + truncate(src, MAX_URL));
        return;
      }
      var where = ev.filename || '';
      if (ev.lineno) {
        where += ':' + ev.lineno + ':' + ev.colno;
      }
      report('error',
             ev.message || String(ev.error || 'unknown error'),
             ev.error && ev.error.stack,
             where);
    } catch (e) { /* reporting failure must stay silent */ }
  }, true);

  window.addEventListener('unhandledrejection', function (ev) {
    try {
      var reason = ev.reason;
      report('rejection',
             (reason && reason.message) || String(reason),
             reason && reason.stack);
    } catch (e) { /* reporting failure must stay silent */ }
  });
})();
