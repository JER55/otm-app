"""
OUTTHINK THE MARKET — shell Streamlit
--------------------------------------
Incorpora le due app JS (Footprint e FakeMove E/L/C). Rendering e websocket
restano nel browser: i dati arrivano dal tuo IP (Italia), non dal server
Streamlit (USA, bloccato da Binance/Bybit).

Struttura lato browser:
  componente Streamlit  ->  shell (barra, tab, orologio sessione USA, fullscreen)
                              ├─ iframe Footprint   (sempre vivo dopo la prima apertura)
                              └─ iframe FakeMove    (idem)
Il cambio vista e' istantaneo: la vista in background continua a ricevere i dati
ma non disegna (window.__OTM_SUSPENDED), quindi non consuma CPU di rendering.

Adattamenti applicati qui al caricamento delle viste:
  1. session-volume-profile.js inserito inline nella Footprint
  2. otm-nav.js (motore di navigazione) inserito in entrambe le viste
  3. rilevamento "localhost" letto dalla pagina principale (non dall'iframe)
  4. in cloud le chiamate di esecuzione (proxy/Netlify) vengono bloccate
"""

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

BASE = Path(__file__).parent
VIEWS = BASE / "views"

# ── Design system (stesso di ThinkCore) ─────────────────────────────────────
INK = "#0B1220"
SURFACE = "#111C2E"
ELEVATED = "#16233A"
TEAL = "#3DD4C8"
MUTED = "#8394B0"
LIGHT = "#E8EEF9"
AMBER = "#F2A93B"
CRIMSON = "#FF5C5C"

st.set_page_config(
    page_title="OTM · Order Flow",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;600&family=JetBrains+Mono:wght@500&display=swap');
html, body, [data-testid="stAppViewContainer"] {{ background:{INK}; }}
[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display:none; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility:hidden; }}
.block-container {{ padding:0.5rem 0.6rem 0 0.6rem !important; max-width:100% !important; }}
.otm-brand {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.05rem;
             letter-spacing:.08em; color:{LIGHT}; }}
