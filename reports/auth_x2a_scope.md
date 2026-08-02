# Faz X2A - Auth Contract Kapsam Belgesi

Tarih: 2026-08-02
Backend baslangic commit: 1491fa6
Rollback tag: backend-auth-contract-x2a-oncesi

## 1. Degistirilen Dosya

app/api/auth.py
tests/test_auth_ben_contract.py (yeni)

## 2. POST /auth/giris - Mevcut Sozlesme (degismedi)

Request: email, sifre, cihaz_id|None, device_name|None, app_version|None
Response (200): token (JWT 90 gun), refresh_token (ayni JWT), tier
Response (hata): 401 yanlis bilgi, 403 dogrulanmamis/pasif, 429 rate limit

## 3. GET /auth/ben - Onceki Sozlesme

id, email, tier, vip_until, email_dogrulandi, is_admin

## 4. GET /auth/ben - Yeni Sozlesme (Faz X2A)

Eski alanlar (kiriLMAZ):
- id: int
- email: str
- tier: str
- vip_until: str veya null
- email_dogrulandi: bool
- is_admin: bool

Yeni alanlar (panel entegrasyonu):
- rol: str (USER / EDITOR / ADMIN)
- is_editor: bool
- is_vip: bool
- aktif: bool

## 5. Yeni Alan Semantigi

rol      -> DB kullanici.rol -- tokenden degil, DB okuma
is_editor -> rol in (EDITOR, ADMIN) or is_admin
is_vip    -> erisim_coz() -- Google Play + manuel VIP hesaplama
aktif     -> DB kullanici.aktif

## 6. Degistirilmeyen Yapilar

JWT TTL: 90 gun
access_token == refresh_token (ayni JWT)
Sifre algoritmasi: bcrypt
Token claimleri: sub, tier, exp
require_admin dependency
require_editor dependency
/auth/giris response
/auth/yenile response
/auth/kayit, /auth/dogrula
Migration: GEREKMEDI

