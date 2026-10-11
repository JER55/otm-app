"""
OUTTHINK THE MARKET — Otmflow, shell Streamlit
-----------------------------------------------
Incorpora le due app JS (FakeMove E/L/C e Footprint). Rendering e websocket
restano nel browser: i dati arrivano dal tuo IP (Italia), non dal server
Streamlit (USA, bloccato da Binance/Bybit).

Struttura lato browser:
  componente Streamlit  ->  shell (barra, tab, ticker BTC, sessione USA, fullscreen)
                              ├─ iframe FakeMove    (vista iniziale)
                              └─ iframe Footprint   (precaricato in background, sospeso)
Il cambio vista e' istantaneo: entrambe le viste sono vive; quella in background
riceve i dati ma non disegna (window.__OTM_SUSPENDED, impostato PRIMA che i suoi
script partano), quindi non consuma CPU di rendering.

Adattamenti applicati qui al caricamento delle viste:
  1. session-volume-profile.js inserito inline nella Footprint
  2. otm-nav.js (motore di navigazione) inserito in entrambe le viste
  3. rilevamento "localhost" letto dalla pagina principale (non dall'iframe)
  4. in cloud le chiamate di esecuzione (proxy/Netlify) vengono bloccate

Identita' della scheda del browser:
  * titolo "Otmflow - OutThinkTheMarket" e logo OTM (page_icon generato con Pillow, nessun file);
  * un componente invisibile riallinea titolo e icona SVG anche sulla pagina esterna
    (su Streamlit Cloud il titolo altrimenti diventa "… · Streamlit").

Lingue (IT · EN · ES, con traduzioni.py e locales/*.json — stesso sistema di ThinkCore):
  * testi Python con tr("..."); testi della shell con t("...") / data-i18n="..." nell'HTML:
    le chiavi della shell sono estratte da SHELL_HTML, nessun elenco da tenere allineato;
  * si parte in italiano; ?lang=en|es nell'indirizzo o [interfaccia] lingua nei Secrets;
  * login: selettore Streamlit; dentro l'app: selettore IT/EN/ES nella barra, cambio
    istantaneo senza ricaricare le viste (scrive ?lang= nell'indirizzo per il reload);
  * le viste ricevono la lingua: window.__OTM_LANG prima dei loro script, poi l'evento
    'otm:lang' (detail.lang) a ogni cambio e OTMNav.instance.setLang(lang) se esiste;
  * FakeMove, Footprint e otm-nav.js sono tradotti a runtime da otm-i18n.js con il catalogo
    locales/views.json (testo DOM, attributi, canvas, alert/confirm, notifiche): i file delle
    viste non vanno modificati.
"""

import hashlib
import json
import re
import urllib.parse
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

import accesso_otm
import traduzioni as tz

tr = tz.tr

BASE = Path(__file__).parent
VIEWS = BASE / "views"

APP_TITLE = "Otmflow - OutThinkTheMarket"

# ── Design system (stesso di ThinkCore) ─────────────────────────────────────
INK = "#0B1220"
SURFACE = "#111C2E"
ELEVATED = "#16233A"
TEAL = "#3DD4C8"
SKY = "#6FA8FF"
MUTED = "#8394B0"
LIGHT = "#E8EEF9"
AMBER = "#F2A93B"
CRIMSON = "#FF5C5C"

# ── Logo OTM ────────────────────────────────────────────────────────────────
# Il range (anello) con il punto che ne evade in alto a destra: il breakout, cioe' "outthink".
# Al centro una candela. Stessa geometria nell'SVG (barra, login, favicon) e nel PNG (page_icon).
OTM_MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32" aria-hidden="true">'
    '<defs>'
    '<linearGradient id="otmG" x1="5" y1="27" x2="27" y2="5" gradientUnits="userSpaceOnUse">'
    f'<stop offset="0" stop-color="{TEAL}"/><stop offset="1" stop-color="{SKY}"/></linearGradient>'
    '<linearGradient id="otmB" x1="0" y1="0" x2="0" y2="32" gradientUnits="userSpaceOnUse">'
    '<stop offset="0" stop-color="#13213A"/><stop offset="1" stop-color="#070D18"/></linearGradient>'
    '</defs>'
    f'<rect x="1" y="1" width="30" height="30" rx="8" fill="url(#otmB)" stroke="{TEAL}" stroke-opacity=".38"/>'
    '<circle cx="16" cy="16" r="9.5" fill="none" stroke="url(#otmG)" stroke-width="2.6" stroke-linecap="round"'
    ' stroke-dasharray="51.4 8.3" transform="rotate(-20 16 16)"/>'
    f'<circle class="otm-dot" cx="24.5" cy="7.5" r="2" fill="{SKY}"/>'
    f'<path d="M16 11.2V20.8" stroke="{TEAL}" stroke-width="1.3" stroke-linecap="round"/>'
    f'<rect x="14.1" y="13.4" width="3.8" height="5.2" rx="1" fill="{TEAL}"/>'
    '</svg>'
)
FAVICON_URL = "data:image/svg+xml," + urllib.parse.quote(OTM_MARK_SVG)


