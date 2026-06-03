# Canlı Takip Sistemi + Alt-Tahmin Çıktısı — Uygulama Raporu (2026-06-03)

Bu belge 03.06.2026 oturumunda yapılan üç işi kayda geçirir:
1. Alt-bahis (Koşu Analizleri) tahminlerinin TXT'ye yazılması.
2. VPS↔lokal 6'lı kupon farkının kök-neden analizi.
3. Yarış-öncesi **canlı takip + zamanlı yeniden üretim + revize bildirimleri** sistemi
   (3 faz) — canlı üretime alındı.

---

## 1. Alt-tahmin TXT çıktısı

**İhtiyaç:** `ganyan_master.py` / `toplu_tahmin.py` çalışınca `TahminSonuçları/` altında
ana dosyanın (`<iso>.txt`) yanında alt oyunların da okunabilir TXT'si olsun
(`<iso>_alt_tahmin.txt`).

**Kök sorun:** Alt oyunlar motorun ham TXT'sinde yok; bültenin `bets` alanından export
aşamasında hesaplanıyor. Ayrıca `toplu_tahmin.py` KO satırına `bets` alanını yazmıyordu
(`ganyan_master.py` yazıyordu) → toplu üretimde alt oyunlar boş çıkıyordu.

**Çözüm:**
- `backend/export/alt_tahmin_yaz.py` (YENİ): `build_day` ile payload'u bellekte üretip
  `TahminSonuçları/<iso>_alt_tahmin.txt` yazar. `yaz_alt_tahmin(iso)` / `yaz_aralik(bas,bit)`.
- `backend/export/alt_oyun_rapor.py`: biçimleme tek merkeze (`format_payload`) taşındı.
- `toplu_tahmin.py`: KO satırına `bets` alanı eklendi (ganyan_master ile senkron) +
  aralık sonunda `yaz_aralik` çağrısı.
- `ganyan_master.py`: tek gün sonrası `yaz_alt_tahmin` çağrısı.

