#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
crea_licenza.py — codici di prova a tempo per Otmflow.

    python crea_licenza.py --nuova-chiave                  # una volta sola → Secrets: LICENSE_SECRET
    python crea_licenza.py --nome "Marco" --durata 30g     # prova di 30 giorni
    python crea_licenza.py --nome "Luca"  --durata 1h      # prova di 1 ora (consegnala subito)
    python crea_licenza.py --verifica OTM-AEAB-....        # stato di un codice
    python crea_licenza.py --elenco                        # codici emessi e stato

Chiave: variabile d'ambiente OTM_LICENSE_SECRET, altrimenti LICENSE_SECRET letta da
.streamlit/secrets.toml (la stessa che hai messo nei Secrets di Streamlit Cloud).
Registro locale: licenze_emesse.csv (nome, id, scadenza). È in .gitignore: il repo è pubblico.

Revoca di un codice prima della scadenza, nei Secrets dell'app:
    LICENZE_REVOCATE = ["7F3A9C21"]
"""
import argparse
import csv
import datetime as dt
import os
import sys
import time

import licenze_otm as lic

QUI = os.path.dirname(os.path.abspath(__file__))
REGISTRO = os.path.join(QUI, "licenze_emesse.csv")
SECRETS_TOML = os.path.join(QUI, ".streamlit", "secrets.toml")
CAMPI = ("emesso", "id", "nome", "durata", "scadenza_epoch", "scadenza_roma")


def ora_roma(epoch: int) -> str:
    try:
        from zoneinfo import ZoneInfo
        d = dt.datetime.fromtimestamp(epoch, ZoneInfo("Europe/Rome"))
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%d/%m/%Y %H:%M UTC")


def leggi_chiave() -> str:
    k = os.environ.get("OTM_LICENSE_SECRET", "").strip()
    if not k and os.path.exists(SECRETS_TOML):
        try:
            import tomllib
            with open(SECRETS_TOML, "rb") as f:
                k = str(tomllib.load(f).get("LICENSE_SECRET", "")).strip()
        except Exception as ex:
            sys.exit(f"Impossibile leggere {SECRETS_TOML}: {ex}")
    if not k:
        sys.exit("Chiave assente: imposta OTM_LICENSE_SECRET oppure LICENSE_SECRET in "
                 ".streamlit/secrets.toml (crea la chiave con --nuova-chiave).")
    if len(k) < lic.MIN_CHIAVE:
        sys.exit(f"Chiave troppo corta: servono almeno {lic.MIN_CHIAVE} caratteri.")
    return k


def registra(riga: dict) -> None:
    nuovo = not os.path.exists(REGISTRO)
    with open(REGISTRO, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CAMPI)
        if nuovo:
            w.writeheader()
        w.writerow(riga)


def elenco() -> None:
    if not os.path.exists(REGISTRO):
        print("Nessun codice emesso.")
        return
    adesso = time.time()
    with open(REGISTRO, encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    print(f"{'ID':<9} {'NOME':<18} {'DURATA':<7} {'SCADENZA (Roma)':<17} STATO")
    for r in righe:
        try:
            resta = int(r["scadenza_epoch"]) - adesso
        except (KeyError, ValueError):
            resta = -1
        stato = "scaduto" if resta <= 0 else (f"attivo · {resta / 86400:.1f} g" if resta >= 86400
                                              else f"attivo · {resta / 60:.0f} min")
        print(f"{r.get('id', ''):<9} {r.get('nome', '')[:18]:<18} {r.get('durata', ''):<7} "
              f"{r.get('scadenza_roma', ''):<17} {stato}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Codici di prova a tempo per Otmflow.")
    ap.add_argument("--nome", default="", help="a chi lo dai (solo nel registro locale)")
    ap.add_argument("--durata", default="30g", help="30g, 7g, 1h, 90m … (di serie 30g)")
    ap.add_argument("--url", default=os.environ.get("OTM_URL", ""), help="indirizzo dell'app per il messaggio")
    ap.add_argument("--nuova-chiave", action="store_true", help="genera LICENSE_SECRET")
    ap.add_argument("--verifica", metavar="CODICE")
    ap.add_argument("--elenco", action="store_true")
    a = ap.parse_args()

    if a.nuova_chiave:
        print("Incolla nei Secrets dell'app (Streamlit Cloud → Settings → Secrets) e in .streamlit/secrets.toml:\n")
        print(f'LICENSE_SECRET = "{lic.nuova_chiave()}"\n')
        print("Attenzione: cambiarla in futuro invalida tutti i codici già consegnati.")
        return
    if a.elenco:
        elenco()
        return
    chiave = leggi_chiave()
    if a.verifica:
        e = lic.verifica(chiave, a.verifica)
        if e.ok:
            print(f"Valido · id {e.id} · scade il {ora_roma(e.scadenza)} (ora italiana)")
        elif e.motivo == "scaduta":
            print(f"Scaduto il {ora_roma(e.scadenza)} · id {e.id}")
        else:
            print(f"Non valido ({e.motivo})")
        return

    try:
        codice, ident, scadenza = lic.genera(chiave, a.durata)
    except ValueError as ex:
        sys.exit(str(ex))
    registra(dict(emesso=dt.datetime.now().isoformat(timespec="seconds"), id=ident, nome=a.nome,
                  durata=a.durata, scadenza_epoch=scadenza, scadenza_roma=ora_roma(scadenza)))
    saluto = f"Ciao {a.nome}," if a.nome else "Ciao,"
    print(f"\nid {ident} · scade il {ora_roma(scadenza)} (ora italiana)\n")
    print("Messaggio da inviare:\n")
    print(f"{saluto} ecco il tuo accesso di prova a Otmflow.")
    if a.url:
        print(f"  Indirizzo: {a.url}")
    print(f"  Codice:    {codice}")
    print(f"  Valido fino al {ora_roma(scadenza)} (ora italiana).")
    print("Inseriscilo nel campo Password. È personale: non condividerlo.\n")


if __name__ == "__main__":
    main()
