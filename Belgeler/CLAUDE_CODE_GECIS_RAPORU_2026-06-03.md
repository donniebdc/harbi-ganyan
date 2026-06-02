# Claude Code Geçiş Raporu — 2026-06-03

Bu rapor, 2026-06-03 oturumunda yapılan tüm güncellemeleri ve sistemin güncel
durumunu özetler. Yarın ofisteki Claude Code oturumu buradan devam edebilir.

> Önceki raporlar: `CLAUDE_CODE_GECIS_RAPORU_2026-06-01_V4.md`,
> operasyon kılavuzu: `SISTEM_TEKNIK_RAPOR_2026-06-02.md` (VPS/servis/cron/deploy).

---

## 1. Bu Oturumda Yapılanlar (özet)

Üç büyük güncelleme (`Güncelleme v3.txt` + `Bahis Türleri.txt`) + 2 ek istek:

| # | İş | Durum |
|---|----|-------|
| Bölüm 1 | Analiz ekranlarında **otomatik yenileme** (scroll korunur) | ✅ deploy/mobil |
| Bölüm 2 | **Bildirimler bloğu** (çan ikonu + sayfa, max 30, push deep-link) | ✅ deploy/mobil |
| Bölüm 3 | **Koşu Analizleri** (13 bahis türü, üretim + canlı grading + VIP) | ✅ deploy/mobil |
| Ek 1 | Admin panelinde **manuel üretim** (tarih/aralık → motoru yeniden çalıştır) | ✅ deploy |
| Ek 2 | GitHub push + bu geçiş raporu + APK build | ✅ |

**Hukuki not:** `hukuki sorumluluklar.txt` kullanıcı talimatıyla **tamamen göz ardı
edildi** ("paranoyak içerik"). Gerçek bahis terminolojisi (kupon, misli, TL, ganyan,
bahis adları) doğrudan kullanılıyor.

---

## 2. Bölüm 1 — Otomatik Yenileme (mobil)

**Dosya:** `app/lib/screens/gunun_analizleri.dart`
- `Timer.periodic(60sn)` — yalnız **bugün + içeriği açık** günde; yarın/yakında/geçmiş/
  kilitli günde otomatik durur.
- `WidgetsBindingObserver` → uygulama ön plana dönünce 1 kez tazeleme.
- `skipLoadingOnReload: true` (hem gün listesi hem gün detayı) → arka plan yenilemede
  **scroll konumu korunur**.

---

## 3. Bölüm 2 — Bildirimler Bloğu

**Backend** (yeni tablo gerekmedi, mevcut `Bildirim` tablosu kullanıldı):
- `app/api/auth.py`: `/auth/bildirimler` limit **50 → 30**.
- `app/bildirim_servis.py`: `gonder()` push `data`'sına `route:"bildirimler"` (deep-link).

**Mobil:**
- `app/lib/screens/bildirimler.dart` (YENİ) — tam sayfa, en yeni→en eski, zaman bilgili.
- `app/lib/api/models.dart` → `BildirimOzet`; `app/lib/state/content.dart` → `bildirimlerProvider`;
  `app/lib/util.dart` → `bildirimZaman()` ("14:32 · bugün" / "dün" / "28 May").
- `app/lib/screens/home.dart` → AppBar **çan ikonu** (giriş yapınca görünür).
- `app/lib/nav_key.dart` (YENİ) + `app/lib/main.dart` (navigatorKey) +
  `app/lib/fcm_setup.dart` → FCM `onMessageOpenedApp`/`getInitialMessage` deep-link.

---

## 4. Bölüm 3 — Koşu Analizleri (13 bahis türü, 6'lı hariç)

