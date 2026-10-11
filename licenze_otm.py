# -*- coding: utf-8 -*-
"""
licenze_otm.py — codici di prova a tempo per Otmflow (solo libreria standard).

Un codice è autosufficiente e firmato, non serve nessun registro sul server:

    OTM-AEAB-CDEF-GHIJ-KLMN-OPQR-STUV
         └── 15 byte in base32: versione · id (4 byte) · scadenza UTC (s) · firma HMAC-SHA256 (6 byte)

  * la firma usa LICENSE_SECRET (Secrets di Streamlit): senza la chiave nessuno può
    creare un codice o allungarne la scadenza; cambiare la chiave invalida TUTTI i codici;
  * la scadenza è assoluta (momento di creazione + durata): un codice da 1h va
    consegnato subito, uno da 30g dura 30 giorni da quando lo crei;
  * revoca di un singolo codice: il suo id nell'elenco LICENZE_REVOCATE dei Secrets;
  * 48 bit di firma: indovinarla a tentativi online (con il ritardo di 1,5 s del login)
    richiederebbe migliaia di anni.

Generatore da riga di comando: crea_licenza.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from dataclasses import dataclass

__all__ = ["Esito", "genera", "verifica", "durata_s", "nuova_chiave", "PREFISSO", "MIN_CHIAVE"]

PREFISSO = "OTM"
VERSIONE = 1
MIN_CHIAVE = 32                                  # caratteri minimi di LICENSE_SECRET
DURATA_MIN_S = 60
DURATA_MAX_S = 366 * 86400
_DOMINIO = b"otm-licenza-v1\x00"                 # separa queste firme da ogni altro uso della chiave
_FORMATO = struct.Struct(">BII")                 # versione, id, scadenza (epoch UTC in secondi)
_FIRMA = 6
_LUNGHEZZA = _FORMATO.size + _FIRMA              # 15 byte → 24 caratteri base32, senza padding
_UNITA = {"m": 60, "min": 60, "h": 3600, "g": 86400, "d": 86400}
_REFUSI = str.maketrans("0189", "OIBG")          # cifre che non esistono in base32, scambiate per lettere


@dataclass(frozen=True)
class Esito:
    ok: bool
    motivo: str = ""          # "" | "chiave" | "formato" | "firma" | "revocata" | "scaduta"
    id: str = ""              # 8 cifre esadecimali (per la revoca)
    scadenza: int = 0         # epoch UTC in secondi


def nuova_chiave() -> str:
    """Chiave casuale da mettere nei Secrets come LICENSE_SECRET (64 caratteri)."""
    return secrets.token_urlsafe(48)


def durata_s(testo) -> int:
    """'30g', '7d', '1h', '90m', '45min' → secondi (da 1 minuto a 366 giorni)."""
    m = re.fullmatch(r"\s*(\d{1,6})\s*(min|m|h|g|d)\s*", str(testo or "").lower())
    if not m:
        raise ValueError(f"durata «{testo}» non valida: usa per esempio 30g, 7g, 1h, 90m")
    s = int(m.group(1)) * _UNITA[m.group(2)]
    if not DURATA_MIN_S <= s <= DURATA_MAX_S:
        raise ValueError(f"durata «{testo}» fuori dai limiti (da 1 minuto a 366 giorni)")
    return s


def _chiave(segreto) -> bytes:
    s = str(segreto or "").strip()
    if len(s) < MIN_CHIAVE:
        raise ValueError(f"LICENSE_SECRET troppo corta: servono almeno {MIN_CHIAVE} caratteri")
    return s.encode("utf-8")


def _firma(chiave: bytes, payload: bytes) -> bytes:
    return hmac.new(chiave, _DOMINIO + payload, hashlib.sha256).digest()[:_FIRMA]


def genera(segreto, durata, *, ora=None, id_hex=None):
    """Nuovo codice. durata: testo ('30g', '1h') o secondi. → (codice, id, scadenza_epoch)."""
    chiave = _chiave(segreto)
    secondi = durata_s(durata) if isinstance(durata, str) else int(durata)
    if not DURATA_MIN_S <= secondi <= DURATA_MAX_S:
        raise ValueError("durata fuori dai limiti (da 1 minuto a 366 giorni)")
    adesso = int(time.time() if ora is None else ora)
    scadenza = adesso + secondi
    ident = secrets.randbits(32) if id_hex is None else int(str(id_hex), 16) & 0xFFFFFFFF
    payload = _FORMATO.pack(VERSIONE, ident, scadenza)
    b32 = base64.b32encode(payload + _firma(chiave, payload)).decode("ascii")
    codice = PREFISSO + "-" + "-".join(b32[i:i + 4] for i in range(0, len(b32), 4))
    return codice, f"{ident:08X}", scadenza


def _normalizza(codice) -> str:
    s = re.sub(r"[\s\-_.·]", "", str(codice or "").upper()).translate(_REFUSI)
    # il corpo inizia sempre con 'A' (versione 1): togliere 'OTM' davanti non è mai ambiguo
    return s[len(PREFISSO):] if s.startswith(PREFISSO) else s


def verifica(segreto, codice, ora=None, revocati=()) -> Esito:
    """Controlla firma, revoca e scadenza. Non solleva mai: l'esito dice il motivo."""
    try:
        chiave = _chiave(segreto)
    except ValueError:
        return Esito(False, "chiave")
    s = _normalizza(codice)
    if not re.fullmatch(r"[A-Z2-7]{24}", s):
        return Esito(False, "formato")
    grezzo = base64.b32decode(s)
    payload, firma = grezzo[:_FORMATO.size], grezzo[_FORMATO.size:]
    if not hmac.compare_digest(firma, _firma(chiave, payload)):
        return Esito(False, "firma")
    versione, ident, scadenza = _FORMATO.unpack(payload)
    if versione != VERSIONE:
        return Esito(False, "formato")
    id_hex = f"{ident:08X}"
    if isinstance(revocati, str):
        revocati = [revocati]
    if id_hex in {str(r).strip().upper() for r in (revocati or ())}:
        return Esito(False, "revocata", id_hex, scadenza)
    if int(time.time() if ora is None else ora) >= scadenza:
        return Esito(False, "scaduta", id_hex, scadenza)
    return Esito(True, "", id_hex, scadenza)
