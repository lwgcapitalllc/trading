// Browser guard for the Playwright MCP server (wired in /.mcp.json via --init-script).
//
// WHY THIS EXISTS
// The Command Center's backend talks to the live trading box. A click on the page can
// stop the armed bot, promote new code under it, deploy a strategy, or rewrite a broker
// account row -- with no undo and no confirmation step that a browser automation would
// pause on. "The agent will be careful" is a rule that lives in somebody's memory, and
// this repo has a standing lesson that such a rule is not one the next command respects.
// So the refusal lives in the page instead: these requests never leave the browser.
//
// WHAT IT DOES NOT DO
// It is NOT a security boundary. It runs inside the page and anything with real intent
// could remove it. It exists to make an ACCIDENT impossible, not an attack. The live
// safety story is still the promote/stop workflow in the root CLAUDE.md.
//
// The read-only twins are deliberately ALLOWED: a promote PREVIEW changes nothing and is
// the whole point of previewing. Lab writes (backtests, sweeps, stacks, stress tests,
// optimizations) are allowed too -- they cost compute, never money.

(function () {
  'use strict';

  var MARKER = '[browser-guard]';

  // Each rule: methods that are refused, and a pattern for the path.
  // Paths are matched with and without the frontend's /api proxy prefix, so hitting the
  // backend port directly is refused the same way as going through the dev server.
  var RULES = [
    {
      what: 'start, stop or restart a bot (fleet-wide or one bot)',
      methods: ['POST'],
      path: /^\/bots(\/[^/]+)?\/(start|stop|restart)$/,
    },
    {
      what: 'promote code under a running bot',
      methods: ['POST'],
      // /bots/<name>/promote is refused; /bots/<name>/promote/preview is not.
      path: /^\/bots\/[^/]+\/promote$/,
    },
    {
      what: 'deploy a strategy to the VPS',
      methods: ['POST'],
      path: /^\/strategies\/[^/]+\/deploy$/,
    },
    {
      what: 'delete a strategy source file',
      methods: ['DELETE'],
      path: /^\/strategies\/[^/]+$/,
    },
    {
      what: 'add, change or remove a broker account (including its password)',
      methods: ['PUT', 'DELETE', 'POST'],
      path: /^\/bots\/accounts\/registry(\/.*)?$/,
    },
    {
      what: 'add or remove a Telegram user',
      methods: ['POST', 'DELETE'],
      path: /^\/bots\/users(\/.*)?$/,
    },
    {
      what: 'start an agent process on a trading box',
      methods: ['POST'],
      path: /^\/system\/(nt8|mt5)-agent\/start$/,
    },
  ];

  // Reduce a request URL to the backend path: drop origin, query and hash, then peel the
  // dev server's /api proxy prefix. Returns null when the URL cannot be understood, and a
  // path we cannot understand is NOT refused -- the guard covers named live actions only.
  function toBackendPath(rawUrl, base) {
    var parsed;
    try {
      parsed = new URL(String(rawUrl), base || 'http://localhost:5173');
    } catch (err) {
      return null;
    }
    var path = parsed.pathname;
    if (path.indexOf('/api/') === 0) path = path.slice(4);
    else if (path === '/api') path = '/';
    if (path.length > 1 && path.charAt(path.length - 1) === '/') path = path.slice(0, -1);
    return path;
  }

  // Returns the matching rule, or null when the request is allowed.
  function refusalFor(method, rawUrl, base) {
    var verb = String(method || 'GET').toUpperCase();
    var path = toBackendPath(rawUrl, base);
    if (path === null) return null;
    for (var i = 0; i < RULES.length; i++) {
      var rule = RULES[i];
      if (rule.methods.indexOf(verb) !== -1 && rule.path.test(path)) return rule;
      }
    return null;
  }

  function refusalError(rule, method, rawUrl) {
    var msg =
      MARKER +
      ' REFUSED ' +
      String(method).toUpperCase() +
      ' ' +
      rawUrl +
      ' -- this would ' +
      rule.what +
      '. Browser automation is not allowed to take live actions. Do it yourself in the ' +
      'app, or use the documented command-line path.';
    return new Error(msg);
  }

  // Node (the check script) loads this file for the matcher only -- there is no page to
  // patch, so stop here.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { refusalFor: refusalFor, toBackendPath: toBackendPath, RULES: RULES };
    return;
  }
  if (typeof window === 'undefined') return;

  var here = typeof location !== 'undefined' ? location.href : undefined;

  // A handle the page can be asked about, so the guard can be PROVEN present without
  // firing a live request to find out. Never let "the guard is on" and "the guard is off
  // and nothing happened to be clicked" look the same.
  window.__browserGuard = {
    active: true,
    marker: MARKER,
    rules: RULES.length,
    refusalFor: function (method, url) {
      var rule = refusalFor(method, url, here);
      return rule ? rule.what : null;
    },
  };

  var realFetch = window.fetch;
  if (typeof realFetch === 'function') {
    window.fetch = function (input, init) {
      var url = input && typeof input === 'object' && 'url' in input ? input.url : input;
      var method =
        (init && init.method) ||
        (input && typeof input === 'object' && input.method) ||
        'GET';
      var rule = refusalFor(method, url, here);
      if (rule) {
        var err = refusalError(rule, method, url);
        console.error(err.message);
        return Promise.reject(err);
      }
      return realFetch.apply(this, arguments);
    };
  }

  var XHR = window.XMLHttpRequest;
  if (XHR && XHR.prototype && typeof XHR.prototype.open === 'function') {
    var realOpen = XHR.prototype.open;
    XHR.prototype.open = function (method, url) {
      var rule = refusalFor(method, url, here);
      if (rule) {
        var err = refusalError(rule, method, url);
        console.error(err.message);
        throw err;
      }
      return realOpen.apply(this, arguments);
    };
  }

  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {
    var realBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (url) {
      var rule = refusalFor('POST', url, here);
      if (rule) {
        console.error(refusalError(rule, 'POST', url).message);
        return false;
      }
      return realBeacon.apply(null, arguments);
    };
  }

  console.info(MARKER + ' active -- live bot, promote, deploy and account writes are refused');
})();
