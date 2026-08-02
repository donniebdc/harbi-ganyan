# Faz X2A - Auth Contract Entegrasyon Raporu

Tarih: 2026-08-02
Baslangic commit: 1491fa6
Bitis commit: 0392fe7
Rollback tag: backend-auth-contract-x2a-oncesi

## /auth/giris Sozlesme (degismedi)
Request: email, sifre, cihaz_id, app_version
Response 200: token, refresh_token, tier
Hatalar: 401 yanlis bilgi / 403 dogrulanmamis-pasif / 429 rate-limit

## /auth/ben Onceki Sozlesme
id, email, tier, vip_until, email_dogrulandi, is_admin

## /auth/ben Yeni Sozlesme (Faz X2A)
Eski alanlar (kirilmaz - Android uyumlulugu):
  id, email, tier, vip_until, email_dogrulandi, is_admin

Yeni alanlar (panel icin additive):
  rol       -> DB kaynagli: USER / EDITOR / ADMIN
  is_editor -> rol in (EDITOR,ADMIN) or is_admin
  is_vip    -> erisim_coz() ile gercek VIP hesaplama
  aktif     -> DB kullanici.aktif

## Pydantic Model
BenResponse eklendi (response_model=BenResponse)
Hassas alanlar yok: sifre_hash, token modelde degil

## Testler
test_editor_role.py     : 6/6  OK
test_vip_service.py     : 16/16 OK
test_auth_ben_contract  : 10/10 OK
TOPLAM                  : 32/32 OK

Test senaryolari:
  USER rolu - is_editor=False, is_vip=False
  EDITOR rolu - is_editor=True
  ADMIN rolu - is_editor=True, is_admin=True
  is_admin=True + USER rolu - is_editor=True (geriye uyumluluk)
  Aktif VIP - is_vip=True
  Suresi gecmis VIP - is_vip=False
  vip_until=None - null serialize
  vip_until mevcut - isoformat string
  aktif=False kullanici
  Hassas alan sizintisi yok

## Degistirilmeyenler
JWT TTL          : 90 gun (degismedi)
access_token     : refresh_token ile ayni JWT (degismedi)
Token claimleri  : sub, tier, exp (degismedi)
Sifre algoritmasi: bcrypt (degismedi)
require_admin    : degismedi
require_editor   : degismedi
/auth/giris response: degismedi
Migration        : GEREKMEDI
Production deploy: YAPILMADI
Servis restart   : YAPILMADI

## Android Uyumluluk Riski
Degisiklik ADDITIVE - mevcut alan silinmedi.
Gson varsayilan: bilinmeyen alanlari gormezden gelir - DUSUK RISK.
Strict parse yapan istemciler: test edilmeli.

## Faz X2B Hazirlik: EVET
Panel NextAuth adapter artik /auth/giris ve /auth/ben kullanabilir.
Session callback: accessToken, tier, rol, is_admin, is_editor, is_vip doldurulabilir.
