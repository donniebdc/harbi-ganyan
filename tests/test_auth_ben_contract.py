# -*- coding: utf-8 -*-
"""Faz X2A: /auth/ben response sozlesme testleri.

Mevcut DB/JWT gerektirmeden izole birim testleri.
"""
from __future__ import annotations
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta


class _FakeErisim:
    def __init__(self, is_vip=False):
        self.is_vip = is_vip


def _make_user(rol="USER", is_admin=False, tier="standart",
               vip_until=None, aktif=True, email_dogrulandi=True, uid=99):
    u = MagicMock()
    u.id = uid
    u.email = "test@example.com"
    u.tier = tier
    u.vip_until = vip_until
    u.email_dogrulandi = email_dogrulandi
    u.is_admin = is_admin
    u.rol = rol
    u.aktif = aktif
    return u


class BenResponseContractTests(unittest.TestCase):

    def _call_ben(self, user, is_vip=False):
        from app.api.auth import ben
        db = MagicMock()
        with patch("app.api.auth.erisim_coz", return_value=_FakeErisim(is_vip)):
            result = ben(user=user, db=db)
        return result

    def _assertFields(self, result):
        zorunlu = ["id","email","tier","vip_until","email_dogrulandi",
                   "is_admin","rol","is_editor","is_vip","aktif"]
        d = result.model_dump()
        for f in zorunlu:
            self.assertIn(f, d)
        self.assertNotIn("sifre_hash", d)
        self.assertNotIn("token", d)

    def test_user_rolu_is_editor_false(self):
        u = _make_user(rol="USER")
        r = self._call_ben(u)
        self._assertFields(r)
        self.assertFalse(r.is_editor)
        self.assertFalse(r.is_vip)
        self.assertEqual(r.rol, "USER")
        self.assertTrue(r.aktif)

    def test_editor_rolu_is_editor_true(self):
        u = _make_user(rol="EDITOR")
        r = self._call_ben(u)
        self.assertTrue(r.is_editor)
        self.assertEqual(r.rol, "EDITOR")

    def test_admin_rolu_is_editor_true(self):
        u = _make_user(rol="ADMIN", is_admin=True)
        r = self._call_ben(u)
        self.assertTrue(r.is_editor)
        self.assertTrue(r.is_admin)

    def test_is_admin_true_user_rolu_is_editor_true(self):
        u = _make_user(rol="USER", is_admin=True)
        r = self._call_ben(u)
        self.assertTrue(r.is_editor)

    def test_aktif_vip_is_vip_true(self):
        vip_bitis = datetime.utcnow() + timedelta(days=30)
        u = _make_user(tier="vip", vip_until=vip_bitis)
        r = self._call_ben(u, is_vip=True)
        self.assertTrue(r.is_vip)
        self.assertEqual(r.tier, "vip")
        self.assertIsNotNone(r.vip_until)

    def test_suresi_gecmis_vip_is_vip_false(self):
        eski = datetime(2020, 1, 1)
        u = _make_user(tier="standart", vip_until=eski)
        r = self._call_ben(u, is_vip=False)
        self.assertFalse(r.is_vip)

    def test_vip_until_none_serializasyon(self):
        u = _make_user(vip_until=None)
        r = self._call_ben(u)
        self.assertIsNone(r.vip_until)

    def test_vip_until_isoformat_string(self):
        dt = datetime(2026, 9, 1, 12, 0, 0)
        u = _make_user(vip_until=dt)
        r = self._call_ben(u, is_vip=True)
        self.assertIsInstance(r.vip_until, str)
        self.assertIn("2026", r.vip_until)

    def test_pasif_kullanici_aktif_false(self):
        u = _make_user(aktif=False)
        r = self._call_ben(u)
        self.assertFalse(r.aktif)

    def test_mevcut_alanlar_korundu(self):
        u = _make_user()
        r = self._call_ben(u)
        d = r.model_dump()
        for f in ["id","email","tier","email_dogrulandi","is_admin"]:
            self.assertIn(f, d)


if __name__ == "__main__":
    unittest.main()



class AdminRoleContractFixTests(unittest.TestCase):
    """X2F-4: is_admin=bool(user.is_admin) kaldırıldı — rol string kolonu öncelikli.

    Regresyon: rol=ADMIN, legacy is_admin=False → is_admin=True olmali.
    """

    def _call_ben(self, user, is_vip=False):
        from app.api.auth import ben
        db = MagicMock()
        with patch("app.api.auth.erisim_coz", return_value=_FakeErisim(is_vip)):
            result = ben(user=user, db=db)
        return result

    def test_admin_rol_legacy_false_is_admin_true(self):
        """Kök neden: rol=ADMIN ama legacy is_admin=False → is_admin=True olmalı."""
        u = _make_user(rol="ADMIN", is_admin=False)
        r = self._call_ben(u)
        self.assertTrue(r.is_admin, "rol=ADMIN => is_admin=True (legacy bool irrelevant)")

    def test_admin_rol_legacy_true_is_admin_true(self):
        """Geriye uyumluluk: rol=ADMIN ve is_admin=True → is_admin=True (değişmez)."""
        u = _make_user(rol="ADMIN", is_admin=True)
        r = self._call_ben(u)
        self.assertTrue(r.is_admin)

    def test_editor_rol_is_admin_false(self):
        """EDITOR rol → is_admin=False."""
        u = _make_user(rol="EDITOR", is_admin=False)
        r = self._call_ben(u)
        self.assertFalse(r.is_admin)

    def test_user_rol_is_admin_false(self):
        """USER rol → is_admin=False."""
        u = _make_user(rol="USER", is_admin=False)
        r = self._call_ben(u)
        self.assertFalse(r.is_admin)

    def test_admin_rol_is_editor_true(self):
        """ADMIN rol → is_editor=True (ADMIN editör yetkisi de içerir)."""
        u = _make_user(rol="ADMIN", is_admin=False)
        r = self._call_ben(u)
        self.assertTrue(r.is_editor)

    def test_editor_rol_is_editor_true(self):
        u = _make_user(rol="EDITOR")
        r = self._call_ben(u)
        self.assertTrue(r.is_editor)
        self.assertFalse(r.is_admin)

    def test_user_rol_is_editor_false(self):
        u = _make_user(rol="USER")
        r = self._call_ben(u)
        self.assertFalse(r.is_editor)
        self.assertFalse(r.is_admin)

    def test_admin_rol_korunur(self):
        """rol alanı değişmeden döner."""
        u = _make_user(rol="ADMIN", is_admin=False)
        r = self._call_ben(u)
        self.assertEqual(r.rol, "ADMIN")

    def test_legacy_admin_bool_only_is_still_editor(self):
        """Legacy: rol=USER ama is_admin=True → is_editor=True, is_admin=True (geriye uyumluluk)."""
        u = _make_user(rol="USER", is_admin=True)
        r = self._call_ben(u)
        self.assertTrue(r.is_editor)
        self.assertTrue(r.is_admin)