İki aile: **tek-koşu** (Plase, İkili, Sıralı İkili, Plase İkili, Sıralı Üçlü, Tabela,
Sıralı Beşli) ve **çok-ayak** (Çifte, Üçlü/Dörtlü/5'li/7'li Ganyan, 7'li Plase).

### Veri akışı (mevcut altılı mimarisinin aynısı)
```
Engine (KO satırına bets) → build_day_json (üretim+grading) → import_to_db
   → DB (kosu_bahis) → serialize → content (VIP endpoint) → mobil
                                 → bildirim_servis (VIP push)
```

### Çekirdek mantık — `backend/export/bahis_uretim.py` (YENİ)
- **Tespit:** bülten `bets` alanını virgülle tokenize ederek hangi bahisler açık.
  Çok-ayak bahisleri bültende yalnız **başlangıç koşusunda** listelenir (6'lı hariç).
- **Seçim:** ANA skoru sıralı atlardan tek öneri; misli = `floor(max_bütçe / kupon_bedeli)`.
- **Grading:** TJK resmi `emiParasalNeticeler_tr` → `kalemler` (her kalemde kombinasyon =
  GERÇEK kazanan, tutar = resmi ödeme). Seçimimiz kapsıyorsa TUTTU; net = tutar × misli.
- Gerçek TJK verisiyle (30.05.2026) doğrulandı: İkili, Sıralı Üçlü (11.424,60), Tabela
  (sırasız), Sıralı Beşli, çok-ayak ganyanlar — hepsi resmi ödemelerle birebir.

### Backend
- `app/models.py` → `KosuBahis` tablosu (`GunHipodrom.bahisler`).
- `alembic/versions/c8a2d4e6f105_kosu_bahis.py` (YENİ) — head: **c8a2d4e6f105**.
- `ganyan_master.py` → KO satırı sonuna `bets` eklendi (geriye uyumlu, p[0..8] korunur).
- `backend/export/build_day_json.py` → `build_bahisler()` + hip payload'a `bahisler`.
- `backend/export/import_to_db.py` → `KosuBahis` yazımı (idempotent).
- `app/serialize.py` → `bahis_payload`, `gh_bahis_payload`.
- `app/api/content.py` → **`GET /gun/{date}/bahisler`** (VIP) + **`GET /istatistik/bahis`**
  (VIP, bahis türü bazında kupon parası/kazanç/net).
- `app/bildirim_servis.py` → `gonder(min_tier="vip")`, `bahis_metni()`, sonuç döngüsü
  (anahtar `{iso}|{hip}|bahis|{bas_kosu}|{tip}`).

### Mobil
- `app/lib/screens/kosu_analizleri.dart` (YENİ) — tarih şeridi, VIP kilidi, açılır-kapanır
  hipodrom→koşu→bahis, canlı `[ ]` kazanan işareti + net kazanç, auto-refresh.
- `app/lib/api/models.dart` → `GunBahisler/BahisHip/BahisAnaliz/BahisSonuc`.
- `app/lib/api/client.dart` → `gunBahisler()` (403→`KilitliHata('vip')`).
- `app/lib/state/content.dart` → `gunBahislerProvider`.
- `app/lib/screens/home.dart` → placeholder yerine `KosuAnalizleri` (5. sekme).

> **ÖNEMLİ:** `bets` artık KO satırına yazıldığı için bahis analizleri **yeni üretilen
> günlerde** görünür. Geçmiş günler için admin panelinden "Manuel Üretim" çalıştırılmalı.

---

## 5. Ek 1 — Admin Manuel Üretim

- `backend/cron/daily_pipeline.py` → **`--uret START [END]`** modu (engine+export+import,
  tarih/aralık, en fazla 31 gün).
- `backend/app/api/admin.py` → **`POST /admin/api/uret`** (arka planda subprocess başlatır)
  + **`GET /admin/api/uret/durum`** (çalışıyor mu + son log satırları).
  - **Kritik:** subprocess `cwd=HG_ENGINE_ROOT` ile çalışır; servis kullanıcısı
    `harbiganyan` motorun cwd-bağıl çıktı klasörlerine (Pegadrom AI Analiz TXT) yazabilsin.
- `backend/app/static/admin.html` → "Manuel Üretim" paneli (tarih seç + canlı log/durum
  4sn'de bir poll).
- **Test edildi:** 24.05.2026 manuel üretildi (kod 0), bahisler DB'ye yazıldı.

---

## 6. VPS Dağıtım Durumu (CANLI)

Tümü `root@141.98.115.217`'ye scp ile gönderildi, migration uygulandı, servis restart.
- Alembic: **c8a2d4e6f105** (head), `kosu_bahis` tablosu mevcut.
- Servis `harbi-ganyan-backend.service` → **active**.
- 30.05.2026 ve 24.05.2026 yeniden üretildi → 134 + bahis kaydı, grading doğru.
- VIP endpoint canlı test: anonim **403**, VIP **200** (at isimleri + grading).

**Cron otomatik akışı (değişiklik gerekmedi):** günlük full üretim artık `bets` yazıyor →
export/import bahisleri grade'liyor → `run_live` VIP'lere bahis bildirimi gönderiyor.

---

## 7. Mobil / APK

- `flutter analyze` → **temiz** (0 issue).
- `flutter build apk --release` → **başarılı**:
  `app/build/app/outputs/flutter-apk/app-release.apk` (~51 MB).
- Flutter 3.44.1 (stable). Bu makinede `C:\Users\aa\flutter`.

---

## 8. Açık / Sıradaki İşler

1. **Faz B** (önceki oturumdan ertelendi): `Bildirimler.txt` madde 5-7 — çekilen at
   takibi + yeniden tahmin (KAPSAM: at çekilince ANA yeniden hesapla, etkilenen
   bahisleri/altılıyı güncelle, bildirim).
2. **Geçmiş günleri backfill** (opsiyonel): alt-bahisleri görmek için admin panelinden
   istenen tarih aralığını "Manuel Üretim" ile yeniden üret.
3. **Bahis seçim genişlikleri** ince ayar: `bahis_uretim.py > BET[*]["width"]` —
   şu an makul varsayılanlar; gerçek isabet/ROI verisiyle kalibre edilebilir.
4. **Google Play yayın** hazırlıkları (APK imzalama, store listing) — ayrı iş.

---

## 8b. Oturum Sonu Düzeltmeleri (deploy sonrası)

Manuel üretim testinden sonra fark edilen ve giderilen sorunlar:

1. **Mobil — geçmiş günler görünmüyordu (DÜZELTİLDİ).**
   `KosuAnalizleri` ekranı tarih şeridinde yalnız `aktif || yakinda` (bugün+yarın)
   günleri gösteriyordu; geçmiş günler filtreleniyordu. Artık **tüm günler**
   (geçmiş + bugün + yarın) şeritte; varsayılan seçim bugün, geçmiş günlerde
   auto-refresh kapalı. (`app/lib/screens/kosu_analizleri.dart`)
   - Backend zaten doğruydu: manuel üretilen 26/27/28.05 → 88/60/102 bahis kaydı DB'de.

2. **Bugün (06-03) bahissizdi (DÜZELTİLDİ).** Cron bugünü deploy'dan ÖNCE (bets'siz
   engine ile) üretmişti. `--uret 2026-06-03` ile yeniden üretildi → **82 bahis**.
   - Genel kural: deploy gününden önce üretilmiş günleri görmek için
     "Manuel Üretim" ile yeniden üret.

3. **APK yeniden derlendi** (mobil düzeltme dahil) — `app-release.apk` ~51 MB.

4. **GitHub:** `analiz/altili-aktarim-optim` → son commit `4f247d7`
   (önceki: `7cc1481` ana özellik commit'i, `e724256` taban).

**Doğrulama özeti (CANLI):** 24/26/27/28/30.05 ve 06-03 günlerinde kosu_bahis
kayıtları mevcut; grading TJK resmi ödemeleriyle birebir; VIP endpoint anonim=403,
VIP=200. `gecmis_gun=30` (son 30 gün şeritte görünür).

---

## 9. Hızlı Komut Hatırlatıcı

```bash
# SSH
ssh -i ~/.ssh/<key> root@141.98.115.217

# Manuel üretim (admin panel: /admin → Manuel Üretim) veya VPS'te:
cd /opt/harbi_ganyan_backend
HG_ENGINE_ROOT=/opt/harbi_ganyan_engine HG_BACKEND_DIR=/opt/harbi_ganyan_backend \
  .venv/bin/python cron/daily_pipeline.py --uret 2026-05-01 2026-05-07

# Migration durumu / yükselt
.venv/bin/python -m alembic -c alembic.ini current
.venv/bin/python -m alembic -c alembic.ini upgrade head

# Servis
systemctl restart harbi-ganyan-backend.service

# APK
cd app && flutter build apk --release
```
