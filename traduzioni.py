# -*- coding: utf-8 -*-
"""
traduzioni.py — interfaccia di ThinkCore in italiano, English ed español.

Come funziona (stile gettext, solo libreria standard):
  * L'italiano è la lingua sorgente: il testo italiano scritto nel codice È la chiave.
        tr("Genera turni")                                   → "Generate rota" in inglese
        tr("{n} h sotto il fabbisogno", n=12)                → segnaposto con nome
        trn("{n} violazione", "{n} violazioni", n)           → singolare / plurale
        trp("giorno", "Mar")                                 → stesso testo, significati diversi
    Una traduzione mancante (o vuota) mostra l'italiano: l'app non si rompe mai e non mostra
    mai chiavi tecniche.
  * Cataloghi in locales/en.json e locales/es.json:
        {"_info": {...}, "messaggi": {"Genera turni": "Generate rota",
                                      "{n} violazione": {"one": "{n} violation", "other": "{n} violations"},
                                      "giorno::Mar": "Tue"}}
    Letti una volta per processo e riletti da soli se il file cambia (controllo al massimo
    ogni 2 s). Nessun eval/exec: solo json.loads.
  * Una lingua per sessione, letta da st.session_state a ogni chiamata. Mai una variabile
    globale: le sessioni contemporanee sono thread dello stesso processo e se la
    ruberebbero a vicenda.
  * Si parte in inglese. Cambia dal selettore IT · EN · ES
    (la scelta resta nell'indirizzo, ?lang=en, e sopravvive al ricaricamento della pagina)
    oppure, per un intero negozio, con [interfaccia] lingua = "es" nei Secrets dell'app.

Sicurezza:
  * codici lingua da un elenco chiuso: nessun percorso costruito da input esterni;
  * file con tetto di dimensione, JSON con chiavi duplicate segnalate;
  * una traduzione che non conserva ESATTAMENTE segnaposto e tag HTML del testo italiano
    viene scartata al caricamento (si mostra l'italiano): un catalogo sbagliato o manomesso
    non può rompere la formattazione né iniettare markup nelle pagine;
  * i segnaposto accettano solo nomi semplici ({n}, {h:.1f}, {v!r}): niente accesso ad
    attributi o indici ({x.__class__} resta testo), quindi nessuna fuga di dati interni.

Controllo completo dei cataloghi rispetto al codice: python controlla_traduzioni.py
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import threading
import time
import unicodedata
from types import MappingProxyType

__all__ = [
    "LINGUE", "BASE", "tr", "trn", "trp", "traduci", "traduci_n", "traduci_p",
    "lingua_corrente", "imposta_lingua", "selettore", "numero", "giorni_brevi",
    "giorni_estesi", "mese", "etichette", "codice_valido", "Cataloghi", "lingua_forzata", "separatori",
]

LINGUE = {"it": "Italiano", "en": "English", "es": "Español"}   # ordine = ordine nel selettore
BASE = "it"                                                      # lingua del codice sorgente
CARTELLA_LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "locales")
SEP_CONTESTO = "::"
MAX_BYTE = 2 * 1024 * 1024
CHIAVE_SESSIONE = "_lingua"          # stato della sessione (non è un widget: sopravvive a st.stop)
CHIAVE_WIDGET = "tc_lingua"          # widget del selettore (classe CSS st-key-tc_lingua)
PARAMETRO_URL = "lang"
FORME_PLURALI = ("one", "other")

GIORNI_BREVI = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
GIORNI_ESTESI = ("Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica")
MESI = ("gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
        "settembre", "ottobre", "novembre", "dicembre")

_log = logging.getLogger("thinkcore.traduzioni")

_RE_SEGNAPOSTO = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?:!([rsa]))?(?::([^{}]*))?\}")
_RE_GRAFFE = re.compile(r"\{[^{}]*\}")
_RE_TAG = re.compile(r"<\s*/?\s*[A-Za-z][^<>]*>")
_SEPARATORI = {"it": (".", ","), "es": (".", ","), "en": (",", ".")}


# ────────────────────────────── utilità pure (testabili senza Streamlit) ──────────────────────────────

def codice_valido(codice):
    """Codice lingua normalizzato ('EN ' → 'en') se è tra quelli previsti, altrimenti None."""
    if not isinstance(codice, str):
        return None
    c = codice.strip().lower()
    return c if c in LINGUE else None


def _norm_tag(t):
    return re.sub(r"\s+", " ", t.strip())


def _firma(testo):
    """Segnaposto/graffe e tag HTML di un testo: una traduzione deve conservarli tutti."""
    return (frozenset(_RE_GRAFFE.findall(testo)),
            tuple(sorted(_norm_tag(t) for t in _RE_TAG.findall(testo))))


def _formatta(modello, valori):
    """Sostituisce SOLO i segnaposto con nome presenti in `valori`; il resto resta com'è
    (graffe di Plotly come %{y:.1f}, testo con parentesi graffe, segnaposto non passati)."""
    if not valori:
        return modello

    def sost(mo):
        nome, conv, spec = mo.group(1), mo.group(2), mo.group(3)
        if nome not in valori:
            return mo.group(0)
        v = valori[nome]
        if conv == "r":
            v = repr(v)
        elif conv == "s":
            v = str(v)
        elif conv == "a":
            v = ascii(v)
        try:
            return format(v, spec or "")
        except (ValueError, TypeError):
            return str(v)            # formato incompatibile: meglio il valore che un errore a video

    return _RE_SEGNAPOSTO.sub(sost, modello)


def separatori(lingua=None):
    """(migliaia, decimali) della lingua: ('.', ',') per it ed es, (',', '.') per en."""
    return _SEPARATORI.get(codice_valido(lingua) or lingua_corrente(), _SEPARATORI[BASE])


def numero(v, decimali=0, *, lingua=None):
    """Numero con i separatori della lingua: 1234.5 → '1.234,5' (it, es) o '1,234.5' (en)."""
    mig, dec = _SEPARATORI.get(codice_valido(lingua) or lingua_corrente(), _SEPARATORI[BASE])
    return f"{v:,.{int(decimali)}f}".translate(str.maketrans({",": mig, ".": dec}))


# ────────────────────────────── cataloghi ──────────────────────────────

class Cataloghi:
    """Cataloghi JSON di una cartella, letti una volta e riletti solo se il file cambia.
    Sicuro tra thread: la lettura avviene sotto lock, il dizionario pubblicato è immutabile."""

    def __init__(self, cartella, verifica_ogni_s=2.0, max_byte=MAX_BYTE):
        self.cartella = os.path.abspath(cartella)
        self._verifica_ogni_s = float(verifica_ogni_s)
        self._max_byte = int(max_byte)
        self._lock = threading.Lock()
        self._cache = {}             # codice → (firma_file, voci, problemi, ultimo_controllo)

    def percorso(self, codice):
        c = codice_valido(codice)
        if c is None or c == BASE:
            return None
        p = os.path.join(self.cartella, c + ".json")
        # difesa in profondità: il file deve stare davvero nella cartella (niente link fuori)
        if os.path.dirname(os.path.realpath(p)) != os.path.realpath(self.cartella):
            return None
        return p

    def voci(self, codice):
        e = self._voce_cache(codice)
        return e[1] if e else MappingProxyType({})

    def problemi(self, codice):
        e = self._voce_cache(codice)
        return list(e[2]) if e else []

    def _voce_cache(self, codice):
        p = self.percorso(codice)
        if p is None:
            return None
        ora = time.monotonic()
        e = self._cache.get(codice)
        if e is not None and ora - e[3] < self._verifica_ogni_s:
            return e
        with self._lock:
            e = self._cache.get(codice)
            if e is not None and ora - e[3] < self._verifica_ogni_s:
                return e
            try:
                s = os.stat(p)
                firma = (s.st_mtime_ns, s.st_size)
            except OSError:
                firma = None
            if e is not None and e[0] == firma:
                e = (e[0], e[1], e[2], ora)
            else:
                voci, problemi = self._carica(p, firma)
                for pr in problemi:
                    _log.warning("traduzioni %s: %s", codice, pr)
                e = (firma, voci, tuple(problemi), ora)
            self._cache[codice] = e
            return e

    def _carica(self, percorso, firma):
        vuoto = MappingProxyType({})
        if firma is None:
            return vuoto, [f"file mancante: {os.path.basename(percorso)} (si mostra l'italiano)"]
        if firma[1] > self._max_byte:
            return vuoto, [f"file troppo grande ({firma[1]} byte, massimo {self._max_byte})"]
        problemi = []

        def coppie(pairs):
            visti = {}
            for k, v in pairs:
                if k in visti:
                    problemi.append(f"chiave duplicata: {k!r} (vale l'ultima)")
                visti[k] = v
            return visti

        try:
            with open(percorso, "rb") as f:
                grezzo = f.read(self._max_byte + 1)
            if len(grezzo) > self._max_byte:
                return vuoto, [f"file troppo grande (oltre {self._max_byte} byte)"]
            dati = json.loads(grezzo.decode("utf-8"), object_pairs_hook=coppie)
        except (OSError, UnicodeDecodeError, ValueError) as ex:
            return vuoto, [f"JSON non valido: {ex}"]
        messaggi = dati.get("messaggi") if isinstance(dati, dict) else None
        if not isinstance(messaggi, dict):
            return vuoto, problemi + ["manca l'oggetto \"messaggi\""]
        voci = {}
        for k, v in messaggi.items():
            k_nfc = unicodedata.normalize("NFC", k)
            esito = self._valida(k_nfc, v)
            if esito is None:
                voci[k_nfc] = v if isinstance(v, str) else MappingProxyType(dict(v))
            elif esito:
                problemi.append(f"{k!r}: {esito}")
        return MappingProxyType(voci), problemi

    @staticmethod
    def _valida(chiave, valore):
        """None = voce valida; '' = voce vuota (non tradotta, si ignora); altro = motivo dello scarto."""
        graffe, tag = _firma(chiave)
        if isinstance(valore, str):
            if not valore:
                return ""
            g2, t2 = _firma(valore)
            if g2 != graffe:
                return "segnaposto diversi dall'italiano: voce scartata"
            if t2 != tag:
                return "tag HTML diversi dall'italiano: voce scartata"
            return None
        if isinstance(valore, dict):
            if set(valore) != set(FORME_PLURALI) or not all(isinstance(valore[f], str) for f in FORME_PLURALI):
                return "plurale: servono esattamente le forme \"one\" e \"other\""
            if not all(valore[f] for f in FORME_PLURALI):
                return ""
            ammesse = graffe | {"{n}"}
            for f in FORME_PLURALI:
                g2, t2 = _firma(valore[f])
                if not g2 <= ammesse:
                    return f"plurale \"{f}\": segnaposto diversi dall'italiano: voce scartata"
                if t2 != tag:
                    return f"plurale \"{f}\": tag HTML diversi dall'italiano: voce scartata"
            return None
        return "il valore deve essere un testo (o un plurale one/other): voce scartata"


_CATALOGHI = Cataloghi(CARTELLA_LOCALES)


def _cerca(lingua, chiave, cataloghi):
    c = codice_valido(lingua)
    if c is None or c == BASE:
        return None
    voci = (cataloghi or _CATALOGHI).voci(c)
    v = voci.get(chiave)
    if v is None and not unicodedata.is_normalized("NFC", chiave):
        v = voci.get(unicodedata.normalize("NFC", chiave))
    return v


# ────────────────────────────── traduzione con lingua esplicita ──────────────────────────────

def traduci(lingua, testo, /, *, _cataloghi=None, **valori):
    """Testo nella lingua indicata (l'italiano se manca la traduzione), con i segnaposto riempiti."""
    voce = _cerca(lingua, testo, _cataloghi)
    return _formatta(voce if isinstance(voce, str) and voce else testo, valori)


def traduci_n(lingua, singolare, plurale, n, /, *, _cataloghi=None, **valori):
    """Singolare o plurale secondo n (it, en, es: singolare solo per 1). {n} è sempre disponibile."""
    valori.setdefault("n", n)
    try:
        uno = float(n) == 1.0
    except (TypeError, ValueError):
        uno = False
    forma = FORME_PLURALI[0] if uno else FORME_PLURALI[1]
    voce = _cerca(lingua, singolare, _cataloghi)
    modello = voce.get(forma) if isinstance(voce, MappingProxyType) else None
    return _formatta(modello or (singolare if uno else plurale), valori)


def traduci_p(lingua, contesto, testo, /, *, _cataloghi=None, **valori):
    """Come traduci, per un testo che cambia significato col contesto (es. 'Mar' = martedì)."""
    voce = _cerca(lingua, f"{contesto}{SEP_CONTESTO}{testo}", _cataloghi)
    return _formatta(voce if isinstance(voce, str) and voce else testo, valori)


def giorni_brevi(lingua=None):
    lg = lingua or lingua_corrente()
    return [traduci_p(lg, "giorno", g) for g in GIORNI_BREVI]


def giorni_estesi(lingua=None):
    lg = lingua or lingua_corrente()
    return [traduci(lg, g) for g in GIORNI_ESTESI]


def mese(i, lingua=None):
    """Nome del mese i (1-12) nella lingua corrente."""
    return traduci_p(lingua or lingua_corrente(), "mese", MESI[int(i) - 1])


# ────────────────────────────── lingua della sessione (Streamlit) ──────────────────────────────

def _st():
    """Il modulo streamlit, solo dentro l'esecuzione di uno script (altrimenti None: test,
    riga di comando, thread di servizio). Evita gli avvisi «missing ScriptRunContext»."""
    try:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return None
    try:
        try:
            ctx = get_script_run_ctx(suppress_warning=True)
        except TypeError:
            ctx = get_script_run_ctx()
        return st if ctx is not None else None
    except Exception:
        return None


def _lingua_iniziale(st):
    """?lang= nell'indirizzo → [interfaccia] lingua nei Secrets → inglese.
    La lingua del browser non conta: in assenza di una scelta esplicita si parte in inglese."""
    try:
        c = codice_valido(st.query_params.get(PARAMETRO_URL))
        if c:
            return c
    except Exception:
        pass
    try:
        sez = st.secrets.get("interfaccia") if hasattr(st.secrets, "get") else None
        c = codice_valido(sez.get("lingua")) if hasattr(sez, "get") else None
        if c:
            return c
    except Exception:
        pass                       # Secrets assenti o illeggibili: ci pensa la licenza a segnalarlo
    return "en"


_FORZATA = threading.local()


@contextlib.contextmanager
def lingua_forzata(codice):
    """Lingua fissata per il thread corrente dentro il blocco: PDF, riga di comando, test.
        with lingua_forzata("es"):
            pdf = genera_pdf(A)
    Le sessioni Streamlit sono thread: l'impostazione non tocca le altre sessioni. Un codice
    non previsto (o None) lascia la lingua com'è."""
    c = codice_valido(codice)
    if c is None:
        yield lingua_corrente()
        return
    prima = getattr(_FORZATA, "lingua", None)
    _FORZATA.lingua = c
    try:
        yield c
    finally:
        _FORZATA.lingua = prima


def lingua_corrente():
    """Lingua forzata nel thread (lingua_forzata), altrimenti quella della sessione Streamlit
    ('it' fuori da Streamlit)."""
    forzata = getattr(_FORZATA, "lingua", None)
    if forzata:
        return forzata
    st = _st()
    if st is None:
        return BASE
    try:
        ss = st.session_state
        c = codice_valido(ss.get(CHIAVE_SESSIONE))
        if c is None:
            c = _lingua_iniziale(st)
            ss[CHIAVE_SESSIONE] = c
        return c
    except Exception:
        return BASE


def imposta_lingua(codice):
    """Cambia la lingua della sessione e la scrive nell'indirizzo (?lang=): sopravvive al
    ricaricamento della pagina e si può salvare nei preferiti. False se il codice non è previsto."""
    c = codice_valido(codice)
    st = _st()
    if c is None or st is None:
        return False
    st.session_state[CHIAVE_SESSIONE] = c
    try:
        st.query_params[PARAMETRO_URL] = c
    except Exception:
        pass
    return True


def _al_cambio_selettore():
    st = _st()
    if st is None:
        return
    scelta = codice_valido(st.session_state.get(CHIAVE_WIDGET))
    if scelta:
        imposta_lingua(scelta)
    else:                          # selezione tolta (versioni senza required): resta la lingua attuale
        st.session_state[CHIAVE_WIDGET] = lingua_corrente()


def selettore(contenitore=None):
    """Selettore IT · EN · ES. Va disegnato prima di qualunque st.stop() della pagina, così
    c'è anche nelle schermate di accesso. Restituisce la lingua corrente."""
    st = _st()
    att = lingua_corrente()
    if st is None:
        return att
    if codice_valido(st.session_state.get(CHIAVE_WIDGET)) != att:
        st.session_state[CHIAVE_WIDGET] = att        # prima del widget: consentito da Streamlit
    dove = contenitore if contenitore is not None else st
    kw = dict(options=list(LINGUE), format_func=lambda c: c.upper(), key=CHIAVE_WIDGET,
              on_change=_al_cambio_selettore, label_visibility="collapsed",
              help=" · ".join(LINGUE.values()))
    try:
        dove.segmented_control(tr("Lingua"), required=True, **kw)
    except TypeError:                                # Streamlit senza `required`
        dove.segmented_control(tr("Lingua"), **kw)
    return lingua_corrente()


# ────────────────────────────── API per il codice dell'app ──────────────────────────────

def tr(testo, /, **valori):
    """Testo nella lingua della sessione. tr("Ore {h:.1f}", h=3.2)"""
    return traduci(lingua_corrente(), testo, **valori)


def trn(singolare, plurale, n, /, **valori):
    """Singolare/plurale nella lingua della sessione. trn("{n} riga", "{n} righe", n)"""
    return traduci_n(lingua_corrente(), singolare, plurale, n, **valori)


def trp(contesto, testo, /, **valori):
    """Testo con contesto nella lingua della sessione. trp("giorno", "Mar")"""
    return traduci_p(lingua_corrente(), contesto, testo, **valori)


def etichette(*testi):
    """Etichette di colonna tradotte per column_config: {nome interno: testo nella lingua}.
    Le colonne dei DataFrame restano in italiano: le usano stili, formati e logica."""
    lg = lingua_corrente()
    return {t: traduci(lg, t) for t in testi}