def _otm_icon():
    """Logo OTM in PNG per page_icon (Pillow e' gia' una dipendenza di Streamlit)."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return "📊"
    S = 256
    hexrgb = lambda h, a=255: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5)) + (a,)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, S - 8, S - 8), radius=60, fill=hexrgb("#0B1426"),
                        outline=hexrgb(TEAL, 110), width=7)
    # anello con gradiente diagonale teal -> sky, aperto in alto a destra
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).arc((52, 52, 204, 204), start=-20, end=290, fill=255, width=22)
    grad = Image.new("RGBA", (S, S))
    a, b = hexrgb(TEAL), hexrgb(SKY)
    gp = grad.load()
    for y in range(S):
        for x in range(S):
            t = max(0.0, min(1.0, (x + (S - y)) / (2 * S)))
            gp[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(4))
    img.paste(grad, (0, 0), mask)
    d.ellipse((196 - 17, 60 - 17, 196 + 17, 60 + 17), fill=hexrgb(SKY))      # il breakout
    d.rounded_rectangle((124, 88, 132, 168), radius=4, fill=hexrgb(TEAL))    # stoppino
    d.rounded_rectangle((112, 107, 144, 149), radius=8, fill=hexrgb(TEAL))   # corpo
    return img.resize((64, 64), Image.LANCZOS)


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=_otm_icon(),
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
.block-container {{ padding:0.25rem 0.4rem 0 0.4rem !important; max-width:100% !important; }}
[data-testid="stMainBlockContainer"] {{ padding-top:0.25rem !important; }}
[data-testid="stVerticalBlock"] {{ gap:0 !important; }}
[data-testid="stElementContainer"]:has(iframe[height="0"]) {{ display:none; }}
.otm-brand {{ display:flex; flex-direction:column; align-items:center; gap:14px; }}
.otm-brand svg {{ width:64px; height:64px; filter:drop-shadow(0 0 22px rgba(61,212,200,.35)); }}
.otm-brand b {{ font-family:'Inter',sans-serif; font-weight:700; font-size:1.6rem;
               letter-spacing:.06em; color:{LIGHT}; }}
.otm-brand b span {{ background:linear-gradient(90deg,{TEAL},{SKY}); -webkit-background-clip:text;
                    background-clip:text; color:transparent; }}
.otm-brand small {{ font-family:'Inter',sans-serif; font-size:.68rem; letter-spacing:.42em;
                   color:{MUTED}; margin-top:-8px; }}
iframe {{ border:1px solid {ELEVATED} !important; border-radius:10px; background:#050a12; display:block; }}
</style>
""",
    unsafe_allow_html=True,
)


# ── Titolo e icona della scheda ─────────────────────────────────────────────
# Componente invisibile: tiene titolo e favicon SVG sulla pagina dell'app e, se raggiungibile,
# sulla pagina esterna (Streamlit Cloud). Streamlit li reimposta a ogni rerun: un observer li riallinea.
_IDENTITY_HTML = """<script>
(function () {
  var T = %%TITLE%%, ICON = %%ICON%%;
  function apply(w) {
    try {
      var d = w.document; if (!d || !d.head) return;
      if (d.title !== T) d.title = T;
      d.querySelectorAll('link[rel~="icon"]:not([data-otm])').forEach(function (l) { l.parentNode.removeChild(l); });
      var l = d.querySelector('link[data-otm]');
      if (!l) { l = d.createElement('link'); l.rel = 'icon'; l.type = 'image/svg+xml'; l.setAttribute('data-otm', '1'); d.head.appendChild(l); }
      if (l.getAttribute('href') !== ICON) l.setAttribute('href', ICON);
    } catch (e) {}
  }
  var wins = [];
  [window.parent, window.top].forEach(function (w) { if (w && w !== window && wins.indexOf(w) < 0) wins.push(w); });
  wins.forEach(function (w) {
    apply(w);
    try {
      var busy = false;
      new w.MutationObserver(function () {
        if (busy) return; busy = true;
        setTimeout(function () { busy = false; apply(w); }, 0);
      }).observe(w.document.head, { childList: true, subtree: true, characterData: true, attributes: true });
    } catch (e) {}
  });
})();
</script>"""


def _tab_identity() -> None:
    components.html(_IDENTITY_HTML.replace("%%TITLE%%", json.dumps(APP_TITLE))
                    .replace("%%ICON%%", json.dumps(FAVICON_URL)), height=0)


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


def _i18n_head() -> str:
    """Catalogo delle viste + traduttore a runtime (otm-i18n.js): vanno in testa alla vista,
    prima di otm-nav.js e dei suoi script, cosi' canvas, alert e DOM sono gia' agganciati."""
    try:
        doc = json.loads((BASE / "locales" / "views.json").read_text(encoding="utf-8"))
        js = (BASE / "otm-i18n.js").read_text(encoding="utf-8")
    except (OSError, ValueError) as ex:
        st.warning(tr("Traduzione delle viste non disponibile: {errore}", errore=ex))
        return ""
    dati = {"esatte": doc.get("esatte", {}), "frammenti": doc.get("frammenti", {})}
    blob = json.dumps(dati, ensure_ascii=False).replace("<", "\\u003c")
    return "<script>window.__OTM_DICT=" + blob + ";</script><script>\n" + js + "\n</script>"


# Correzioni sul sorgente delle viste (se la riga non c'e' piu', la vista resta com'e')
_PATCHES = {
    # il messaggio si cancellava confrontando il testo del DOM, che la traduzione puo' aver cambiato
    "fakemove": [(
        "function _flash(t) { if (_msg) { _msg.textContent = t; setTimeout(() => { if (_msg.textContent === t) _msg.textContent = ''; }, 2200); } }",
        "function _flash(t) { if (_msg) { _msg.textContent = t; const _id = (_flash._n = (_flash._n || 0) + 1); setTimeout(() => { if (_flash._n === _id) _msg.textContent = ''; }, 2200); } }",
    )],
}


def _inject(html: str, nav_js: str, name: str = "") -> str:
    # dentro l'iframe srcdoc location.hostname e' vuoto: usiamo quello della pagina principale
    html = html.replace("window.location.hostname", "window.__OTM_HOST")
    html = html.replace("location.hostname", "window.__OTM_HOST")
    for vecchio, nuovo in _PATCHES.get(name, []):
        if vecchio in html:
            html = html.replace(vecchio, nuovo)
        else:
            st.warning(tr("Correzione non applicata alla vista {nome}: riga non trovata.", nome=name))
    head = _i18n_head() + _SHIM + "<script>\n" + nav_js + "\n</script>"
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


@st.cache_data(show_spinner=False, ttl=900)
def _fetch_remote(fname: str) -> str:
    import urllib.error
    import urllib.request

    token = _secret("GITHUB_TOKEN")
    repo = _secret("VIEWS_REPO", "JER55/otm-streamlit")
    branch = _secret("VIEWS_BRANCH", "main")
    if not token:
        raise RuntimeError(tr("GITHUB_TOKEN mancante nei Secrets"))
    req = urllib.request.Request(
        _secret("GITHUB_API", "https://api.github.com") + f"/repos/{repo}/contents/views/{fname}?ref={branch}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.raw+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "otm-streamlit"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        hint = {401: tr("token non valido o scaduto"), 403: tr("token senza permesso Contents: Read"),
                404: tr("repo o file non trovato (il token ha accesso al repo? il file è in views/?)")}.get(e.code, "")
        try:
            msg = json.loads(e.read().decode()).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(tr("GitHub {codice} su views/{file}: {motivo}", codice=e.code, file=fname,
                              motivo=f"{hint} {msg}".strip())) from None
    except (urllib.error.URLError, TimeoutError) as e:     # rete giu' o timeout: messaggio, non traceback
        raise RuntimeError(tr("Impossibile contattare GitHub: {errore}", errore=getattr(e, "reason", e))) from None


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
            st.warning(tr("Tag di session-volume-profile.js non trovato nella Footprint: SVP non caricato."))
    else:
        html = _read("fakemove.html")
    return _inject(html, nav, name)


