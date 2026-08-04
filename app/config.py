# -*- coding: utf-8 -*-
"""Uygulama ayarlari. Lokal gelistirme: SQLite. Uretim (VPS): PostgreSQL (HG_DATABASE_URL)."""
from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEV_JWT_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    # env_file MUTLAK yol: cron/manuel script'ler farkli cwd'den (or. engine kokunden)
    # calistiginda bile DAIMA backend/.env yuklenmesi icin.
    model_config = SettingsConfigDict(
        env_prefix="HG_", env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # Lokal varsayilan: dosya tabanli SQLite (sunucu gerektirmez).
    # Uretim: HG_DATABASE_URL=postgresql+psycopg2://user:pass@host/db
    database_url: str = f"sqlite:///{BACKEND_DIR / 'harbiganyan.db'}"

    # Auth / JWT
    app_env: str = "development"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_alg: str = "HS256"
    cors_origins: str = "*"
    jwt_expire_min: int = 60 * 24 * 90  # 90 gun (her guncellemede yeniden giris istememesi icin)

    # Token V2 — feature flag ve TTL ayarlari (Faz X2F-2)
    # HG_AUTH_TOKEN_V2_ENABLED=true ile etkinlestirilir; varsayilan KAPALI.
    auth_token_v2_enabled: bool = False
    # Virgülle ayrilmis pozitif integer kullanici ID leri. Bos->canary kapali.
    # Global flag false iken yalnizca bu IDler V2 alir. Fail-closed parser.
    auth_token_v2_allowlist_user_ids: str = ""
    access_token_minutes: int = 15        # V2 access token omru (dakika)
    refresh_token_days: int = 30          # V2 refresh token omru (gun)
    token_issuer: str = "harbiganyan"     # JWT iss claim
    token_audience: str = "harbiganyan-app"  # JWT aud claim

    # SMTP (dogrulama kodu) - MVP'de bossa kod konsola yazilir
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "Harbi Ganyan <no-reply@harbiganyan.app>"

    # Icerik
    gecmis_gun: int = 60  # "Gecmis Analizler" penceresi

    # FCM push (Firebase). firebase_sa = service-account JSON yolu (gizli, git'e girmez).
    firebase_sa: str = ""
    firebase_project: str = "harbi-ganyan"

    google_play_package: str = "app.harbiganyan.harbi_ganyan"
    google_play_sa: str = ""

    # Telegram operasyon bildirimleri
    telegram_alerts_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_env_label: str = "PRODUCTION"

    @property
    def token_v2_allowlist(self) -> frozenset:
        import logging as _l
        _log = _l.getLogger(__name__)
        raw = self.auth_token_v2_allowlist_user_ids or ""
        if not raw.strip():
            return frozenset()
        ids: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                uid = int(part)
                if uid > 0:
                    ids.add(uid)
                else:
                    _log.warning('Token V2 allowlist: gecersiz ID atlandı')
            except (ValueError, TypeError):
                _log.warning('Token V2 allowlist: gecersiz format atlandı')
        _log.info('Token V2 allowlist: %d kullanici yuklendi', len(ids))
        return frozenset(ids)

    @property
    def production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    def validate_for_runtime(self) -> None:
        if not self.production:
            return
        if self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            raise RuntimeError("HG_JWT_SECRET must be a strong production secret.")
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if not origins or "*" in origins:
            raise RuntimeError("HG_CORS_ORIGINS must not be '*' in production.")
        # Token V2 TTL sanilik degerler reddedilir
        if self.access_token_minutes <= 0:
            raise RuntimeError("HG_ACCESS_TOKEN_MINUTES must be positive.")
        if self.refresh_token_days <= 0:
            raise RuntimeError("HG_REFRESH_TOKEN_DAYS must be positive.")


settings = Settings()
