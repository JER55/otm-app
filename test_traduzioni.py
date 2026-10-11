# -*- coding: utf-8 -*-
"""Test di traduzioni.py (solo libreria standard: python -m unittest test_traduzioni -v)."""
import json
import os
import shutil
import tempfile
import time
import unittest

import logging

import traduzioni as tz

logging.getLogger("thinkcore.traduzioni").setLevel(logging.ERROR)   # scarti attesi nei test


def _scrivi(cartella, codice, messaggi, info=None):
    dati = {"_info": info or {"lingua": codice}, "messaggi": messaggi}
    with open(os.path.join(cartella, codice + ".json"), "w", encoding="utf-8") as f:
        json.dump(dati, f, ensure_ascii=False)


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="tz_test_")
        _scrivi(self.dir, "en", {
            "Genera turni": "Generate rota",
            "Vuota": "",
            "Ore {h:.1f}": "Hours {h:.1f}",
            "Totale <b>{v}</b>": "Total <b>{v}</b>",
            "Ore {h}": "Hours {hours}",                                   # segnaposto diverso: scartata
            "Somma <b>{v}</b>": "Sum <img src=x onerror=alert(1)> {v}",   # tag diversi: scartata
            "Numero": 5,                                                  # non stringa: scartata
            "{n} violazione": {"one": "{n} violation", "other": "{n} violations"},
            "giorno::Mar": "Tue",
            "Mar": "Sea",
            "%{y:.1f} h · {n} righe": "%{y:.1f} h · {n} rows",
        })
        _scrivi(self.dir, "es", {"Genera turni": "Generar turnos"})
        self.cat = tz.Cataloghi(self.dir, verifica_ogni_s=0)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def t(self, lingua, testo, /, **kw):
        return tz.traduci(lingua, testo, _cataloghi=self.cat, **kw)


class TestRicerca(Base):
    def test_italiano_restituisce_il_testo_sorgente(self):
        self.assertEqual(self.t("it", "Genera turni"), "Genera turni")

    def test_inglese_e_spagnolo_dal_catalogo(self):
        self.assertEqual(self.t("en", "Genera turni"), "Generate rota")
        self.assertEqual(self.t("es", "Genera turni"), "Generar turnos")

    def test_voce_mancante_ricade_sull_italiano(self):
        self.assertEqual(self.t("en", "Testo non tradotto"), "Testo non tradotto")

    def test_voce_vuota_ricade_sull_italiano(self):
        self.assertEqual(self.t("en", "Vuota"), "Vuota")

    def test_lingua_non_ammessa_ricade_sull_italiano(self):
        self.assertEqual(self.t("fr", "Genera turni"), "Genera turni")
        self.assertEqual(self.t("../en", "Genera turni"), "Genera turni")

    def test_contesto_separa_omonimi(self):
        self.assertEqual(tz.traduci_p("en", "giorno", "Mar", _cataloghi=self.cat), "Tue")
        self.assertEqual(self.t("en", "Mar"), "Sea")
        self.assertEqual(tz.traduci_p("it", "giorno", "Mar", _cataloghi=self.cat), "Mar")


class TestFormattazione(Base):
    def test_segnaposto_con_specifica_di_formato(self):
        self.assertEqual(self.t("en", "Ore {h:.1f}", h=3.14159), "Hours 3.1")
        self.assertEqual(self.t("it", "Ore {h:.1f}", h=3.14159), "Ore 3.1")

    def test_graffe_non_passate_restano_intatte(self):
        self.assertEqual(self.t("en", "%{y:.1f} h · {n} righe", n=3), "%{y:.1f} h · 3 rows")

    def test_nessun_accesso_ad_attributi_o_indici(self):
        self.assertEqual(self.t("it", "{x.__class__} {x[0]}", x="ab"), "{x.__class__} {x[0]}")

    def test_valore_mancante_non_solleva(self):
        self.assertEqual(self.t("it", "{a} e {b}", a=1), "1 e {b}")

    def test_formato_incompatibile_non_solleva(self):
        self.assertEqual(self.t("it", "{x:.1f}", x="abc"), "abc")

    def test_conversione_repr(self):
        self.assertEqual(self.t("it", "valore {v!r}", v="a"), "valore 'a'")

    def test_segnaposto_con_nomi_dei_parametri(self):
        # parametri solo posizionali: un segnaposto può chiamarsi come loro
        self.assertEqual(self.t("it", "{testo} / {lingua}", testo="a", lingua="b"), "a / b")
        self.assertEqual(tz.traduci_n("it", "{n} {singolare}", "{n} {plurale}", 2, plurale="x",
                                      _cataloghi=self.cat), "2 x")

    def test_senza_valori_nessuna_formattazione(self):
        self.assertEqual(self.t("it", "{non_toccare} 100%"), "{non_toccare} 100%")


