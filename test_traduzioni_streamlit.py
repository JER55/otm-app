# -*- coding: utf-8 -*-
"""Test del selettore di lingua dentro Streamlit (AppTest). python -m unittest test_traduzioni_streamlit -v"""
import json
import logging
import os
import shutil
import tempfile
import textwrap
import unittest

try:
    from streamlit.testing.v1 import AppTest
except Exception:                                    # Streamlit non installato: test saltati
    AppTest = None

import traduzioni as tz

logging.getLogger("thinkcore.traduzioni").setLevel(logging.ERROR)

SCRIPT = textwrap.dedent('''
    import streamlit as st
    import traduzioni as tz
    tz.selettore()
    if st.session_state.get("ferma"):
        st.stop()                       # come la schermata d'accesso: il resto non viene disegnato
    st.markdown(tz.tr("Genera turni"))
    st.checkbox(tz.tr("Opzione"), value=True, key="opz")
    st.markdown("LINGUA=" + tz.lingua_corrente())
''')


@unittest.skipIf(AppTest is None, "Streamlit non installato")
class TestSelettore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="tz_st_")
        loc = os.path.join(self.dir, "locales")
        os.makedirs(loc)
        for cod, msg in (("en", {"Genera turni": "Generate rota", "Opzione": "Option", "Lingua": "Language"}),
                         ("es", {"Genera turni": "Generar turnos", "Opzione": "Opción", "Lingua": "Idioma"})):
            with open(os.path.join(loc, cod + ".json"), "w", encoding="utf-8") as f:
                json.dump({"messaggi": msg}, f, ensure_ascii=False)
        self._orig = tz._CATALOGHI
        tz._CATALOGHI = tz.Cataloghi(loc, verifica_ogni_s=0)
        self.script = os.path.join(self.dir, "app_prova.py")
        with open(self.script, "w", encoding="utf-8") as f:
            f.write(SCRIPT)

    def tearDown(self):
        tz._CATALOGHI = self._orig
        shutil.rmtree(self.dir, ignore_errors=True)

    def _app(self):
        return AppTest.from_file(self.script, default_timeout=30)

    def test_predefinita_italiano(self):
        at = self._app().run()
        self.assertFalse(at.exception)
        self.assertEqual(at.markdown[0].value, "Genera turni")
        self.assertEqual(at.markdown[-1].value, "LINGUA=it")

    def test_lingua_dall_indirizzo(self):
        at = self._app()
        at.query_params["lang"] = "es"
        at.run()
        self.assertEqual(at.markdown[0].value, "Generar turnos")
        self.assertEqual(at.checkbox[0].label, "Opción")

    def test_indirizzo_non_valido_ignorato(self):
        at = self._app()
        at.query_params["lang"] = "../../etc/passwd"
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.markdown[-1].value, "LINGUA=it")

    def test_browser_in_inglese_parte_comunque_in_italiano(self):
        # scelta di prodotto: si parte in italiano, la lingua del browser non conta
        at = self._app()
        at.run()
        self.assertEqual(at.markdown[-1].value, "LINGUA=it")

    def test_lingua_dai_secrets(self):
        at = self._app()
        at.secrets["interfaccia"] = {"lingua": "en"}
        at.run()
        self.assertEqual(at.markdown[0].value, "Generate rota")

    def test_cambio_dal_selettore_conserva_i_widget(self):
        at = self._app().run()
        at.checkbox(key="opz").uncheck().run()
        at.segmented_control(key=tz.CHIAVE_WIDGET).set_value("en").run()
        self.assertEqual(at.markdown[0].value, "Generate rota")
        self.assertEqual(at.checkbox(key="opz").label, "Option")
        self.assertFalse(at.checkbox(key="opz").value)          # lo stato non si azzera
        self.assertEqual(at.query_params.get("lang"), "en")

    def test_lingua_sopravvive_a_una_pagina_fermata(self):
        at = self._app().run()
        at.segmented_control(key=tz.CHIAVE_WIDGET).set_value("es").run()
        at.session_state["ferma"] = True
        at.run()                                                # selettore disegnato, resto no
        at.session_state["ferma"] = False
        at.run()
        self.assertEqual(at.markdown[-1].value, "LINGUA=es")


if __name__ == "__main__":
    unittest.main()
