/* ============================================================================
 * otm-i18n.js — OUTTHINK THE MARKET · traduzione a runtime delle viste (IT · EN · ES)
 * ----------------------------------------------------------------------------
 * Iniettato da app.py in FakeMove e Footprint, prima dei loro script.
 * Le viste restano com'erano: i testi (italiani o inglesi) vengono tradotti
 * mentre compaiono, usando il catalogo locales/views.json.
 *
 *   window.__OTM_DICT   catalogo { esatte: {...}, frammenti: {...} } (da app.py)
 *   window.__OTM_LANG   lingua iniziale 'it' | 'en' | 'es'
 *   evento 'otm:lang'   detail.lang: cambio lingua a vista già aperta
 *
 * Dove traduce:
 *   · testo DOM (anche quello creato dopo, via MutationObserver) + attributi
 *     title / placeholder / aria-label / data-tip
 *   · canvas: fillText / strokeText / measureText (le etichette dei grafici)
 *   · alert / confirm / prompt e Notification
 *
 * Regole: voce "esatta" = intero testo del nodo (spazi ai bordi ignorati);
 * "frammento" = sottostringa dentro testi composti (la più lunga vince);
 * {nome} nel frammento = parte variabile. Testo senza voce: resta com'è.
 * Il testo originale di ogni nodo è conservato, quindi si può passare
 * da una lingua all'altra senza perdere nulla.
 * ==========================================================================*/