class TestSicurezzaCatalogo(Base):
    def test_traduzione_con_segnaposto_diversi_scartata(self):
        self.assertEqual(self.t("en", "Ore {h}", h=2), "Ore 2")
        self.assertTrue(any("Ore {h}" in p for p in self.cat.problemi("en")))

    def test_traduzione_che_aggiunge_tag_scartata(self):
        self.assertEqual(self.t("en", "Somma <b>{v}</b>", v=1), "Somma <b>1</b>")

    def test_tag_conservati_ammessi(self):
        self.assertEqual(self.t("en", "Totale <b>{v}</b>", v=7), "Total <b>7</b>")

    def test_valore_non_stringa_scartato(self):
        self.assertEqual(self.t("en", "Numero"), "Numero")

    def test_json_non_valido_non_rompe_nulla(self):
        with open(os.path.join(self.dir, "es.json"), "w", encoding="utf-8") as f:
            f.write("{ questo non è json")
        cat = tz.Cataloghi(self.dir, verifica_ogni_s=0)
        self.assertEqual(tz.traduci("es", "Genera turni", _cataloghi=cat), "Genera turni")
        self.assertTrue(cat.problemi("es"))

    def test_file_troppo_grande_ignorato(self):
        cat = tz.Cataloghi(self.dir, verifica_ogni_s=0, max_byte=10)
        self.assertEqual(tz.traduci("en", "Genera turni", _cataloghi=cat), "Genera turni")
        self.assertTrue(cat.problemi("en"))

    def test_chiavi_duplicate_segnalate(self):
        with open(os.path.join(self.dir, "es.json"), "w", encoding="utf-8") as f:
            f.write('{"messaggi": {"A": "uno", "A": "dos"}}')
        cat = tz.Cataloghi(self.dir, verifica_ogni_s=0)
        self.assertEqual(tz.traduci("es", "A", _cataloghi=cat), "dos")
        self.assertTrue(any("duplicat" in p for p in cat.problemi("es")))

    def test_file_mancante_non_rompe_nulla(self):
        os.remove(os.path.join(self.dir, "es.json"))
        cat = tz.Cataloghi(self.dir, verifica_ogni_s=0)
        self.assertEqual(tz.traduci("es", "Genera turni", _cataloghi=cat), "Genera turni")

    def test_ricarica_quando_il_file_cambia(self):
        self.assertEqual(self.t("es", "Genera turni"), "Generar turnos")
        time.sleep(0.01)
        _scrivi(self.dir, "es", {"Genera turni": "Crear turnos", "Nuovo": "Nuevo"})
        self.assertEqual(self.t("es", "Genera turni"), "Crear turnos")


class TestPlurali(Base):
    def test_singolare_e_plurale(self):
        self.assertEqual(tz.traduci_n("en", "{n} violazione", "{n} violazioni", 1, _cataloghi=self.cat),
                         "1 violation")
        self.assertEqual(tz.traduci_n("en", "{n} violazione", "{n} violazioni", 3, _cataloghi=self.cat),
                         "3 violations")

    def test_plurale_italiano_dal_codice(self):
        self.assertEqual(tz.traduci_n("it", "{n} violazione", "{n} violazioni", 0, _cataloghi=self.cat),
                         "0 violazioni")
        self.assertEqual(tz.traduci_n("it", "{n} violazione", "{n} violazioni", 1, _cataloghi=self.cat),
                         "1 violazione")

    def test_plurale_mancante_ricade_sull_italiano(self):
        self.assertEqual(tz.traduci_n("es", "{n} riga", "{n} righe", 2, _cataloghi=self.cat), "2 righe")


