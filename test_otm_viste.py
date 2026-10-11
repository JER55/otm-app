# -*- coding: utf-8 -*-
"""Catalogo delle viste (locales/views.json).  python -m unittest test_otm_viste -v

Controlla che il catalogo sia ben formato (it/en/es, segnaposto uguali, niente tag) e che
ogni voce corrisponda a un testo che esiste davvero nei file delle viste: se cambi un testo
in fakemove.html / footprint.html / otm-nav.js e la voce non e' piu' valida, il test lo dice.
I confronti con i sorgenti girano solo dove c'e' la cartella views/ (repo privato, uso locale).
"""
import html
import json
import os
import re
import unittest

QUI = os.path.dirname(os.path.abspath(__file__))
VIEWS = os.path.join(QUI, "views")
CATALOGO = os.path.join(QUI, "locales", "views.json")
FILE_VISTE = ("fakemove.html", "footprint.html", "otm-nav.js", "session-volume-profile.js")
LINGUE = ("it", "en", "es")
_RE_SEGN = re.compile(r"\{(\w+)\}")


def _carica():
    with open(CATALOGO, encoding="utf-8") as f:
        return json.load(f)


def _sorgente():
    """Testo dei file delle viste con le sequenze di escape risolte (\\u00b7, \\n, \\', &amp;...)."""
    out = []
    for nome in FILE_VISTE:
        p = os.path.join(VIEWS, nome)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                t = f.read()
            t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
            t = t.replace("\\n", "\n").replace("\\'", "'").replace('\\"', '"')
            out.append(html.unescape(t))
    return "\n".join(out)


def _voci(cat):
    for sezione in ("esatte", "frammenti"):
        for k, v in cat[sezione].items():
            yield sezione, k, v


class TestFormato(unittest.TestCase):
    def setUp(self):
        self.cat = _carica()

    def test_sezioni_presenti(self):
        self.assertGreater(len(self.cat["esatte"]), 50)
        self.assertGreater(len(self.cat["frammenti"]), 30)

    def test_tre_lingue_non_vuote(self):
        for sez, k, v in _voci(self.cat):
            self.assertEqual(set(v), set(LINGUE), f"{sez}: {k!r}")
            for lg in LINGUE:
                self.assertIsInstance(v[lg], str, f"{k!r} [{lg}]")
                self.assertTrue(v[lg].strip(), f"{k!r} [{lg}] vuota")

    def test_segnaposto_uguali_in_tutte_le_lingue(self):
        for sez, k, v in _voci(self.cat):
            base = set(_RE_SEGN.findall(k))
            for lg in LINGUE:
                self.assertEqual(set(_RE_SEGN.findall(v[lg])), base, f"{k!r} [{lg}]")

    def test_nessun_tag_html(self):
        for sez, k, v in _voci(self.cat):
            for lg in LINGUE:
                self.assertNotRegex(v[lg], r"[<>]", f"{k!r} [{lg}]")

    def test_chiave_nella_lingua_del_sorgente_resta_uguale(self):
        # la voce della lingua in cui e' scritto il sorgente non deve cambiare il testo
        for sez, k, v in _voci(self.cat):
            if len(k) <= 2:                  # chiavi simboliche (es. 'gg' = unita' dei giorni nel righello)
                continue
            self.assertIn(k.strip(), {v[lg].strip() for lg in LINGUE}, f"{k!r}: nessuna lingua coincide con la chiave")

    def test_esatte_senza_spazi_ai_bordi(self):
        for k in self.cat["esatte"]:
            self.assertEqual(k, k.strip(), repr(k))

    def test_chiavi_senza_duplicati_tra_sezioni(self):
        doppie = set(self.cat["esatte"]) & set(self.cat["frammenti"])
        self.assertEqual(doppie, set())

    def test_traduzioni_non_vuote_per_le_altre_lingue(self):
        # una voce che in en ed es resta uguale all'italiano e' ammessa solo per i termini di trading
        for sez, k, v in _voci(self.cat):
            if v["en"] == v["es"] == v["it"]:
                self.assertLess(len(k), 24, f"{k!r}: identica nelle tre lingue (voce inutile?)")


@unittest.skipUnless(os.path.isdir(VIEWS), "cartella views/ assente (repo pubblico)")
class TestContraSorgenti(unittest.TestCase):
    def setUp(self):
        self.cat = _carica()
        self.src = _sorgente()

    def test_ogni_voce_esiste_nei_sorgenti(self):
        mancanti = []
        for sez, k, v in _voci(self.cat):
            pezzi = [p.strip() for p in _RE_SEGN.split(k) if p.strip()] if "{" in k else [k.strip()]
            if sez == "frammenti" and "{" in k:
                pezzi = [p.strip() for p in re.split(r"\{\w+\}", k) if p.strip()]
            for p in pezzi:
                if p not in self.src:
                    mancanti.append(k)
                    break
        self.assertEqual(mancanti, [], "voci del catalogo non piu' presenti nelle viste")


if __name__ == "__main__":
    unittest.main()
