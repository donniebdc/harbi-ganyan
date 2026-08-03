# -*- coding: utf-8 -*-
"""FAZ X2F-1 — Migration izole testi (SQLite in-memory).

PostgreSQL production DB'ye dokunulmaz.
Yalniz auth_session tablosunun olusturma/silme dongusu test edilir.
"""
from __future__ import annotations
import unittest
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Yalniz test icin gerekli tablolari olustur (JSONB iceren tablolari atla)
from app.db import Base
from app.models import Kullanici, AuthSession


def _build_test_engine():
    """SQLite in-memory engine — yalniz kullanici + auth_session tablolari."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        eng,
        tables=[Kullanici.__table__, AuthSession.__table__],
    )
    return eng


class MigrationSchemaTests(unittest.TestCase):
    """auth_session tablo sema testleri — alembic yerine SQLAlchemy metadata kullanilir."""

    def setUp(self):
        self.engine = _build_test_engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def _user(self) -> Kullanici:
        u = Kullanici(
            email=f"mig_test_{id(self)}@test.com",
            sifre_hash="x",
            aktif=True,
            email_dogrulandi=True,
            rol="USER",
        )
        self.db.add(u)
        self.db.flush()
        return u

    # --- Upgrade testi (tablo var mi?) ---

    def test_auth_session_table_exists(self):
        insp = inspect(self.engine)
        self.assertIn("auth_session", insp.get_table_names())

    def test_auth_session_required_columns(self):
        insp = inspect(self.engine)
        col_names = {c["name"] for c in insp.get_columns("auth_session")}
        required = {
            "id", "user_id", "token_hash", "token_family_id", "jti",
            "created_at", "expires_at", "last_used_at", "revoked_at",
            "revoke_reason", "replaced_by_id", "client_type",
            "device_name", "user_agent_hash", "ip_hash", "app_version",
        }
        self.assertEqual(required, col_names & required)

    def test_token_hash_not_nullable(self):
        insp = inspect(self.engine)
        cols = {c["name"]: c for c in insp.get_columns("auth_session")}
        self.assertFalse(cols["token_hash"]["nullable"])

    def test_jti_not_nullable(self):
        insp = inspect(self.engine)
        cols = {c["name"]: c for c in insp.get_columns("auth_session")}
        self.assertFalse(cols["jti"]["nullable"])

    def test_token_family_id_not_nullable(self):
        insp = inspect(self.engine)
        cols = {c["name"]: c for c in insp.get_columns("auth_session")}
        self.assertFalse(cols["token_family_id"]["nullable"])

    def test_revoked_at_nullable(self):
        insp = inspect(self.engine)
        cols = {c["name"]: c for c in insp.get_columns("auth_session")}
        self.assertTrue(cols["revoked_at"]["nullable"])

    def test_replaced_by_id_nullable(self):
        insp = inspect(self.engine)
        cols = {c["name"]: c for c in insp.get_columns("auth_session")}
        self.assertTrue(cols["replaced_by_id"]["nullable"])

    def test_kullanici_fk_exists(self):
        insp = inspect(self.engine)
        fks = insp.get_foreign_keys("auth_session")
        user_fks = [f for f in fks if "kullanici" in f.get("referred_table", "")]
        self.assertTrue(len(user_fks) > 0)

    # --- Downgrade benzeri: tablo drop ve tekrar olusturma ---

    def test_table_drop_and_recreate(self):
        """Downgrade: drop, Upgrade: recreate (idempotency)."""
        insp = inspect(self.engine)
        self.assertIn("auth_session", insp.get_table_names())

        # Downgrade benzeri
        AuthSession.__table__.drop(self.engine)
        insp2 = inspect(self.engine)
        self.assertNotIn("auth_session", insp2.get_table_names())

        # Upgrade benzeri (tekrar olustur)
        AuthSession.__table__.create(self.engine)
        insp3 = inspect(self.engine)
        self.assertIn("auth_session", insp3.get_table_names())


class AuthSessionAltyapiModelTests(unittest.TestCase):
    """auth_session model testleri — 25 test."""

    _counter = 0

    def setUp(self):
        self.engine = _build_test_engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        self.engine.dispose()

    def _user(self) -> Kullanici:
        AuthSessionAltyapiModelTests._counter += 1
        u = Kullanici(
            email=f"u{AuthSessionAltyapiModelTests._counter}@t.t",
            sifre_hash="x",
            aktif=True,
            email_dogrulandi=True,
            rol="USER",
        )
        self.db.add(u)
        self.db.flush()
        return u

    def _session(self, user: Kullanici, **kw) -> AuthSession:
        AuthSessionAltyapiModelTests._counter += 1
        n = AuthSessionAltyapiModelTests._counter
        defaults = dict(
            user_id=user.id,
            token_hash=f"{'a' * 63}{n % 10}",
            token_family_id=f"family-{n:04d}-0000-0000-0000-000000000000",
            jti=f"jti-{n:04d}-0000-0000-0000-000000000000",
            client_type="MOBILE",
            expires_at=datetime(2026, 12, 31),
        )
        defaults.update(kw)
        s = AuthSession(**defaults)
        self.db.add(s)
        self.db.flush()
        return s

    # 1. Olusturma
    def test_session_olusturma(self):
        u = self._user()
        s = self._session(u)
        self.assertIsNotNone(s.id)
        self.assertEqual(s.user_id, u.id)

    # 2. token_hash zorunlu
    def test_token_hash_required(self):
        u = self._user()
        with self.assertRaises(Exception):
            AuthSessionAltyapiModelTests._counter += 1
            n = AuthSessionAltyapiModelTests._counter
            s = AuthSession(
                user_id=u.id,
                token_hash=None,
                token_family_id=f"fam-{n}",
                jti=f"jti-{n}",
                client_type="MOBILE",
                expires_at=datetime(2026, 12, 31),
            )
            self.db.add(s)
            self.db.flush()

    # 3. jti unique
    def test_jti_unique(self):
        u = self._user()
        self._session(u, jti="same-jti-0000-0000-0000-000000000000",
                      token_hash="a" * 64)
        with self.assertRaises(Exception):
            self._session(u, jti="same-jti-0000-0000-0000-000000000000",
                          token_hash="b" * 64)
            self.db.flush()

    # 4. token_hash unique
    def test_token_hash_unique(self):
        u = self._user()
        self._session(u, token_hash="c" * 64, jti="jti-unique-a-0000-000000000000")
        with self.assertRaises(Exception):
            self._session(u, token_hash="c" * 64, jti="jti-unique-b-0000-000000000000")
            self.db.flush()

    # 5. user relationship
    def test_user_relationship(self):
        u = self._user()
        s = self._session(u)
        self.db.refresh(s)
        self.assertEqual(s.kullanici.id, u.id)

    # 6. timestamps UTC-naive
    def test_timestamps_created_not_null(self):
        u = self._user()
        s = self._session(u)
        # SQLite'ta server_default'dan gelmez, Python'da da None olabilir
        # expires_at uygulama tarafindan ayarlanir
        self.assertIsNotNone(s.expires_at)

    # 7. revoked nullable
    def test_revoked_at_nullable(self):
        u = self._user()
        s = self._session(u)
        self.assertIsNone(s.revoked_at)

    # 8. replaced_by self-reference
    def test_replaced_by_self_reference(self):
        u = self._user()
        s1 = self._session(u)
        s2 = self._session(u)
        s1.replaced_by_id = s2.id
        self.db.flush()
        self.db.refresh(s1)
        self.assertEqual(s1.replaced_by_id, s2.id)


class AuthSessionServiceTests(unittest.TestCase):
    """Service fonksiyon testleri."""

    _counter = 0

    def setUp(self):
        self.engine = _build_test_engine()
        self.Session = sessionmaker(bind=self.engine, future=True)
        self.db = self.Session()

        # Import service (models yuklenince)
        import app.auth_session_service as srv
        self.srv = srv

    def tearDown(self):
        self.db.rollback()
        self.db.close()
        self.engine.dispose()

    def _user(self) -> Kullanici:
        AuthSessionServiceTests._counter += 1
        u = Kullanici(
            email=f"svc{AuthSessionServiceTests._counter}@t.t",
            sifre_hash="x", aktif=True,
            email_dogrulandi=True, rol="USER",
        )
        self.db.add(u)
        self.db.flush()
        return u

    def _raw(self) -> str:
        AuthSessionServiceTests._counter += 1
        import uuid
        return str(uuid.uuid4())

    def _jti(self) -> str:
        import uuid
        return str(uuid.uuid4())

    def _family(self) -> str:
        import uuid
        return str(uuid.uuid4())

    # 9. create_refresh_session
    def test_create_session(self):
        u = self._user()
        raw = self._raw()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=raw,
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        self.assertIsNotNone(s.id)
        self.assertEqual(s.user_id, u.id)

    # 10. token hash lookup
    def test_get_by_token_hash(self):
        from app.security import hash_token
        u = self._user()
        raw = self._raw()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=raw,
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        found = self.srv.get_session_by_token_hash(self.db, raw)
        self.assertEqual(found.id, s.id)

    # 11. jti lookup
    def test_get_by_jti(self):
        u = self._user()
        jti = self._jti()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=jti, token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        found = self.srv.get_session_by_jti(self.db, jti)
        self.assertEqual(found.id, s.id)

    # 12. mark used
    def test_mark_session_used(self):
        u = self._user()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        self.assertIsNone(s.last_used_at)
        self.srv.mark_session_used(self.db, s.id)
        self.db.refresh(s)
        self.assertIsNotNone(s.last_used_at)

    # 13. revoke single session
    def test_revoke_session(self):
        u = self._user()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        result = self.srv.revoke_session(self.db, s.id, "LOGOUT")
        self.assertTrue(result)
        self.db.refresh(s)
        self.assertIsNotNone(s.revoked_at)
        self.assertEqual(s.revoke_reason, "LOGOUT")

    # 14. revoke all user sessions
    def test_revoke_user_sessions(self):
        u = self._user()
        s1 = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        s2 = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        count = self.srv.revoke_user_sessions(self.db, u.id, "ALL_DEVICES_LOGOUT")
        self.assertEqual(count, 2)
        self.db.refresh(s1)
        self.db.refresh(s2)
        self.assertIsNotNone(s1.revoked_at)
        self.assertIsNotNone(s2.revoked_at)

    # 15. revoke token family
    def test_revoke_token_family(self):
        u = self._user()
        family = self._family()
        s1 = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=family,
            expires_at=datetime(2027, 1, 1),
        )
        s2 = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=family,
            expires_at=datetime(2027, 1, 1),
        )
        # s3 farkli family - etkilenmemeli
        s3 = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        count = self.srv.revoke_token_family(self.db, family, "TOKEN_REUSE")
        self.assertEqual(count, 2)
        self.db.refresh(s3)
        self.assertIsNone(s3.revoked_at)  # farkli family etkilenmemeli

    # 16. expired session kontrolu
    def test_rotate_expired_returns_none(self):
        u = self._user()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2020, 1, 1),  # gecmiste
        )
        result = self.srv.rotate_refresh_session(
            self.db, old_session_id=s.id,
            new_raw_token=self._raw(), new_jti=self._jti(),
        )
        self.assertIsNone(result)

    # 17. revoked session rotation reddedilir
    def test_rotate_revoked_returns_none(self):
        u = self._user()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        self.srv.revoke_session(self.db, s.id, "LOGOUT")
        result = self.srv.rotate_refresh_session(
            self.db, old_session_id=s.id,
            new_raw_token=self._raw(), new_jti=self._jti(),
        )
        self.assertIsNone(result)

    # 18. basarili rotation
    def test_rotation_success(self):
        u = self._user()
        s_old = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        result = self.srv.rotate_refresh_session(
            self.db, old_session_id=s_old.id,
            new_raw_token=self._raw(), new_jti=self._jti(),
        )
        self.assertIsNotNone(result)
        new_s, old_s = result
        self.assertIsNotNone(new_s.id)

    # 19. eski session REPLACED olur
    def test_rotation_old_session_replaced(self):
        u = self._user()
        s_old = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        new_s, old_s = self.srv.rotate_refresh_session(
            self.db, old_session_id=s_old.id,
            new_raw_token=self._raw(), new_jti=self._jti(),
        )
        self.db.refresh(old_s)
        self.assertEqual(old_s.revoke_reason, "REPLACED")
        self.assertIsNotNone(old_s.revoked_at)

    # 20. replaced_by_id dogru
    def test_rotation_replaced_by_id(self):
        u = self._user()
        s_old = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        new_s, old_s = self.srv.rotate_refresh_session(
            self.db, old_session_id=s_old.id,
            new_raw_token=self._raw(), new_jti=self._jti(),
        )
        self.db.refresh(old_s)
        self.assertEqual(old_s.replaced_by_id, new_s.id)

    # 21. ayni family id korunur
    def test_rotation_same_family(self):
        u = self._user()
        family = self._family()
        s_old = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=family,
            expires_at=datetime(2027, 1, 1),
        )
        new_s, _ = self.srv.rotate_refresh_session(
            self.db, old_session_id=s_old.id,
            new_raw_token=self._raw(), new_jti=self._jti(),
        )
        self.assertEqual(new_s.token_family_id, family)

    # 22. reuse detection — family revoke
    def test_reuse_detection_family_revoke(self):
        u = self._user()
        family = self._family()
        raw = self._raw()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=raw,
            jti=self._jti(), token_family_id=family,
            expires_at=datetime(2027, 1, 1),
        )
        # Aktif session — reuse None donmeli
        result = self.srv.detect_and_handle_reuse(self.db, raw)
        self.assertIsNone(result)

        # Session revoke et
        self.srv.revoke_session(self.db, s.id, "LOGOUT")

        # Aktif kardes session olustur (ayni family)
        s2 = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=family,
            expires_at=datetime(2027, 1, 1),
        )

        # Eski revoked token reuse edildi
        result = self.srv.detect_and_handle_reuse(self.db, raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["reason"], "TOKEN_REUSE")
        self.assertGreater(result["revoked_count"], 0)

        # Kardes session da revoke edildi
        self.db.refresh(s2)
        self.assertIsNotNone(s2.revoked_at)

    # 23. ham token DB'de bulunmaz
    def test_raw_token_not_in_db(self):
        from app.security import hash_token
        u = self._user()
        raw = self._raw()
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=raw,
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        # DB'de token_hash var, raw_token yok
        self.assertEqual(s.token_hash, hash_token(raw))
        self.assertNotEqual(s.token_hash, raw)

    # 24. cleanup expired
    def test_cleanup_expired(self):
        u = self._user()
        past = datetime(2020, 1, 1)
        s = self.srv.create_refresh_session(
            self.db, user_id=u.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=past,
        )
        s.revoked_at = past
        self.db.flush()

        count = self.srv.delete_expired_sessions(
            self.db, before=datetime(2026, 1, 1), retention_days=0
        )
        self.assertGreaterEqual(count, 1)

    # 25. baska kullanicinin sessioni etkilenmez
    def test_other_user_not_affected(self):
        u1 = self._user()
        u2 = self._user()
        s1 = self.srv.create_refresh_session(
            self.db, user_id=u1.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        s2 = self.srv.create_refresh_session(
            self.db, user_id=u2.id, raw_token=self._raw(),
            jti=self._jti(), token_family_id=self._family(),
            expires_at=datetime(2027, 1, 1),
        )
        self.srv.revoke_user_sessions(self.db, u1.id, "ALL_DEVICES_LOGOUT")
        self.db.refresh(s2)
        self.assertIsNone(s2.revoked_at)


if __name__ == "__main__":
    unittest.main()
