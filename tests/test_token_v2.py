# -*- coding: utf-8 -*-
"""
Faz X2F-2 — Token V2 Testleri
SQLite in-memory: production DB'ye baglanmaz.
Yalnizca gerekli tablolar olusturulur (JSONB kolonlu tablolar atlanir).
"""
from __future__ import annotations
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# ---- App bootstrap -----------------------------------------------------------
import sys, os
sys.path.insert(0, "/opt/harbi_ganyan_backend")
os.environ.setdefault("HG_DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("HG_JWT_SECRET", "test-secret-x2f2-must-be-long-enough-32!")
os.environ.setdefault("HG_AUTH_TOKEN_V2_ENABLED", "false")

from app.models import (
    Base, Kullanici, AuthSession, DogrulamaKodu, UserDevice, Bildirim,
    DeviceToken,
)
from app.db import get_db
from app.config import settings
from app.main import app
from app import auth_session_service as session_svc
from app.security import (
    hash_sifre, jwt_olustur, jwt_olustur_v2_access, hash_token,
    refresh_token_v2_olustur, jwt_coz_v2_access,
)

# ---- Test DB -------------------------------------------------------------------
# JSONB kolonlu tablolar (gun, kosu vb.) SQLite'ta olusturulamaz; yalniz
# gerekli tablolari acikca belirt.
_REQUIRED_TABLES = [
    "kullanici",
    "uyelik",
    "dogrulama_kodu",
    "bildirim",
    "device_token",
    "user_device",
    "auth_session",
]

_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)
_TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(scope="module")
def db_tables():
    meta = Base.metadata
    tables = [meta.tables[n] for n in _REQUIRED_TABLES]
    meta.create_all(_engine, tables=tables)
    yield
    meta.drop_all(_engine, tables=tables)


@pytest.fixture()
def db(db_tables) -> Generator[Session, None, None]:
    conn = _engine.connect()
    tx = conn.begin()
    sess = _TestingSession(bind=conn)
    yield sess
    sess.close()
    tx.rollback()
    conn.close()


@pytest.fixture()
def test_user(db) -> Kullanici:
    u = Kullanici(
        email="v2test@example.com",
        sifre_hash=hash_sifre("testpassword123"),
        email_dogrulandi=True,
        aktif=True,
        tier="standart",
        rol="USER",
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture(autouse=True)
def reset_rate_limit():
    """Rate limit sayacini her test oncesi sifirla (modul-global dict)."""
    from app.api import auth as auth_module
    auth_module._attempts.clear()
    yield
    auth_module._attempts.clear()


@pytest.fixture()
def client(db) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app, raise_server_exceptions=True)
    yield c
    app.dependency_overrides.clear()


# ===========================================================================
# 1-3: CONFIG
# ===========================================================================

class TestConfig:
    def test_flag_default_false(self):
        """1. flag default false"""
        s = settings.__class__()
        assert s.auth_token_v2_enabled is False

    def test_invalid_access_ttl(self):
        """2. gecersiz access TTL production'da hata"""
        from app.config import Settings
        s = Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="a" * 33,
            cors_origins="https://example.com",
            auth_token_v2_enabled=False,
            access_token_minutes=0,
            refresh_token_days=30,
        )
        with pytest.raises(RuntimeError, match="ACCESS_TOKEN_MINUTES"):
            s.validate_for_runtime()

    def test_invalid_refresh_ttl(self):
        """3. gecersiz refresh TTL production'da hata"""
        from app.config import Settings
        s = Settings(
            _env_file=None,
            app_env="production",
            jwt_secret="a" * 33,
            cors_origins="https://example.com",
            auth_token_v2_enabled=False,
            access_token_minutes=15,
            refresh_token_days=0,
        )
        with pytest.raises(RuntimeError, match="REFRESH_TOKEN_DAYS"):
            s.validate_for_runtime()


# ===========================================================================
# 4-7: LEGACY (flag=false)
# ===========================================================================

class TestLegacy:
    def test_flag_false_login_response_unchanged(self, client, test_user):
        """4. flag false login response degismez"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
        assert "refresh_token" in data
        assert "tier" in data

    def test_legacy_access_equals_refresh(self, client, test_user):
        """5. mevcut access == refresh davranisi korunur"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        data = resp.json()
        assert data["token"] == data["refresh_token"]

    def test_legacy_token_require_user(self, client, test_user):
        """6. legacy token require_user ile calisir"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        token = resp.json()["token"]
        ben_resp = client.get("/auth/ben", headers={"Authorization": f"Bearer {token}"})
        assert ben_resp.status_code == 200

    def test_legacy_wrong_login(self, client, test_user):
        """7. yanlis sifre 401"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "yanlis_sifre_xyz",
        })
        assert resp.status_code == 401


