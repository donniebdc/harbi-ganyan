# -*- coding: utf-8 -*-
"""FCM (Firebase Cloud Messaging) HTTP v1 push gönderimi.

Hafif yaklaşım: firebase-admin yerine google-auth ile service-account'tan OAuth2
erişim jetonu alınır, FCM v1 uç noktasına POST atılır. Service-account JSON yolu
HG_FIREBASE_SA env değişkeninde (gizli; git'e girmez). Yapılandırma yoksa no-op.
"""
from __future__ import annotations
import os
import threading

import requests

from .config import settings

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_lock = threading.Lock()
_creds = None


def _credentials():
    """Service-account kimlik bilgisi (tekil). Yapılandırma yoksa None."""
    global _creds
    if _creds is not None:
        return _creds
    path = settings.firebase_sa
    if not path or not os.path.exists(path):
        return None
    try:
        from google.oauth2 import service_account
        with _lock:
            if _creds is None:
                _creds = service_account.Credentials.from_service_account_file(
                    path, scopes=[_FCM_SCOPE])
    except Exception as e:  # google-auth yoksa veya dosya bozuksa
        print(f"[fcm] credentials yüklenemedi: {e}")
        return None
    return _creds


def _access_token() -> str | None:
    creds = _credentials()
    if creds is None:
        return None
    try:
        import google.auth.transport.requests as gtr
        creds.refresh(gtr.Request())
        return creds.token
    except Exception as e:
        print(f"[fcm] token yenilenemedi: {e}")
        return None


def aktif() -> bool:
    """FCM yapılandırılmış mı?"""
    return _credentials() is not None


def push_gonder(tokens: list[str], baslik: str, mesaj: str,
                data: dict | None = None) -> tuple[int, list[str]]:
    """Verilen token'lara bildirim gönderir.
    Döner: (başarılı_sayısı, geçersiz_tokenlar) — geçersizler DB'den silinmeli."""
    tokens = [t for t in (tokens or []) if t]
    if not tokens:
        return 0, []
    access = _access_token()
    if not access:
        return 0, []
    url = f"https://fcm.googleapis.com/v1/projects/{settings.firebase_project}/messages:send"
    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}
    basari = 0
    gecersiz: list[str] = []
    veri = {k: str(v) for k, v in (data or {}).items()}
    for t in tokens:
        body = {"message": {
            "token": t,
            "notification": {"title": baslik, "body": mesaj},
            "data": veri,
            "android": {"priority": "high"},
        }}
        try:
            r = requests.post(url, headers=headers, json=body, timeout=10)
            if r.status_code == 200:
                basari += 1
            elif r.status_code in (400, 404):
                # UNREGISTERED / geçersiz token -> temizlenmeli
                gecersiz.append(t)
        except Exception as e:
            print(f"[fcm] gönderim hatası: {e}")
    return basari, gecersiz


def kullanicilara_push(db, kullanici_idler: list[int], baslik: str, mesaj: str,
                       data: dict | None = None) -> int:
    """Verilen kullanıcı id'lerinin tüm cihazlarına push; geçersiz token'ları siler."""
    if not aktif() or not kullanici_idler:
        return 0
    from .models import DeviceToken
    rows = (db.query(DeviceToken)
            .filter(DeviceToken.kullanici_id.in_(kullanici_idler)).all())
    tokens = [r.token for r in rows]
    if not tokens:
        return 0
    basari, gecersiz = push_gonder(tokens, baslik, mesaj, data)
    if gecersiz:
        db.query(DeviceToken).filter(DeviceToken.token.in_(gecersiz)).delete(
            synchronize_session=False)
        db.commit()
    return basari