def _blob(html: str) -> str:
    # JSON dentro <script type="application/json">: niente "<" letterali, cosi'
    # nessun </script> o <!-- della vista puo' chiudere o alterare il blocco.
    return json.dumps(html).replace("<", "\\u003c")


@st.cache_data(show_spinner=False, ttl=900)
def _build_shell(_key: float, local: bool, _shell_ver: str) -> str:
    # _shell_ver = hash di SHELL_HTML + logo: se modifichi la shell la cache si invalida subito
    return (SHELL_HTML
            .replace("%%MARK%%", OTM_MARK_SVG)
            .replace("%%LOCAL%%", "true" if local else "false")
            .replace("%%FP%%", _blob(_build_view("footprint")))
            .replace("%%FM%%", _blob(_build_view("fakemove"))))


def shell_keys(shell: str) -> list:
    """Testi traducibili della shell: t("...") nello script, data-i18n="..." e data-i18n-title="..." nell'HTML."""
    keys = set(re.findall(r'\bt\("([^"\\]+)"', shell))
    keys |= set(re.findall(r'data-i18n(?:-title)?="([^"]+)"', shell))
    return sorted(keys)


def _i18n_shell() -> str:
    # i testi della shell in tutte e tre le lingue: il cambio dalla barra e' istantaneo, senza rerun.
    # Stessi cataloghi (e stessi controlli su segnaposto e tag) dei testi Python.
    keys = shell_keys(SHELL_HTML)
    d = {lg: {k: tz.traduci(lg, k) for k in keys} for lg in tz.LINGUE}
    return json.dumps(d, ensure_ascii=False).replace("<", "\\u003c")


def load_shell(local: bool, lang: str) -> str:
    # in locale la cache si invalida quando cambi un file; da remoto vale il ttl di 15 minuti
    files = {f for fs in VIEW_FILES.values() for f in fs}
    key = max((VIEWS / f).stat().st_mtime for f in files) if LOCAL_VIEWS else 0.0
    for extra in (BASE / "otm-i18n.js", BASE / "locales" / "views.json"):     # file della traduzione
        try:
            key = max(key, extra.stat().st_mtime)
        except OSError:
            pass
    ver = hashlib.sha1((SHELL_HTML + OTM_MARK_SVG).encode()).hexdigest()[:12]
    try:
        with st.spinner(tr("Carico le viste…")):
            html = _build_shell(key, local, ver)
    except RuntimeError as e:
        st.error(tr("Impossibile caricare le viste: {errore}", errore=e))
        st.stop()
    # lingua e testi fuori dalla cache: i segnaposto sono nell'<head>, prima delle viste
    lang = tz.codice_valido(lang) or tz.BASE
    return html.replace("%%LANG%%", lang, 1).replace("%%I18N%%", _i18n_shell(), 1)


