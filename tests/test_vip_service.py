# -*- coding: utf-8 -*-
"""uyelik_servis birim testleri (SQLite in-memory, deterministik now fixture)."""
from __future__ import annotations
import unittest
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Kullanici, Uyelik
from app import uyelik_servis as srv

NOW = datetime(2026, 8, 1, 12, 0, 0)  # sabit test saati (UTC-naive)


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False},
                        poolclass=StaticPool, future=True)
    # JSONB iceren model tablolarindan kacinmak icin yalniz gerekli tablolar:
    Base.metadata.create_all(eng, tables=[
        Kullanici.__table__, Uyelik.__table__])
    return eng


class VipServiceTests(unittest.TestCase):
    def setUp(self):
        self.engine = _engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    _sayac = 0

    def _user(self, tier="standart", vip_until=None, vip_source=None) -> Kullanici:
        VipServiceTests._sayac += 1
        u = Kullanici(email=f"u{VipServiceTests._sayac}@t.t", sifre_hash="x", tier=tier,
                      vip_until=vip_until, vip_source=vip_source,
                      email_dogrulandi=True, is_admin=False, aktif=True, rol="USER")
        self.db.add(u)
        self.db.flush()
        return u

    def _gp(self, user, expires, aktif=True):
        VipServiceTests._sayac += 1
        r = Uyelik(kullanici_id=user.id, tier="vip", kaynak="google_play",
                   aktif=aktif, purchase_token=f"tok{user.id}-{VipServiceTests._sayac}",
                   expires_at=expires)
        self.db.add(r)
        self.db.flush()
        return r

    # 1
    def test_gelecek_manuel_vip(self):
        u = self._user("vip", NOW + timedelta(days=3), "manuel")
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertTrue(e.is_vip)
        self.assertEqual(e.source, "MANUAL")
        self.assertEqual(e.tier_for_response, "vip")

    # 2
    def test_gecmis_manuel_gp_yok_standart(self):
        u = self._user("vip", NOW - timedelta(days=1), "manuel")
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertFalse(e.is_vip)
        self.assertEqual(e.source, "NONE")
        self.assertTrue(e.expired_manual)
        self.assertEqual(e.tier_for_response, "standart")

    # 3
    def test_gecmis_manuel_gp_aktif_vip(self):
        u = self._user("vip", NOW - timedelta(days=1), "manuel")
        self._gp(u, NOW + timedelta(days=5))
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertTrue(e.is_vip)
        self.assertEqual(e.source, "GOOGLE_PLAY")
        self.assertTrue(e.google_play_active)

    # 4
    def test_null_vip_until_standart(self):
        u = self._user("standart")
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertFalse(e.is_vip)
        self.assertEqual(e.source, "NONE")

    # 5 — ESKI HATANIN CEKIRDEGI: tier=vip + vip_until NULL + hicbir aktif kaynak
    def test_null_vip_until_tier_vip_fail_closed(self):
        u = self._user("vip")  # vip_until NULL, uyelik yok
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertFalse(e.is_vip, "tier=vip tek basina VIP erisimi VERMEMELI")

    # 5b — admin'in SURESIZ atamasi (aktif admin uyelik, bitis NULL) VIP'tir
    def test_suresiz_admin_uyelik_vip(self):
        u = self._user("vip")
        self.db.add(Uyelik(kullanici_id=u.id, tier="vip", kaynak="admin",
                           aktif=True, bitis=None))
        self.db.flush()
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertTrue(e.is_vip)
        self.assertEqual(e.source, "MANUAL")
        self.assertIsNone(e.effective_until)

    # 6
    def test_add_days_aktife_ekler(self):
        u = self._user("vip", NOW + timedelta(days=3), "manuel")
        eski, yeni = srv.manuel_vip_gun_ekle(self.db, u, 5, NOW)
        self.assertEqual(yeni, NOW + timedelta(days=8))  # kalan sure korunur
        self.assertEqual(eski, NOW + timedelta(days=3))

    # 7
    def test_add_days_gecmiste_simdiden(self):
        u = self._user("vip", NOW - timedelta(days=2), "manuel")
        _, yeni = srv.manuel_vip_gun_ekle(self.db, u, 5, NOW)
        self.assertEqual(yeni, NOW + timedelta(days=5))

    # 8
    def test_add_days_null_simdiden(self):
        u = self._user("standart")
        _, yeni = srv.manuel_vip_gun_ekle(self.db, u, 5, NOW)
        self.assertEqual(yeni, NOW + timedelta(days=5))
        self.assertEqual(u.tier, "vip")
        self.assertEqual(u.vip_source, "manuel")

    # 9
    def test_add_days_tam_5_gun(self):
        u = self._user("standart")
        _, yeni = srv.manuel_vip_gun_ekle(self.db, u, 5, NOW)
        self.assertEqual((yeni - NOW).days, 5)

    # 10
    def test_set_until_gelecek_vip(self):
        u = self._user("standart")
        hedef = NOW + timedelta(days=10)
        _, yeni = srv.manuel_vip_tarih_belirle(self.db, u, hedef, NOW)
        self.assertEqual(yeni, hedef)
        self.assertEqual(u.tier, "vip")
        self.assertTrue(srv.erisim_coz(self.db, u, NOW).is_vip)

    # 11
    def test_set_until_gecmis_gecersiz(self):
        u = self._user("vip", NOW + timedelta(days=3), "manuel")
        srv.manuel_vip_tarih_belirle(self.db, u, NOW - timedelta(days=1), NOW)
        e = srv.erisim_coz(self.db, u, NOW)
        self.assertFalse(e.is_vip)
        self.assertEqual(u.tier, "standart")

    # 12
    def test_expire_bitirir(self):
        u = self._user("vip", NOW + timedelta(days=9), "manuel")
        srv.manuel_vip_gun_ekle(self.db, u, 1, NOW)  # uyelik kaydi da olussun
        srv.manuel_vip_bitir(self.db, u, NOW + timedelta(seconds=1))
        e = srv.erisim_coz(self.db, u, NOW + timedelta(seconds=2))
        self.assertFalse(e.is_vip)
        self.assertEqual(u.tier, "standart")
        self.assertIsNotNone(u.vip_until)  # audit: NULL yapilmaz

    # 13
    def test_expire_gp_bozulmaz(self):
        u = self._user("vip", NOW + timedelta(days=9), "manuel")
        gp = self._gp(u, NOW + timedelta(days=4))
        srv.manuel_vip_bitir(self.db, u, NOW)
        e = srv.erisim_coz(self.db, u, NOW + timedelta(seconds=1))
        self.assertTrue(e.is_vip)
        self.assertEqual(e.source, "GOOGLE_PLAY")
        self.assertTrue(gp.aktif)  # GP kaydina dokunulmadi
        self.assertEqual(u.tier, "vip")

    # 14
    def test_tz_aware_normalize(self):
        u = self._user("standart")
        aware = datetime(2026, 8, 11, 15, 0, tzinfo=timezone(timedelta(hours=3)))
        _, yeni = srv.manuel_vip_tarih_belirle(self.db, u, aware, NOW)
        self.assertIsNone(yeni.tzinfo)
        self.assertEqual(yeni, datetime(2026, 8, 11, 12, 0))  # UTC naive

    # 15 — now fixture deterministik (tum testler NOW ile calisti); temizlik testi
    def test_temizlik_idempotent(self):
        u1 = self._user("vip", NOW - timedelta(days=1), "manuel")   # dusmeli
        u2 = self._user("vip", NOW + timedelta(days=1), "manuel")   # kalmali
        u3 = self._user("vip")                                       # kalinti, dusmeli
        self.assertEqual(srv.suresi_dolan_manuel_temizle(self.db, NOW), 2)
        self.assertEqual(u1.tier, "standart")
        self.assertEqual(u2.tier, "vip")
        self.assertEqual(u3.tier, "standart")
        self.assertEqual(srv.suresi_dolan_manuel_temizle(self.db, NOW), 0)  # idempotent


if __name__ == "__main__":
    unittest.main()
