# FAZ X2F-2 — Token V2 Uygulama Raporu

**Tarih:** 2026-08-03  
**Başlangıç HEAD:** 67dc062  
**Rollback Tag:** backend-token-v2-x2f2-oncesi → 67dc062  
**Kaynak Commit:** 05d32ed  
**Migration:** 5d272977ff1d

---

## Uygulama Özeti

### config.py

```
auth_token_v2_enabled: bool = False   # HG_AUTH_TOKEN_V2_ENABLED
access_token_minutes: int = 15
refresh_token_days: int = 30
token_issuer: str = "harbiganyan"
token_audience: str = "harbiganyan-app"
```

Production validation: access_token_minutes > 0, refresh_token_days > 0 zorunlu.

### security.py

Eklenen fonksiyonlar:
- `jwt_olustur_v2_access(user_id, tier) → (token, jti, expires_at)` — aud+iss+type=access
- `jwt_coz_v2_access(token) → dict|'expired'|None` — aud doğrulamalı
- `refresh_token_v2_olustur() → str` — opak UUID4 (ham token DB'ye gitmez)

Mevcut fonksiyonlar değiştirilmedi.

### api/auth.py

- `_token_pair_v2()`: kısa ömürlü access + opak refresh, session kaydı
- `/auth/giris`: flag=false→legacy, flag=true→V2 response
- `/auth/yenile`: flag=false→legacy JWT decode, flag=true→rotate_refresh_session
- `/auth/cikis`: flag=false→stateless, flag=true→revoke_session(reason=LOGOUT)

### deps.py

`current_user()` decode sırası:
1. `jwt_coz_v2_access()` — V2 access token (aud+type=access)
2. `jwt_coz()` — Legacy token (aud yok)
3. type=refresh JWT → reddedilir

---

## Doğrulama Sonuçları

| Kontrol | Sonuç |
|---|---|
| compileall | Temiz |
| 37 yeni test | 37/37 |
| 91 regresyon testi | 91/91 |
| Toplam | 128/128 |
| Alembic heads | 5d272977ff1d (tek head) |
| Migration production | UYGULANDHI |
| Feature flag .env | HG_AUTH_TOKEN_V2_ENABLED=false |
| Servis restart | YAPILDI |
| Yeni PID | 1400693 |
| Startup exception | YOK |
| Legacy login (401) | DOĞRULANDI |
| /auth/ben (auth yok) | 401 DOĞRULANDI |
| OpenAPI endpointleri | Mevcut + /auth/yenile |
| Panel kaynak değişikliği | YOK |
| Mobil kaynak değişikliği | YOK |
| Production V2 aktivasyonu | YAPILMADI |

---

## Kritik Kararlar

### Opak Refresh Token
Refresh token = UUID4 opak string. Avantaj: DB'de saklanmayan raw token → rainbow table geçersiz. Dezavantaj: refresh token kaybolursa client yeni login gerektirir.

### İki Adımlı Bearer Decode
`current_user()` önce V2 (aud zorunlu), başarısızsa legacy (aud yok). Bu sayede hem V2 hem legacy tokenlar sorunsuz çalışır.

### Feature Flag Granülerliği
Tek flag tüm sistemi kontrol eder. X2F-3'te panel ve mobil ayrı flag kontrolüne geçebilir.

---

## Sonraki Adım: X2F-3

- Panel NextAuth'ın `/auth/yenile`'yi kullanması
- Backend logout'unda `revoke_session()` çağrısı
- Kontrollü test hesaplarıyla production V2 aktivasyonu
- Mobil geçiş planı
