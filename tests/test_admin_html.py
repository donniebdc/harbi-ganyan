# -*- coding: utf-8 -*-
"""admin.html statik kontrolleri (Faz 1C)."""
from __future__ import annotations
import re
import unittest
from pathlib import Path

HTML = (Path(__file__).resolve().parents[1] / "app" / "static" / "admin.html"
        ).read_text(encoding="utf-8")


class AdminHtmlTests(unittest.TestCase):
    def test_yeni_bloklar_var(self):
        for parca in ["VIP Mesaj", "hediyeUserId", "1 Hafta Hediye VIP Tanımla",
                      "Gün Ekle", "Tarih Belirle", "VIP Bitir"]:
            self.assertIn(parca, HTML, parca)

    def test_mevcut_bloklar_korunmus(self):
        for parca in ["Kullanıcı Ekle", "Bildirim Gönder", "Şifre",
                      "hg_admin_token", "tierFilter"]:
            self.assertIn(parca, HTML, parca)
        # +7g/+14g/+30g/+60g butonlari [7,14,30,60] dongusuyle uretiliyor
        self.assertIn("[7,14,30,60]", HTML)
        self.assertIn("`+${g}g`", HTML)

    def test_manuel_uretim_kaldirildi(self):
        for parca in ["Manuel Üretim", "Tahmin Motoru", "/admin/api/uret",
                      "uret/durum", "uretPoll", "uretBaslat"]:
            self.assertNotIn(parca, HTML, parca)

    def test_xss_innerhtml_yok(self):
        self.assertNotIn("innerHTML", HTML,
                         "kullanici verisi icin innerHTML kullanilmamali")
        # dinamik icerik textContent / createElement ile
        self.assertIn("textContent", HTML)
        self.assertIn("createElement", HTML)
        self.assertIn("replaceChildren", HTML)

    def test_template_interpolasyonu_dom_dogru(self):
        # Satir uretiminde kullanici emaili el('td', null, u.email) ile basiliyor
        self.assertIn("el('td', null, u.email)", HTML)
        # eski tehlikeli desen yok:
        self.assertIsNone(re.search(r"innerHTML\s*=", HTML))

    def test_idempotency_uuid(self):
        self.assertIn("idempotency_key", HTML)
        self.assertIn("randomUUID", HTML)


if __name__ == "__main__":
    unittest.main()
