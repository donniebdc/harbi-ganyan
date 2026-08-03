# FAZ X2F-2 — Token V2 Kapsam Raporu

**Tarih:** 2026-08-03  
**Kaynak Commit:** 05d32ed  
**Migration:** 5d272977ff1d (bu fazda production'a uygulandı)  
**Feature Flag:** HG_AUTH_TOKEN_V2_ENABLED=false

---

## Kapsam

### Yeni Dosyalar

| Dosya | İçerik |
|---|---|
| `tests/test_token_v2.py` | 37 Token V2 testi |

### Değiştirilen Dosyalar

| Dosya | Değişiklik |
|---|---|
| `app/config.py` | auth_token_v2_enabled, access_token_minutes, refresh_token_days, token_issuer, token_audience |
| `app/security.py` | jwt_olustur_v2_access(), jwt_coz_v2_access(), refresh_token_v2_olustur() |
| `app/api/auth.py` | _token_pair_v2(), V2 login, V2 yenile, V2 cikis |
| `app/deps.py` | İki adımlı decode (V2 + legacy), type=refresh rejection |

---

## Ayarlar

| Env Var | Varsayılan | Açıklama |
|---|---|---|
| HG_AUTH_TOKEN_V2_ENABLED | false | Token V2 master switch |
| HG_ACCESS_TOKEN_MINUTES | 15 | Access token ömrü (dakika) |
| HG_REFRESH_TOKEN_DAYS | 30 | Refresh token ömrü (gün) |
| HG_TOKEN_ISSUER | harbiganyan | JWT iss claim |
| HG_TOKEN_AUDIENCE | harbiganyan-app | JWT aud claim |

---

## Feature Flag Davranışı

**flag=false (production varsayılan):**
- /auth/giris: legacy response (access=refresh=90gün JWT)
- /auth/yenile: legacy JWT decode + yeniden verme
- /auth/cikis: stateless, idempotent başarı
- Mevcut mobil uygulama etkilenmez

**flag=true (izole test ortamı):**
- /auth/giris: kısa ömürlü access JWT + ayrı opak refresh token
- /auth/yenile: stateful rotation (rotate_refresh_session)
- /auth/cikis: refresh session revoke (reason=LOGOUT)
- Reuse detection: family revoke tetiklenir

---

## Güvenlik Tasarımı

- Ham refresh token DB'ye asla yazılmaz (SHA-256 hash_token())
- V2 access token claimleri: sub, type=access, jti, iat, exp, iss, aud
- Refresh token: opak UUID4 — JWT değil
- Rotation atomik: with_for_update
- Reuse: revoked token yeniden kullanılırsa tüm family revoke
- type=refresh JWT bearer API erişiminde reddedilir
- Legacy token: type claim yok → legacy yoldan kabul edilir
- IP ve User-Agent: SHA-256 hash (PII minimizasyonu)

---

## Migration Durumu

| Adım | Sonuç |
|---|---|
| Önceki head | j6k7l8m9n010 |
| Migration | 5d272977ff1d (IF NOT EXISTS) |
| Production uygulandı | EVET |
| Doğrulama | 16 kolon, 2 FK, 7 index, 0 satır |
| Mevcut kullanıcı verisi | DOKUNULMADI |

---

## Test Özeti

| Grup | Test | Sonuç |
|---|---|---|
| Config | 3 | 3/3 |
| Legacy | 4 | 4/4 |
| V2 Login | 6 | 6/6 |
| V2 Refresh | 9 | 9/9 |
| V2 Logout | 3 | 3/3 |
| Token Type | 6 | 6/6 |
| Regresyon | 6 | 6/6 |
| **Toplam yeni** | **37** | **37/37** |
| **Önceki regresyon** | 91 | 91/91 |
| **Genel toplam** | **128** | **128/128** |
