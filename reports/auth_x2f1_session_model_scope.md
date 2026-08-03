# FAZ X2F-1 — Session Model Kapsam Raporu

**Tarih:** 2026-08-03  
**Faz:** X2F-1 — Stateful Refresh Session DB Modeli ve Migration Altyapisi  
**Başlangıç HEAD:** ea9d144  
**Rollback Tag:** backend-refresh-session-x2f1-oncesi  
**Kaynak Commit:** 1628825

---

## 1. Mevcut UserDevice Değerlendirmesi

| Alan | Değer | Stateful Refresh için Uygunluk |
|---|---|---|
| `device_id` | Client-sağlanan string (Android UUID) | UYGUN DEĞİL — token identity farklı kavram |
| `revoked_at` | Nullable DateTime | Tekrar kullanılabilir |
| `revoke_reason` | String(100) | Tekrar kullanılabilir |
| `is_active` | Boolean | Tekrar kullanılabilir |
| `token_hash` | YOK | Eksik — eklenecek alan |
| `jti` | YOK | Eksik |
| `token_family_id` | YOK | Eksik |
| `replaced_by_id` | YOK | Eksik |
| `expires_at` | YOK | Eksik |

**Sonuç:** UserDevice cihaz kimliği takibi içindir, token session yaşam döngüsü için değil.

---

## 2. Model Kararı

**Karar: Yeni `AuthSession` tablosu (UserDevice genişletilmedi)**

Gerekçe:
- `UserDevice.device_id` = client'ın sağladığı string (Android device UUID)
- `AuthSession.token_hash` = server'ın ürettiği token'ın SHA-256 hash'i
- Bir cihazın birden fazla session'ı olabilir (login → logout → login)
- Token rotation yeni satır oluşturur; `device_id` güncellenmez
- `replaced_by_id` self-reference bir cihaz tablosunda anlamsız olurdu
- Ayrı tablo: tek sorumluluk ilkesi, geriye uyumluluk riski yok

---

## 3. Yeni AuthSession Alanları

| Alan | Tip | Açıklama |
|---|---|---|
| `id` | Integer PK | Birincil anahtar |
| `user_id` | FK → kullanici.id | CASCADE DELETE |
| `token_hash` | String(64) NOT NULL | SHA-256 hex — ham token saklanmaz |
| `token_family_id` | String(36) NOT NULL | Rotation zinciri UUID4 |
| `jti` | String(36) NOT NULL | JWT ID (UUID4) |
| `created_at` | DateTime | Server default now() |
| `expires_at` | DateTime NOT NULL | Token son kullanma tarihi |
| `last_used_at` | DateTime nullable | Son kullanım zamanı |
| `revoked_at` | DateTime nullable | Revoke edilme zamanı |
| `revoke_reason` | String(20) nullable | CHECK constraint ile sınırlı |
| `replaced_by_id` | FK → auth_session.id nullable | SET NULL on delete |
| `client_type` | String(10) NOT NULL default UNKNOWN | CHECK constraint |
| `device_name` | String(100) nullable | İnsan okunabilir cihaz adı |
| `user_agent_hash` | String(64) nullable | UA'nın SHA-256 hash'i |
| `ip_hash` | String(64) nullable | IP'nin SHA-256 hash'i |
| `app_version` | String(20) nullable | Uygulama sürümü |

---

## 4. Index ve Constraint Tasarımı

| Obje | Tip | Amaç |
|---|---|---|
| `uq_auth_session_jti` | UNIQUE | JTI birden fazla session'da kullanılamaz |
| `uq_auth_session_token_hash` | UNIQUE | Aynı token iki kez kaydedilemez |
| `ck_auth_session_client_type` | CHECK | PANEL/MOBILE/API/UNKNOWN |
| `ck_auth_session_revoke_reason` | CHECK | 10 izinli neden + NULL |
| `ix_auth_session_user_id` | INDEX | Kullanıcı bazlı sorgular |
| `ix_auth_session_token_family_id` | INDEX | Family bazlı sorgular |
| `ix_auth_session_expires` | INDEX | Cleanup sorguları |
| `ix_auth_session_user_revoked` | COMPOSITE | Aktif session listesi |
| `ix_auth_session_family_revoked` | COMPOSITE | Family revoke ve reuse detection |

---

## 5. Token Hash Yaklaşımı

**Kullanılan:** `hash_token()` — SHA-256 hex (mevcut `security.py`)

- Giriş: UUID4 (122 bit entropi)
- Çıkış: 64 karakter hex string
- Deterministic lookup: evet (aynı token → aynı hash)
- Rainbow table riski: düşük (yüksek entropi girdi)
- Preimage riski: SHA-256 için kabul edilebilir
- Secret rotation etkisi: yok (keyed değil)
- Karar: UUID4 için SHA-256 kabul edilebilir; HMAC ile daha iyi olur ama mevcut kod uyumluluğu için SHA-256 korundu

---

## 6. Rotation Tasarımı

`rotate_refresh_session()` şu adımları tek transaction'da gerçekleştirir:

1. Eski session `with_for_update=True` ile kilitlenir
2. Revoked veya expired kontrolü yapılır → None döner
3. Yeni session aynı `token_family_id` ile oluşturulur
4. Eski session: `revoked_at`, `revoke_reason=REPLACED`, `replaced_by_id=new.id`
5. `db.flush()` ile transaction tamamlanır

Concurrent iki rotation: `uq_auth_session_jti` veya `uq_auth_session_token_hash` unique constraint ihlali IntegrityError üretir.

**SQLite Sınırlaması:** `with_for_update` SQLite'ta satır kiliti desteklemez. Concurrent test simüle edilemez. PostgreSQL'de gerçek row-level locking çalışır.

---

## 7. Reuse Detection Tasarımı

`detect_and_handle_reuse()` akışı:

1. Ham token hash'lenir, session aranır
2. Session aktifse → None (reuse yok)
3. Session revoke edilmişse → family ID bulunur
4. `revoke_token_family()` ile family'nin TÜM aktif session'ları `TOKEN_REUSE` nedeniyle revoke edilir
5. Güvenlik metadata dict döner

---

## 8. Cleanup Stratejisi

`delete_expired_sessions()`:
- Koşul: `expires_at < cutoff AND revoked_at IS NOT NULL AND revoked_at < retain_cutoff`
- Aktif session hiçbir zaman silinmez
- `retention_days=7` default: revoke'dan 7 gün sonra silinir
- Production job X2F-2 veya bakım fazında systemd timer ile eklenecek

---

## 9. Güvenlik Doğrulama

- raw_token log taraması: TEMİZ
- token_hash repr taraması: TEMİZ
- `__repr__` içinde yalnız `family_id[:8]` görünür
- Test fixture'ları UUID4 kullanır, gerçek token içermez
- Raporlarda credentials yok
