# -*- coding: utf-8 -*-
"""
Faz X2F-5 -- Kullanici Bazli Token V2 Canary Testleri
SQLite in-memory, production DB kullanmaz.
"""
from __future__ import annotations
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, "/opt/harbi_ganyan_backend")
os.environ.setdefault("HG_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("HG_JWT_SECRET", "test-secret-x2f5-must-be-long-enough-32!")
os.environ.setdefault("HG_AUTH_TOKEN_V2_ENABLED", "false")

from app.config import settings
from app.api.auth import is_token_v2_enabled_for_user
from app.models import Base, Kullanici, AuthSession, DogrulamaKodu, UserDevice, Bildirim, DeviceToken
from app.db import get_db
from app.main import app
from app.security import hash_sifre, hash_token
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_REQUIRED_TABLES = [
    "kullanici", "uyelik", "dogrulama_kodu", "bildirim",
    "device_token", "user_device", "auth_session",
]

_engine_c = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
_SessionC = sessionmaker(autocommit=False, autoflush=False, bind=_engine_c)


@pytest.fixture(scope="module")
def db_tables_c():
    meta = Base.metadata
    tables = [meta.tables[n] for n in _REQUIRED_TABLES]
    meta.create_all(_engine_c, tables=tables)
    yield
    meta.drop_all(_engine_c, tables=tables)


@pytest.fixture()
def db_c(db_tables_c):
    conn = _engine_c.connect()
    tx = conn.begin()
    sess = _SessionC(bind=conn)
    yield sess
    sess.close()
    tx.rollback()
    conn.close()


@pytest.fixture()
def canary_user(db_c):
    u = Kullanici(
        email="canary@internal.test",
        sifre_hash=hash_sifre("CanaryPass123!"),
        email_dogrulandi=True,
        tier="standart",
        rol="USER",
        aktif=True,
    )
    db_c.add(u)
    db_c.commit()
    db_c.refresh(u)
    return u


@pytest.fixture()
def legacy_user(db_c):
    u = Kullanici(
        email="legacy@internal.test",
        sifre_hash=hash_sifre("LegacyPass123!"),
        email_dogrulandi=True,
        tier="vip",
        rol="USER",
        aktif=True,
    )
    db_c.add(u)
    db_c.commit()
    db_c.refresh(u)
    return u


@pytest.fixture()
def client_c(db_c):
    app.dependency_overrides[get_db] = lambda: db_c
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestAllowlistParser:
    """Allowlist parser: fail-closed, whitespace, duplicate, gecersiz giris."""

    def test_empty_string_returns_empty_set(self):
        """C1: Bos string -> empty frozenset."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", ""):
            assert settings.token_v2_allowlist == frozenset()

    def test_whitespace_only_returns_empty_set(self):
        """C2: Yalniz whitespace -> empty frozenset."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "   "):
            assert settings.token_v2_allowlist == frozenset()

    def test_valid_single_id(self):
        """C3: Tek gecerli ID."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "42"):
            assert 42 in settings.token_v2_allowlist

    def test_valid_multiple_ids(self):
        """C4: Birden fazla gecerli ID."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "1,36,59"):
            assert settings.token_v2_allowlist == frozenset({1, 36, 59})

    def test_whitespace_trimmed_around_ids(self):
        """C5: ID etrafindaki bosluklar temizlenir."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", " 1 , 36 , 59 "):
            assert settings.token_v2_allowlist == frozenset({1, 36, 59})

    def test_duplicate_ids_deduplicated(self):
        """C6: Tekrarlayan IDler teke indirilir."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "5,5,5"):
            assert settings.token_v2_allowlist == frozenset({5})

    def test_invalid_string_ignored(self):
        """C7: Gecersiz string (harf) yok sayilir -- fail-closed."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "abc,42"):
            assert settings.token_v2_allowlist == frozenset({42})

    def test_zero_id_ignored(self):
        """C8: Sifir ID yok sayilir."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "0,5"):
            assert settings.token_v2_allowlist == frozenset({5})

    def test_negative_id_ignored(self):
        """C9: Negatif ID yok sayilir."""
        with patch.object(settings, "auth_token_v2_allowlist_user_ids", "-1,7"):
            assert settings.token_v2_allowlist == frozenset({7})


class TestResolver:
    """is_token_v2_enabled_for_user: global flag + allowlist kombinasyonlari."""

    def test_global_true_any_user_gets_v2(self):
        """R1: Global flag true -> herkes V2 alir."""
        with patch.object(settings, "auth_token_v2_enabled", True):
            assert is_token_v2_enabled_for_user(999) is True

    def test_global_true_none_user_id(self):
        """R2: Global flag true + user_id None -> True."""
        with patch.object(settings, "auth_token_v2_enabled", True):
            assert is_token_v2_enabled_for_user(None) is True

    def test_global_false_empty_allowlist_returns_false(self):
        """R3: Global false + bos allowlist -> false."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", ""):
                assert is_token_v2_enabled_for_user(1) is False

    def test_global_false_user_in_allowlist(self):
        """R4: Global false + kullanici allowlist'te -> True."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", "42"):
                assert is_token_v2_enabled_for_user(42) is True

    def test_global_false_user_not_in_allowlist(self):
        """R5: Global false + kullanici allowlist disinda -> False."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", "42"):
                assert is_token_v2_enabled_for_user(99) is False

    def test_none_user_id_returns_false(self):
        """R6: user_id None -> False."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", "42"):
                assert is_token_v2_enabled_for_user(None) is False

    def test_invalid_allowlist_entries_fail_closed(self):
        """R7: Gecersiz allowlist girisleri fail-closed."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", "abc,xyz"):
                assert is_token_v2_enabled_for_user(1) is False


class TestCanaryLogin:
    """Canary kullanici V2 login alir; legacy kullanici eski tokeni alir."""

    def test_allowlisted_user_gets_v2_response(self, client_c, canary_user):
        """L1: Allowlist'teki kullanici login'de V2 format alir."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", str(canary_user.id)):
                r = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["access_token"] != data["refresh_token"]
        assert data["expires_in"] == settings.access_token_minutes * 60

    def test_non_allowlisted_user_gets_legacy_response(self, client_c, legacy_user):
        """L2: Allowlist disindaki kullanici legacy token alir."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", "99999"):
                r = client_c.post("/auth/giris", json={"email": legacy_user.email, "sifre": "LegacyPass123!"})
        assert r.status_code == 200
        data = r.json()
        assert data["token"] == data["refresh_token"]

    def test_allowlisted_user_no_raw_token_in_db(self, client_c, canary_user, db_c):
        """L3: Allowlist kullanicisinin ham refresh token DB'ye yazilmaz."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", str(canary_user.id)):
                r = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
        assert r.status_code == 200
        raw_refresh = r.json()["refresh_token"]
        session = db_c.query(AuthSession).filter_by(
            token_hash=hash_token(raw_refresh), user_id=canary_user.id
        ).first()
        assert session is not None
        assert not hasattr(session, "raw_token")

    def test_two_users_different_mode_same_endpoint(self, client_c, canary_user, legacy_user):
        """L4: Ayni endpoint'te iki kullanici farkli mod alir."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", str(canary_user.id)):
                r_c = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
                r_l = client_c.post("/auth/giris", json={"email": legacy_user.email, "sifre": "LegacyPass123!"})
        assert r_c.status_code == 200
        assert r_l.status_code == 200
        assert r_c.json()["access_token"] != r_c.json()["refresh_token"]
        assert r_l.json()["token"] == r_l.json()["refresh_token"]


class TestCanaryRefresh:
    """Canary V2 session refresh; legacy token refresh bozulmaz."""

    def _canary_login(self, client_c, canary_user):
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", str(canary_user.id)):
                r = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
        assert r.status_code == 200
        return r.json()

    def test_canary_v2_refresh_succeeds(self, client_c, canary_user):
        """RF1: Canary V2 session refresh basarir."""
        login = self._canary_login(client_c, canary_user)
        refresh = login["refresh_token"]
        r = client_c.post("/auth/yenile", json={"refresh_token": refresh})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["refresh_token"] != refresh

    def test_canary_old_refresh_rejected_after_rotation(self, client_c, canary_user):
        """RF2: Rotation sonrasi eski refresh reddedilir."""
        login = self._canary_login(client_c, canary_user)
        old_refresh = login["refresh_token"]
        r1 = client_c.post("/auth/yenile", json={"refresh_token": old_refresh})
        assert r1.status_code == 200
        r2 = client_c.post("/auth/yenile", json={"refresh_token": old_refresh})
        assert r2.status_code == 401

    def test_canary_reuse_revokes_family(self, client_c, canary_user):
        """RF3: Reuse tespiti family'yi revoke eder."""
        login = self._canary_login(client_c, canary_user)
        t1 = login["refresh_token"]
        r2 = client_c.post("/auth/yenile", json={"refresh_token": t1})
        assert r2.status_code == 200
        t2 = r2.json()["refresh_token"]
        client_c.post("/auth/yenile", json={"refresh_token": t1})
        r3 = client_c.post("/auth/yenile", json={"refresh_token": t2})
        assert r3.status_code == 401

    def test_legacy_user_refresh_not_affected(self, client_c, legacy_user):
        """RF4: Legacy kullanici refresh bozulmaz."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", ""):
                r_login = client_c.post("/auth/giris", json={"email": legacy_user.email, "sifre": "LegacyPass123!"})
        assert r_login.status_code == 200
        legacy_token = r_login.json()["refresh_token"]
        r_refresh = client_c.post("/auth/yenile", json={"refresh_token": legacy_token})
        assert r_refresh.status_code == 200

    def test_canary_session_independent_of_legacy_user(self, client_c, canary_user, legacy_user):
        """RF5: Canary session legacy kullanicinin sessioniyla karismaz."""
        login_c = self._canary_login(client_c, canary_user)
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", ""):
                login_l = client_c.post("/auth/giris", json={"email": legacy_user.email, "sifre": "LegacyPass123!"}).json()
        client_c.post("/auth/yenile", json={"refresh_token": login_l["refresh_token"]})
        r = client_c.post("/auth/yenile", json={"refresh_token": login_c["refresh_token"]})
        assert r.status_code == 200


class TestCanaryLogout:
    """V2 session logout revoke -- allowlist bagimsiz."""

    def _login_and_get_access(self, client_c, canary_user):
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", str(canary_user.id)):
                r = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
        assert r.status_code == 200
        return r.json()

    def test_canary_logout_revokes_session(self, client_c, canary_user, db_c):
        """LO1: Canary logout V2 session'i revoke eder."""
        login = self._login_and_get_access(client_c, canary_user)
        access = login["access_token"]
        refresh = login["refresh_token"]
        r_out = client_c.post(
            "/auth/cikis",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r_out.status_code == 200
        r_ref = client_c.post("/auth/yenile", json={"refresh_token": refresh})
        assert r_ref.status_code == 401

    def test_canary_double_logout_idempotent(self, client_c, canary_user):
        """LO2: Cift logout idempotent (hata vermez)."""
        login = self._login_and_get_access(client_c, canary_user)
        access = login["access_token"]
        refresh = login["refresh_token"]
        client_c.post(
            "/auth/cikis",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        r2 = client_c.post(
            "/auth/cikis",
            json={"refresh_token": refresh},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r2.status_code == 200

    def test_legacy_logout_not_broken(self, client_c, legacy_user):
        """LO3: Legacy kullanici logout bozulmaz."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", ""):
                r = client_c.post("/auth/giris", json={"email": legacy_user.email, "sifre": "LegacyPass123!"})
        assert r.status_code == 200
        access = r.json()["token"]
        r_out = client_c.post("/auth/cikis", headers={"Authorization": f"Bearer {access}"})
        assert r_out.status_code == 200


class TestCanaryRegression:
    """Mevcut auth testleri canary degisikliginden etkilenmemeli."""

    def test_ben_endpoint_works(self, client_c, canary_user):
        """REG1: /auth/ben canary kullanici icin dogru doner."""
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", str(canary_user.id)):
                r_login = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
        access = r_login.json()["access_token"]
        r_ben = client_c.get("/auth/ben", headers={"Authorization": f"Bearer {access}"})
        assert r_ben.status_code == 200
        data = r_ben.json()
        assert data["email"] == canary_user.email
        assert "rol" in data
        assert "is_admin" in data

    def test_global_v2_false_allowlist_empty_all_legacy(self, client_c, canary_user, legacy_user):
        """REG2: Bos allowlist ile global false -> herkes legacy."""
        from app.api import auth as auth_mod
        auth_mod._attempts.clear()
        with patch.object(settings, "auth_token_v2_enabled", False):
            with patch.object(settings, "auth_token_v2_allowlist_user_ids", ""):
                r1 = client_c.post("/auth/giris", json={"email": canary_user.email, "sifre": "CanaryPass123!"})
                r2 = client_c.post("/auth/giris", json={"email": legacy_user.email, "sifre": "LegacyPass123!"})
        assert r1.status_code == 200, f"REG2 canary: {r1.json()}"
        assert r2.status_code == 200, f"REG2 legacy: {r2.json()}"
        assert r1.json()["token"] == r1.json()["refresh_token"]
        assert r2.json()["token"] == r2.json()["refresh_token"]
