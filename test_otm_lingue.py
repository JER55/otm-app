# -*- coding: utf-8 -*-
"""Lingue di OTM · Order Flow (IT · EN · ES).  python -m unittest test_otm_lingue -v

1. Ogni testo di app.py — tr("...") in Python, t("...") / data-i18n nella shell — ha la
   traduzione in locales/en.json e locales/es.json; nessuna voce orfana, nessuna scartata.
2. La schermata d'accesso compare nella lingua scelta (?lang=, Secrets, selettore).
3. Con l'accesso fatto la shell si costruisce con lingua e testi delle tre lingue dentro.
4. Titolo e logo della scheda: "Otmflow - OutThinkTheMarket" e favicon OTM.
"""
import ast
import json
import logging
import os
import re
import shutil
import tempfile
import unittest

import traduzioni as tz

try:
    from streamlit.testing.v1 import AppTest
except Exception:
    AppTest = None

logging.getLogger("thinkcore.traduzioni").setLevel(logging.ERROR)

QUI = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(QUI, "app.py")


def _sorgente():
    with open(APP, encoding="utf-8") as f:
        return f.read()


def testi_python(src):
    """Primo argomento letterale di ogni chiamata tr(...)."""
    out = set()
    for n in ast.walk(ast.parse(src)):
        if (isinstance(n, ast.Call) and getattr(n.func, "id", None) == "tr" and n.args
                and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)):
            out.add(n.args[0].value)
    return out


def testi_shell(src):
    """Stessa estrazione di app.shell_keys, applicata a SHELL_HTML letto dal sorgente."""
    shell = next(n.value.value for n in ast.walk(ast.parse(src))
                 if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "SHELL_HTML")
    keys = set(re.findall(r'\bt\("([^"\\]+)"', shell))
    keys |= set(re.findall(r'data-i18n(?:-title)?="([^"]+)"', shell))
    return keys


class TestCataloghiCompleti(unittest.TestCase):
    def setUp(self):
        src = _sorgente()
        self.usati = testi_python(src) | testi_shell(src) | {"Lingua"}   # "Lingua": tz.selettore
        self.cat = tz.Cataloghi(tz.CARTELLA_LOCALES, verifica_ogni_s=0)

    def test_nessun_testo_senza_traduzione(self):
        for lg in ("en", "es"):
            mancanti = sorted(k for k in self.usati if not self.cat.voci(lg).get(k))
            self.assertEqual(mancanti, [], f"{lg}: testi senza traduzione")

    def test_nessuna_voce_orfana(self):
        for lg in ("en", "es"):
            orfane = sorted(set(self.cat.voci(lg)) - self.usati)
            self.assertEqual(orfane, [], f"{lg}: voci non usate da app.py")

    def test_nessuna_voce_scartata(self):
        for lg in ("en", "es"):
            self.assertEqual(self.cat.problemi(lg), [], lg)

    def test_trovati_testi_shell_e_python(self):
        src = _sorgente()
        self.assertIn("CARICAMENTO", testi_shell(src))
        self.assertIn("chiude tra {d}", testi_shell(src))
        self.assertIn("FLUSSO 60s", testi_shell(src))
        self.assertIn("ENTRA", testi_python(src))

    def test_testi_shell_senza_virgolette_doppie(self):
        # finiscono in t("...") e in attributi HTML: una " li spezzerebbe
        for k in testi_shell(_sorgente()):
            self.assertNotIn('"', k)


class TestIdentitaScheda(unittest.TestCase):
    def test_titolo_e_logo(self):
        src = _sorgente()
        self.assertIn('APP_TITLE = "Otmflow - OutThinkTheMarket"', src)
        self.assertIn("page_title=APP_TITLE", src)
        self.assertIn("page_icon=_otm_icon()", src)


