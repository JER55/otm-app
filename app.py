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
  * titolo "Otmflow - OutThinkTheMarket" e logo OTM (page_icon dai byte PNG incorporati);
  * un componente invisibile riallinea titolo e icona SVG anche sulla pagina esterna
    (su Streamlit Cloud il titolo altrimenti diventa "… · Streamlit").

Lingue (IT · EN · ES, con traduzioni.py e locales/*.json — stesso sistema di ThinkCore):
  * testi Python con tr("..."); testi della shell con t("...") / data-i18n="..." nell'HTML:
    le chiavi della shell sono estratte da SHELL_HTML, nessun elenco da tenere allineato;
  * si parte in inglese; ?lang=it|es nell'indirizzo o [interfaccia] lingua nei Secrets;
  * login: selettore Streamlit; dentro l'app: selettore IT/EN/ES nella barra, cambio
    istantaneo senza ricaricare le viste (scrive ?lang= nell'indirizzo per il reload);
  * le viste ricevono la lingua: window.__OTM_LANG prima dei loro script, poi l'evento
    'otm:lang' (detail.lang) a ogni cambio e OTMNav.instance.setLang(lang) se esiste;
  * FakeMove, Footprint e otm-nav.js sono tradotti a runtime da otm-i18n.js con il catalogo
    locales/views.json (testo DOM, attributi, canvas, alert/confirm, notifiche): i file delle
    viste non vanno modificati.
"""

import base64
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
# Immagini originali dalla pagina OTM Liquidity: il mark per icona/barra e il logo
# completo è disponibile per gli usi che richiedono il wordmark.
LOGO_MARK = (
    "data:image/png;base64,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"
)
LOGO_FULL = (
    "data:image/jpeg;base64,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"
    "r//2Q=="
)
OTM_MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 164 164" width="32" height="32" aria-hidden="true">'
    '<defs>'
    '<linearGradient id="otm-mark-body" x1="0" y1="0" x2="1" y2="1">'
    '<stop stop-color="#0B1220"/><stop offset=".48" stop-color="#050a12"/><stop offset="1" stop-color="#020406"/>'
    '</linearGradient>'
    '<linearGradient id="otm-mark-gold" x1="0" y1="0" x2="1" y2="1">'
    '<stop stop-color="#FFF44F"/><stop offset=".48" stop-color="#FFD21C"/><stop offset="1" stop-color="#F2A93B"/>'
    '</linearGradient>'
    '<linearGradient id="otm-mark-cyan" x1="0" y1="0" x2="1" y2="1">'
    '<stop stop-color="#d9fbff"/><stop offset=".35" stop-color="#59E1FF"/><stop offset="1" stop-color="#137da8"/>'
    '</linearGradient>'
    '<radialGradient id="otm-mark-caustic" cx=".18" cy=".08" r=".92">'
    '<stop stop-color="#59E1FF" stop-opacity=".4"/><stop offset=".55" stop-color="#59E1FF" stop-opacity=".08"/><stop offset="1" stop-color="#59E1FF" stop-opacity="0"/>'
    '</radialGradient>'
    '<radialGradient id="otm-mark-orb-cyan">'
    '<stop stop-color="#fff"/><stop offset=".22" stop-color="#b9f7ff"/><stop offset=".58" stop-color="#59E1FF"/><stop offset="1" stop-color="#59E1FF" stop-opacity="0"/>'
    '</radialGradient>'
    '<radialGradient id="otm-mark-orb-violet">'
    '<stop stop-color="#fff"/><stop offset=".3" stop-color="#d7c9ff"/><stop offset=".68" stop-color="#9B7BFF"/><stop offset="1" stop-color="#9B7BFF" stop-opacity="0"/>'
    '</radialGradient>'
    '<radialGradient id="otm-mark-hologram" cx=".5" cy=".58" r=".58">'
    '<stop stop-color="#59E1FF" stop-opacity=".4"/><stop offset=".48" stop-color="#59E1FF" stop-opacity=".16"/><stop offset="1" stop-color="#59E1FF" stop-opacity="0"/>'
    '</radialGradient>'
    '<radialGradient id="otm-mark-rim" cx="1" cy=".55" r=".74">'
    '<stop stop-color="#F2A93B" stop-opacity=".38"/><stop offset=".42" stop-color="#F2A93B" stop-opacity=".12"/><stop offset="1" stop-color="#F2A93B" stop-opacity="0"/>'
    '</radialGradient>'
    '<linearGradient id="otm-mark-glass-sheen" x1="0" y1="0" x2="1" y2="1">'
    '<stop stop-color="#fff" stop-opacity=".48"/><stop offset=".38" stop-color="#d9fbff" stop-opacity=".16"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
    '</linearGradient>'
    '<linearGradient id="otm-mark-side" x1="0" y1="0" x2="0" y2="1">'
    '<stop stop-color="#16273a"/><stop offset=".36" stop-color="#07101b"/><stop offset="1" stop-color="#020406"/>'
    '</linearGradient>'
    '<linearGradient id="otm-mark-comet-cyan" x1="1" y1="0" x2="0" y2="0">'
    '<stop stop-color="#d9fbff" stop-opacity=".92"/><stop offset=".24" stop-color="#59E1FF" stop-opacity=".52"/><stop offset="1" stop-color="#59E1FF" stop-opacity="0"/>'
    '</linearGradient>'
    '<linearGradient id="otm-mark-comet-violet" x1="1" y1="0" x2="0" y2="0">'
    '<stop stop-color="#f4eeff" stop-opacity=".86"/><stop offset=".25" stop-color="#9B7BFF" stop-opacity=".48"/><stop offset="1" stop-color="#9B7BFF" stop-opacity="0"/>'
    '</linearGradient>'
    '<clipPath id="otm-mark-clip"><rect x="28" y="28" width="108" height="108" rx="28"/></clipPath>'
    '<clipPath id="otm-mark-reflection-clip"><rect x="28" y="82" width="108" height="54"/></clipPath>'
    '<mask id="otm-mark-orbit-back"><rect x="0" y="0" width="164" height="82" fill="#fff"/></mask>'
    '<mask id="otm-mark-orbit-front"><rect x="0" y="82" width="164" height="82" fill="#fff"/></mask>'
    '<filter id="otm-mark-glow" x="-70%" y="-70%" width="240%" height="240%">'
    '<feGaussianBlur stdDeviation="3.2" result="otm-mark-blur"/>'
    '<feColorMatrix in="otm-mark-blur" type="matrix" values="0 0 0 0 .08 0 0 0 0 .72 0 0 0 0 1 0 0 0 .88 0" result="otm-mark-light"/>'
    '<feMerge><feMergeNode in="otm-mark-light"/><feMergeNode in="SourceGraphic"/></feMerge>'
    '</filter>'
    '<filter id="otm-mark-shadow" x="-35%" y="-35%" width="170%" height="180%">'
    '<feGaussianBlur in="SourceAlpha" stdDeviation="5" result="otm-mark-shadow-blur"/>'
    '<feOffset dy="4" result="otm-mark-shadow-offset"/>'
    '<feColorMatrix in="otm-mark-shadow-offset" type="matrix" values="0 0 0 0 0 0 0 0 0 .12 0 0 0 0 .2 0 0 0 .8 0" result="otm-mark-shadow-color"/>'
    '<feMerge><feMergeNode in="otm-mark-shadow-color"/><feMergeNode in="SourceGraphic"/></feMerge>'
    '</filter>'
    '<filter id="otm-mark-glass" x="-20%" y="-20%" width="140%" height="140%">'
    '<feTurbulence type="fractalNoise" baseFrequency=".035" numOctaves="2" seed="12" result="otm-mark-noise"/>'
    '<feSpecularLighting in="otm-mark-noise" surfaceScale="4" specularConstant=".7" specularExponent="22" lighting-color="#c8f7ff" result="otm-mark-specular">'
    '<feDistantLight azimuth="225" elevation="55"/></feSpecularLighting>'
    '<feComposite in="otm-mark-specular" in2="SourceAlpha" operator="in" result="otm-mark-specular-mask"/>'
    '<feGaussianBlur in="otm-mark-specular-mask" stdDeviation=".35" result="otm-mark-soft-specular"/>'
    '<feMerge><feMergeNode in="SourceGraphic"/><feMergeNode in="otm-mark-soft-specular"/></feMerge>'
    '</filter>'
    '<filter id="otm-mark-reflection" x="-10%" y="-10%" width="120%" height="120%">'
    '<feGaussianBlur stdDeviation="2" result="otm-mark-reflection-blur"/>'
    '<feColorMatrix in="otm-mark-reflection-blur" type="saturate" values=".55"/>'
    '</filter>'
    '<filter id="otm-mark-neural-glass" x="-5%" y="-5%" width="110%" height="110%">'
    '<feColorMatrix type="saturate" values=".9"/>'
    '</filter>'
    '<filter id="otm-mark-bevel" x="-12%" y="-12%" width="124%" height="130%">'
    '<feGaussianBlur in="SourceAlpha" stdDeviation="1.3" result="otm-mark-bevel-blur"/>'
    '<feOffset dy="1.5" result="otm-mark-bevel-offset"/>'
    '<feComposite in="otm-mark-bevel-offset" in2="SourceAlpha" operator="out" result="otm-mark-bevel-edge"/>'
    '<feMerge><feMergeNode in="otm-mark-bevel-edge"/><feMergeNode in="SourceGraphic"/></feMerge>'
    '</filter>'
    '<filter id="otm-mark-caustic-filter" x="-5%" y="-5%" width="110%" height="110%">'
    '<feTurbulence type="fractalNoise" baseFrequency=".05" numOctaves="2" seed="29" result="otm-mark-caustic-noise"/>'
    '<feColorMatrix in="otm-mark-caustic-noise" type="matrix" values="0 0 0 0 .18 0 0 0 0 .78 0 0 0 0 1 0 0 0 .22 0"/>'
    '</filter>'
    '</defs>'
    '<style>'
    '.otm-mark-orbit-trace{stroke-dasharray:18 150;stroke-dashoffset:0;animation:otm-mark-orbit-flow 4.2s linear infinite}'
    '.otm-mark-orbit-trace-violet{stroke-dasharray:10 14;animation:otm-mark-orbit-flow 6s linear infinite reverse}'
    '.otm-mark-comet{fill:none;stroke-linecap:round;filter:url(#otm-mark-glow);animation:otm-mark-comet-drift 4.2s ease-in-out infinite}'
    '.otm-mark-comet-violet{animation-duration:6s;animation-delay:-2.2s}'
    '.otm-mark-sheen{opacity:0;animation:otm-mark-sweep 5.2s cubic-bezier(.4,0,.2,1) infinite}'
    '.otm-mark-sheen-b{opacity:0;animation:otm-mark-sweep 5.2s cubic-bezier(.4,0,.2,1) 2.6s infinite}'
    '.otm-mark-caustics{opacity:.18;mix-blend-mode:overlay;animation:otm-mark-caustic-pulse 7s ease-in-out infinite}'
    '.otm-mark-orb-pulse{transform-box:fill-box;transform-origin:center;animation:otm-mark-pulse 2.4s ease-in-out infinite}'
    '.otm-mark-dust{transform-box:fill-box;transform-origin:center;animation:otm-mark-float 11s ease-in-out infinite}'
    '.otm-mark-dust-2{animation-duration:8.5s;animation-delay:-3s}.otm-mark-dust-3{animation-duration:13s;animation-delay:-7s}'
    '.otm-mark-dust-4{animation-duration:9.5s;animation-delay:-4s}.otm-mark-dust-5{animation-duration:12s;animation-delay:-8s}'
    '.otm-mark-dust-6{animation-duration:10s;animation-delay:-2s}'
    '@keyframes otm-mark-orbit-flow{to{stroke-dashoffset:-168}}'
    '@keyframes otm-mark-comet-drift{0%,100%{opacity:.35}50%{opacity:1}}'
    '@keyframes otm-mark-sweep{0%,16%{opacity:0;transform:translateX(-18px)}42%{opacity:.38}68%,100%{opacity:0;transform:translateX(18px)}}'
    '@keyframes otm-mark-pulse{0%,100%{opacity:.78;transform:scale(.88)}50%{opacity:1;transform:scale(1.12)}}'
    '@keyframes otm-mark-caustic-pulse{0%,100%{opacity:.08}50%{opacity:.2}}'
    '@keyframes otm-mark-float{0%,100%{transform:translateY(0);opacity:.3}50%{transform:translateY(-3px);opacity:.85}}'
    '@media(prefers-reduced-motion:reduce){.otm-mark-orbit-trace,.otm-mark-orbit-trace-violet,.otm-mark-comet,.otm-mark-sheen,.otm-mark-sheen-b,.otm-mark-caustics,.otm-mark-orb-pulse,.otm-mark-dust{animation:none!important}}'
    '</style>'
    '<g class="otm-orbit-a" mask="url(#otm-mark-orbit-back)"><ellipse cx="82" cy="82" rx="78" ry="32" transform="rotate(-27 82 82)" fill="none" stroke="#59E1FF" stroke-opacity=".34" stroke-width="1.3"/></g>'
    '<g class="otm-orbit-b" mask="url(#otm-mark-orbit-back)"><ellipse cx="82" cy="82" rx="73" ry="49" transform="rotate(37 82 82)" fill="none" stroke="#9B7BFF" stroke-opacity=".28" stroke-width="1.1" stroke-dasharray="2 4"/></g>'
    '<ellipse cx="82" cy="152" rx="48" ry="5" fill="#000" opacity=".4" filter="url(#otm-mark-reflection)"/>'
    '<rect x="30" y="31" width="108" height="108" rx="28" fill="#020406" stroke="#03070d" stroke-width="2"/>'
    '<rect x="29" y="30" width="108" height="108" rx="28" fill="url(#otm-mark-side)" stroke="#0b1928" stroke-width="1.4"/>'
    '<rect x="28" y="28" width="108" height="108" rx="28" fill="#040810" stroke="#59E1FF" stroke-opacity=".3" stroke-width="1.4" filter="url(#otm-mark-shadow)"/>'
    '<g clip-path="url(#otm-mark-clip)">'
    '<rect x="28" y="28" width="108" height="108" rx="28" fill="url(#otm-mark-body)"/>'
    '<rect x="28" y="28" width="108" height="108" rx="28" fill="url(#otm-mark-caustic)"/>'
    '<path d="M29 29h106v38c-18-16-39-23-62-20-18 2-32 11-44 25z" fill="#59E1FF" fill-opacity=".14"/>'
    '<path d="M29 101c25 20 67 26 107 6v29H29z" fill="#07101b" fill-opacity=".72"/>'
    '<rect class="otm-mark-caustics" x="28" y="28" width="108" height="108" fill="#59E1FF" filter="url(#otm-mark-caustic-filter)"/>'
    '<path d="M29 62c17-23 35-31 66-34 15-1 27 2 39 8v-8H29z" fill="#e8fdff" fill-opacity=".12"/>'
    '<path d="M32 111c26 17 65 23 101 5v20H32z" fill="#F2A93B" fill-opacity=".12"/>'
    '<path d="M35 42c20-10 47-14 72-7" fill="none" stroke="#d9fbff" stroke-opacity=".42" stroke-width="1.2" stroke-linecap="round"/>'
    '<path d="M40 124c20 8 48 10 70 2" fill="none" stroke="#59E1FF" stroke-opacity=".2" stroke-width="1"/>'
    '<ellipse cx="82" cy="87" rx="39" ry="29" fill="url(#otm-mark-hologram)" filter="url(#otm-mark-glow)"/>'
    '<ellipse cx="82" cy="126" rx="43" ry="13" fill="url(#otm-mark-rim)"/>'
    '<image href="' + LOGO_MARK + '" x="28" y="28" width="108" height="108" transform="translate(0 164) scale(1 -1)" clip-path="url(#otm-mark-reflection-clip)" opacity=".14" filter="url(#otm-mark-reflection)"/>'
    '<image href="' + LOGO_MARK + '" x="28" y="28" width="108" height="108" preserveAspectRatio="xMidYMid meet" filter="url(#otm-mark-neural-glass)"/>'
    '<path class="otm-mark-sheen" d="M35 48c18-13 43-17 67-12l-40 65c-9 14-20 22-32 26z" fill="#fff" fill-opacity=".42" filter="url(#otm-mark-glow)"/>'
    '<path class="otm-mark-sheen-b" d="M89 30c15 2 31 9 45 21l-26 44c-3-20-9-43-19-65z" fill="url(#otm-mark-glass-sheen)" filter="url(#otm-mark-glow)"/>'
    '<path d="M28 28h108v108H28z" fill="none" stroke="#e6fbff" stroke-opacity=".22" stroke-width="1.3" filter="url(#otm-mark-bevel)"/>'
    '<rect x="28.8" y="28.8" width="106.4" height="106.4" rx="27.5" fill="none" stroke="#59E1FF" stroke-opacity=".35" stroke-width=".7"/>'
    '<path d="M34 39c11-8 25-12 39-14" fill="none" stroke="#fff" stroke-opacity=".18" stroke-width="2" stroke-linecap="round"/>'
    '</g>'
    '<g class="otm-orbit-a" mask="url(#otm-mark-orbit-front)">'
    '<ellipse class="otm-mark-orbit-trace" cx="82" cy="82" rx="78" ry="32" transform="rotate(-27 82 82)" fill="none" stroke="url(#otm-mark-cyan)" stroke-width="1.65"/>'
    '<path class="otm-mark-comet" d="M112 43c9 2 18 6 25 12" stroke="url(#otm-mark-comet-cyan)" stroke-width="3" filter="url(#otm-mark-reflection)"/>'
    '<circle class="otm-mark-orb-pulse" cx="151" cy="52" r="9" fill="url(#otm-mark-orb-cyan)" filter="url(#otm-mark-glow)"/>'
    '<circle class="otm-mark-orb-pulse" cx="151" cy="52" r="2.3" fill="#efffff"/>'
    '</g>'
    '<g class="otm-orbit-b" mask="url(#otm-mark-orbit-front)">'
    '<ellipse class="otm-mark-orbit-trace-violet" cx="82" cy="82" rx="73" ry="49" transform="rotate(37 82 82)" fill="none" stroke="#9B7BFF" stroke-opacity=".76" stroke-width="1.2" stroke-dasharray="2 4"/>'
    '<path class="otm-mark-comet otm-mark-comet-violet" d="M23 104c7-5 13-10 17-18" stroke="url(#otm-mark-comet-violet)" stroke-width="2.5" filter="url(#otm-mark-reflection)"/>'
    '<circle class="otm-mark-orb-pulse" cx="18" cy="112" r="6.5" fill="url(#otm-mark-orb-violet)" filter="url(#otm-mark-glow)"/>'
    '<circle class="otm-mark-orb-pulse" cx="18" cy="112" r="1.7" fill="#f7f1ff"/>'
    '</g>'
    '<g filter="url(#otm-mark-glow)">'
    '<circle class="otm-mark-dust" cx="12" cy="69" r=".9" fill="#59E1FF"/>'
    '<circle class="otm-mark-dust otm-mark-dust-2" cx="151" cy="91" r=".7" fill="#c9faff"/>'
    '<circle class="otm-mark-dust otm-mark-dust-3" cx="45" cy="13" r=".8" fill="#9B7BFF"/>'
    '<circle class="otm-mark-dust otm-mark-dust-4" cx="124" cy="18" r=".65" fill="#59E1FF"/>'
    '<circle class="otm-mark-dust otm-mark-dust-5" cx="19" cy="139" r=".75" fill="#9B7BFF"/>'
    '<circle class="otm-mark-dust otm-mark-dust-6" cx="147" cy="132" r="1" fill="#F2A93B"/>'
    '</g>'
    '<rect x="28.7" y="28.7" width="106.6" height="106.6" rx="27.5" fill="none" stroke="#59E1FF" stroke-opacity=".35" stroke-width="1.25" transform="translate(-.35 0)"/>'
    '<rect x="28.7" y="28.7" width="106.6" height="106.6" rx="27.5" fill="none" stroke="#9B7BFF" stroke-opacity=".28" stroke-width="1.1" transform="translate(.35 0)"/>'
    '<rect x="28.7" y="28.7" width="106.6" height="106.6" rx="27.5" fill="none" stroke="url(#otm-mark-cyan)" stroke-opacity=".78" stroke-width="1.2"/>'
    '</svg>'
)
# SCELTA: il PNG originale resta il soggetto centrale del mark; il lockup completo usa lo stesso badge SVG.
LOGO_FULL = (
    "data:image/svg+xml,"
    + urllib.parse.quote(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 164">'
        '<defs><linearGradient id="otm-mark-full-gold" x1="0" y1="0" x2="1" y2="1">'
        '<stop stop-color="#FFF44F"/><stop offset=".48" stop-color="#FFD21C"/><stop offset="1" stop-color="#F2A93B"/>'
        '</linearGradient><filter id="otm-mark-full-depth" x="-10%" y="-30%" width="125%" height="170%">'
        '<feGaussianBlur in="SourceAlpha" stdDeviation="1.2" result="otm-mark-full-edge"/>'
        '<feOffset in="otm-mark-full-edge" dy="1.5" result="otm-mark-full-bevel"/>'
        '<feColorMatrix in="otm-mark-full-bevel" type="matrix" values="0 0 0 0 .08 0 0 0 0 .1 0 0 0 0 .16 0 0 0 .85 0" result="otm-mark-full-shadow"/>'
        '<feSpecularLighting in="SourceAlpha" surfaceScale="2" specularConstant=".72" specularExponent="18" lighting-color="#fff7d1" result="otm-mark-full-specular">'
        '<feDistantLight azimuth="225" elevation="55"/></feSpecularLighting>'
        '<feComposite in="otm-mark-full-specular" in2="SourceAlpha" operator="in" result="otm-mark-full-highlight"/>'
        '<feMerge><feMergeNode in="otm-mark-full-shadow"/><feMergeNode in="SourceGraphic"/><feMergeNode in="otm-mark-full-highlight"/></feMerge></filter>'
        '<linearGradient id="otm-mark-full-glass" x1="0" y1="0" x2="0" y2="1">'
        '<stop stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
        '</linearGradient></defs>'
        + OTM_MARK_SVG.replace('width="32" height="32"', 'x="0" y="0" width="164" height="164"')
        + '<text x="186" y="88" font-family="Inter,Arial,sans-serif" font-size="59" font-weight="900" letter-spacing="-2" fill="#F5F7FB" filter="url(#otm-mark-full-depth)">OTM'
        '<tspan fill="url(#otm-mark-full-gold)">FLOW</tspan></text>'
        '<rect x="185" y="101" width="425" height="9" fill="url(#otm-mark-full-glass)" opacity=".08" style="mix-blend-mode:screen"/>'
        '<text x="190" y="119" font-family="Inter,Arial,sans-serif" font-size="11" font-weight="600" letter-spacing="4.6" fill="#8FA9C7">OUTTHINK THE MARKET</text>'
        '</svg>',
        safe="/=:#;(),'",
    )
)
FAVICON_URL = "data:image/svg+xml," + urllib.parse.quote(OTM_MARK_SVG)


def _otm_icon():
    """Restituisce i byte PNG del mark OTM per page_icon."""
    return base64.b64decode(LOGO_MARK.split(",", 1)[1])

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=_otm_icon(),
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [data-testid="stAppViewContainer"] {{ background:{INK}; }}
[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display:none; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility:hidden; }}
.block-container {{ padding:0.25rem 0.4rem 0 0.4rem !important; max-width:100% !important; }}
[data-testid="stMainBlockContainer"] {{ padding-top:0.25rem !important; }}
[data-testid="stVerticalBlock"] {{ gap:0 !important; }}
[data-testid="stElementContainer"]:has(iframe[height="0"]) {{ display:none; }}
.otm-brand {{ display:flex; flex-direction:column; align-items:center; gap:16px; }}
.otm-brand svg {{ width:208px; height:208px; filter:drop-shadow(0 0 22px rgba(29,184,225,.32)) drop-shadow(0 0 24px rgba(242,190,46,.18)); }}
.otm-brand svg .otm-orbit-a {{ transform-origin:82px 82px; animation:otm-spin 14s linear infinite; }}
.otm-brand svg .otm-orbit-b {{ transform-origin:82px 82px; animation:otm-spinr 22s linear infinite; }}
@keyframes otm-spin {{ to {{ transform:rotate(360deg); }} }}
@keyframes otm-spinr {{ to {{ transform:rotate(-360deg); }} }}
@media (prefers-reduced-motion:reduce) {{ .otm-brand svg .otm-orbit-a,.otm-brand svg .otm-orbit-b {{ animation:none; }} }}
.otm-brand b {{ font-family:'Inter',sans-serif; font-weight:800; font-size:1.9rem;
               letter-spacing:.055em; color:#F5F7FB; }}
.otm-brand b span {{ background:linear-gradient(100deg,#FFF44F,#FFD21C 68%,#F2A93B); -webkit-background-clip:text;
                    background-clip:text; color:transparent; }}
.otm-brand small {{ font-family:'Inter',sans-serif; font-size:.72rem; letter-spacing:.42em;
                   color:#8FA9C7; margin-top:-8px; }}
@media (max-width:640px) {{ .otm-brand svg {{ width:176px; height:176px; }} }}
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
    "footprint": [(
        "#kiyo-fp-head{display:flex;align-items:center;gap:0;padding:11px 16px;",
        "#kiyo-fp-head{display:flex;align-items:center;gap:0;height:43px;min-height:43px;"
        "flex:0 0 43px;box-sizing:border-box;padding:6px 14px;",
    )],
}


def _inject(html: str, nav_js: str, name: str = "") -> str:
    # dentro l'iframe srcdoc location.hostname e' vuoto: usiamo quello della pagina principale
    html = html.replace("window.location.hostname", "window.__OTM_HOST")
    html = html.replace("location.hostname", "window.__OTM_HOST")
    for vecchio, nuovo in _PATCHES.get(name, []):
        if vecchio in html:
            html = html.replace(vecchio, nuovo)
        elif (name != "footprint" or not re.search(
                r"#kiyo-fp-head\{display:flex;align-items:center;gap:0;height:43px;min-height:43px;",
                html)):
            st.warning(tr("Correzione non applicata alla vista {nome}: riga non trovata.", nome=name))
    if name == "footprint":
        html, pulsanti = re.subn(
            r"""(?m)^[ \t]*'<button id="kiyo-fp-(?:refresh|close)"[^'\r\n]*</button>' \+[ \t]*(?:\r?\n|$)""",
            "",
            html,
        )
        html, listener = re.subn(
            r"""(?m)^[ \t]*head\.querySelector\('#kiyo-fp-(?:refresh|close)'\)\.addEventListener\('click', (?:refresh|close)\);[ \t]*""",
            "",
            html,
        )
        if pulsanti not in (0, 2) or listener not in (0, 2):
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
def _build_shell(_key: float, local: bool, shell_ver: str) -> str:
    # shell_ver = hash di SHELL_HTML + logo: fa parte della chiave della cache.
    _ = shell_ver
    shell_mark = OTM_MARK_SVG.replace("otm-mark", "otm-shell-mark")
    loader_mark = OTM_MARK_SVG.replace("otm-mark", "otm-loader-mark")
    return (SHELL_HTML
            .replace("%%MARK%%", shell_mark, 1)
            .replace("%%MARK%%", loader_mark, 1)
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
    lang = tz.codice_valido(lang) or "en"
    return html.replace("%%LANG%%", lang, 1).replace("%%I18N%%", _i18n_shell(), 1)


# ── Shell lato browser ──────────────────────────────────────────────────────
SHELL_HTML = r"""<!doctype html>
<html lang="%%LANG%%"><head><meta charset="utf-8">
<script>var OTM_I18N = %%I18N%%;</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root{--ink:#0B1220;--surf:#111C2E;--elev:#16233A;--teal:#3DD4C8;--sky:#6FA8FF;--muted:#8394B0;--dim:#56657F;
    --light:#E8EEF9;--amber:#F2A93B;--red:#FF5C5C;--green:#2EE6A6;--hh:50px;
    --glass:rgba(255,255,255,.035);--line:rgba(255,255,255,.07);--line-hi:rgba(157,183,220,.16)}
  *{box-sizing:border-box}
  html,body{height:100%;margin:0;background:#050a12;overflow:hidden;color:var(--light);font-family:'Inter',sans-serif}
  #shell{display:flex;flex-direction:column;height:100%}

  /* ── barra ─────────────────────────────────────────────────────────── */
  header{position:relative;isolation:isolate;overflow:hidden;height:var(--hh);flex:0 0 var(--hh);
    display:flex;align-items:center;gap:10px;padding:0 12px;
    background:
      radial-gradient(560px 120px at 2% -30%,rgba(61,212,200,.17),transparent 66%),
      radial-gradient(500px 110px at 96% -30%,rgba(111,168,255,.12),transparent 68%),
      linear-gradient(180deg,#121f33 0%,#0a111e 100%);
    border-bottom:1px solid rgba(111,168,255,.22);
    box-shadow:0 7px 24px rgba(0,0,0,.28),inset 0 1px 0 rgba(255,255,255,.055),inset 0 -1px 0 rgba(0,0,0,.28)}
  header::before{content:'';position:absolute;inset:0;z-index:-1;pointer-events:none;
    background-image:linear-gradient(rgba(255,255,255,.032) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.032) 1px,transparent 1px);
    background-size:18px 18px;background-position:-1px -1px;
    -webkit-mask-image:linear-gradient(90deg,#000 0,rgba(0,0,0,.25) 22%,transparent 45%,transparent 60%,rgba(0,0,0,.4) 100%);
            mask-image:linear-gradient(90deg,#000 0,rgba(0,0,0,.25) 22%,transparent 45%,transparent 60%,rgba(0,0,0,.4) 100%)}
  /* linea di "sweep": una passata di liquidita' che attraversa la barra */
  header::after{content:'';position:absolute;left:0;bottom:-1px;width:22%;height:1px;pointer-events:none;
    background:linear-gradient(90deg,transparent,var(--teal) 55%,var(--sky) 80%,transparent);
    box-shadow:0 0 9px 1px rgba(61,212,200,.36);transform:translateX(-110%);animation:sweep 9s cubic-bezier(.65,0,.35,1) infinite}
  @keyframes sweep{0%{transform:translateX(-110%)}60%,100%{transform:translateX(370%)}}

  .brand{position:relative;display:flex;align-items:center;gap:10px;flex:0 0 auto;text-decoration:none;color:inherit;user-select:none;padding:0 7px 0 2px;
    border-radius:12px;transition:background .2s ease,box-shadow .2s ease}
  .brand:hover{background:linear-gradient(100deg,rgba(61,212,200,.075),rgba(111,168,255,.025));box-shadow:inset 0 0 0 1px rgba(143,220,239,.09)}
  .brand svg{width:40px;height:40px;display:block;overflow:visible;
    filter:drop-shadow(0 2px 5px rgba(0,0,0,.52)) drop-shadow(0 0 7px rgba(61,212,200,.16));
    transition:transform .32s cubic-bezier(.2,.8,.2,1),filter .32s ease}
  .brand:hover svg{transform:translateY(-1px) scale(1.055);filter:drop-shadow(0 3px 7px rgba(0,0,0,.45)) drop-shadow(0 0 11px rgba(61,212,200,.3))}
  .brand svg .otm-orbit-a{transform-origin:82px 82px;animation:otm-spin 14s linear infinite}
  .brand svg .otm-orbit-b{transform-origin:82px 82px;animation:otm-spinr 22s linear infinite}
  @keyframes otm-spin{to{transform:rotate(360deg)}}
  @keyframes otm-spinr{to{transform:rotate(-360deg)}}
  .brand .otm-dot{transform-origin:24.5px 7.5px;animation:breakout 3.2s ease-in-out infinite}
  @keyframes breakout{0%,100%{transform:translate(0,0);opacity:1}45%{transform:translate(1.1px,-1.1px);opacity:1}55%{opacity:.55}}
  .wm{display:flex;flex-direction:column;line-height:1;gap:1px}
  .wm b{font:800 15px/1 'Inter',sans-serif;letter-spacing:.075em;color:#F5F7FB;text-shadow:0 1px 8px rgba(111,168,255,.16)}
  .wm b span{background:linear-gradient(100deg,#FFF978 0%,#FFD21C 52%,#F2A93B 100%);-webkit-background-clip:text;background-clip:text;color:transparent;
    filter:drop-shadow(0 1px 5px rgba(242,169,59,.2))}
  .wm small{margin-top:4px;font:600 7px/1 'Inter',sans-serif;letter-spacing:.34em;color:#91a9c6;white-space:nowrap}
  .sep{width:1px;height:30px;background:linear-gradient(180deg,transparent,rgba(123,161,200,.3) 22%,rgba(123,161,200,.3) 78%,transparent);flex:0 0 1px}

  nav{position:relative;display:flex;gap:2px;background:linear-gradient(180deg,rgba(4,10,20,.74),rgba(3,9,18,.56));
    border:1px solid rgba(157,183,220,.2);border-radius:12px;padding:3px;
    box-shadow:inset 0 1px 0 rgba(255,255,255,.055),inset 0 -2px 5px rgba(0,0,0,.22),0 3px 10px rgba(0,0,0,.16);
    flex:0 0 auto;transition:border-color .2s ease,box-shadow .2s ease}
  nav:hover{border-color:rgba(157,183,220,.3);box-shadow:inset 0 1px 0 rgba(255,255,255,.065),inset 0 -2px 5px rgba(0,0,0,.22),0 4px 14px rgba(0,0,0,.2)}
  nav button{all:unset;cursor:pointer;position:relative;z-index:1;padding:5px 12px;border-radius:8px;
    font:700 10px/18px 'Inter',sans-serif;letter-spacing:.085em;color:#8e9db4;transition:color .18s,background .18s,text-shadow .18s;white-space:nowrap}
  nav button:hover:not(.on){color:#f2f7ff;background:rgba(255,255,255,.055)}
  nav button:focus-visible{outline:1px solid rgba(61,212,200,.92);outline-offset:2px;box-shadow:0 0 0 4px rgba(61,212,200,.1)}
  nav button.on{color:#04111b;text-shadow:0 1px 0 rgba(255,255,255,.36),0 0 12px rgba(255,255,255,.24)}
  nav button kbd{font:700 8px/15px 'Inter',sans-serif;margin-left:8px;padding:0 4px;border:1px solid rgba(225,244,255,.12);border-radius:4px;
    color:rgba(225,244,255,.82);background:rgba(4,15,27,.2);opacity:.88}
  nav button .ld{display:inline-block;width:5px;height:5px;border-radius:50%;margin-left:6px;vertical-align:1px;background:currentColor;opacity:0;transition:opacity .2s}
  nav button.loading .ld{opacity:.7;animation:blink .8s infinite}
  @keyframes blink{50%{opacity:.15}}
  nav .ink{position:absolute;top:3px;bottom:3px;left:0;border-radius:8px;
    background:linear-gradient(112deg,#42d9cc 0%,#55ddd2 37%,#59cfe3 69%,#69b9fa 100%);
    box-shadow:0 3px 12px rgba(61,212,200,.25),0 0 20px rgba(111,168,255,.12),inset 0 1px 0 rgba(255,255,255,.58),inset 0 -1px 0 rgba(5,33,53,.12);
    transition:transform .24s cubic-bezier(.2,.8,.2,1),width .24s cubic-bezier(.2,.8,.2,1)}
  nav.noanim .ink{transition:none}

  /* ── ticker BTC: prezzo, 24h, flusso aggressori 60 s ── */
  .tick{display:flex;align-items:center;gap:11px;height:36px;padding:0 12px;border-radius:11px;
    background:linear-gradient(180deg,rgba(20,35,56,.92),rgba(12,21,35,.9));border:1px solid rgba(143,169,205,.16);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.055),0 4px 12px rgba(0,0,0,.12);white-space:nowrap;cursor:default;flex:0 1 auto}
  .sym{display:flex;align-items:center;gap:7px;font:800 10.5px 'Inter',sans-serif;letter-spacing:.07em;color:var(--light)}
  .sym em{font:600 8px 'Inter',sans-serif;font-style:normal;letter-spacing:.06em;color:var(--dim);
    padding:1px 4px;border:1px solid var(--line);border-radius:3px}
  .tdot{width:7px;height:7px;border-radius:50%;background:var(--dim);box-shadow:0 0 0 3px rgba(131,148,176,.09)}
  .tdot.on{background:var(--green);box-shadow:0 0 0 3px rgba(46,230,166,.1),0 0 9px rgba(46,230,166,.5);animation:pulse 1.8s infinite}
  .px{font:700 14px 'Inter',sans-serif;font-variant-numeric:tabular-nums;letter-spacing:-.025em;color:var(--light);
    min-width:82px;text-align:right;transition:color .5s ease,text-shadow .5s ease}
  .px.up{color:var(--green);text-shadow:0 0 12px rgba(46,230,166,.45);transition:none}
  .px.dn{color:var(--red);text-shadow:0 0 12px rgba(255,92,92,.45);transition:none}
  .chg{font:700 10px 'Inter',sans-serif;font-variant-numeric:tabular-nums;color:var(--muted);
    padding:4px 7px;border-radius:6px;background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.035)}
  .chg.up{color:var(--green);background:rgba(46,230,166,.085);border-color:rgba(46,230,166,.1)}
  .chg.dn{color:var(--red);background:rgba(255,92,92,.085);border-color:rgba(255,92,92,.1)}
  .flow{display:flex;align-items:center;gap:8px;padding-left:12px;border-left:1px solid var(--line-hi)}
  .fl{font:700 8px 'Inter',sans-serif;letter-spacing:.12em;color:#71829d}
  .bar{position:relative;width:70px;height:6px;border-radius:4px;overflow:hidden;background:rgba(255,92,92,.7);
    box-shadow:0 0 10px rgba(0,0,0,.4) inset}
  .bar i{position:absolute;left:0;top:0;bottom:0;width:50%;background:linear-gradient(90deg,#1fc58d,var(--green));
    transition:width .45s cubic-bezier(.2,.8,.2,1);box-shadow:2px 0 6px rgba(46,230,166,.6)}
  .bar::after{content:'';position:absolute;left:50%;top:-1px;bottom:-1px;width:1px;background:rgba(255,255,255,.55)}
  .bar.idle{background:rgba(255,255,255,.08)} .bar.idle i{opacity:0}
  .fd{font:700 10px 'Inter',sans-serif;font-variant-numeric:tabular-nums;min-width:50px;color:var(--muted)}
  .fd.up{color:var(--green)} .fd.dn{color:var(--red)}

  .sp{flex:1;min-width:0}
  header>*:not(.sp){flex-shrink:0}

  /* ── sessione USA con avanzamento ── */
  .market-time{display:flex;align-items:center;gap:12px;flex:0 0 auto}
  .clk{display:flex;flex-direction:column;align-items:flex-end;line-height:1;cursor:default;padding:0 3px}
  .clk small{font:700 7px 'Inter',sans-serif;letter-spacing:.22em;color:#71829d}
  .clk b{margin-top:4px;font:700 12px 'Inter',sans-serif;font-variant-numeric:tabular-nums;letter-spacing:.025em;color:var(--light)}
  .sess{position:relative;display:flex;align-items:center;gap:7px;height:34px;padding:0 10px;border-radius:10px;
    border:1px solid var(--line-hi);background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.012));
    font:600 9px 'Inter',sans-serif;color:var(--muted);white-space:nowrap;overflow:hidden;cursor:default}
  .sess-tag{font:700 8px 'Inter',sans-serif;letter-spacing:.11em;color:#8fa2bf;padding-right:6px;border-right:1px solid var(--line-hi)}
  .sess b{font:800 9px 'Inter',sans-serif;letter-spacing:.065em;color:var(--light)}
  .sess .nx{font:600 9px 'Inter',sans-serif;color:#91a0b7}
  .sess .tr{position:absolute;left:0;right:0;bottom:0;height:2px;background:rgba(255,255,255,.04)}
  .sess .tr i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--teal),var(--sky));transition:width 1s linear}
  .sess.open{border-color:rgba(61,212,200,.2);background:linear-gradient(180deg,rgba(61,212,200,.075),rgba(61,212,200,.025))}
  .sess.pre .tr i{background:linear-gradient(90deg,#c9801f,var(--amber))}
  .sess.pre{border-color:rgba(242,169,59,.22);background:linear-gradient(180deg,rgba(242,169,59,.075),rgba(242,169,59,.025))}
  .dot{width:6px;height:6px;border-radius:50%;background:var(--dim)}
  .dot.open{background:var(--teal);animation:pulse 1.8s infinite}
  .dot.pre{background:var(--amber)}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(61,212,200,.55)}70%{box-shadow:0 0 0 6px rgba(61,212,200,0)}100%{box-shadow:0 0 0 0 rgba(61,212,200,0)}}

  .pill{display:flex;align-items:center;gap:7px;font:700 8px 'Inter',sans-serif;letter-spacing:.09em;padding:6px 9px;
    border-radius:7px;border:1px solid;white-space:nowrap;cursor:help}
  .pill::before{content:'';width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor;flex:0 0 6px}
  .pill.live{color:var(--red);border-color:rgba(255,92,92,.4);background:rgba(255,92,92,.08)}
  .pill.live::before{animation:blink 1.2s infinite}
  .pill.safe{color:var(--teal);border-color:rgba(61,212,200,.35);background:rgba(61,212,200,.07)}

  .lang{display:flex;background:rgba(3,9,18,.38);border:1px solid var(--line-hi);border-radius:8px;padding:2px}
  .lang button{all:unset;cursor:pointer;padding:3px 7px;border-radius:5px;color:var(--muted);
    font:700 9px/16px 'Inter',sans-serif;letter-spacing:.04em;transition:color .15s,background .15s}
  .lang button:hover:not(.on){color:var(--light)}
  .lang button:focus-visible{outline:1px solid var(--teal);outline-offset:1px}
  .lang button.on{color:#04111b;background:linear-gradient(135deg,var(--teal),#59b4f2);box-shadow:0 1px 7px rgba(61,212,200,.2)}
  .ib{all:unset;cursor:pointer;width:32px;height:32px;border-radius:9px;display:grid;place-items:center;color:#8b9ab1;
    border:1px solid var(--line-hi);background:rgba(255,255,255,.025);transition:color .15s,background .15s,border-color .15s,transform .15s}
  .ib:hover{color:var(--teal);background:rgba(61,212,200,.075);border-color:rgba(61,212,200,.3);transform:translateY(-1px)}
  .ib:focus-visible{outline:1px solid var(--teal);outline-offset:1px}
  .ib svg{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}

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

  @media (max-width:1580px){.flow{display:none}}
  @media (max-width:1340px){.tick{display:none}.wm small{display:none}header{gap:8px}}
  @media (max-width:980px){.market-time{display:none}}
  @media (max-width:760px){header{gap:7px;padding:0 8px}.wm,.sep{display:none}nav button{padding:4px 8px}nav button kbd{display:none}.tick{gap:7px;padding:0 8px}.flow{gap:5px;padding-left:8px}.bar{width:48px}}
  @media (max-width:520px){.tick{height:32px;gap:6px}.sym em{display:none}.px{min-width:66px;font-size:12px}.chg{font-size:9px;padding:3px 5px}nav button{font-size:9px;padding:3px 6px}.ib{width:29px;height:29px}}
  @media (prefers-reduced-motion:reduce){header::after,.brand .otm-dot,.brand svg .otm-orbit-a,.brand svg .otm-orbit-b,.tdot.on,.dot.open{animation:none}}
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
    <div class="tick" id="tick">
      <span class="sym"><i class="tdot" id="tlive"></i>BTC<em>PERP</em></span>
      <b class="px" id="tpx">—</b>
      <span class="chg" id="tch">—</span>
      <span class="flow" id="tflow"><span class="fl" data-i18n="FLUSSO 60s"></span><span class="bar idle" id="tbar"><i id="tbuy"></i></span><span class="fd" id="tfd">—</span></span>
    </div>
    <div class="sp"></div>
    <div class="market-time">
      <div class="clk" data-i18n-title="Ora di Roma"><small data-i18n="ROMA"></small><b id="clock">--:--:--</b></div>
      <div class="sess" id="sess" role="status" aria-live="off" data-i18n-title="Sessione cash USA 09:30–16:00 New York (le VA della Footprint usano questa sessione)">
        <span class="sess-tag">USA</span><span class="dot" id="sdot"></span><b id="sst"></b><span class="nx" id="snext"></span><span class="tr"><i id="sbar"></i></span>
      </div>
    </div>
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
      dot.className = 'dot open'; box.className = 'sess open';
      st.textContent = t("APERTA"); nx.textContent = t("chiude tra {d}", { d: dur(CLOSE - mins) });
      bar.style.width = ((mins - OPEN) / (CLOSE - OPEN) * 100).toFixed(2) + '%';
      return;
    }
    var until;
    if (weekday && mins < OPEN) until = OPEN - mins;
    else { var days = wd === 5 ? 3 : (wd === 6 ? 2 : 1); until = days * 1440 - mins + OPEN; }
    var pre = weekday && mins >= PRE && mins < OPEN;
    dot.className = 'dot' + (pre ? ' pre' : '');
    box.className = 'sess' + (pre ? ' pre' : '');
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
