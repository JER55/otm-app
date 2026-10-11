# -*- coding: utf-8 -*-
"""Codici di prova di Otmflow.  python -m unittest test_licenze_otm -v"""
import unittest

import licenze_otm as lic

K = "k" * 40
T0 = 1_760_000_000


class TestLicenze(unittest.TestCase):
    def test_valido_fino_alla_scadenza_esclusa(self):
        c, ident, scad = lic.genera(K, "1h", ora=T0)
        self.assertEqual(scad, T0 + 3600)
        self.assertTrue(lic.verifica(K, c, ora=T0 + 3599).ok)
        e = lic.verifica(K, c, ora=T0 + 3600)
        self.assertEqual((e.ok, e.motivo, e.id), (False, "scaduta", ident))

    def test_trenta_giorni(self):
        c, _, scad = lic.genera(K, "30g", ora=T0)
        self.assertEqual(scad - T0, 30 * 86400)
        self.assertTrue(lic.verifica(K, c, ora=T0 + 29 * 86400).ok)

    def test_formato_codice(self):
        c, _, _ = lic.genera(K, "1h", ora=T0)
        self.assertRegex(c, r"^OTM(-[A-Z2-7]{4}){6}$")

    def test_chiave_diversa_rifiuta(self):
        c, _, _ = lic.genera(K, "30g", ora=T0)
        self.assertEqual(lic.verifica("x" * 40, c, ora=T0).motivo, "firma")

    def test_ogni_carattere_modificato_rifiuta(self):
        c, _, _ = lic.genera(K, "30g", ora=T0)
        for i, ch in enumerate(c):
            if ch in "-" or i < 4:
                continue
            altro = "B" if ch != "B" else "C"
            self.assertFalse(lic.verifica(K, c[:i] + altro + c[i + 1:], ora=T0).ok, i)

    def test_refusi_tollerati(self):
        c, _, _ = lic.genera(K, "30g", ora=T0)
        self.assertTrue(lic.verifica(K, "  " + c.lower().replace("-", " ") + " ", ora=T0).ok)
        self.assertTrue(lic.verifica(K, c[4:], ora=T0).ok)                 # senza prefisso
        self.assertTrue(lic.verifica(K, "0" + c[1:], ora=T0).ok)           # 0TM invece di OTM

    def test_revoca(self):
        c, ident, _ = lic.genera(K, "30g", ora=T0)
        self.assertEqual(lic.verifica(K, c, ora=T0, revocati=[ident.lower()]).motivo, "revocata")
        self.assertEqual(lic.verifica(K, c, ora=T0, revocati=ident).motivo, "revocata")
        self.assertTrue(lic.verifica(K, c, ora=T0, revocati=["00000000"]).ok)

    def test_chiave_corta_o_assente(self):
        self.assertEqual(lic.verifica("corta", "OTM-AAAA", ora=T0).motivo, "chiave")
        self.assertEqual(lic.verifica(None, "OTM-AAAA", ora=T0).motivo, "chiave")
        with self.assertRaises(ValueError):
            lic.genera("corta", "1h")

    def test_input_spazzatura(self):
        for x in (None, "", "password", "OTM-", "OTM-" + "A" * 30, 123, "<script>"):
            self.assertFalse(lic.verifica(K, x, ora=T0).ok, x)

    def test_durate(self):
        self.assertEqual(lic.durata_s("30g"), 30 * 86400)
        self.assertEqual(lic.durata_s("7d"), 7 * 86400)
        self.assertEqual(lic.durata_s("1h"), 3600)
        self.assertEqual(lic.durata_s(" 90 m "), 5400)
        self.assertEqual(lic.durata_s("45min"), 2700)
        for x in ("", "30", "0h", "400g", "1 settimana", "-1h"):
            with self.assertRaises(ValueError):
                lic.durata_s(x)

    def test_codici_diversi_a_ogni_emissione(self):
        a, ia, _ = lic.genera(K, "1h", ora=T0)
        b, ib, _ = lic.genera(K, "1h", ora=T0)
        self.assertNotEqual(ia, ib)
        self.assertNotEqual(a, b)

    def test_nuova_chiave_abbastanza_lunga(self):
        self.assertGreaterEqual(len(lic.nuova_chiave()), lic.MIN_CHIAVE)


if __name__ == "__main__":
    unittest.main()