@unittest.skipIf(AppTest is None, "Streamlit non installato")
class TestAccesso(unittest.TestCase):
    def _app(self, lang=None, password="segreta"):
        at = AppTest.from_file(APP, default_timeout=30)
        if password:
            at.secrets["APP_PASSWORD"] = password
        if lang:
            at.query_params["lang"] = lang
        return at.run()

    def test_italiano_predefinito(self):
        at = self._app()
        self.assertFalse(at.exception)
        self.assertEqual(at.text_input(key="otm_pwd").label, "Password")
        self.assertEqual(at.button[0].label, "ENTRA")

    def test_inglese_dall_indirizzo(self):
        at = self._app("en")
        self.assertEqual(at.button[0].label, "ENTER")

    def test_spagnolo_dall_indirizzo(self):
        at = self._app("es")
        self.assertEqual(at.text_input(key="otm_pwd").label, "Contraseña")
        self.assertEqual(at.button[0].label, "ENTRAR")

    def test_cambio_dal_selettore(self):
        at = self._app()
        at.segmented_control(key=tz.CHIAVE_WIDGET).set_value("en").run()
        self.assertEqual(at.button[0].label, "ENTER")
        self.assertEqual(at.query_params.get("lang"), "en")

    def test_password_errata_tradotta(self):
        at = self._app("es")
        at.text_input(key="otm_pwd").input("no")
        at.button[0].click().run()
        self.assertIn("Contraseña incorrecta.", [e.value for e in at.error])

    def test_secret_mancante_tradotto(self):
        at = self._app("en", password=None)
        self.assertIn("APP_PASSWORD not set in Secrets: access blocked.", [e.value for e in at.error])
        self.assertTrue(at.segmented_control)                 # selettore presente anche qui


@unittest.skipIf(AppTest is None, "Streamlit non installato")
class TestShell(unittest.TestCase):
    """Copia dell'app con viste finte: login fatto, la shell deve contenere lingua e testi."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="otm_st_")
        for f in ("app.py", "traduzioni.py", "otm-i18n.js"):
            shutil.copy(os.path.join(QUI, f), self.dir)
        shutil.copytree(os.path.join(QUI, "locales"), os.path.join(self.dir, "locales"))
        v = os.path.join(self.dir, "views")
        os.makedirs(v)
        pagine = {
            "fakemove.html": "<!doctype html><html><head><title>FM</title></head><body>FM</body></html>",
            "footprint.html": ('<!doctype html><html><head><script src="session-volume-profile.js"></script>'
                               "</head><body>FP</body></html>"),
            "session-volume-profile.js": "window.SVP=1;",
            "otm-nav.js": "window.OTMNav={};",
        }
        for nome, testo in pagine.items():
            with open(os.path.join(v, nome), "w", encoding="utf-8") as f:
                f.write(testo)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _iframes(self, lang):
        at = AppTest.from_file(os.path.join(self.dir, "app.py"), default_timeout=30)
        at.secrets["APP_PASSWORD"] = "x"
        at.session_state["otm_auth"] = True
        at.query_params["lang"] = lang
        at.run()
        self.assertFalse(at.exception)
        return [e.proto.srcdoc for e in at.main if getattr(e, "type", "") == "iframe"]

    def _html(self, lang):
        shell = [s for s in self._iframes(lang) if "var OTM_I18N" in s]
        self.assertEqual(len(shell), 1)
        return shell[0]

    def test_shell_in_spagnolo(self):
        html = self._html("es")
        self.assertIn('<html lang="es">', html)
        self.assertNotIn("%%LANG%%", html)
        self.assertNotIn("%%I18N%%", html)
        self.assertNotIn("%%MARK%%", html)
        i18n = json.loads(re.search(r"var OTM_I18N = (\{.*?\});</script>", html).group(1))
        self.assertEqual(set(i18n), {"it", "en", "es"})
        self.assertEqual(i18n["es"]["CARICAMENTO"], "CARGANDO")
        self.assertEqual(i18n["en"]["chiude tra {d}"], "closes in {d}")
        self.assertEqual(i18n["it"]["CHIUSA"], "CHIUSA")
        self.assertEqual(i18n["es"]["FLUSSO 60s"], "FLUJO 60s")

    def test_componente_identita_scheda(self):
        ident = [s for s in self._iframes("it") if "data:image/svg+xml" in s and "OTM_I18N" not in s]
        self.assertEqual(len(ident), 1)
        self.assertIn('"Otmflow - OutThinkTheMarket"', ident[0])

    def test_viste_ricevono_lingua_catalogo_e_traduttore(self):
        html = self._html("en")
        blob = re.search(r'<script type="application/json" id="v-fakemove">(.*?)</script>', html, re.S).group(1)
        vista = json.loads(blob)
        self.assertIn("window.__OTM_LANG=' + JSON.stringify(LANG)", html)  # la shell la mette prima degli script della vista
        self.assertLess(vista.index("window.__OTM_DICT="), vista.index("window.OTMi18n = {"))
        self.assertIn('"Disponibile"', vista)                              # il catalogo c'e'

    def test_lingua_non_valida_ricade_sull_italiano(self):
        html = self._html("../../etc")
        self.assertIn('<html lang="it">', html)


if __name__ == "__main__":
    unittest.main()
