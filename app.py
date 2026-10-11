"""
OUTTHINK THE MARKET — shell Streamlit
--------------------------------------
Incorpora le due app JS (Footprint e FakeMove E/L/C) cosi' come sono.
Il rendering e i websocket restano nel browser: i dati arrivano dal tuo
IP (Italia), non dal server Streamlit (USA, bloccato da Binance/Bybit).

I file in views/ sono le copie originali dei repo, NON modificate.
Gli adattamenti per l'iframe vengono applicati qui, al caricamento:
  1. session-volume-profile.js inserito inline nella Footprint
  2. rilevamento "localhost" letto dalla pagina Streamlit (non dall'iframe)
  3. in cloud le chiamate di esecuzione (proxy/Netlify) vengono bloccate
"""

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
[data-testid="stHeader"] {{ background:transparent; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility:hidden; }}
.block-container {{ padding:3rem 0.8rem 0.4rem 0.8rem !important; max-width:100% !important; }}
[data-testid="stSidebar"] {{ background:{SURFACE}; border-right:1px solid {ELEVATED}; }}
.otm-bar {{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; }}
.otm-brand {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.05rem;
             letter-spacing:.08em; color:{LIGHT}; }}
.otm-brand span {{ color:{TEAL}; }}
.otm-pill {{ font-family:'JetBrains Mono',Consolas,monospace; font-size:.72rem; padding:3px 10px;
            border-radius:999px; border:1px solid; white-space:nowrap; }}
.otm-live {{ color:{CRIMSON}; border-color:{CRIMSON}55; background:{CRIMSON}14; }}
.otm-safe {{ color:{TEAL}; border-color:{TEAL}55; background:{TEAL}14; }}
.otm-note {{ font-family:Inter,sans-serif; color:{MUTED}; font-size:.8rem; line-height:1.5; }}
iframe {{ border:1px solid {ELEVATED} !important; border-radius:10px; background:#050a12; }}
div[data-testid="stSegmentedControl"] button {{ font-family:'Space Grotesk',sans-serif; }}
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
# Gira PRIMA di ogni altro script della pagina.
_SHIM = """<script>
(function () {
  var h = '';
  try { h = window.parent.location.hostname || ''; } catch (e) {}
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


def _inject_shim(html: str) -> str:
    # dentro l'iframe srcdoc location.hostname e' vuoto: usiamo quello della pagina Streamlit
    html = html.replace("window.location.hostname", "window.__OTM_HOST")
    html = html.replace("location.hostname", "window.__OTM_HOST")
    low = html.lower()
    i = low.find("<head>")
    if i != -1:
        j = i + len("<head>")
        return html[:j] + _SHIM + html[j:]
    return _SHIM + html


# ── Origine delle viste ─────────────────────────────────────────────────────
# Se la cartella views/ e' accanto ad app.py (repo privato, uso locale) si leggono
# i file da disco. Altrimenti (repo pubblico su Streamlit Cloud) si scaricano dal
# repo PRIVATO con un token nei Secrets:
#   GITHUB_TOKEN = "github_pat_..."         (fine-grained, Contents: Read-only)
#   VIEWS_REPO   = "JER55/otm-streamlit"     (opzionale, questo e' il default)
VIEW_FILES = {"footprint": ["footprint.html", "session-volume-profile.js"], "fakemove": ["fakemove.html"]}
LOCAL_VIEWS = (VIEWS / "footprint.html").exists()


def _secret(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default))
    except Exception:
        return default


@st.cache_data(show_spinner="Carico la vista…", ttl=900)
def _fetch_remote(fname: str) -> str:
    import json
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
                404: "repo o file non trovato (il token ha accesso al repo?)"}.get(e.code, "")
        try:
            msg = json.loads(e.read().decode()).get("message", "")
        except Exception:
            msg = ""
        raise RuntimeError(f"GitHub {e.code} su views/{fname}: {hint} {msg}".strip()) from None


def _read(fname: str) -> str:
    if LOCAL_VIEWS:
        return (VIEWS / fname).read_text(encoding="utf-8")
    return _fetch_remote(fname)


@st.cache_data(show_spinner=False, ttl=900)
def _build_view(name: str, _key: float) -> str:
    if name == "footprint":
        html, svp = _read("footprint.html"), _read("session-volume-profile.js")
        tag = '<script src="session-volume-profile.js"></script>'
        if tag in html:
            html = html.replace(tag, "<script>\n" + svp + "\n</script>")
        else:
            st.warning("Tag di session-volume-profile.js non trovato nella Footprint: SVP non caricato.")
    else:
        html = _read("fakemove.html")
    return _inject_shim(html)


def load_view(name: str) -> str:
    # in locale la cache si invalida quando cambi un file; da remoto vale il ttl di 15 minuti
    key = max((VIEWS / f).stat().st_mtime for f in VIEW_FILES[name]) if LOCAL_VIEWS else 0.0
    try:
        return _build_view(name, key)
    except RuntimeError as e:
        st.error(f"Impossibile caricare la vista: {e}")
        st.stop()


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

# ── Sidebar: impostazioni ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="otm-brand">OUTTHINK <span>THE MARKET</span></div>', unsafe_allow_html=True)
    st.write("")
    height = st.slider("Altezza grafico (px)", 600, 1400, 880, step=20)
    st.markdown(
        '<div class="otm-note">Cambiare altezza ricarica il grafico (riparte il seed dei dati).</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    if local:
        st.markdown(
            '<div class="otm-note"><b>Modalità locale.</b> Il pannello ordini della Footprint usa il proxy '
            "<code>localhost:3333</code>: avvia <code>node local-bitget-proxy.js</code> per il trading live. "
            "Il tetto di 0,1 BTC del proxy resta attivo.</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="otm-note"><b>Modalità cloud.</b> Solo analisi: le chiamate di esecuzione sono '
            "bloccate. Per operare usa l'app in locale con il proxy.</div>",
            unsafe_allow_html=True,
        )

# ── Barra superiore ─────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([2.2, 3, 1.6], vertical_alignment="center")
with c1:
    st.markdown('<div class="otm-brand">OTM <span>· ORDER FLOW</span></div>', unsafe_allow_html=True)
with c2:
    view = st.segmented_control(
        "Vista",
        options=["footprint", "fakemove"],
        format_func=lambda v: {"footprint": "FOOTPRINT", "fakemove": "FAKEMOVE E/L/C"}[v],
        default="footprint",
        label_visibility="collapsed",
        key="view",
    ) or "footprint"
with c3:
    if local:
        st.markdown('<div class="otm-bar"><span class="otm-pill otm-live">● LOCALE · LIVE VIA PROXY</span></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="otm-bar"><span class="otm-pill otm-safe">● CLOUD · SOLO ANALISI</span></div>',
                    unsafe_allow_html=True)

# ── Vista: una sola alla volta (niente websocket doppi in background) ────────
components.html(load_view(view), height=height, scrolling=False)
