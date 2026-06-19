# -*- coding: utf-8 -*-
"""Uygulama ayarları. Lokal geliştirme: SQLite. Üretim (VPS): PostgreSQL (HG_DATABASE_URL)."""
from __future__ import annotations
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
DEV_JWT_SECRET = "dev-secret-change-me"


class Settings(BaseSettings):
    # env_file MUTLAK yol: cron/manuel script'ler farklı cwd'den (ör. engine kökü)
    # çalıştığında bile DAİMA backend/.env yüklensin. Göreli ".env" olursa cwd'de
    # .env bulunmaz -> sessizce SQLite varsayılanına düşer (postgres yerine).
    model_config = SettingsConfigDict(
        env_prefix="HG_", env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    # Lokal varsayılan: dosya tabanlı SQLite (sunucu gerektirmez).
    # Üretim: HG_DATABASE_URL=postgresql+psycopg2://user:pass@host/db
    database_url: str = f"sqlite:///{BACKEND_DIR / 'harbiganyan.db'}"

    # Auth / JWT
    app_env: str = "development"
    jwt_secret: str = DEV_JWT_SECRET
    jwt_alg: str = "HS256"
    cors_origins: str = "*"
    jwt_expire_min: int = 60 * 24 * 90  # 90 gün (her güncellemede yeniden giriş istememesi için)

    # SMTP (doğrulama kodu) — MVP'de boşsa kod konsola yazılır
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    smtp_from: str = "Harbi Ganyan <no-reply@harbiganyan.app>"

    # İçerik
    gecmis_gun: int = 30  # "Geçmiş Analizler" penceresi

    # FCM push (Firebase). firebase_sa = service-account JSON yolu (gizli, git'e girmez).
    firebase_sa: str = ""
    firebase_project: str = "harbi-ganyan"

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


settings = Settings()
