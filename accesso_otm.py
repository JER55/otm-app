# -*- coding: utf-8 -*-
"""
accesso_otm.py — schermata d'accesso di Otmflow: password del titolare O codice di prova.

    exp = accesso_otm.richiedi_accesso(local, OTM_MARK_SVG)     # None = titolare, epoch = prova
    components.html(accesso_otm.con_scadenza(load_shell(...), exp), height=860, scrolling=False)

Secrets (Streamlit Cloud → Settings → Secrets):
    APP_PASSWORD     = "..."                 # tu: accesso senza scadenza (come prima)
    LICENSE_SECRET   = "..."                 # da: python crea_licenza.py --nuova-chiave
    LICENZE_REVOCATE = ["7F3A9C21"]          # facoltativo: id dei codici da spegnere subito

Scadenza, su due livelli:
  * server: a ogni rerun il codice in sessione viene riverificato (firma, revoca, scadenza);
  * browser: la shell non fa rerun, quindi un timer chiude le viste allo scoccare della scadenza.
    Usa l'orologio monotono (performance.now) agganciato all'ora del SERVER: spostare
    indietro l'orologio del PC non allunga la prova. Ricaricando, si torna al login.
"""
import datetime as dt
import hmac
import json
import time

import streamlit as st

import licenze_otm as lic
import traduzioni as tz

tr = tz.tr

# testi del timer nel browser (passati in tutte e tre le lingue: il cambio lingua è istantaneo)
TESTI_SCADENZA = (
    "PROVA · {d}",
    "Licenza di prova: alla scadenza le viste si chiudono",
    "Licenza di prova scaduta",
    "Ricarica la pagina e inserisci un nuovo codice per continuare.",
)


def _secret(chiave, predefinito=""):
    try:
        return st.secrets.get(chiave, predefinito)
    except Exception:
        return predefinito


def _revocati():
    v = _secret("LICENZE_REVOCATE", [])
    return [v] if isinstance(v, str) else list(v or [])