# ── Shell lato browser ──────────────────────────────────────────────────────
SHELL_HTML = r"""<!doctype html>
<html lang="%%LANG%%"><head><meta charset="utf-8">
<script>var OTM_I18N = %%I18N%%;</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=Inter:wght@500;600;700;800&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  :root{--ink:#0B1220;--surf:#111C2E;--elev:#16233A;--teal:#3DD4C8;--sky:#6FA8FF;--muted:#8394B0;--dim:#56657F;
    --light:#E8EEF9;--amber:#F2A93B;--red:#FF5C5C;--green:#2EE6A6;--hh:44px;
    --glass:rgba(255,255,255,.035);--line:rgba(255,255,255,.07)}
  *{box-sizing:border-box}
  html,body{height:100%;margin:0;background:#050a12;overflow:hidden;color:var(--light);font-family:Inter,system-ui,sans-serif}
  #shell{display:flex;flex-direction:column;height:100%}

  /* ── barra ─────────────────────────────────────────────────────────── */
  header{position:relative;isolation:isolate;overflow:hidden;height:var(--hh);flex:0 0 var(--hh);
    display:flex;align-items:center;gap:12px;padding:0 8px 0 9px;
    background:
      radial-gradient(420px 90px at 0% 0%,rgba(61,212,200,.16),transparent 70%),
      radial-gradient(520px 90px at 100% 0%,rgba(111,168,255,.10),transparent 70%),
      linear-gradient(180deg,#0f1a2b 0%,#0a111e 100%);
    border-bottom:1px solid rgba(61,212,200,.12)}
  header::before{content:'';position:absolute;inset:0;z-index:-1;pointer-events:none;
    background-image:linear-gradient(rgba(255,255,255,.028) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.028) 1px,transparent 1px);
    background-size:18px 18px;background-position:-1px -1px;
    -webkit-mask-image:linear-gradient(90deg,#000 0,rgba(0,0,0,.25) 22%,transparent 45%,transparent 60%,rgba(0,0,0,.4) 100%);
            mask-image:linear-gradient(90deg,#000 0,rgba(0,0,0,.25) 22%,transparent 45%,transparent 60%,rgba(0,0,0,.4) 100%)}
  /* linea di "sweep": una passata di liquidita' che attraversa la barra */
  header::after{content:'';position:absolute;left:0;bottom:-1px;width:28%;height:1px;pointer-events:none;
    background:linear-gradient(90deg,transparent,var(--teal) 55%,var(--sky) 80%,transparent);
    box-shadow:0 0 10px 1px rgba(61,212,200,.45);transform:translateX(-110%);animation:sweep 7s cubic-bezier(.65,0,.35,1) infinite}
  @keyframes sweep{0%{transform:translateX(-110%)}60%,100%{transform:translateX(370%)}}

  .brand{display:flex;align-items:center;gap:9px;flex:0 0 auto;text-decoration:none;color:inherit;user-select:none}
  .brand svg{width:28px;height:28px;display:block;filter:drop-shadow(0 0 8px rgba(61,212,200,.35));transition:transform .4s cubic-bezier(.2,.8,.2,1)}
  .brand:hover svg{transform:rotate(-8deg) scale(1.06)}
  .brand .otm-dot{transform-origin:24.5px 7.5px;animation:breakout 3.2s ease-in-out infinite}
  @keyframes breakout{0%,100%{transform:translate(0,0);opacity:1}45%{transform:translate(1.1px,-1.1px);opacity:1}55%{opacity:.55}}
  .wm{display:flex;flex-direction:column;line-height:1}
  .wm b{font:700 15px/1 'Inter',sans-serif;letter-spacing:.05em;color:var(--light)}
  .wm b span{background:linear-gradient(90deg,var(--teal),var(--sky));-webkit-background-clip:text;background-clip:text;color:transparent}
  .wm small{margin-top:4px;font:600 7.5px/1 'Inter',sans-serif;letter-spacing:.34em;color:var(--dim);white-space:nowrap}
  .sep{width:1px;height:22px;background:linear-gradient(180deg,transparent,var(--line),transparent);flex:0 0 1px}

  nav{position:relative;display:flex;background:var(--glass);border:1px solid var(--line);border-radius:10px;padding:3px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.04)}
  nav button{all:unset;cursor:pointer;position:relative;z-index:1;padding:4px 12px;border-radius:7px;
    font:700 10.5px/18px 'Inter',sans-serif;letter-spacing:.1em;color:var(--muted);transition:color .18s;white-space:nowrap}
  nav button:hover{color:var(--light)}
  nav button:focus-visible{outline:1px solid var(--teal);outline-offset:1px}
  nav button.on{color:#04110f}
  nav button kbd{font:700 9px 'JetBrains Mono',monospace;margin-left:7px;padding:0 4px;border-radius:3px;
    background:rgba(255,255,255,.08);opacity:.55}
  nav button .ld{display:inline-block;width:5px;height:5px;border-radius:50%;margin-left:6px;vertical-align:1px;background:currentColor;opacity:0;transition:opacity .2s}
  nav button.loading .ld{opacity:.7;animation:blink .8s infinite}
  @keyframes blink{50%{opacity:.15}}
  nav .ink{position:absolute;top:3px;bottom:3px;left:0;border-radius:7px;
    background:linear-gradient(135deg,#46e0d3 0%,var(--teal) 45%,#59b4f2 100%);
    box-shadow:0 0 18px rgba(61,212,200,.35),inset 0 1px 0 rgba(255,255,255,.35);
    transition:transform .24s cubic-bezier(.2,.8,.2,1),width .24s cubic-bezier(.2,.8,.2,1)}
  nav.noanim .ink{transition:none}

  /* ── ticker BTC: prezzo, 24h, flusso aggressori 60 s ── */
  .tick{display:flex;align-items:center;gap:10px;height:30px;padding:0 11px 0 9px;border-radius:9px;
    background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.015));border:1px solid var(--line);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.04);white-space:nowrap;cursor:default}
  .sym{display:flex;align-items:center;gap:6px;font:700 10.5px 'Inter',sans-serif;letter-spacing:.08em;color:var(--light)}
  .sym em{font:600 8px 'JetBrains Mono',monospace;font-style:normal;letter-spacing:.06em;color:var(--dim);
    padding:1px 4px;border:1px solid var(--line);border-radius:3px}
  .tdot{width:6px;height:6px;border-radius:50%;background:var(--dim)}
  .tdot.on{background:var(--green);animation:pulse 1.8s infinite}
  .px{font:700 13px 'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;letter-spacing:-.01em;color:var(--light);
    min-width:78px;text-align:right;transition:color .5s ease,text-shadow .5s ease}
  .px.up{color:var(--green);text-shadow:0 0 12px rgba(46,230,166,.45);transition:none}
  .px.dn{color:var(--red);text-shadow:0 0 12px rgba(255,92,92,.45);transition:none}
  .chg{font:600 10.5px 'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;color:var(--muted);
    padding:2px 6px;border-radius:5px;background:rgba(255,255,255,.04)}
  .chg.up{color:var(--green);background:rgba(46,230,166,.09)}
  .chg.dn{color:var(--red);background:rgba(255,92,92,.09)}
  .flow{display:flex;align-items:center;gap:7px;padding-left:10px;border-left:1px solid var(--line)}
  .fl{font:700 8.5px 'Inter',sans-serif;letter-spacing:.16em;color:var(--dim)}
  .bar{position:relative;width:78px;height:5px;border-radius:3px;overflow:hidden;background:rgba(255,92,92,.75);
    box-shadow:0 0 10px rgba(0,0,0,.4) inset}
  .bar i{position:absolute;left:0;top:0;bottom:0;width:50%;background:linear-gradient(90deg,#1fc58d,var(--green));
    transition:width .45s cubic-bezier(.2,.8,.2,1);box-shadow:2px 0 6px rgba(46,230,166,.6)}
  .bar::after{content:'';position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:rgba(255,255,255,.55)}
  .bar.idle{background:rgba(255,255,255,.08)} .bar.idle i{opacity:0}
  .fd{font:700 10.5px 'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;min-width:52px;color:var(--muted)}
  .fd.up{color:var(--green)} .fd.dn{color:var(--red)}

  .sp{flex:1;min-width:0}
  header>*:not(.sp){flex-shrink:0}

  /* ── sessione USA con avanzamento ── */
  .sess{position:relative;display:flex;align-items:center;gap:7px;height:30px;padding:0 10px;border-radius:9px;
    border:1px solid var(--line);background:var(--glass);font:600 10.5px Inter,sans-serif;color:var(--muted);white-space:nowrap;overflow:hidden;cursor:default}
  .sess b{font:700 10.5px 'Inter',sans-serif;letter-spacing:.08em;color:var(--light)}
  .sess .nx{font:600 10px 'JetBrains Mono',monospace;color:var(--muted)}
  .sess .tr{position:absolute;left:0;right:0;bottom:0;height:2px;background:rgba(255,255,255,.04)}
  .sess .tr i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--teal),var(--sky));transition:width 1s linear}
  .sess.pre .tr i{background:linear-gradient(90deg,#c9801f,var(--amber))}
  .dot{width:6px;height:6px;border-radius:50%;background:var(--dim)}
  .dot.open{background:var(--teal);animation:pulse 1.8s infinite}
  .dot.pre{background:var(--amber)}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(61,212,200,.55)}70%{box-shadow:0 0 0 6px rgba(61,212,200,0)}100%{box-shadow:0 0 0 0 rgba(61,212,200,0)}}

  .clk{display:flex;flex-direction:column;align-items:flex-end;line-height:1;cursor:default}
  .clk small{font:700 7.5px 'Inter',sans-serif;letter-spacing:.3em;color:var(--dim)}
  .clk b{margin-top:3px;font:700 13px 'JetBrains Mono',monospace;font-variant-numeric:tabular-nums;color:var(--light)}

  .pill{display:flex;align-items:center;gap:6px;font:700 9px 'JetBrains Mono',monospace;letter-spacing:.06em;padding:4px 9px;
    border-radius:999px;border:1px solid;white-space:nowrap;cursor:default}
  .pill::before{content:'';width:5px;height:5px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor}
  .pill.live{color:var(--red);border-color:rgba(255,92,92,.4);background:rgba(255,92,92,.08)}
  .pill.live::before{animation:blink 1.2s infinite}
  .pill.safe{color:var(--teal);border-color:rgba(61,212,200,.35);background:rgba(61,212,200,.07)}

  .lang{display:flex;background:var(--glass);border:1px solid var(--line);border-radius:8px;padding:2px}
  .lang button{all:unset;cursor:pointer;padding:2px 7px;border-radius:6px;color:var(--muted);
    font:700 9.5px/16px 'JetBrains Mono',monospace;letter-spacing:.04em;transition:color .15s,background .15s}
  .lang button:hover:not(.on){color:var(--light)}
  .lang button:focus-visible{outline:1px solid var(--teal);outline-offset:1px}
  .lang button.on{color:#04110f;background:linear-gradient(135deg,var(--teal),#59b4f2)}
  .ib{all:unset;cursor:pointer;width:28px;height:28px;border-radius:8px;display:grid;place-items:center;color:var(--muted);
    border:1px solid var(--line);background:var(--glass);transition:all .15s}
  .ib:hover{color:var(--light);background:rgba(61,212,200,.1);border-color:rgba(61,212,200,.3)}
  .ib:focus-visible{outline:1px solid var(--teal);outline-offset:1px}
  .ib svg{width:14px;height:14px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}

  #stage{position:relative;flex:1;min-height:0;background:#050a12}
  /* dissolvenza incrociata: la vista uscente resta visibile finche' non e' sfumata */
  iframe.view{position:absolute;inset:0;width:100%;height:100%;border:0;opacity:0;visibility:hidden;pointer-events:none;
    transition:opacity .14s ease,visibility 0s linear .14s}
  iframe.view.on{opacity:1;visibility:visible;pointer-events:auto;z-index:1;transition:opacity .14s ease,visibility 0s}
  #loader{position:absolute;inset:0;display:none;place-items:center;pointer-events:none;z-index:5}
  #loader.on{display:grid}
  #loader div{display:flex;flex-direction:column;align-items:center;font:700 11px 'Inter',sans-serif;letter-spacing:.2em;color:var(--muted)}
  #loader svg{width:40px;height:40px;margin-bottom:14px;animation:breathe 1.6s ease-in-out infinite}
  @keyframes breathe{50%{opacity:.45;transform:scale(.94)}}
  #loader i{display:block;width:180px;height:2px;margin-top:12px;background:linear-gradient(90deg,transparent,var(--teal),transparent);
    background-size:200% 100%;animation:sh 1.1s linear infinite}
  @keyframes sh{from{background-position:200% 0}to{background-position:-200% 0}}

  @media (max-width:1580px){.hide-xl{display:none}}
  @media (max-width:1340px){.hide-l{display:none}}
  @media (max-width:1120px){.hide-t{display:none}}
  @media (max-width:980px){.hide-m{display:none}}
  @media (max-width:640px){.wm,.sep{display:none} nav button{padding:3px 8px} nav button kbd{display:none}}
  @media (prefers-reduced-motion:reduce){header::after,.brand .otm-dot,.tdot.on,.dot.open{animation:none}}
</style></head>
<body><div id="shell">
  <header>
    <div class="brand" title="Otmflow · OutThink The Market">%%MARK%%<div class="wm"><b>OTM<span>FLOW</span></b><small>OUTTHINK THE MARKET</small></div></div>
    <span class="sep"></span>
    <nav id="tabs" class="noanim" role="tablist">
      <i class="ink"></i>
      <button role="tab" data-v="fakemove">FAKEMOVE E/L/C<i class="ld"></i><kbd>[</kbd></button>
      <button role="tab" data-v="footprint">FOOTPRINT<i class="ld"></i><kbd>]</kbd></button>
    </nav>
    <div class="tick hide-t" id="tick" data-i18n-title="BTCUSDT perpetuo · ultimo prezzo, variazione 24h e flusso aggressori degli ultimi 60 secondi (Binance Futures, dal tuo browser)">
      <span class="sym"><i class="tdot" id="tlive"></i>BTC<em>PERP</em></span>
      <b class="px" id="tpx">—</b>
      <span class="chg" id="tch">—</span>
      <span class="flow hide-l" id="tflow"><span class="fl" data-i18n="FLUSSO 60s"></span><span class="bar idle" id="tbar"><i id="tbuy"></i></span><span class="fd" id="tfd">—</span></span>
    </div>
    <div class="sp"></div>
    <div class="sess hide-xl" id="sess" data-i18n-title="Sessione cash USA 09:30–16:00 New York (le VA della Footprint usano questa sessione)"><span class="dot" id="sdot"></span><span>US <b id="sst"></b></span><span class="nx" id="snext"></span><span class="tr"><i id="sbar"></i></span></div>
    <div class="clk hide-m" data-i18n-title="Ora di Roma"><small data-i18n="ROMA"></small><b id="clock">--:--:--</b></div>
    <span class="pill" id="mode"></span>
    <div class="lang" id="lang" role="radiogroup" data-i18n-title="Lingua">
      <button role="radio" data-l="it" title="Italiano">IT</button>
      <button role="radio" data-l="en" title="English">EN</button>
      <button role="radio" data-l="es" title="Español">ES</button>
    </div>
    <button class="ib" id="b-help" data-i18n-title="Comandi grafico (?)"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.2v.1"/></svg></button>
    <button class="ib" id="b-fs" data-i18n-title="Schermo intero (F)"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>
  </header>
  <main id="stage"><div id="loader"><div>%%MARK%%<span data-i18n="CARICAMENTO"></span><i></i></div></div></main>
</div>
<script type="application/json" id="v-fakemove">%%FM%%</script>
<script type="application/json" id="v-footprint">%%FP%%</script>
<script>
(function () {
  var LOCAL = %%LOCAL%%;
  var START = 'fakemove';                      // vista mostrata all'apertura
  var ORDER = ['fakemove', 'footprint'];
  var V = { fakemove: { f: null, ready: false }, footprint: { f: null, ready: false } };
  var stage = document.getElementById('stage'), loader = document.getElementById('loader');
  var tabs = document.getElementById('tabs'), ink = tabs.querySelector('.ink');
  var cur = null, pseudo = false, lastCycle = 0;
  var LOCALE = { it: 'it-IT', en: 'en-US', es: 'es-ES' };

  // ── lingua: testi da OTM_I18N (generato in Python dai cataloghi locales/*.json) ──
  var LANG = OTM_I18N[document.documentElement.lang] ? document.documentElement.lang : 'it';
  function t(k, v) {
    var d = OTM_I18N[LANG] || {}, s = d[k] || k;
    if (v) s = s.replace(/\{(\w+)\}/g, function (m, n) { return Object.prototype.hasOwnProperty.call(v, n) ? v[n] : m; });
    return s;
  }
  var mode = document.getElementById('mode');
  mode.className = 'pill ' + (LOCAL ? 'live' : 'safe');
  function applyLang() {
    document.documentElement.lang = LANG;
    document.querySelectorAll('[data-i18n]').forEach(function (el) { el.textContent = t(el.getAttribute('data-i18n')); });
    document.querySelectorAll('[data-i18n-title]').forEach(function (el) { el.title = t(el.getAttribute('data-i18n-title')); });
    mode.textContent = LOCAL ? t("● LOCALE · LIVE").replace(/^●\s*/, '') : t("● CLOUD · ANALISI").replace(/^●\s*/, '');
    mode.title = LOCAL ? t("Ordini reali tramite local-bitget-proxy.js (tetto 0,1 BTC)")
                       : t("Esecuzione disattivata: per operare usa l'app in locale con il proxy");
    document.querySelectorAll('#lang button').forEach(function (b) {
      var on = b.getAttribute('data-l') === LANG;
      b.classList.toggle('on', on); b.setAttribute('aria-checked', on ? 'true' : 'false');
    });
    if (typeof setFormats === 'function') setFormats();
    if (typeof tick === 'function') tick();
    if (typeof paintTicker === 'function') paintTicker(true);
    if (typeof moveInk === 'function') moveInk();
  }
  function pushLang(n) {                          // la vista riceve la lingua (variabile + evento + setLang)
    var w = win(n); if (!w) return;
    try {
      if (w.__OTM_LANG === LANG && V[n].langSent) return;
      w.__OTM_LANG = LANG; V[n].langSent = true;
      w.document.documentElement.lang = LANG;
      w.dispatchEvent(new w.CustomEvent('otm:lang', { detail: { lang: LANG } }));
      var i = nav(n); if (i && typeof i.setLang === 'function') i.setLang(LANG);
    } catch (e) {}
  }
  function setLang(l) {
    if (!OTM_I18N[l] || l === LANG) return;
    LANG = l; applyLang();
    ORDER.forEach(function (n) { if (V[n].ready) pushLang(n); });
    // ?lang= nell'indirizzo: al ricaricamento Streamlit riparte in questa lingua
    [window.parent, window.top].forEach(function (w, i, a) {
      if (i && w === a[0]) return;
      try { var u = new URL(w.location.href); u.searchParams.set('lang', l); w.history.replaceState(w.history.state, '', u.toString()); } catch (e) {}
    });
  }

  function win(n) { return V[n].f && V[n].f.contentWindow; }
  function nav(n) { var w = win(n); return w && w.OTMNav && w.OTMNav.instance; }
  function btn(n) { return tabs.querySelector('button[data-v="' + n + '"]'); }
  function editable(el) { return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)); }

  function applySuspend() {
    ORDER.forEach(function (n) {
      var w = win(n); if (!w) return;
      var off = (n !== cur); w.__OTM_SUSPENDED = off;
      if (!off) { var i = nav(n); if (i) i.resume(); }
    });
  }
  function syncLoader() {
    var busy = cur && V[cur].f && !V[cur].ready;
    loader.classList.toggle('on', !!busy);
    ORDER.forEach(function (n) { var b = btn(n); if (b) b.classList.toggle('loading', !!V[n].f && !V[n].ready); });
  }
  function focusView(n, delay) {
    setTimeout(function () { if (cur === n) { try { V[n].f.contentWindow.focus(); } catch (e) {} } }, delay || 0);
  }

  function frame(n) {
    if (V[n].f) return V[n].f;
    var f = document.createElement('iframe');
    f.className = 'view'; f.title = n;
    f.setAttribute('allow', 'fullscreen; clipboard-read; clipboard-write; autoplay');
    f.addEventListener('load', function () {
      V[n].ready = true; syncLoader(); applySuspend(); pushLang(n);
      var w = f.contentWindow;
      try {
        w.addEventListener('keydown', function (e) {
          if (e.ctrlKey || e.metaKey || e.altKey || editable(e.target)) return;
          if (e.key === 'Escape' && pseudo && !e.defaultPrevented) { setPseudo(false); return; }
          // [ ] funzionano anche con il focus sul grafico
          if (e.key === '[' || e.key === ']') { e.preventDefault(); cycle(e.key === ']' ? 1 : -1); }
        });
      } catch (e) {}
      if (n === cur) focusView(n, 40);
    });
    // prima di ogni script della vista: la lingua e, se non e' quella attiva, la sospensione
    // (cosi' non disegna nemmeno al primo frame)
    var html = JSON.parse(document.getElementById('v-' + n).textContent);
    var pre = '<script>window.__OTM_LANG=' + JSON.stringify(LANG) + ';document.documentElement.lang=window.__OTM_LANG;'
            + (n !== cur ? 'window.__OTM_SUSPENDED=true;' : '') + '<\/script>';
    html = /<head[^>]*>/i.test(html) ? html.replace(/<head[^>]*>/i, function (m) { return m + pre; }) : pre + html;
    f.srcdoc = html;
    stage.appendChild(f); V[n].f = f;
    syncLoader();
    return f;
  }

  function moveInk() {
    var b = tabs.querySelector('button.on'); if (!b) return;
    ink.style.width = b.offsetWidth + 'px';
    ink.style.transform = 'translateX(' + b.offsetLeft + 'px)';
  }
  function show(n) {
    if (!V[n]) n = START;
    if (cur === n) return;
    cur = n;
    frame(n);
    ORDER.forEach(function (k) { if (V[k].f) V[k].f.classList.toggle('on', k === n); });
    tabs.querySelectorAll('button').forEach(function (b) {
      var on = b.getAttribute('data-v') === n;
      b.classList.toggle('on', on); b.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    moveInk(); applySuspend(); syncLoader();
    if (V[n].ready) focusView(n, 30);
  }
  function cycle(d) {
    var now = Date.now(); if (now - lastCycle < 150) return;   // evita doppio scatto (shell + vista)
    lastCycle = now;
    var i = ORDER.indexOf(cur); show(ORDER[(i + d + ORDER.length) % ORDER.length]);
  }

  // precarica le altre viste quando il browser e' libero: il primo switch e' gia' istantaneo
  function preload() {
    ORDER.forEach(function (n) { if (!V[n].f) frame(n); });
  }

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
      var h = Math.max(480, Math.floor(H - r.top - 4));
      if (Math.abs((parseFloat(fe.style.height) || 0) - h) > 1) fe.style.height = h + 'px';
    } catch (e) {}
  }
  try { window.top.addEventListener('resize', fit); } catch (e) {}
  [0, 150, 600, 1500, 3000].forEach(function (ms) { setTimeout(fit, ms); });
  window.addEventListener('resize', moveInk);

  // ── ticker BTCUSDT perp: websocket Binance Futures aperto dal browser (IP dell'utente) ──
  // Prezzo dall'ultimo aggTrade, variazione 24h dal ticker, flusso aggressori = volume
  // eseguito a mercato in acquisto vs vendita negli ultimi 60 s (bucket da 1 s, orologio dell'exchange).
  // E' contesto di mercato, non un segnale.
  var TK = { px: null, prev: null, chg: null, buy: new Float64Array(60), sell: new Float64Array(60),
             sec: 0, off: 0, ws: null, ok: false, fails: 0, last: 0, flashT: 0 };
  var fmtPx, fmtPct, fmtQty;
  function setFormats() {
    var loc = LOCALE[LANG] || 'it-IT';
    fmtPx = new Intl.NumberFormat(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1, useGrouping: 'always' });
    fmtPct = new Intl.NumberFormat(loc, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' });
    fmtQty = new Intl.NumberFormat(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1, signDisplay: 'always' });
  }
  try { setFormats(); } catch (e) {
    fmtPx = { format: function (v) { return v.toFixed(1); } };
    fmtPct = { format: function (v) { return (v >= 0 ? '+' : '') + v.toFixed(2); } };
    fmtQty = fmtPct;
  }
  function roll(sec) {
    if (!TK.sec) { TK.sec = sec; return; }
    if (sec <= TK.sec) return;
    for (var k = TK.sec + 1; k <= Math.min(sec, TK.sec + 60); k++) { TK.buy[k % 60] = 0; TK.sell[k % 60] = 0; }
    TK.sec = sec;
  }
  function feed() {
    if (!window.WebSocket) return;
    var ws, dead = false;
    function retry() {
      if (dead) return; dead = true; TK.ok = false; TK.fails++;
      try { ws.close(); } catch (e) {}
      setTimeout(feed, Math.min(30000, 1000 * Math.pow(2, Math.min(TK.fails, 5))));
    }
    // USDⓈ-M: /stream legacy dismesso (Binance 2026-03-06) -> route /market (aggTrade, ticker)
    try { ws = new WebSocket('wss://fstream.binance.com/market/stream?streams=btcusdt@aggTrade/btcusdt@ticker'); }
    catch (e) { TK.fails++; setTimeout(feed, 15000); return; }
    TK.ws = ws;
    ws.onmessage = function (ev) {
      var m; try { m = JSON.parse(ev.data); } catch (e) { return; }
      var d = m && m.data; if (!d) return;
      TK.ok = true; TK.fails = 0; TK.last = Date.now();
      if (d.e === 'aggTrade') {
        var q = +d.q, ts = +d.T;
        TK.off = ts - Date.now();
        var sec = Math.floor(ts / 1000); roll(sec);
        if (sec > TK.sec - 60) { if (d.m) TK.sell[sec % 60] += q; else TK.buy[sec % 60] += q; }
        TK.px = +d.p;
      } else if (d.e === '24hrTicker') {
        TK.chg = +d.P; if (TK.px == null) TK.px = +d.c;
      }
    };
    ws.onerror = retry;
    ws.onclose = retry;
  }
  var EL = { live: document.getElementById('tlive'), px: document.getElementById('tpx'), ch: document.getElementById('tch'),
             bar: document.getElementById('tbar'), buy: document.getElementById('tbuy'), fd: document.getElementById('tfd'),
             flow: document.getElementById('tflow') };
  function txt(el, s) { if (el.textContent !== s) el.textContent = s; }
  function cls(el, base, mod) { var c = base + (mod ? ' ' + mod : ''); if (el.className !== c) el.className = c; }
  function paintTicker(force) {
    var fresh = TK.ok && Date.now() - TK.last < 15000;
    cls(EL.live, 'tdot', fresh ? 'on' : '');
    if (TK.px == null) {
      txt(EL.px, '—');
      txt(EL.ch, TK.fails > 3 ? t("feed non disponibile") : t("connessione…")); cls(EL.ch, 'chg', '');
      cls(EL.bar, 'bar', 'idle'); txt(EL.fd, '—'); cls(EL.fd, 'fd', '');
      return;
    }
    if (TK.prev != null && TK.px !== TK.prev) {
      cls(EL.px, 'px', TK.px > TK.prev ? 'up' : 'dn'); TK.flashT = Date.now();
    } else if (Date.now() - TK.flashT > 450) cls(EL.px, 'px', '');
    TK.prev = TK.px;
    txt(EL.px, fmtPx.format(TK.px));
    if (TK.chg != null) { txt(EL.ch, fmtPct.format(TK.chg) + '%'); cls(EL.ch, 'chg', TK.chg > 0 ? 'up' : TK.chg < 0 ? 'dn' : ''); }
    roll(Math.floor((Date.now() + TK.off) / 1000));
    var B = 0, S = 0;
    for (var i = 0; i < 60; i++) { B += TK.buy[i]; S += TK.sell[i]; }
    if (B + S <= 0) { cls(EL.bar, 'bar', 'idle'); txt(EL.fd, '—'); cls(EL.fd, 'fd', ''); return; }
    var p = B / (B + S), dlt = B - S;
    cls(EL.bar, 'bar', '');
    EL.buy.style.width = (p * 100).toFixed(1) + '%';
    txt(EL.fd, 'Δ ' + fmtQty.format(dlt));
    cls(EL.fd, 'fd', dlt > 0 ? 'up' : dlt < 0 ? 'dn' : '');
    var tip = t("acquisti {b}% · vendite {s}%", { b: Math.round(p * 100), s: 100 - Math.round(p * 100) });
    if (EL.flow.title !== tip) EL.flow.title = tip;
  }

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
    var OPEN = 570, CLOSE = 960, PRE = 240, dot = document.getElementById('sdot');
    var st = document.getElementById('sst'), nx = document.getElementById('snext');
    var box = document.getElementById('sess'), bar = document.getElementById('sbar');
    var weekday = wd >= 1 && wd <= 5;
    if (weekday && mins >= OPEN && mins < CLOSE) {
      dot.className = 'dot open'; box.className = 'sess hide-xl open';
      st.textContent = t("APERTA"); nx.textContent = t("chiude tra {d}", { d: dur(CLOSE - mins) });
      bar.style.width = ((mins - OPEN) / (CLOSE - OPEN) * 100).toFixed(2) + '%';
      return;
    }
    var until;
    if (weekday && mins < OPEN) until = OPEN - mins;
    else { var days = wd === 5 ? 3 : (wd === 6 ? 2 : 1); until = days * 1440 - mins + OPEN; }
    var pre = weekday && mins >= PRE && mins < OPEN;
    dot.className = 'dot' + (pre ? ' pre' : '');
    box.className = 'sess hide-xl' + (pre ? ' pre' : '');
    bar.style.width = pre ? ((mins - PRE) / (OPEN - PRE) * 100).toFixed(2) + '%' : '0%';
    st.textContent = pre ? t("PRE-MARKET") : t("CHIUSA");
    nx.textContent = t("apre tra {d}", { d: dur(until) });
  }
  applyLang(); setInterval(tick, 1000);
  feed(); setInterval(paintTicker, 400);
  window.addEventListener('pagehide', function () { try { TK.ws && TK.ws.close(); } catch (e) {} });

  // ── input ──
  // pointerdown invece di click: lo switch parte alla pressione, non al rilascio
  tabs.addEventListener('pointerdown', function (e) { var b = e.target.closest('button'); if (b && e.button === 0) { e.preventDefault(); show(b.getAttribute('data-v')); } });
  tabs.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { var b = e.target.closest('button'); if (b) { e.preventDefault(); show(b.getAttribute('data-v')); } } });
  document.getElementById('lang').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (b) { setLang(b.getAttribute('data-l')); focusView(cur, 0); }
  });
  document.getElementById('b-fs').addEventListener('click', fullscreen);
  document.getElementById('b-help').addEventListener('click', function () { var i = nav(cur); if (i) i.help(); });
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey || e.metaKey || e.altKey || editable(e.target)) return;
    if (e.key === '[' || e.key === ']') { e.preventDefault(); cycle(e.key === ']' ? 1 : -1); return; }
    if (e.key === 'Escape' && pseudo) { setPseudo(false); return; }
    var i = nav(cur); if (i) i.key(e);           // tasti premuti sulla barra: girati al grafico attivo
  });
  document.addEventListener('fullscreenchange', function () { setTimeout(fit, 50); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(moveInk);

  window.OTMShell = { show: show, cycle: cycle, fullscreen: fullscreen, exitPseudo: function () { if (pseudo) setPseudo(false); },
                      setLang: setLang, lang: function () { return LANG; }, t: t };

  show(START);
  requestAnimationFrame(function () { moveInk(); requestAnimationFrame(function () { tabs.classList.remove('noanim'); }); });
  (window.requestIdleCallback || function (cb) { return setTimeout(cb, 1200); })(preload, { timeout: 2500 });
})();
</script>
</body></html>"""


# ── Accesso ─────────────────────────────────────────────────────────────────
# L'HTML delle viste (cioe' la logica della strategia) viene inviato al browser SOLO dopo
# l'accesso (accesso_otm.py). Secrets in Streamlit Cloud: Settings > Secrets
#   APP_PASSWORD   = "la-tua-password"   accesso del titolare, senza scadenza
#   LICENSE_SECRET = "..."               chiave dei codici di prova (crea_licenza.py --nuova-chiave)
# In locale senza secret l'accesso e' libero; in cloud senza secret l'app si blocca.


_tab_identity()
local = _is_local()
scadenza = accesso_otm.richiedi_accesso(local, OTM_MARK_SVG)

# Un solo componente: la shell gestisce tab, viste e schermo intero lato browser,
# quindi nessun rerun di Streamlit quando cambi vista o ridimensioni.
components.html(accesso_otm.con_scadenza(load_shell(local, tz.lingua_corrente()), scadenza),
                height=860, scrolling=False)