class TestNumeriEDate(unittest.TestCase):
    def test_numeri_per_lingua(self):
        self.assertEqual(tz.numero(1234.5, 1, lingua="en"), "1,234.5")
        self.assertEqual(tz.numero(1234.5, 1, lingua="it"), "1.234,5")
        self.assertEqual(tz.numero(1234.5, 1, lingua="es"), "1.234,5")
        self.assertEqual(tz.numero(134623, 0, lingua="it"), "134.623")
        self.assertEqual(tz.numero(-0.04, 1, lingua="en"), "-0.0")


class TestCodici(unittest.TestCase):
    def test_codice_valido(self):
        self.assertEqual(tz.codice_valido("EN"), "en")
        self.assertEqual(tz.codice_valido(" es "), "es")
        self.assertIsNone(tz.codice_valido("fr"))
        self.assertIsNone(tz.codice_valido("../../etc/passwd"))
        self.assertIsNone(tz.codice_valido(None))
        self.assertIsNone(tz.codice_valido(["en"]))


class TestLinguaForzata(unittest.TestCase):
    """Per il PDF e la riga di comando: una lingua per il thread corrente, senza Streamlit."""

    def test_fuori_da_streamlit_e_italiano(self):
        self.assertEqual(tz.lingua_corrente(), "it")

    def test_forzata_dentro_il_blocco(self):
        with tz.lingua_forzata("es"):
            self.assertEqual(tz.lingua_corrente(), "es")
        self.assertEqual(tz.lingua_corrente(), "it")

    def test_annidata(self):
        with tz.lingua_forzata("en"):
            with tz.lingua_forzata("es"):
                self.assertEqual(tz.lingua_corrente(), "es")
            self.assertEqual(tz.lingua_corrente(), "en")

    def test_codice_non_previsto_o_none_non_cambia_nulla(self):
        with tz.lingua_forzata("en"):
            with tz.lingua_forzata("fr"):
                self.assertEqual(tz.lingua_corrente(), "en")
            with tz.lingua_forzata(None):
                self.assertEqual(tz.lingua_corrente(), "en")

    def test_ripristinata_anche_con_eccezione(self):
        with self.assertRaises(ValueError):
            with tz.lingua_forzata("es"):
                raise ValueError("x")
        self.assertEqual(tz.lingua_corrente(), "it")

    def test_isolata_per_thread(self):
        import threading
        visto = []
        with tz.lingua_forzata("es"):
            t = threading.Thread(target=lambda: visto.append(tz.lingua_corrente()))
            t.start(); t.join()
        self.assertEqual(visto, ["it"])

    def test_separatori_della_lingua(self):
        self.assertEqual(tz.separatori("en"), (",", "."))
        self.assertEqual(tz.separatori("es"), (".", ","))
        with tz.lingua_forzata("en"):
            self.assertEqual(tz.separatori(), (",", "."))
            self.assertEqual(tz.numero(1234.5, 1), "1,234.5")


class TestCataloghiReali(unittest.TestCase):
    """I cataloghi consegnati: caricati senza voci scartate e con le stesse chiavi."""

    def test_cataloghi_consegnati_puliti(self):
        cat = tz.Cataloghi(tz.CARTELLA_LOCALES, verifica_ogni_s=0)
        for codice in ("en", "es"):
            voci = cat.voci(codice)
            self.assertGreater(len(voci), 20, codice)          # OTM: ~30 voci (ThinkCore: >100)
            self.assertEqual(cat.problemi(codice), [], codice)
        self.assertEqual(set(cat.voci("en")), set(cat.voci("es")))


if __name__ == "__main__":
    unittest.main()
