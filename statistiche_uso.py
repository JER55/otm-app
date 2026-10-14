# -*- coding: utf-8 -*-
"""statistiche_uso.py — statistiche d'uso dell'app (streamlit-analytics2), senza cookie né JS.

Uso (in app.py):
    import statistiche_uso
    with statistiche_uso.traccia():
        ...codice dell'app...

Dashboard: aggiungi  ?analytics=on  all'URL dell'app e inserisci la password.

Configurazione (Streamlit Cloud → Settings → Secrets):
    [analytics]
    password = "una-password-lunga"          # per VEDERE la dashboard
    # facoltativo, per non perdere lo storico ai riavvii del container:
    token = "github_pat_..."                 # fine-grained, Contents: Read and write
    repo  = "JER55/thinkcore-state"          # un repo PRIVATO (va bene quello di ThinkCore)
    path  = "otmflow"                        # cartella dedicata a questa app

Il tracciamento è SEMPRE acceso, su ogni app, senza configurare nulla. La password
serve solo a VEDERE la dashboard: senza [analytics].password la dashboard resta chiusa
da una password casuale che nessuno conosce (la libreria, senza password, la
mostrerebbe a chiunque aggiunga ?analytics=on all'URL). I dati intanto si raccolgono.

Persistenza: il filesystem di Streamlit Cloud è effimero. Con token/repo in
[analytics] i due file (analytics.json = contatori, analytics.events.jsonl = eventi)
vengono salvati su quel repo al massimo ogni SYNC_MIN minuti e solo se cambiati: al
riavvio si perdono al più gli ultimi SYNC_MIN minuti. Senza token/repo i dati restano
solo in memoria e ripartono da zero a ogni riavvio dell'app.

Nota: i grafici vivono in un iframe JS, quindi qui si contano visite, visitatori,
durata e dispositivi, non i click dentro i grafici.

Privacy: niente IP salvati (solo un hash giornaliero), i testi liberi digitati
restano "<text>" (store_values=False). Qualunque errore qui dentro NON blocca l'app.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
import time
from contextlib import contextmanager

log = logging.getLogger("otm.statistiche")


def _cfg_analytics():
    try:
        import streamlit as st
        return st.secrets.get("analytics") or {}
    except Exception:
        return {}


def _github_cfg():
    cfg = _cfg_analytics()
    try:
        token, repo = cfg.get("token"), cfg.get("repo")
    except Exception:
        return None
    if not token or not repo:
        return None
    return dict(token=str(token), repo=str(repo), path=str(cfg.get("path", "otmflow")).strip("/"))


def _gh_request(method, url, token, **kw):
    import requests
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    return requests.request(method, url, headers=headers, timeout=15, **kw)

FILE_CONTATORI = "analytics.json"
FILE_EVENTI = "analytics.events.jsonl"
SYNC_MIN = 15                          # minuti tra un salvataggio e l'altro sul repo
PRIMA_SYNC_S = 120                     # primo salvataggio 2 minuti dopo l'avvio
MAX_EVENTI_BYTE = 4 * 1024 * 1024      # oltre: si tengono solo gli eventi più recenti
RUN = "run"                            # un evento per ogni rerun: se ne tengono solo gli estremi

_stato = {"pronto": False, "firme": {}}
_PW_CHIUSA = secrets.token_urlsafe(32)    # dashboard chiusa finché non imposti la password
_lock = threading.Lock()


def _password():
    try:
        pw = _cfg_analytics().get("password")
    except Exception:
        pw = None
    return str(pw) if pw else None


def _cartella():
    """Cartella locale, fissata al primo uso: resta la stessa anche se token/repo
    arrivano dopo, così i dati già raccolti non restano indietro."""
    d = _stato.get("cartella")
    if d is None:
        cfg = _github_cfg()
        sotto = (cfg["path"] if cfg else "locale").replace("/", "_") or "root"
        d = _stato["cartella"] = os.path.join("/tmp", "otm_analytics", sotto)
    os.makedirs(d, exist_ok=True)
    return d


# ── GitHub: GET in formato raw (la Contents API in JSON si ferma a 1 MB) ──────────
def _url(cfg, nome):
    return f"https://api.github.com/repos/{cfg['repo']}/contents/{cfg['path']}/{nome}"


def _scarica(cfg, nome, dest):
    import requests
    r = requests.get(_url(cfg, nome), timeout=20, headers={
        "Authorization": f"token {cfg['token']}", "Accept": "application/vnd.github.raw"})
    if r.status_code == 200:
        with open(dest, "wb") as f:
            f.write(r.content)
    elif r.status_code != 404:                  # 404 = prima volta, nessuno storico
        log.warning("statistiche: download %s HTTP %s", nome, r.status_code)


def _carica(cfg, nome, src):
    with open(src, "rb") as f:
        contenuto = base64.b64encode(f.read()).decode("ascii")
    url = _url(cfg, nome)
    get = _gh_request("GET", url, cfg["token"])
    payload = {"message": f"OTMFLOW: statistiche d'uso ({nome})", "content": contenuto}
    if get.status_code == 200:
        payload["sha"] = get.json().get("sha")
    put = _gh_request("PUT", url, cfg["token"], json=payload)
    if put.status_code not in (200, 201):
        raise RuntimeError(f"HTTP {put.status_code} {put.text[:120]}")


def _sfoltisci_eventi(path):
    """Degli eventi 'run' tiene solo il primo e l'ultimo di ogni sessione (bastano per
    durata media e rimbalzo); oltre MAX_EVENTI_BYTE toglie gli eventi più vecchi."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        righe = f.readlines()
    eventi = []
    for r in righe:
        try:
            eventi.append((json.loads(r), r if r.endswith("\n") else r + "\n"))
        except Exception:
            continue
    primo, ultimo = {}, {}
    for i, (e, _) in enumerate(eventi):
        if e.get("kind") == RUN:
            primo.setdefault(e.get("session"), i)
            ultimo[e.get("session")] = i
    estremi = set(primo.values()) | set(ultimo.values())
    tenute = [r for i, (e, r) in enumerate(eventi) if e.get("kind") != RUN or i in estremi]
    totale = sum(len(r.encode("utf-8")) for r in tenute)
    while tenute and totale > MAX_EVENTI_BYTE:
        totale -= len(tenute.pop(0).encode("utf-8"))
    if len(tenute) != len(righe):
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(tenute)


