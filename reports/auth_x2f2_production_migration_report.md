# FAZ X2F-2 — Production Migration Raporu

**Tarih:** 2026-08-03  
**Migration:** 5d272977ff1d (add_stateful_refresh_sessions)  
**Önceki Head:** j6k7l8m9n010  
**DB Dump:** /opt/backups/harbi_ganyan_backend/x2f2_20260803_195819/prod_db_x2f2_pre.dump (2.15 MB)

---

## Pre-Flight Kontrolleri

| Kontrol | Sonuç |
|---|---|
| Git HEAD (pre) | 67dc062 |
| Alembic head (pre) | j6k7l8m9n010 |
| Servis durumu (pre) | active/running |
| DB dump boyutu | 2,152,547 bytes |
| DB dump izni | 600 (yalnız root) |
| Migration checksum | alındi (sha256) |
| Rollback tag | backend-token-v2-x2f2-oncesi → 67dc062 |

---

## Migration Analizi (5d272977ff1d)

| Özellik | Değer |
|---|---|
| down_revision | j6k7l8m9n010 |
| Yeni tablo | auth_session |
| Mevcut tablo silme | YOK |
| Mevcut kullanıcı verisi güncelleme | YOK |
| Auth endpoint davranışı etkisi | YOK |
| IF NOT EXISTS | EVET (idempotent) |

---

## Migration Uygulaması

```
alembic current   → j6k7l8m9n010
alembic upgrade head  → (exit 0)
  Running upgrade j6k7l8m9n010 -> 5d272977ff1d
alembic current   → 5d272977ff1d (head)
```

---

## Şema Doğrulaması

| Kontrol | Sonuç |
|---|---|
| Kolon sayısı | 16 |
| FK sayısı | 2 (kullanici + self-reference) |
| Index sayısı | 7 |
| Başlangıç satır sayısı | 0 |
| Mevcut kullanıcı kayıtları | DOKUNULMADI |

---

## Deploy Sonrası

| Kontrol | Sonuç |
|---|---|
| Servis restart | YAPILDI |
| Yeni PID | 1400693 |
| Startup exception | YOK |
| Alembic current (post) | 5d272977ff1d |
| /auth/ben (unauthorized) | 401 Giriş gerekli |
| Yanlış login | 401 Email veya sifre hatali |
| OpenAPI /auth/* endpointleri | Mevcut (11 endpoint) |
| 5xx hatası | YOK |

---

## Rollback Planı

```bash
# Flag false olduğunu doğrula
grep HG_AUTH_TOKEN_V2_ENABLED /opt/harbi_ganyan_backend/.env

# Kaynak revert
git revert 05d32ed

# Servis restart
sudo systemctl restart harbi-ganyan-backend.service

# Migration downgrade (tablo BOŞ ve kullanılmıyorsa)
# alembic downgrade j6k7l8m9n010
# DB dump restore: pg_restore -d <db> /opt/backups/.../prod_db_x2f2_pre.dump
```

**NOT:** auth_session tablosunda V2 oturumları oluşmuşsa (flag=true sonrası) downgrade öncesi manuel değerlendirme gerekir.