**Not:** `bets` yalnız canlı TJK bülteninde olduğundan, eski (bets'siz) günler için
`toplu_tahmin.py` yeniden çalıştırılmalı.

---

## 2. VPS↔lokal 6'lı kupon farkı — kök neden

**Bulgu (rapor: `Belgeler/ALTILI_FARK_ANALIZI_2026-06-03.md`):** Kod aynı; fark girdi
verisinden. Üç sapma:
- **(A) Pegadrom Yarış Akışı bayat önbellek (baskın):** `collect_range(force=False)`
  mevcut TXT'yi yeniden indirmiyor. VPS 03.06 verisini 02.06'da çekip önbelleğe almış;
  yarış günü bayat akışla üretmiş. Akış ANA skorda 0.50 ağırlık → 5-satır/kupon değişti.
- **(B) AGF snapshot zaman farkı (minör).**
- **(C) Lokalde CSV jokey arşivi yok** → JOK=0.050 (yalnız 10–13 atlı koşularda etkili).

Bu bulgu, aşağıdaki canlı takip sisteminin gerekçesi oldu (yarış günü taze akış şart).

---

## 3. Canlı takip sistemi (3 faz) — CANLI ÜRETİMDE

### Zaman çizelgesi (yarış günü D)
1. **D-1 17:50 TR** → VPS'te D üretilir (taze Pegadrom akışı). `daily` timer.
2. **D-1 18:00 TR** → yayın + "Yarının analizleri uygulamaya işlenmiştir". `yayin` timer.
3. **D, her hipodromun ilk koşusu −3 saat** → gün TEKRAR üretilir (force Pegadrom) +
   premium+ bildirimi "… koşuları öncesi analizler tekrar gözden geçirildi".
4. **−3h'tan ilk koşu −10dk'ya kadar, 30 dk'da bir** → jokey/koşmaz/pist değişikliği
   taranır; varsa tüm gün yeniden üretilir + "… yenilendi | Sebep: …".
5. **Alt-bahis** → her koşu kendi saati −5dk'ya kadar taranır; değişiklikte yeniden
   üretim + VIP bildirimi "Koşu Analizleri yenilendi | Sebep: …".
6. **Ana sayfa** → "Son analiz zamanı DD.MM.YYYY | HH:MM" bilgisi.

### Onaylanan kararlar
- İlk koşu referansı: **her hipodrom kendi ilk koşusuna göre** (bağımsız pencere).
- Yeniden üretim kapsamı: **tüm gün** (engine gün-bazlı).
- Tetikleyiciler: **koşmaz/çıkan at + jokey + pist/mesafe** (AGF hariç).

### Faz 1 — Zamanlama + son_analiz + T-3h regen + revize bildirimi
- `backend/app/models.py`: `Gun.son_analiz` (DateTime), `Gun.son_analiz_sebep` (String).
- `backend/export/import_to_db.py`: `ensure_schema` içine idempotent `ALTER TABLE … ADD
  COLUMN` (Postgres+SQLite uyumlu; create_all mevcut tabloya sütun eklemez).
  **Doğrulandı:** importer `Gun` satırını silmez → `son_analiz` reimport'larda korunur.
- `backend/cron/daily_pipeline.py`: `run_full(iso, taze_pegadrom, sebep)` — taze ise
  engine'den önce `collect_range(force=True)`; sonunda `son_analiz` + giriş snapshot.
  `run_canli_takip()` orkestratörü (T-3h regen) + `--canli-takip` modu.
- `backend/app/bildirim_servis.py`: `bildir_revize(...)`, orkestrasyon markerları
  (`marker_var`/`marker_yaz`, bildirimden bağımsız). Yayın mesajı güncellendi.
- `backend/app/serialize.py` + Flutter `app/lib/api/models.dart` +
  `app/lib/screens/gun_icerik.dart`: payload'a `son_analiz`/`son_analiz_sebep` + ana
  sayfa "Son analiz zamanı" bilgi şeridi.

### Faz 2 — Değişiklik taraması (30 dk, jokey/koşmaz/pist)
- `backend/cron/canli_takip.py` (YENİ): `mevcut_giris(iso)` TJK'dan güncel giriş tablosu;
  `snapshot_kaydet/yukle` (`out/<iso>_giris.json`); `diff(eski, yeni)` → sebep metinleri.
- `run_full` her üretimde giriş snapshot'ı yakalar (diff referansı).
- `run_canli_takip`: ilk koşu −3h .. −10dk arası 30 dk slotlu tarama; tetikleyici
  değişiklikte tüm gün regen + premium revize bildirimi (sebep hash'li idempotent anahtar).

### Faz 3 — Alt-bahis koşu-bazlı tarama + ana sayfa info
- `run_canli_takip`: tarama penceresi son koşu −5dk'ya kadar uzatıldı; her koşu için
  kendi saati −5dk son-tarama. Tek diff paylaşılır, tek regen yapılır; gün-seviyesi
  (premium) ve alt-bahis (VIP) bildirimleri ayrı gider.

---

## 4. VPS deploy + canlı doğrulama (2026-06-03 16:30 TR)

**Deploy:**
- 6 backend dosyası `/opt/harbi_ganyan_backend`'e (yedekler `/tmp/*.bak`).
- Postgres şema migration: `gun.son_analiz` + `son_analiz_sebep` eklendi.
- Backend servis restart (sağlık: ok).
- systemd: `daily.timer` 06:00→**14:50 UTC** (17:50 TR); YENİ `canli.timer` (her 10 dk,
  04–20 UTC) + `canli.service`; `yayin` 15:00 UTC değişmedi; `live`/`results` dokunulmadı.

**Canlı senaryo (ilk tick 13:30 UTC):** ELAZIG T-3h penceresi açık (ilk koşu 17:45 TR) →
gün taze Pegadrom akışıyla yeniden üretildi (16 koşu force indirildi) → DB'ye 2 hipodrom/
4 altılı yazıldı.

**Doğrulama:**
| Kontrol | Sonuç |
|---|---|
| `Gun.son_analiz` | `2026-06-03 16:30:42`, sebep "…tekrar gözden geçirildi" ✅ |
| markerlar | `2026-06-03\|ELAZIG\|t3_done`, `…\|revize\|t3` ✅ |
| revize bildirimi | 5 premium+ kullanıcıya in-app + FCM ✅ |
| giriş snapshot | `out/2026-06-03_giris.json` (11KB) ✅ |
| İSTANBUL | bildirim YOK (T-3h penceresi geçmişti — doğru) ✅ |

---

## 5. Değişen/eklenen dosyalar

**Backend (canlı takip):** `app/models.py`, `app/bildirim_servis.py`, `app/serialize.py`,
`export/import_to_db.py`, `cron/daily_pipeline.py`, `cron/canli_takip.py` (yeni).

**Backend (alt-tahmin):** `export/alt_tahmin_yaz.py` (yeni), `export/alt_oyun_rapor.py`,
kök `toplu_tahmin.py`, `ganyan_master.py`.

**Flutter:** `app/pubspec.yaml` (1.0.10+11→1.0.11+12), `app/lib/api/models.dart`,
`app/lib/screens/gun_icerik.dart`.

**Belgeler:** `ALTILI_FARK_ANALIZI_2026-06-03.md`, `CANLI_TAKIP_SISTEMI_2026-06-03.md`.

---

## 6. APK dağıtımı + oturum-koruyan kurulum (2026-06-03)

**Re-login kök nedeni (çözüldü):** `flutter install` uygulamayı silip kuruyor →
`flutter_secure_storage` token'ı gidiyor → her güncellemede login. İmza sorunu DEĞİL
(kurulu APK release-imzalı, CN=Harbi Ganyan). Çözüm: **`adb install -r`** (yerinde
güncelleme, aynı imza, oturum KORUNUR — canlı kanıtlandı: install -r sonrası giriş kaldı).

**Kural:** ASLA `flutter install` kullanma. Her zaman `adb install -r app-release.apk`.

**Dağıtım otomasyonu:**
- `app/yayinla.ps1` (yeni): build → yerel kopya (`APK/harbi_ganyan_<ver>.apk`) →
  Google Drive yükleme (rclone) → `adb install -r` (oturum-koruyan). Bayraklar
  `-SkipBuild`, `-NoInstall`.
- **Google Drive:** rclone v1.74.2 kuruldu + Drive OAuth yetkilendirildi. `gdrive:`
  remote'u hedef klasöre (`root_folder_id=14TkmH…`) bağlı. Token `%APPDATA%\rclone\
  rclone.conf`'ta (repo dışı; `refresh_token` ile otomatik yenilenir).
- `.gitignore`: `APK/` + `*.apk` eklendi (52MB binary git'e girmez).
- Bu sürüm yüklendi: `harbi_ganyan_1.0.11+12.apk` (Drive + yerel).

**Komutlar:**
- Tam akış: `powershell -ExecutionPolicy Bypass -File app\yayinla.ps1`
- Sadece kurulum: `adb install -r "…\app\build\app\outputs\flutter-apk\app-release.apk"`

## 7. Admin panel: şifre yönetimi + üyelik aralıkları (2026-06-03)

**Şifre yönetimi (admin.html + admin.py):**
- Kullanıcı satırına **"Şifre"** butonu eklendi → yeni şifre belirleme/üretme.
- Yeni uç: `POST /admin/api/kullanicilar/{id}/sifre` (`SifreResetReq`). `sifre`
  verilirse (min 6) onunla, verilmezse 12 karakter rastgele geçici şifre üretilir;
  yanıt yeni şifreyi BİR KEZ düz metin döner (admin kullanıcıya iletir).
- **GÜVENLİK NOTU:** Şifreler bcrypt ile hash'li (`sifre_hash`); mevcut şifre düz
  metin **GÖRÜNTÜLENEMEZ** (hash geri çevrilemez). "Görebilme" yerine güvenli
  karşılığı olan **reset/değiştir** akışı uygulandı; düz-metin şifre saklanmaz/sızdırılmaz.

**Üyelik uzatma aralıkları (admin.html):**
- Kullanıcı satırındaki `+7g` / `+30g` yanına **`+14g`** ve **`+60g`** eklendi
  (`extendUser(id, days)` → `uzat_gun`). Sıra: +7g +14g +30g +60g.

Değişen dosyalar: `backend/app/api/admin.py`, `backend/app/static/admin.html`.

## 8. Açık işler / notlar
- **Flutter APK** yeniden derlenip kurulmalı (sürüm 1.0.11+12) — "Son analiz zamanı"
  şeridi yeni build'de görünür. `app/yayinla.ps1` ile dağıt (Drive + yerel + adb -r).
- canli.timer her 10 dk çalışıp bugünden itibaren değişiklik tarıyor; gerçek bir
  jokey/koşmaz değişiminde canlı regen + bildirim gözlemlenebilir.
- Pegadrom force-tazeleme yarış günü bayat-akış sorununu (bkz. §2-A) yapısal olarak çözer.
- betsignal (port 8000) ve sonuç-takibi (live/results) timer'larına dokunulmadı.
- **Admin panel değişiklikleri VPS'e deploy edilmeli** (admin.py + admin.html + backend
  restart) — canlı admin panelinde görünmesi için.
