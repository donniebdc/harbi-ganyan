# -*- coding: utf-8 -*-
"""Admin VIP API testleri (TestClient + dependency override, SQLite in-memory).

Production main.py lifespan'i KULLANILMAZ (JSONB tablolari SQLite'ta olusmaz);
yalniz admin router'i iceren kucuk bir FastAPI app kurulur.
"""
from __future__ import annotations
import unittest
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.deps import require_user
from app.models import Bildirim, GonderilenBildirim, Kullanici, Uyelik
from app.api import admin as admin_api
from app import fcm, uyelik_servis as srv

NOW = datetime.utcnow()


class _Ctx:
    """Test baglaminda aktif principal + fake push sayaci."""
    principal: Kullanici | None = None
    push_calls: list = []
    push_fail = False


def _fake_push(db, ids, baslik, mesaj, data):
    if _Ctx.push_fail:
        raise RuntimeError("fcm test hatasi")
    _Ctx.push_calls.append((tuple(ids), baslik, mesaj))
    return len(ids)


class AdminVipApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://",
                                   connect_args={"check_same_thread": False},
                                   poolclass=StaticPool, future=True)
        Base.metadata.create_all(cls.engine, tables=[
            Kullanici.__table__, Uyelik.__table__,
            Bildirim.__table__, GonderilenBildirim.__table__])
        cls.Session = sessionmaker(bind=cls.engine, future=True)
        app = FastAPI()
        app.include_router(admin_api.router)

        def _db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[require_user] = lambda: _Ctx.principal
        cls.client = TestClient(app)
        cls._orig_push = fcm.kullanicilara_push
        fcm.kullanicilara_push = _fake_push

    @classmethod
    def tearDownClass(cls):
        fcm.kullanicilara_push = cls._orig_push
        cls.engine.dispose()

    def setUp(self):
        _Ctx.push_calls = []
        _Ctx.push_fail = False
        db = self.Session()
        for t in (Bildirim, GonderilenBildirim, Uyelik, Kullanici):
            db.query(t).delete()
        self.admin = Kullanici(email="admin@t.t", sifre_hash="x", tier="standart",
                               is_admin=True, rol="ADMIN", aktif=True,
                               email_dogrulandi=True)
        self.user = Kullanici(email="std@t.t", sifre_hash="x", tier="standart",
                              is_admin=False, rol="USER", aktif=True,
                              email_dogrulandi=True)
        db.add_all([self.admin, self.user])
        db.commit()
        db.refresh(self.admin); db.refresh(self.user)
        self.uid = self.user.id
        db.close()
        _Ctx.principal = self.admin

    def _vip(self, uid, body):
        return self.client.patch(f"/admin/api/kullanicilar/{uid}/vip", json=body)

    # 1
    def test_add_days_200(self):
        r = self._vip(self.uid, {"operation": "add_days", "days": 5})
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertTrue(j["ok"] and j["is_vip"])
        self.assertEqual(j["vip_source"], "MANUAL")
        self.assertIsNone(j["old_vip_until"])
        self.assertIsNotNone(j["new_vip_until"])

    # 2
    def test_set_until_200(self):
        hedef = (NOW + timedelta(days=10)).isoformat()
        r = self._vip(self.uid, {"operation": "set_until", "vip_until": hedef})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(r.json()["is_vip"])

    # 3
    def test_expire_200(self):
        self._vip(self.uid, {"operation": "add_days", "days": 5})
        r = self._vip(self.uid, {"operation": "expire"})
        self.assertEqual(r.status_code, 200, r.text)
        j = r.json()
        self.assertFalse(j["is_vip"])
        self.assertFalse(j["google_play_active"])

    # 4-5
    def test_user_ve_editor_403(self):
        for rol in ("USER", "EDITOR"):
            _Ctx.principal = self.user
            self.user.rol = rol
            r = self._vip(self.uid, {"operation": "add_days", "days": 5})
            self.assertEqual(r.status_code, 403, rol)

    # 6
    def test_olmayan_kullanici_404(self):
        r = self._vip(999999, {"operation": "add_days", "days": 5})
        self.assertEqual(r.status_code, 404)

    # 7-9
    def test_days_sinirlari_422(self):
        for d in (0, -1, 366):
            r = self._vip(self.uid, {"operation": "add_days", "days": d})
            self.assertEqual(r.status_code, 422, f"days={d}")

    # 10
    def test_bozuk_tarih_422(self):
        r = self._vip(self.uid, {"operation": "set_until", "vip_until": "bozuk-tarih"})
        self.assertEqual(r.status_code, 422)

    # 11
    def test_operation_eksik_422(self):
        r = self._vip(self.uid, {"days": 5})
        self.assertEqual(r.status_code, 422)

    # 12
    def test_add_days_days_yok_422(self):
        r = self._vip(self.uid, {"operation": "add_days"})
        self.assertEqual(r.status_code, 422)

    # 13
    def test_set_until_vip_until_yok_422(self):
        r = self._vip(self.uid, {"operation": "set_until"})
        self.assertEqual(r.status_code, 422)

    # 14-15
    def test_expire_gp_korunur_ve_efektif_alanlar(self):
        db = self.Session()
        db.add(Uyelik(kullanici_id=self.uid, tier="vip", kaynak="google_play",
                      aktif=True, purchase_token="tok-gp-1",
                      expires_at=NOW + timedelta(days=3)))
        u = db.get(Kullanici, self.uid)
        u.tier = "vip"
        db.commit(); db.close()
        r = self._vip(self.uid, {"operation": "expire"})
        j = r.json()
        self.assertTrue(j["is_vip"])                 # GP korundu
        self.assertTrue(j["google_play_active"])
        self.assertEqual(j["vip_source"], "GOOGLE_PLAY")
        self.assertIsNotNone(j["effective_until"])

    # ── Hediye VIP ──────────────────────────────────────────────────────────
    def _hediye(self, uid, key="k1"):
        return self.client.post(f"/admin/api/kullanicilar/{uid}/hediye-vip",
                                json={"idempotency_key": key})

    def test_hediye_standart_7_gun(self):
        r = self._hediye(self.uid)
        self.assertEqual(r.status_code, 201, r.text)
        j = r.json()
        yeni = datetime.fromisoformat(j["new_vip_until"])
        self.assertAlmostEqual((yeni - datetime.utcnow()).total_seconds(),
                               7 * 86400, delta=120)
        self.assertTrue(j["is_vip"] and j["notification_created"] and j["push_sent"])

    def test_hediye_aktif_manuel_bitise_ekler(self):
        self._vip(self.uid, {"operation": "add_days", "days": 3})
        r = self._hediye(self.uid, "k2")
        j = r.json()
        eski = datetime.fromisoformat(j["old_vip_until"])
        yeni = datetime.fromisoformat(j["new_vip_until"])
        self.assertAlmostEqual((yeni - eski).total_seconds(), 7 * 86400, delta=5)

    def test_hediye_gecmisten_simdiden(self):
        self._vip(self.uid, {"operation": "set_until",
                             "vip_until": (NOW - timedelta(days=2)).isoformat()})
        r = self._hediye(self.uid, "k3")
        yeni = datetime.fromisoformat(r.json()["new_vip_until"])
        self.assertAlmostEqual((yeni - datetime.utcnow()).total_seconds(),
                               7 * 86400, delta=120)

    def test_hediye_bildirim_sabit_metin(self):
        self._hediye(self.uid, "k4")
        db = self.Session()
        b = db.query(Bildirim).filter_by(kullanici_id=self.uid).one()
        self.assertEqual(b.baslik, "1 Hafta Hediye Vip")
        self.assertEqual(b.mesaj, "1 Hafta Hediye Vip hesabınıza tanımlanmıştır.")
        db.close()

    def test_hediye_push_hatasi_vip_korunur(self):
        _Ctx.push_fail = True
        r = self._hediye(self.uid, "k5")
        j = r.json()
        self.assertTrue(j["ok"] and j["is_vip"] and j["notification_created"])
        self.assertFalse(j["push_sent"])
        db = self.Session()
        self.assertEqual(db.query(Bildirim).filter_by(kullanici_id=self.uid).count(), 1)
        db.close()

    def test_hediye_idempotency(self):
        r1 = self._hediye(self.uid, "ayni-key")
        t1 = r1.json()["new_vip_until"]
        r2 = self._hediye(self.uid, "ayni-key")
        j2 = r2.json()
        self.assertTrue(j2.get("repeated"))
        self.assertEqual(j2["new_vip_until"], t1)  # sure TEKRAR eklenmedi
        r3 = self._hediye(self.uid, "farkli-key")  # yeni islem sayilir
        t3 = datetime.fromisoformat(r3.json()["new_vip_until"])
        self.assertAlmostEqual((t3 - datetime.fromisoformat(t1)).total_seconds(),
                               7 * 86400, delta=5)

    def test_hediye_404_ve_403(self):
        self.assertEqual(self._hediye(999999).status_code, 404)
        _Ctx.principal = self.user
        self.assertEqual(self._hediye(self.uid, "k9").status_code, 403)

    # ── Entegrasyon akisi ───────────────────────────────────────────────────
    def test_entegrasyon_akisi(self):
        # 5 gun ekle -> resolver VIP -> gecmise cek -> VIP degil -> hediye -> tekrar VIP
        self._vip(self.uid, {"operation": "add_days", "days": 5})
        db = self.Session()
        u = db.get(Kullanici, self.uid)
        self.assertTrue(srv.erisim_coz(db, u).is_vip)
        db.close()
        self._vip(self.uid, {"operation": "set_until",
                             "vip_until": (NOW - timedelta(hours=1)).isoformat()})
        db = self.Session()
        u = db.get(Kullanici, self.uid)
        self.assertFalse(srv.erisim_coz(db, u).is_vip)
        db.close()
        self._hediye(self.uid, "flow-key")
        db = self.Session()
        u = db.get(Kullanici, self.uid)
        self.assertTrue(srv.erisim_coz(db, u).is_vip)
        db.close()
        # kullanici listesi additive alanlar
        r = self.client.get("/admin/api/kullanicilar")
        row = [x for x in r.json()["kullanicilar"] if x["id"] == self.uid][0]
        self.assertIn("is_vip", row)
        self.assertIn("vip_kaynak", row)
        self.assertTrue(row["is_vip"])


if __name__ == "__main__":
    unittest.main()