def _data(epoch):
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.fromtimestamp(epoch, ZoneInfo("Europe/Rome")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def _messaggio(esito):
    if esito.motivo == "scaduta":
        return tr("Codice di prova scaduto il {data}.", data=_data(esito.scadenza))
    if esito.motivo == "revocata":
        return tr("Codice di prova revocato.")
    return tr("Password errata.")          # firma/formato/chiave: nessun indizio a chi prova a caso


def richiedi_accesso(is_local: bool, mark_svg: str):
    """None = titolare (nessuna scadenza); intero = scadenza epoch del codice di prova.
    Senza accesso disegna il login e ferma la pagina (st.stop)."""
    password = str(_secret("APP_PASSWORD", "") or "")
    segreto = str(_secret("LICENSE_SECRET", "") or "")
    ss = st.session_state
    if not password and not segreto and is_local:
        return None

    avviso = None
    if ss.get("otm_auth"):
        codice = ss.get("otm_codice")
        if not codice:
            return None                                   # entrato con la password
        e = lic.verifica(segreto, codice, revocati=_revocati())
        if e.ok:
            return e.scadenza
        ss["otm_auth"] = False                            # scaduto o revocato durante la sessione
        ss.pop("otm_codice", None)
        avviso = _messaggio(e)

    # selettore IT · EN · ES prima di ogni st.stop(): c'è anche sulla schermata d'accesso
    _, sel = st.columns([5, 1])
    tz.selettore(sel)
    if not password and not segreto:
        st.error(tr("APP_PASSWORD non configurata nei Secrets: accesso bloccato."))
        st.stop()
    if segreto and len(segreto.strip()) < lic.MIN_CHIAVE:
        st.warning(tr("LICENSE_SECRET troppo corta (minimo 32 caratteri): codici di prova disattivati."))

    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown('<div class="otm-brand" style="margin:9vh 0 22px">' + mark_svg
                    + '<b>OTM<span>FLOW</span></b><small>OUTTHINK THE MARKET</small></div>',
                    unsafe_allow_html=True)
        with st.form("otm_login"):
            pwd = st.text_input(tr("Password"), type="password", key="otm_pwd",
                                placeholder=tr("password o codice di prova OTM-…"))
            ok = st.form_submit_button(tr("ENTRA"), use_container_width=True)
        if ok:
            if password and hmac.compare_digest(pwd.encode(), password.encode()):
                ss["otm_auth"] = True
                ss.pop("otm_codice", None)
                st.rerun()
            e = lic.verifica(segreto, pwd, revocati=_revocati()) if segreto else lic.Esito(False, "chiave")
            if e.ok:
                ss["otm_auth"] = True
                ss["otm_codice"] = pwd.strip()
                st.rerun()
            time.sleep(1.5)                               # rallenta i tentativi a forza bruta
            st.error(_messaggio(e))
        elif avviso:
            st.error(avviso)
    st.stop()


_SCADENZA_JS = r"""<style>
.pill.lic{color:var(--amber);border-color:rgba(242,169,59,.4);background:rgba(242,169,59,.08)}
.pill.lic.warn{color:var(--red);border-color:rgba(255,92,92,.45);background:rgba(255,92,92,.1)}
#otm-scaduta{position:absolute;inset:0;z-index:9;display:grid;place-items:center;background:#050a12}
#otm-scaduta div{display:flex;flex-direction:column;align-items:center;gap:10px;text-align:center;padding:0 16px}
#otm-scaduta svg{width:48px;height:48px;opacity:.6}
#otm-scaduta b{font:700 15px 'Space Grotesk',sans-serif;letter-spacing:.12em;color:var(--amber)}
#otm-scaduta span{font:500 12.5px Inter,sans-serif;color:var(--muted)}
</style>
<script>
(function () {
  var EXP = %%EXP%% * 1000, NOW = %%NOW%%, T = %%TESTI%%;
  var dl = performance.now() + (EXP - NOW), skew = NOW - Date.now(), dead = false;
  var LOC = { it: 'it-IT', en: 'en-US', es: 'es-ES' };
  function lang() { try { return window.OTMShell.lang(); } catch (e) { return document.documentElement.lang || 'it'; } }
  function t(k) { var d = T[lang()] || T.it || {}; return d[k] || k; }
  // il minore dei due: monotono (non si inganna cambiando l'ora) e da calendario (copre la sospensione del PC)
  function left() { return Math.min(dl - performance.now(), EXP - (Date.now() + skew)); }
  function fmt(ms) {
    if (ms < 86400000) { var m = Math.max(1, Math.ceil(ms / 60000)), h = Math.floor(m / 60); return (h ? h + 'h ' : '') + (m % 60) + 'm'; }
    try { return new Intl.DateTimeFormat(LOC[lang()] || 'it-IT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Rome' }).format(new Date(EXP)); }
    catch (e) { return new Date(EXP).toISOString().slice(0, 16).replace('T', ' '); }
  }
  var pill = document.createElement('span'); pill.className = 'pill lic';
  var mode = document.getElementById('mode');
  if (mode && mode.parentNode) mode.parentNode.insertBefore(pill, mode);
  function lock() {
    dead = true;
    document.querySelectorAll('iframe.view').forEach(function (f) { try { f.srcdoc = ''; f.parentNode.removeChild(f); } catch (e) {} });
    ['v-fakemove', 'v-footprint'].forEach(function (id) { var s = document.getElementById(id); if (s) s.parentNode.removeChild(s); });
    var stage = document.getElementById('stage') || document.body, ld = document.getElementById('loader');
    if (ld) ld.classList.remove('on');
    var o = document.createElement('div'); o.id = 'otm-scaduta';
    var mark = document.querySelector('.brand svg');
    o.innerHTML = '<div>' + (mark ? mark.outerHTML : '') + '<b></b><span></span></div>';
    stage.appendChild(o);
    paint();
  }
  function paint() {
    var o = document.getElementById('otm-scaduta');
    if (o) { o.querySelector('b').textContent = t('Licenza di prova scaduta'); o.querySelector('span').textContent = t('Ricarica la pagina e inserisci un nuovo codice per continuare.'); }
    pill.title = t('Licenza di prova: alla scadenza le viste si chiudono');
  }
  function step() {
    if (dead) { paint(); return; }                 // segue anche i cambi di lingua dopo la scadenza
    var l = left();
    if (l <= 0) { pill.textContent = t('PROVA · {d}').replace('{d}', '0m'); pill.className = 'pill lic warn'; lock(); return; }
    pill.textContent = t('PROVA · {d}').replace('{d}', fmt(l));
    pill.className = 'pill lic' + (l < 600000 ? ' warn' : '');
    paint();
  }
  step(); setInterval(step, 1000);
})();
</script>"""


def con_scadenza(html: str, scadenza):
    """Aggiunge alla shell il badge della prova e la chiusura delle viste a scadenza.
    scadenza None (titolare): la shell resta com'è."""
    if not scadenza:
        return html
    testi = {lg: {k: tz.traduci(lg, k) for k in TESTI_SCADENZA} for lg in tz.LINGUE}
    js = (_SCADENZA_JS.replace("%%EXP%%", str(int(scadenza)))
          .replace("%%NOW%%", str(int(time.time() * 1000)))
          .replace("%%TESTI%%", json.dumps(testi, ensure_ascii=False).replace("<", "\\u003c")))
    i = html.rfind("</body>")       # le viste sono JSON senza "<" letterali: l'ultimo </body> è della shell
    return html[:i] + js + html[i:] if i != -1 else html + js
