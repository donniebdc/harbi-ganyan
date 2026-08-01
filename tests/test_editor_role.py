# -*- coding: utf-8 -*-
"""require_editor izole birim testleri (DB/token gerektirmez).

Dependency dogrudan fonksiyon olarak cagrilir; Kullanici yerine ayni alanlari
tasiyan basit fixture nesnesi kullanilir (require_editor yalniz rol/is_admin okur).
"""
from __future__ import annotations
import unittest

from fastapi import HTTPException

from app.deps import require_editor


class _FakeUser:
    def __init__(self, rol, is_admin):
        self.rol = rol
        self.is_admin = is_admin


class RequireEditorTests(unittest.TestCase):
    def _expect_403(self, user):
        with self.assertRaises(HTTPException) as ctx:
            require_editor(user=user)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_user_rolu_reddedilir(self):
        self._expect_403(_FakeUser("USER", False))

    def test_editor_rolu_gecer(self):
        u = _FakeUser("EDITOR", False)
        self.assertIs(require_editor(user=u), u)

    def test_admin_rolu_gecer(self):
        u = _FakeUser("ADMIN", False)
        self.assertIs(require_editor(user=u), u)

    def test_user_rolu_is_admin_true_gecer(self):
        # Geriye uyumluluk: is_admin=True her zaman gecer.
        u = _FakeUser("USER", True)
        self.assertIs(require_editor(user=u), u)

    def test_legacy_rol_none_is_admin_true_gecer(self):
        u = _FakeUser(None, True)
        self.assertIs(require_editor(user=u), u)

    def test_legacy_rol_none_is_admin_false_reddedilir(self):
        self._expect_403(_FakeUser(None, False))


if __name__ == "__main__":
    unittest.main()