(function () {
  'use strict';
  if (window.OTMi18n) return;

  var LANGS = { it: 1, en: 1, es: 1 };
  var dict = window.__OTM_DICT || {};
  var LANG = LANGS[window.__OTM_LANG] ? window.__OTM_LANG : 'it';
  var ATTRS = ['title', 'placeholder', 'aria-label', 'data-tip'];
  var HAS_WORD = /[A-Za-zÀ-ÿ]{2}/;

  // ── compilazione del catalogo ────────────────────────────────────────────
  var exact = Object.create(null);                 // testo -> {it,en,es}
  var fragLit = [];                                // [{k, v}] letterali, dal più lungo
  var fragPat = [];                                // [{re, names, v}] con {nome}
  var fragRe = null, fragMap = Object.create(null);

  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  (function build() {
    var E = dict.esatte || {}, F = dict.frammenti || {}, k;
    for (k in E) exact[k] = E[k];
    var lits = [];
    for (k in F) {
      if (k.indexOf('{') >= 0 && /\{\w+\}/.test(k)) {
        var names = [];
        var src = esc(k).replace(/\\\{(\w+)\\\}/g, function (m, n) { names.push(n); return '(\\S+?)'; });
        fragPat.push({ re: new RegExp(src, 'g'), names: names, v: F[k], len: k.length });
      } else { lits.push(k); fragMap[k] = F[k]; }
    }
    lits.sort(function (a, b) { return b.length - a.length; });
    fragLit = lits;
    fragPat.sort(function (a, b) { return b.len - a.len; });
    if (lits.length) fragRe = new RegExp(lits.map(esc).join('|'), 'g');
  })();

  // ── traduzione di una stringa ────────────────────────────────────────────
  var cache = new Map();
  function val(entry) { var s = entry && entry[LANG]; return (typeof s === 'string' && s) ? s : null; }

  function compute(s) {
    var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s), core = m[2];
    if (core) {
      var hit = exact[core] || (/\s{2,}/.test(core) ? exact[core.replace(/\s+/g, ' ')] : null);
      var v = val(hit); if (v) return m[1] + v + m[3];
    }
    var out = s;
    for (var i = 0; i < fragPat.length; i++) {         // frammenti con parti variabili
      var p = fragPat[i], tv = val(p.v); if (!tv) continue;
      p.re.lastIndex = 0;
      out = out.replace(p.re, function () {
        var a = arguments, r = tv;
        for (var j = 0; j < p.names.length; j++) r = r.split('{' + p.names[j] + '}').join(a[j + 1]);
        return r;
      });
    }
    if (fragRe) {
      fragRe.lastIndex = 0;
      out = out.replace(fragRe, function (x) { var t = val(fragMap[x]); return t == null ? x : t; });
    }
    return out;
  }
  function tr(s) {
    if (typeof s !== 'string' || s.length < 2 || !HAS_WORD.test(s)) return s;
    var c = cache.get(s); if (c !== undefined) return c;
    var out = compute(s);
    if (cache.size > 5000) cache.clear();
    cache.set(s, out);
    return out;
  }

  // ── DOM: testo e attributi, con l'originale sempre conservato ────────────
  var TEXT = new WeakMap();                         // nodo di testo -> {src, out}
  var ATTR = new WeakMap();                         // elemento -> {attr: {src, out}}
  var SKIP = { SCRIPT: 1, STYLE: 1, TEXTAREA: 1, NOSCRIPT: 1 };

  function doText(n) {
    var cur = n.nodeValue, rec = TEXT.get(n), src = (rec && cur === rec.out) ? rec.src : cur;
    var out = tr(src);
    if (out !== cur) n.nodeValue = out;
    if (out !== src) TEXT.set(n, { src: src, out: out }); else if (rec) TEXT.delete(n);
  }
  function doAttr(el, a) {
    var cur = el.getAttribute(a); if (cur == null) return;
    var map = ATTR.get(el), rec = map && map[a], src = (rec && cur === rec.out) ? rec.src : cur;
    var out = tr(src);
    if (out !== cur) el.setAttribute(a, out);
    if (out !== src) { if (!map) { map = {}; ATTR.set(el, map); } map[a] = { src: src, out: out }; }
    else if (rec) delete map[a];
  }
  function doEl(el) { for (var i = 0; i < ATTRS.length; i++) if (el.hasAttribute(ATTRS[i])) doAttr(el, ATTRS[i]); }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (root.parentNode && !SKIP[root.parentNode.nodeName]) doText(root); return; }
    if (root.nodeType !== 1 || SKIP[root.nodeName]) return;
    doEl(root);
    var w = document.createTreeWalker(root, 1 | 4, null), n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) { if (!SKIP[n.parentNode.nodeName]) doText(n); }
      else if (!SKIP[n.nodeName]) doEl(n);
    }
  }

  var mo = null;
  function onMutations(list) {
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r.type === 'characterData') { if (r.target.parentNode && !SKIP[r.target.parentNode.nodeName]) doText(r.target); }
      else if (r.type === 'attributes') doAttr(r.target, r.attributeName);
      else for (var j = 0; j < r.addedNodes.length; j++) walk(r.addedNodes[j]);
    }
  }
  function observe() {
    if (mo || !window.MutationObserver) return;
    mo = new MutationObserver(onMutations);
    mo.observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }

  // ── canvas, finestre di dialogo, notifiche ───────────────────────────────
  (function patchCanvas() {
    var P = window.CanvasRenderingContext2D && window.CanvasRenderingContext2D.prototype; if (!P) return;
    ['fillText', 'strokeText', 'measureText'].forEach(function (name) {
      var orig = P[name]; if (typeof orig !== 'function') return;
      P[name] = function (text) {
        if (typeof text === 'string') arguments[0] = tr(text);
        return orig.apply(this, arguments);
      };
    });
  })();
  ['alert', 'confirm', 'prompt'].forEach(function (name) {
    var orig = window[name]; if (typeof orig !== 'function') return;
    window[name] = function (msg) {
      var a = Array.prototype.slice.call(arguments);
      if (a.length) a[0] = tr(String(a[0]));
      return orig.apply(window, a);
    };
  });
  (function patchNotification() {
    var N = window.Notification; if (typeof N !== 'function') return;
    var W = function (title, opts) {
      if (opts && typeof opts.body === 'string') { opts = Object.assign({}, opts); opts.body = tr(opts.body); }
      return new N(tr(String(title)), opts);
    };
    W.prototype = N.prototype;
    try { Object.defineProperty(W, 'permission', { get: function () { return N.permission; } }); } catch (e) {}
    if (N.requestPermission) W.requestPermission = N.requestPermission.bind(N);
    try { window.Notification = W; } catch (e) {}
  })();

  // ── cambio lingua ────────────────────────────────────────────────────────
  function redraw() {
    try { var i = window.OTMNav && window.OTMNav.instance; if (i && i.adapter && i.adapter.redraw) i.adapter.redraw(); } catch (e) {}
  }
  function setLang(l) {
    if (!LANGS[l] || l === LANG) return LANG;
    LANG = l; cache.clear();
    if (document.body) walk(document.documentElement);
    redraw();
    return LANG;
  }
  window.addEventListener('otm:lang', function (e) { if (e && e.detail) setLang(e.detail.lang); });

  window.OTMi18n = { t: tr, lang: function () { return LANG; }, setLang: setLang, version: '1.0' };

  observe();
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', function () { walk(document.documentElement); });
  else walk(document.documentElement);
})();