.otm-brand span {{ color:{TEAL}; }}
iframe {{ border:1px solid {ELEVATED} !important; border-radius:12px; background:#050a12; display:block; }}
</style>
""",
    unsafe_allow_html=True,
)


# ── Rilevamento ambiente (lato server, solo per il badge) ───────────────────
def _is_local() -> bool:
    try:
        host = (st.context.headers.get("host") or "").split(":")[0]
    except Exception:
        host = ""
    return host in ("localhost", "127.0.0.1") or host.startswith("192.168.") or host.endswith(".local")


# ── Adattamenti per l'iframe ────────────────────────────────────────────────
# Gira PRIMA di ogni altro script della vista.
_SHIM = """<script>
(function () {
  var h = '';
  try { h = window.top.location.hostname || ''; } catch (e) { try { h = window.parent.location.hostname || ''; } catch (e2) {} }
  window.__OTM_HOST = h;
  var isLocal = h === 'localhost' || h === '127.0.0.1' || h.indexOf('192.168.') === 0 || /\\.local$/.test(h);
  window.__OTM_LOCAL = isLocal;
  if (!isLocal) {
    // Cloud: niente esecuzione. Blocca proxy locale e Netlify prima che partano richieste.
    var _f = window.fetch.bind(window);
    window.fetch = function (u, o) {
      try {
        var s = typeof u === 'string' ? u : (u && u.url) || '';
        if (s.indexOf('/.netlify/functions/') !== -1 || s.indexOf('localhost:3333') !== -1) {
          return Promise.reject(new Error('OTM: esecuzione disattivata in cloud'));
        }
      } catch (e) {}
      return _f(u, o);
    };
  }
})();
</script>"""


def _inject(html: str, nav_js: str) -> str:
    # dentro l'iframe srcdoc location.hostname e' vuoto: usiamo quello della pagina principale
    html = html.replace("window.location.hostname", "window.__OTM_HOST")
    html = html.replace("location.hostname", "window.__OTM_HOST")
    head = _SHIM + "<script>\n" + nav_js + "\n</script>"
    i = html.lower().find("<head>")
    if i != -1:
        j = i + len("<head>")
        return html[:j] + head + html[j:]
    return head + html


# ── Origine delle viste ─────────────────────────────────────────────────────
# Se la cartella views/ e' accanto ad app.py (repo privato, uso locale) si leggono
# i file da disco. Altrimenti (repo pubblico su Streamlit Cloud) si scaricano dal
# repo PRIVATO con un token nei Secrets:
#   GITHUB_TOKEN = "github_pat_..."         (fine-grained, Contents: Read-only)
#   VIEWS_REPO   = "JER55/otm-streamlit"     (opzionale, questo e' il default)
VIEW_FILES = {
    "footprint": ["footprint.html", "session-volume-profile.js", "otm-nav.js"],
    "fakemove": ["fakemove.html", "otm-nav.js"],
}
LOCAL_VIEWS = (VIEWS / "footprint.html").exists()


def _secret(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


@st.cache_data(show_spinner="Carico la vista…", ttl=900)
def _fetch_remote(fname: str) -> str:
    import urllib.error
    import urllib.request

    token = _secret("GITHUB_TOKEN")
    repo = _secret("VIEWS_REPO", "JER55/otm-streamlit")
    branch = _secret("VIEWS_BRANCH", "main")
    if not token:
        raise RuntimeError("GITHUB_TOKEN mancante nei Secrets")
    req = urllib.request.Request(
        _secret("GITHUB_API", "https://api.github.com") + f"/repos/{repo}/contents/views/{fname}?ref={branch}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "otm-streamlit"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        hint = {401: "token non valido o scaduto", 403: "token senza permesso Contents: Read",
                404: "repo o file non trovato (il token ha accesso al repo? il file e' in views/?)"}.get(e.code, "")
        try:
            msg = json.loads(e.read().decode()).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(f"GitHub {e.code} su views/{fname}: {hint} {msg}".strip()) from None


def _read(fname: str) -> str:
    if LOCAL_VIEWS:
        return (VIEWS / fname).read_text(encoding="utf-8")
    return _fetch_remote(fname)


def _build_view(name: str) -> str:
    nav = _read("otm-nav.js")
    if name == "footprint":
        html, svp = _read("footprint.html"), _read("session-volume-profile.js")
        tag = '<script src="session-volume-profile.js"></script>'
        if tag in html:
            html = html.replace(tag, "<script>\n" + svp + "\n</script>")
        else:
            st.warning("Tag di session-volume-profile.js non trovato nella Footprint: SVP non caricato.")
    else:
        html = _read("fakemove.html")
    return _inject(html, nav)


def _blob(html: str) -> str:
    # JSON dentro <script type="application/json">: niente "<" letterali, cosi'
    # nessun </script> o <!-- della vista puo' chiudere o alterare il blocco.
    return json.dumps(html).replace("<", "\\u003c")


@st.cache_data(show_spinner=False, ttl=900)
def _build_shell(_key: float, local: bool) -> str:
    return (SHELL_HTML
            .replace("%%LOCAL%%", "true" if local else "false")
            .replace("%%FP%%", _blob(_build_view("footprint")))
            .replace("%%FM%%", _blob(_build_view("fakemove"))))


def load_shell(local: bool) -> str:
    # in locale la cache si invalida quando cambi un file; da remoto vale il ttl di 15 minuti
    files = {f for fs in VIEW_FILES.values() for f in fs}
    key = max((VIEWS / f).stat().st_mtime for f in files) if LOCAL_VIEWS else 0.0
    try:
        return _build_shell(key, local)
    except RuntimeError as e:
        st.error(f"Impossibile caricare le viste: {e}")
        st.stop()


# ── Shell lato browser ──────────────────────────────────────────────────────
SHELL_HTML = r"""<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root{--ink:#0B1220;--surf:#111C2E;--elev:#16233A;--teal:#3DD4C8;--muted:#8394B0;--light:#E8EEF9;--amber:#F2A93B;--red:#FF5C5C;}
  *{box-sizing:border-box}
  html,body{height:100%;margin:0;background:#050a12;overflow:hidden;color:var(--light);font-family:Inter,system-ui,sans-serif}
  #shell{display:flex;flex-direction:column;height:100%}
  header{height:46px;flex:0 0 46px;display:flex;align-items:center;gap:16px;padding:0 12px 0 14px;
    background:linear-gradient(180deg,#0f1828,#0b1220);border-bottom:1px solid var(--elev)}
  .brand{font:700 14px 'Space Grotesk',sans-serif;letter-spacing:.1em;white-space:nowrap}
  .brand span{color:var(--teal)}
  nav{position:relative;display:flex;background:#0a111d;border:1px solid var(--elev);border-radius:10px;padding:3px}
  nav button{all:unset;cursor:pointer;position:relative;z-index:1;padding:6px 14px;border-radius:7px;
    font:700 11.5px 'Space Grotesk',sans-serif;letter-spacing:.09em;color:var(--muted);transition:color .2s;white-space:nowrap}
  nav button:hover{color:var(--light)}
  nav button.on{color:#06110f}
  nav button kbd{font:700 9.5px 'JetBrains Mono',monospace;margin-left:7px;opacity:.55}
  nav .ink{position:absolute;top:3px;bottom:3px;left:3px;border-radius:7px;background:var(--teal);
    box-shadow:0 0 18px rgba(61,212,200,.35);transition:transform .28s cubic-bezier(.2,.8,.2,1),width .28s cubic-bezier(.2,.8,.2,1)}
  .sp{flex:1}
  .chip{display:flex;align-items:center;gap:7px;font:600 11px Inter,sans-serif;color:var(--muted);white-space:nowrap}
  .chip b{font:700 11.5px 'JetBrains Mono',monospace;color:var(--light);letter-spacing:.02em}
  .dot{width:7px;height:7px;border-radius:50%;background:var(--muted)}
  .dot.open{background:var(--teal);box-shadow:0 0 0 0 rgba(61,212,200,.6);animation:pulse 1.8s infinite}
  .dot.pre{background:var(--amber)}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(61,212,200,.55)}70%{box-shadow:0 0 0 7px rgba(61,212,200,0)}100%{box-shadow:0 0 0 0 rgba(61,212,200,0)}}
  .pill{font:700 10.5px 'JetBrains Mono',monospace;padding:4px 10px;border-radius:999px;border:1px solid;white-space:nowrap;cursor:default}
  .pill.live{color:var(--red);border-color:rgba(255,92,92,.4);background:rgba(255,92,92,.08)}
  .pill.safe{color:var(--teal);border-color:rgba(61,212,200,.4);background:rgba(61,212,200,.08)}
  .ib{all:unset;cursor:pointer;width:30px;height:30px;border-radius:8px;display:grid;place-items:center;color:var(--muted);
    border:1px solid transparent;transition:all .15s}
  .ib:hover{color:var(--light);background:rgba(61,212,200,.1);border-color:rgba(61,212,200,.25)}
  .ib svg{width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
  #stage{position:relative;flex:1;min-height:0;background:#050a12}
  iframe.view{position:absolute;inset:0;width:100%;height:100%;border:0;visibility:hidden;opacity:0;transition:opacity .18s}
  iframe.view.on{visibility:visible;opacity:1}
  #loader{position:absolute;inset:0;display:none;place-items:center;pointer-events:none;z-index:5}
  #loader.on{display:grid}
  #loader div{font:700 11px 'Space Grotesk',sans-serif;letter-spacing:.2em;color:var(--muted)}
  #loader i{display:block;width:180px;height:2px;margin-top:12px;background:linear-gradient(90deg,transparent,var(--teal),transparent);
    background-size:200% 100%;animation:sh 1.1s linear infinite}
  @keyframes sh{from{background-position:200% 0}to{background-position:-200% 0}}
  @media (max-width:980px){.hide-m{display:none}}
  @media (max-width:640px){.brand{display:none} nav button{padding:6px 9px} nav button kbd{display:none}}
</style></head>
<body><div id="shell">
  <header>
    <div class="brand">OTM <span>· ORDER FLOW</span></div>
    <nav id="tabs">
      <i class="ink"></i>
      <button data-v="footprint">FOOTPRINT<kbd>[</kbd></button>
      <button data-v="fakemove">FAKEMOVE E/L/C<kbd>]</kbd></button>
    </nav>
    <div class="sp"></div>
    <div class="chip hide-m" id="sess" title="Sessione cash USA 09:30–16:00 New York (le VA della Footprint usano questa sessione)"><span class="dot" id="sdot"></span><span id="stxt">US</span></div>
    <div class="chip hide-m" title="Ora di Roma">ROMA <b id="clock">--:--:--</b></div>
    <span class="pill" id="mode"></span>
    <button class="ib" id="b-help" title="Comandi grafico (?)"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.2v.1"/></svg></button>
    <button class="ib" id="b-fs" title="Schermo intero (F)"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>
  </header>
  <main id="stage"><div id="loader"><div>CARICAMENTO<i></i></div></div></main>
</div>
<script type="application/json" id="v-footprint">%%FP%%</script>
<script type="application/json" id="v-fakemove">%%FM%%</script>
<script>
(function () {
  var LOCAL = %%LOCAL%%;
  var ORDER = ['footprint', 'fakemove'];
  var V = { footprint: { f: null }, fakemove: { f: null } };
  var stage = document.getElementById('stage'), loader = document.getElementById('loader');
  var tabs = document.getElementById('tabs'), ink = tabs.querySelector('.ink');
  var cur = null, pseudo = false;
  function lsGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  var mode = document.getElementById('mode');
  mode.className = 'pill ' + (LOCAL ? 'live' : 'safe');
  mode.textContent = LOCAL ? '● LOCALE · LIVE VIA PROXY' : '● CLOUD · SOLO ANALISI';
  mode.title = LOCAL ? 'Ordini reali tramite local-bitget-proxy.js (tetto 0,1 BTC)' : 'Esecuzione disattivata: per operare usa l\'app in locale con il proxy';

  function win(n) { return V[n].f && V[n].f.contentWindow; }
  function nav(n) { var w = win(n); return w && w.OTMNav && w.OTMNav.instance; }
  function applySuspend() {
    ORDER.forEach(function (n) {
      var w = win(n); if (!w) return;
      var off = (n !== cur); w.__OTM_SUSPENDED = off;
      if (!off) { var i = nav(n); if (i) i.resume(); }
    });
  }
  function frame(n) {
    if (V[n].f) return V[n].f;
    var f = document.createElement('iframe');
    f.className = 'view'; f.title = n;
    f.setAttribute('allow', 'fullscreen; clipboard-read; clipboard-write; autoplay');
    f.addEventListener('load', function () {
      loader.classList.remove('on'); applySuspend();
      var w = f.contentWindow;
      try { w.addEventListener('keydown', function (e) { if (e.key === 'Escape' && pseudo && !e.defaultPrevented) setPseudo(false); }); } catch (e) {}
      if (n === cur) setTimeout(function () { try { w.focus(); } catch (e) {} }, 60);
    });
    loader.classList.add('on');
    f.srcdoc = JSON.parse(document.getElementById('v-' + n).textContent);
    stage.appendChild(f); V[n].f = f;
    return f;
  }
  function moveInk() {
    var b = tabs.querySelector('button.on'); if (!b) return;
    ink.style.width = b.offsetWidth + 'px';
    ink.style.transform = 'translateX(' + (b.offsetLeft - 3) + 'px)';
  }
  function show(n) {
    if (!V[n]) n = 'footprint';
    if (cur === n) return;
    cur = n; lsSet('otm_view', n);
    var f = frame(n);
    ORDER.forEach(function (k) { if (V[k].f) V[k].f.classList.toggle('on', k === n); });
    tabs.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b.getAttribute('data-v') === n); });
    moveInk(); applySuspend();
    setTimeout(function () { try { f.contentWindow.focus(); } catch (e) {} }, 40);
  }
  function cycle(d) { var i = ORDER.indexOf(cur); show(ORDER[(i + d + ORDER.length) % ORDER.length]); }

  // ── schermo intero: API nativa, altrimenti "pseudo" (iframe a tutta pagina) ──
  function setPseudo(on) {
    var fe = window.frameElement; if (!fe) return;
    pseudo = on;
    if (on) {
      fe.setAttribute('data-otm-prev', fe.getAttribute('style') || '');
      fe.style.cssText += ';position:fixed !important;inset:0 !important;width:100vw !important;height:100vh !important;z-index:999999 !important;border-radius:0 !important;';
    } else { fe.setAttribute('style', fe.getAttribute('data-otm-prev') || ''); fit(); }
  }
  function fullscreen() {
    var d = document;
    if (d.fullscreenElement) { d.exitFullscreen(); return; }
    if (pseudo) { setPseudo(false); return; }
    var el = d.documentElement;
    if (d.fullscreenEnabled && el.requestFullscreen) el.requestFullscreen().catch(function () { setPseudo(true); });
    else setPseudo(true);
  }

  // ── altezza: il componente riempie lo schermo ──
  function fit() {
    var fe = window.frameElement; if (!fe || pseudo || document.fullscreenElement) return;
    try {
      var r = fe.getBoundingClientRect(), H = window.top.innerHeight;
      var h = Math.max(480, Math.floor(H - r.top - 10));
      if (Math.abs((parseFloat(fe.style.height) || 0) - h) > 1) fe.style.height = h + 'px';
    } catch (e) {}
  }
  try { window.top.addEventListener('resize', fit); } catch (e) {}
  [0, 150, 600, 1500, 3000].forEach(function (t) { setTimeout(fit, t); });
  window.addEventListener('resize', moveInk);

  // ── orologio + sessione USA ──
  var fmtRome = new Intl.DateTimeFormat('it-IT', { timeZone: 'Europe/Rome', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  var fmtNY = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  var WD = { Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6, Sun: 0 };
  function dur(min) { min = Math.max(0, Math.round(min)); var h = Math.floor(min / 60), m = min % 60; return (h ? h + 'h ' : '') + (h && m < 10 ? '0' : '') + m + 'm'; }
  function tick() {
    var d = new Date();
    document.getElementById('clock').textContent = fmtRome.format(d);
    var o = {}; fmtNY.formatToParts(d).forEach(function (p) { o[p.type] = p.value; });
    var wd = WD[o.weekday], mins = (+o.hour % 24) * 60 + (+o.minute) + (+o.second) / 60;
    var OPEN = 570, CLOSE = 960, PRE = 240, dot = document.getElementById('sdot'), txt = document.getElementById('stxt');
    var weekday = wd >= 1 && wd <= 5;
    if (weekday && mins >= OPEN && mins < CLOSE) { dot.className = 'dot open'; txt.innerHTML = 'US <b>APERTA</b> · chiude ' + dur(CLOSE - mins); return; }
    var until;
    if (weekday && mins < OPEN) until = OPEN - mins;
    else { var days = wd === 5 ? 3 : (wd === 6 ? 2 : 1); until = days * 1440 - mins + OPEN; }
    var pre = weekday && mins >= PRE && mins < OPEN;
    dot.className = 'dot' + (pre ? ' pre' : '');
    txt.innerHTML = 'US <b>' + (pre ? 'PRE-MARKET' : 'CHIUSA') + '</b> · apre ' + dur(until);
  }
  tick(); setInterval(tick, 1000);

  // ── input ──
  tabs.addEventListener('click', function (e) { var b = e.target.closest('button'); if (b) show(b.getAttribute('data-v')); });
  document.getElementById('b-fs').addEventListener('click', fullscreen);
  document.getElementById('b-help').addEventListener('click', function () { var i = nav(cur); if (i) i.help(); });
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '[' || e.key === ']') { e.preventDefault(); cycle(e.key === ']' ? 1 : -1); return; }
    if (e.key === 'Escape' && pseudo) { setPseudo(false); return; }
    var i = nav(cur); if (i) i.key(e);           // tasti premuti sulla barra: girati al grafico attivo
  });
  document.addEventListener('fullscreenchange', function () { setTimeout(fit, 50); });

  window.OTMShell = { show: show, cycle: cycle, fullscreen: fullscreen, exitPseudo: function () { if (pseudo) setPseudo(false); } };
  show(lsGet('otm_view') || 'footprint');
})();
</script>
</body></html>"""


# ── Accesso con password ────────────────────────────────────────────────────
# L'HTML delle viste (cioe' la logica della strategia) viene inviato al browser
# SOLO dopo il login. Password in Streamlit Cloud: Settings > Secrets
#   APP_PASSWORD = "la-tua-password"
# In locale senza secret l'accesso e' libero; in cloud senza secret l'app si blocca.
def _require_login(is_local: bool) -> None:
    import hmac
    import time

    try:
        expected = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        expected = ""
    if not expected:
        if is_local:
            return
        st.error("APP_PASSWORD non configurata nei Secrets: accesso bloccato.")
        st.stop()
    if st.session_state.get("otm_auth"):
        return

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div class="otm-brand" style="text-align:center;margin:12vh 0 18px">'
                    'OUTTHINK <span>THE MARKET</span></div>', unsafe_allow_html=True)
        with st.form("otm_login"):
            pwd = st.text_input("Password", type="password")
            ok = st.form_submit_button("ENTRA", use_container_width=True)
        if ok:
            if hmac.compare_digest(pwd.encode(), str(expected).encode()):
                st.session_state["otm_auth"] = True
                st.rerun()
            time.sleep(1.5)  # rallenta i tentativi a forza bruta
            st.error("Password errata.")
    st.stop()


local = _is_local()
_require_login(local)

# Un solo componente: la shell gestisce tab, viste e schermo intero lato browser,
# quindi nessun rerun di Streamlit quando cambi vista o ridimensioni.
components.html(load_shell(local), height=860, scrolling=False)