def _firma(path):
    try:
        s = os.stat(path)
        return (s.st_size, s.st_mtime_ns)
    except OSError:
        return None


def _sincronizza(cartella):
    cfg = _github_cfg()
    if cfg is None:
        return
    with _lock:                                 # lo stesso file non va scritto mentre lo carico
        _sfoltisci_eventi(os.path.join(cartella, FILE_EVENTI))
        for nome in (FILE_CONTATORI, FILE_EVENTI):
            p = os.path.join(cartella, nome)
            f = _firma(p)
            if f is None or _stato["firme"].get(nome) == f:
                continue
            try:
                _carica(cfg, nome, p)
                _stato["firme"][nome] = f
            except Exception as ex:
                log.warning("statistiche: upload %s fallito: %s", nome, ex)


def _ciclo(cartella):
    attesa = PRIMA_SYNC_S                      # primo salvataggio presto, poi ogni SYNC_MIN
    while True:
        time.sleep(attesa)
        attesa = SYNC_MIN * 60
        try:
            _sincronizza(cartella)
        except Exception as ex:
            log.warning("statistiche: sincronizzazione fallita: %s", ex)


def _avvia_sync(cartella):
    if not _stato.get("sync"):
        threading.Thread(target=_ciclo, args=(cartella,), daemon=True,
                         name="otm-statistiche").start()
        _stato["sync"] = True


def _prepara():
    """Una volta per processo: scarica lo storico e avvia il salvataggio periodico.

    Se token/repo arrivano DOPO l'avvio (Streamlit applica i Secrets nuovi senza
    riavviare l'app), il salvataggio parte al primo run successivo; lo storico sul
    repo viene letto al prossimo riavvio."""
    cartella = _cartella()
    with _lock:
        if _stato["pronto"]:
            if not _stato.get("sync") and _github_cfg() is not None:
                _avvia_sync(cartella)
            return cartella
        cfg = _github_cfg()
        if cfg is not None:
            for nome in (FILE_CONTATORI, FILE_EVENTI):
                try:
                    _scarica(cfg, nome, os.path.join(cartella, nome))
                except Exception as ex:
                    log.warning("statistiche: download %s fallito: %s", nome, ex)
            for nome in (FILE_CONTATORI, FILE_EVENTI):
                _stato["firme"][nome] = _firma(os.path.join(cartella, nome))
            _avvia_sync(cartella)
        _stato["pronto"] = True
    return cartella


def _salva_subito(cartella):
    """Scrive SUBITO visita/pagina vista/run di questo run e i contatori.

    Dopo st.stop() Streamlit vieta ogni accesso a session_state (solleva di nuovo
    StopException), quindi stop_tracking non può più girare: senza questo, le visite
    fermate sulla schermata di accesso, su una licenza non valida o a fine prova
    andrebbero perse. Così con st.stop() si perdono solo i click di quel run."""
    import streamlit as st
    from streamlit_analytics2 import storage
    from streamlit_analytics2.state import data
    in_sospeso = st.session_state.get("_sa2_pending") or []
    if in_sospeso:
        storage.open_store(os.path.join(cartella, FILE_EVENTI)).append(in_sospeso)
        st.session_state["_sa2_pending"] = []
    with open(os.path.join(cartella, FILE_CONTATORI), "w") as f:
        json.dump(data, f)


def _e_stop(ex):
    return type(ex).__name__ == "StopException"


@contextmanager
def traccia():
    """Come sa2.track(), ma non perde le visite chiuse da st.stop() e non rompe mai l'app."""
    pw = _password() or _PW_CHIUSA
    attivo, kw = False, {}
    try:
        import streamlit_analytics2 as sa2
        cartella = _prepara()
        kw = dict(unsafe_password=pw,
                  save_to_json=os.path.join(cartella, FILE_CONTATORI),
                  load_from_json=os.path.join(cartella, FILE_CONTATORI))
        with _lock:
            sa2.start_tracking(**kw)
            _salva_subito(cartella)
        attivo = True
    except Exception as ex:
        log.warning("statistiche: avvio fallito, app senza tracciamento: %s", ex)
    fermato = False
    try:
        yield
    except BaseException as ex:                 # st.stop(), st.rerun() o errore dell'app
        fermato = _e_stop(ex)
        raise
    finally:
        if attivo and not fermato:              # dopo st.stop() session_state è off-limits
            try:
                with _lock:
                    sa2.stop_tracking(**kw)
            except Exception as ex:
                log.warning("statistiche: chiusura run fallita: %s", ex)
