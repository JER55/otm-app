# -*- coding: utf-8 -*-
"""Accesso di Otmflow: password del titolare e codici di prova, provati con Streamlit AppTest.

    python -m unittest test_accesso_otm -v
"""
import os
import shutil
import tempfile
import time
import unittest

try:
    from streamlit.testing.v1 import AppTest
except Exception:                                   # Streamlit non installato
    AppTest = None

import licenze_otm as lic
import traduzioni  # noqa: F401  — caricato dal repo, non dalla cartella temporanea poi cancellata

QUI = os.path.dirname(os.path.abspath(__file__))
K = "k" * 40
PWD = "password-del-titolare"


@unittest.skipIf(AppTest is None, "Streamlit non installato")
class TestAccesso(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="otm_acc_")
        for f in ("app.py", "traduzioni.py", "otm-i18n.js", "accesso_otm.py", "licenze_otm.py"):
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

    def _app(self, **secrets):
        at = AppTest.from_file(os.path.join(self.dir, "app.py"), default_timeout=30)
        for k, v in secrets.items():
            at.secrets[k] = v
        return at

    @staticmethod
    def _shell(at):
        s = [e.proto.srcdoc for e in at.main if getattr(e, "type", "") == "iframe" and "var OTM_I18N" in e.proto.srcdoc]
        return s[0] if s else None

    def _entra(self, at, testo):
        at.run()
        at.text_input(key="otm_pwd").input(testo)
        at.button[0].click().run()
        self.assertFalse(at.exception)

    # ── titolare ────────────────────────────────────────────────────────────
    def test_password_titolare_entra_senza_scadenza(self):
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        self._entra(at, PWD)
        html = self._shell(at)
        self.assertIsNotNone(html)
        self.assertNotIn("otm-scaduta", html)
        self.assertNotIn("%%", html.split("<body>")[1].split("v-fakemove")[0])

    def test_password_errata_non_entra(self):
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        self._entra(at, "sbagliata")
        self.assertIsNone(self._shell(at))
        self.assertIn("Password errata.", [e.value for e in at.error])

    def test_senza_licenze_il_login_resta_quello_di_prima(self):
        at = self._app(APP_PASSWORD=PWD)
        self._entra(at, PWD)
        self.assertIsNotNone(self._shell(at))
        at2 = self._app(APP_PASSWORD=PWD)
        self._entra(at2, "OTM-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA")
        self.assertIsNone(self._shell(at2))

    # ── codici di prova ─────────────────────────────────────────────────────
    def test_codice_valido_entra_con_timer_di_scadenza(self):
        codice, _, scad = lic.genera(K, "1h")
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        self._entra(at, codice)
        html = self._shell(at)
        self.assertIsNotNone(html)
        self.assertIn(f"var EXP = {scad} * 1000", html)
        self.assertIn("otm-scaduta", html)
        self.assertIn("PRUEBA", html)                  # i testi del timer ci sono in tutte e tre le lingue
        self.assertEqual(html.count("</body>"), 1)

    def test_codice_digitato_con_refusi_entra(self):
        codice, _, _ = lic.genera(K, "30g")
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        self._entra(at, "  " + codice.lower().replace("-", " ") + " ")
        self.assertIsNotNone(self._shell(at))

    def test_codice_funziona_anche_senza_password_titolare(self):
        codice, _, _ = lic.genera(K, "1h")
        at = self._app(LICENSE_SECRET=K)
        self._entra(at, codice)
        self.assertIsNotNone(self._shell(at))

    def test_codice_scaduto_rifiutato_con_data(self):
        codice, _, _ = lic.genera(K, 3600, ora=time.time() - 7200)
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        self._entra(at, codice)
        self.assertIsNone(self._shell(at))
        self.assertTrue(any(e.value.startswith("Codice di prova scaduto il ") for e in at.error))

    def test_codice_revocato_rifiutato(self):
        codice, ident, _ = lic.genera(K, "30g")
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K, LICENZE_REVOCATE=[ident])
        self._entra(at, codice)
        self.assertIsNone(self._shell(at))
        self.assertIn("Codice di prova revocato.", [e.value for e in at.error])

    def test_codice_firmato_con_altra_chiave_rifiutato_senza_indizi(self):
        codice, _, _ = lic.genera("z" * 40, "30g")
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        self._entra(at, codice)
        self.assertIsNone(self._shell(at))
        self.assertIn("Password errata.", [e.value for e in at.error])

    def test_sessione_con_codice_scaduto_torna_al_login(self):
        codice, _, _ = lic.genera(K, 3600, ora=time.time() - 7200)
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET=K)
        at.session_state["otm_auth"] = True
        at.session_state["otm_codice"] = codice
        at.run()
        self.assertFalse(at.exception)
        self.assertIsNone(self._shell(at))
        self.assertTrue(any(e.value.startswith("Codice di prova scaduto il ") for e in at.error))
        self.assertFalse(at.session_state["otm_auth"])

    def test_chiave_corta_avvisa_e_non_accetta_codici(self):
        at = self._app(APP_PASSWORD=PWD, LICENSE_SECRET="corta")
        at.run()
        self.assertTrue(any("troppo corta" in w.value for w in at.warning))
        at.text_input(key="otm_pwd").input("OTM-AAAA-AAAA-AAAA-AAAA-AAAA-AAAA")
        at.button[0].click().run()
        self.assertIsNone(self._shell(at))


if __name__ == "__main__":
    unittest.main()