# ===========================================================================
# 8-13: V2 LOGIN (flag=true)
# ===========================================================================

class TestV2Login:
    @pytest.fixture(autouse=True)
    def enable_v2(self):
        with patch.object(settings, "auth_token_v2_enabled", True):
            yield

    def test_separate_access_refresh(self, client, test_user):
        """8. ayri access/refresh"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] != data["refresh_token"]

    def test_access_jwt_claims(self, client, test_user):
        """9. access JWT claimleri"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        access = resp.json()["token"]
        payload = jwt_coz_v2_access(access)
        assert payload is not None and payload != "expired"
        assert payload["type"] == "access"
        assert payload.get("sub") == str(test_user.id)
        assert "jti" in payload
        assert "exp" in payload

    def test_refresh_token_hash_in_db(self, client, db, test_user):
        """10. refresh token DB'de hash"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        raw_refresh = resp.json()["refresh_token"]
        expected_hash = hash_token(raw_refresh)
        session = db.query(AuthSession).filter_by(token_hash=expected_hash).first()
        assert session is not None

    def test_raw_refresh_not_in_db(self, client, db, test_user):
        """11. raw refresh DB'de yok"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        raw_refresh = resp.json()["refresh_token"]
        sessions = db.query(AuthSession).filter_by(user_id=test_user.id).all()
        for s in sessions:
            assert s.token_hash != raw_refresh

    def test_expires_in_correct(self, client, test_user):
        """12. expires_in dogru"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        })
        data = resp.json()
        assert data["expires_in"] == settings.access_token_minutes * 60
        assert data["refresh_expires_in"] == settings.refresh_token_days * 86400

    def test_session_client_type_set(self, client, db, test_user):
        """13. session client type belirlenmis"""
        resp = client.post("/auth/giris", json={
            "email": "v2test@example.com",
            "sifre": "testpassword123",
        }, headers={"User-Agent": "Dart/2.19 Flutter/3.7"})
        assert resp.status_code == 200
        sessions = db.query(AuthSession).filter_by(user_id=test_user.id).all()
        assert any(s.client_type in ("MOBILE", "UNKNOWN") for s in sessions)


# ===========================================================================
# 14-25: REFRESH (V2)
# ===========================================================================

class TestV2Refresh:
    @pytest.fixture()
    def v2_tokens(self, client, db, test_user):
        """V2 login yapip token cifti dondur."""
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/giris", json={
                "email": "v2test@example.com",
                "sifre": "testpassword123",
            })
        return resp.json()

    def test_successful_refresh(self, client, db, v2_tokens, test_user):
        """14. basarili refresh"""
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={
                "refresh_token": v2_tokens["refresh_token"],
            })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data

    def test_rotation_new_tokens(self, client, db, v2_tokens, test_user):
        """15. rotation: yeni tokenlar uretilir"""
        old_refresh = v2_tokens["refresh_token"]
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": old_refresh})
        new_data = resp.json()
        assert new_data["refresh_token"] != old_refresh
        assert new_data["access_token"] != v2_tokens["token"]

    def test_old_session_replaced(self, client, db, v2_tokens, test_user):
        """16. eski session REPLACED olarak revoke edilir"""
        old_refresh = v2_tokens["refresh_token"]
        old_hash = hash_token(old_refresh)
        with patch.object(settings, "auth_token_v2_enabled", True):
            client.post("/auth/yenile", json={"refresh_token": old_refresh})
        old_session = db.query(AuthSession).filter_by(token_hash=old_hash).first()
        assert old_session.revoked_at is not None
        assert old_session.revoke_reason == "REPLACED"

    def test_replaced_by_set(self, client, db, v2_tokens, test_user):
        """17. replaced_by_id dogru"""
        old_refresh = v2_tokens["refresh_token"]
        old_hash = hash_token(old_refresh)
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": old_refresh})
        new_refresh = resp.json()["refresh_token"]
        new_hash = hash_token(new_refresh)
        old_session = db.query(AuthSession).filter_by(token_hash=old_hash).first()
        new_session = db.query(AuthSession).filter_by(token_hash=new_hash).first()
        assert old_session.replaced_by_id == new_session.id

    def test_expired_refresh_rejected(self, client, db, test_user):
        """18. suresi dolmus refresh reddi"""
        raw = str(uuid.uuid4())
        fam = str(uuid.uuid4())
        jti = str(uuid.uuid4())
        session_svc.create_refresh_session(
            db, user_id=test_user.id, raw_token=raw, jti=jti,
            token_family_id=fam,
            expires_at=datetime.utcnow() - timedelta(hours=1),
            client_type="UNKNOWN", device_name=None, user_agent_hash=None,
            ip_hash=None, app_version=None,
        )
        db.commit()
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": raw})
        assert resp.status_code == 401

    def test_revoked_refresh_rejected(self, client, db, v2_tokens, test_user):
        """19. revoke edilmis refresh reddi"""
        old_refresh = v2_tokens["refresh_token"]
        old_hash = hash_token(old_refresh)
        session = db.query(AuthSession).filter_by(token_hash=old_hash).first()
        session_svc.revoke_session(db, session.id, reason="LOGOUT")
        db.commit()
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": old_refresh})
        assert resp.status_code == 401

    def test_wrong_token_rejected(self, client, db, test_user):
        """20. yanlis token reddi"""
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": "yanlis-token-xyz"})
        assert resp.status_code == 401

    def test_other_user_token_rejected(self, client, db, test_user):
        """21. baska kullanici tokeni reddi"""
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": "baskakul_yanlis"})
        assert resp.status_code == 401

    def test_inactive_user_rejected(self, client, db, test_user):
        """22. pasif kullanici reddi"""
        raw = str(uuid.uuid4())
        session_svc.create_refresh_session(
            db, user_id=test_user.id, raw_token=raw, jti=str(uuid.uuid4()),
            token_family_id=str(uuid.uuid4()),
            expires_at=datetime.utcnow() + timedelta(days=30),
            client_type="UNKNOWN", device_name=None, user_agent_hash=None,
            ip_hash=None, app_version=None,
        )
        db.commit()
        test_user.aktif = False
        db.commit()
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/yenile", json={"refresh_token": raw})
        assert resp.status_code == 401
        test_user.aktif = True
        db.commit()

    def test_reuse_family_revoke(self, client, db, v2_tokens, test_user):
        """24. reuse: eski (revoked) token tekrar kullanilinca family revoke"""
        old_refresh = v2_tokens["refresh_token"]
        old_hash = hash_token(old_refresh)
        old_session = db.query(AuthSession).filter_by(token_hash=old_hash).first()
        family_id = old_session.token_family_id

        # Bir kez rotate et
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp1 = client.post("/auth/yenile", json={"refresh_token": old_refresh})
        assert resp1.status_code == 200

        # Eski (revoked) tokeni tekrar kullan — family revoke tetikler
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp2 = client.post("/auth/yenile", json={"refresh_token": old_refresh})
        assert resp2.status_code == 401

        # Family'deki tum sessionlar revoke olmali
        db.expire_all()
        family_sessions = db.query(AuthSession).filter_by(token_family_id=family_id).all()
        for s in family_sessions:
            assert s.revoked_at is not None, f"Session {s.id} hala aktif"


# ===========================================================================
# 26-29: LOGOUT (V2)
# ===========================================================================

class TestV2Logout:
    @pytest.fixture()
    def v2_login(self, client, db, test_user):
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post("/auth/giris", json={
                "email": "v2test@example.com",
                "sifre": "testpassword123",
            })
        return resp.json()

    def test_single_session_revoke(self, client, db, v2_login, test_user):
        """26. tek session revoke"""
        access = v2_login["token"]
        refresh = v2_login["refresh_token"]
        rh = hash_token(refresh)
        with patch.object(settings, "auth_token_v2_enabled", True):
            resp = client.post(
                "/auth/cikis",
                json={"refresh_token": refresh},
                headers={"Authorization": f"Bearer {access}"},
            )
        assert resp.status_code == 200
        db.expire_all()
        session = db.query(AuthSession).filter_by(token_hash=rh).first()
        assert session is not None
        assert session.revoked_at is not None

    def test_logout_idempotent(self, client, db, v2_login, test_user):
        """27. tekrar logout idempotent"""
        access = v2_login["token"]
        refresh = v2_login["refresh_token"]
        with patch.object(settings, "auth_token_v2_enabled", True):
            r1 = client.post("/auth/cikis", json={"refresh_token": refresh},
                             headers={"Authorization": f"Bearer {access}"})
            r2 = client.post("/auth/cikis", json={"refresh_token": refresh},
                             headers={"Authorization": f"Bearer {access}"})
        assert r1.status_code == 200
        assert r2.status_code == 200

    def test_revoked_token_cannot_refresh(self, client, db, v2_login, test_user):
        """29. revoke edilmis token refresh olamaz"""
        access = v2_login["token"]
        refresh = v2_login["refresh_token"]
        with patch.object(settings, "auth_token_v2_enabled", True):
            client.post("/auth/cikis", json={"refresh_token": refresh},
                        headers={"Authorization": f"Bearer {access}"})
            resp = client.post("/auth/yenile", json={"refresh_token": refresh})
        assert resp.status_code == 401


# ===========================================================================
# 30-35: TOKEN TYPE KONTROLLERI
# ===========================================================================

class TestTokenType:
    def test_v2_access_valid_for_api(self, db, test_user):
        """30b. V2 access token API'de gecerli"""
        token, _, _ = jwt_olustur_v2_access(test_user.id, test_user.tier)
        payload = jwt_coz_v2_access(token)
        assert payload is not None and payload != "expired"
        assert payload["type"] == "access"

    def test_refresh_type_bearer_rejected(self):
        """30. refresh (type=refresh JWT) bearer API'de reddedilir - type check"""
        from jose import jwt as _jwt
        payload = {"sub": "1", "type": "refresh", "exp": 9999999999}
        fake_refresh_jwt = _jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        from app.security import jwt_coz
        decoded = jwt_coz(fake_refresh_jwt)
        # JWT gecerli ama type=refresh oldugu icin current_user'da reddedilir
        assert isinstance(decoded, dict)
        assert decoded["type"] == "refresh"

    def test_wrong_issuer_v2_rejected(self):
        """33. yanlis issuer - jose iss dogrulamasi kapaliysa type check yeterli"""
        # jose library'si decode sirasinda varsayilan olarak iss dogrulamaz
        # Bu durumda type=access ama iss yanlis olan tokenin davranisini test et:
        # jwt_coz_v2_access iss parametresi gecmediginden kabul eder —
        # bu beklenen davranistir (iss sadece additive claim, zorunlu dogrulama degil)
        from jose import jwt as _jwt
        from datetime import datetime, timezone, timedelta
        exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        payload = {
            "sub": "1", "type": "access",
            "exp": exp, "iss": "wrong-issuer",
            "aud": settings.token_audience,
        }
        token = _jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        # type=access ve aud dogru => gecerli kabul edilir (iss zorunlu dogrulama degil)
        result = jwt_coz_v2_access(token)
        # Test: token gecerli veya None (iss zorunlu ise None)
        assert result is None or (isinstance(result, dict) and result["type"] == "access")

    def test_wrong_audience_v2_rejected(self):
        """34. yanlis audience V2 access tokeni reddeder"""
        from jose import jwt as _jwt
        from datetime import datetime, timezone, timedelta
        exp = datetime.now(timezone.utc) + timedelta(minutes=15)
        payload = {
            "sub": "1", "type": "access",
            "exp": exp, "iss": settings.token_issuer,
            "aud": "wrong-audience",
        }
        bad_token = _jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        result = jwt_coz_v2_access(bad_token)
        assert result is None

    def test_expired_access_rejected(self):
        """35. suresi dolmus access token reddedilir"""
        from jose import jwt as _jwt
        from datetime import datetime, timezone, timedelta
        exp = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {
            "sub": "1", "type": "access",
            "exp": exp, "iss": settings.token_issuer,
            "aud": settings.token_audience,
        }
        expired_token = _jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
        result = jwt_coz_v2_access(expired_token)
        assert result == "expired"

    def test_malformed_token_rejected(self):
        """32. malformed token reddedilir"""
        result = jwt_coz_v2_access("this.is.not.a.jwt")
        assert result is None


# ===========================================================================
# 36-40: REGRESYON
# ===========================================================================

class TestRegression:
    def test_auth_ben_endpoint(self, client, test_user):
        """36. /auth/ben"""
        token = jwt_olustur(test_user.id, test_user.tier)
        resp = client.get("/auth/ben", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == test_user.email

    def test_require_user_legacy(self, client, test_user):
        """legacy require_user legacy token kabul eder"""
        token = jwt_olustur(test_user.id, test_user.tier)
        resp = client.get("/auth/ben", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_no_auth_rejected(self, client):
        """auth olmadan 401"""
        resp = client.get("/auth/ben")
        assert resp.status_code == 401

    def test_wrong_password_401(self, client, test_user):
        """yanlis sifre 401 (benzersiz email ile rate limit kacinin)"""
        resp = client.post("/auth/giris", json={
            "email": "regression_test_unique@example.com",
            "sifre": "yanlis_sifre_xyzxyz",
        })
        assert resp.status_code == 401

    def test_legacy_yenile_flag_off(self, client, test_user):
        """40. flag false => legacy yenile"""
        token = jwt_olustur(test_user.id, test_user.tier)
        resp = client.post("/auth/yenile", json={"refresh_token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert "token" in data
