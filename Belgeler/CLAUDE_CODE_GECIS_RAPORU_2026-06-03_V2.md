# Claude Code Geçiş Raporu — 2026-06-03 (V2)

Bu rapor, 2026-06-03 ikinci oturumunda yapılan tüm güncellemeleri, işlem ağacını,
teknik detayları ve sistemin güncel/yedek durumunu özetler. **Tek kaynak doğrusu
(SSOT): GitHub `analiz/altili-aktarim-optim` dalı.**

> Önceki raporlar (kronolojik): `CLAUDE_CODE_GECIS_RAPORU_2026-06-01_V4.md`,
> `SISTEM_TEKNIK_RAPOR_2026-06-02.md` (VPS/servis/cron/deploy kılavuzu),
> `CLAUDE_CODE_GECIS_RAPORU_2026-06-03.md` (Koşu Analizleri ilk sürümü).

---

## 0. Tek Bakışta Bu Oturum

| Konu | Sonuç |
|------|-------|
| **Koşu Analizleri yeni görsel şablon** (kolon-bazlı) | ✅ deploy + mobil |
| **Nested (genişleyen iç içe) kolon mantığı** (Güncelleme.txt) | ✅ deploy + backfill |
| **Kritik bug: `.env` göreli yol → yanlış DB (SQLite)** | ✅ kalıcı çözüldü |
| **VIP "Koşu Analizleri Yayınlandı" bildirimi + yalnız başarılı alt oyun** | ✅ deploy + canlı test |
| **Son 31 gün tam üretim (04.05–03.06)** | ✅ eksik gün yok |
| **Tam sistem yedeği (VPS + lokal)** | ✅ bu oturumda alındı |

**APK:** `1.0.8+9` (50.4 MB) — `app/build/app/outputs/flutter-apk/app-release.apk`
**Son commit:** `64ceb6a` (lokal = origin = VPS kod senkron)

---

## 1. İşlem Ağacı (bu oturum commit'leri)

```
64ceb6a  kosu analizleri UI rotusu: Plase adsiz, IKRAMIYE/KAZANC ayri satir, KAZANC yesil
923761a  bildirim: VIP kosu analizleri yayin duyurusu + yalniz basarili alt oyun bildirimi
5f9fb74  config: .env mutlak yola sabitlendi (cwd-bagimsiz DB secimi)
8ae6d26  Kosu Analizleri: nested kolon + yeni gorsel sablon
--- (önceki oturum sınırı) ---
8c89374  Geçiş raporu: oturum sonu düzeltmeleri
```

Bu oturumda değişen dosyalar (11): `bahis_uretim.py`, `build_day_json.py`,
`import_to_db.py`, `serialize.py`, `bildirim_servis.py`, `config.py`,
`daily_pipeline.py`, `models.dart`, `kosu_analizleri.dart`, `theme.dart`, `pubspec.yaml`.

---

## 2. Koşu Analizleri — Yeni Görsel Şablon

Eski tasarım at-çipleri kullanıyordu; yeni tasarım **kolon-bazlı** ve TJK kupon
mantığına uygun.

**Alt başlıklar:**
- Hipodrom: `TJK RESMİ ALT OYUNLARI` (sarı)
- Koşu: `N ALT OYUN` (sarı)

**Bahis kartı (örnek — İkili, başarılı):**
```
İkili                                    ANALİZ BAŞARILI   (yeşil rozet)
1. KOLON  :  2 / [4] / 8                  ([n] yeşil = o kolonun gerçek kazananı)
2. KOLON  :  2 / 4 / [8]
66 MİSLİ | 198 TL                         (camgöbeği)
─────────────────────────────
KAZANAN  :  4 / 8                         (sarı)
İKRAMİYE :  6,36                          (sarı)
KAZANÇ   :  6,36 * 66 = 419,76            (YEŞİL — yalnız tutunca)
```
- Rozet: `ANALİZ BAŞARILI` (yeşil) / `ANALİZ BAŞARISIZ` (kırmızı).
- Plase tek kolon, etiketsiz; KAZANAN yalnız numara (at adı yok).
- Kaybeden analizde `KAZANÇ` satırı görünmez; `İKRAMİYE` (resmi ödeme) yine görünür.

**Dosyalar:** `app/lib/screens/kosu_analizleri.dart` (kart yeniden tasarımı),
`app/lib/api/models.dart` (`BahisSonuc`: `ikramiye/net/kazanan/adlar`),
`app/lib/theme.dart` (`camgobegi` rengi eklendi).

---

## 3. Nested (Genişleyen İç İçe) Kolon Mantığı

**Sorun (Güncelleme.txt):** Alt oyunlar her zaman "box" (her kolona aynı atlar)
kuruluyordu. İstenen: kolonlara farklı atlar; banko varsa 1. kolon dar, sonraki
kolonlar geniş.

**Karar:** **Genişleyen iç içe (nested)** strateji + **son 30 gün backfill**.

**Üretim (`backend/export/bahis_uretim.py` → `uret_tek`):**
- **PLASE:** tek at (yüksek misli mantığı).
- **Sırasız** (İkili, Plase İkili, Tabela): box — tek havuz, görünümde N kolon.
- **Sıralı** (Sıralı İkili/Üçlü/Beşli): `base = pozisyon sayısı`; kolon i = ilk
  `(base+i)` ANA atı (üst küme). Örn. Sıralı Üçlü →
  `[2,7,9] / [2,7,9,10] / [2,7,9,10,11]`.
- `_sirali_komb()`: aynı atı iki pozisyona yazmayan **distinct-ordered** kombinasyon
  sayacı (TJK bedel kuralı). Bütçeye sığana dek `base` küçültülür; sonra
  `misli = floor(max_bütçe / kupon_bedeli)`.

**Grading (`grade`):** Kolon-bazlı. **İkramiye TUTSA DA TUTMASA DA** döndürülür
(resmi ödeme her durumda gösterilir; PLASE'de yalnız tutarsa). `kazanan_kombo`
kolon-bazlı `[[w0],[w1],...]` (mobilde yeşil `[n]` işareti için).

**Şema (DB migration GEREKMEDİ — mevcut JSON alanları yeniden kullanıldı):**
- `KosuBahis.kolonlar` (JSON) zaten çoklu kolon destekliyordu.
- `KosuBahis.ganyan` artık **resmi ikramiye** (kayıpta da dolu).
- `KosuBahis.kazanan` (JSON) artık `{"kombo": [[..]...], "adlar": {at_no: ad}}`.
- `serialize.bahis_payload` eski (düz liste) ve yeni (dict) `kazanan` şeklini tolere eder.

**Doğrulama (birim test — mockup ile birebir):**
İkili 198 TL/66 misli, Sıralı Üçlü nested `2/7/9 → 2/7/9/10 → 2/7/9/10/11`,
ikramiye kayıpta da görünür, Plase kazanan numarası.

---

## 4. KRİTİK BUG — `.env` Göreli Yol → Yanlış Veritabanı

**Belirti:** Manuel `daily_pipeline` çalıştırmaları postgres yerine SQLite'a yazıyordu;
mobilde veri güncellenmiyor gibi görünüyordu.

**Kök neden:** `app/config.py` → `env_file=".env"` **göreli** yoldu. pydantic-settings
`.env`'i o anki **çalışma dizininden (cwd)** okur. Cron/manuel script'ler
`cwd=/opt/harbi_ganyan_engine`'den çalışınca orada `.env` yok → `HG_DATABASE_URL`
yüklenmez → varsayılan **SQLite** (`backend/harbiganyan.db`) kullanılır.
systemd cron bunu `EnvironmentFile=/opt/harbi_ganyan_backend/.env` ile maskeliyordu,
ama elle çalıştırmada `HG_DATABASE_URL` export edilmezse veri yanlış DB'ye giderdi.

**Kalıcı çözüm (`5f9fb74`):**
```python
model_config = SettingsConfigDict(
    env_prefix="HG_", env_file=str(BACKEND_DIR / ".env"), extra="ignore")
```
`env_file` artık **mutlak yol**. cwd ne olursa olsun her zaman `backend/.env` yüklenir.

**Doğrulama:** `cwd=engine` + `HG_DATABASE_URL` export edilmeden export-only çalıştırıldı
→ **hiç SQLite oluşmadı**, postgres kullanıldı. Stray `harbiganyan.db` silindi.

---

## 5. Bildirim Sistemi — Koşu Analizleri (VIP)

**Önceki davranış:** Her alt oyun (başarılı + başarısız) tek tek bildiriliyordu;
yayın duyurusu hiç yoktu.

**Yeni davranış (`923761a`):**
1. **Yayın duyurusu (tek bildirim):** Gün yayınlanınca (18:00 TR = 15:00 UTC `yayin`
   timer'ı) VIP'e **bir kez** "Koşu Analizleri Yayınlandı" bildirimi gider
   (`bildirim_servis.bildir_kosu_analiz_yayin`, idempotent anahtar `<iso>|kosu_analiz_yayin`).
2. **Yalnız başarılı alt oyunlar:** `bildir_gun_sonuclari` artık sadece **TUTTU**
   olan analizleri VIP'e bildirir (`if not b.tuttu: continue`). Takip her koşu için
   sürer (grading `run_live`'da), ama başarısızlar VIP'i spam'lemez.

**Canlı test:** 06-04 için yayın bildirimi tetiklendi → 5 VIP kullanıcıya in-app +
FCM push başarıyla gitti. İdempotent olduğundan akşam timer tekrar göndermez.

**Mevcut durum:** 5 aktif VIP, 6 cihaz token. 4 timer aktif
(daily 06:00, results 08–20/10dk, live 08–20/2dk, yayin 15:00 UTC).

---

## 6. Son 31 Gün Tam Üretim (04.05–03.06)

`daily_pipeline.py --uret 2026-05-04 2026-06-03` ile **tam üretim** (engine scraping +
export + import) arka planda çalıştırıldı (~19 sn/gün, ~10 dk toplam).

- **31/31 gün** alt oyunlarla dolu, **eksik gün YOK**.
- Gün başına 60–136 alt oyun (toplam ~3.000 `kosu_bahis` kaydı).
- Hepsi yeni nested kolon formatında, postgres'e yazıldı (config fix sayesinde).

> **VPS'te elle üretim hatırlatıcı:** `cwd` engine olsa bile config fix sonrası
> `HG_DATABASE_URL` otomatik yüklenir. Yine de `HG_ENGINE_ROOT` ve `HG_BACKEND_DIR`
> set edilmeli:
> ```bash
> export HG_ENGINE_ROOT=/opt/harbi_ganyan_engine HG_BACKEND_DIR=/opt/harbi_ganyan_backend
> cd /opt/harbi_ganyan_engine
> /opt/harbi_ganyan_backend/.venv/bin/python /opt/harbi_ganyan_backend/cron/daily_pipeline.py --uret 2026-05-04 2026-06-03   # tam (scraping)
> # veya scraping'siz (mevcut engine çıktısını yeni mantıkla yeniden işle):
> ...daily_pipeline.py --export-only 2026-05-04 2026-06-03
> ```

---

## 7. VPS Dağıtım Durumu (CANLI)

`root@141.98.115.217` — Ubuntu 22.04, UTC. Port 8001 (Harbi Ganyan), 8000 (betsignal — DOKUNULMADI).

- Servis `harbi-ganyan-backend.service` → **active**, `https://api.harbiganyan.com` → 200.
- Backend kodu = GitHub `64ceb6a` ile aynı (scp ile dağıtıldı).
- DB: PostgreSQL `harbi_ganyan@localhost`, Alembic head `c8a2d4e6f105`.
- Backend dizini git deposu DEĞİL (scp ile yönetilir). Kod kaynağı: GitHub.

**Deploy yöntemi (kod değişince):**
```bash
scp -i ~/.ssh/hg_vps_claude backend/.../dosya.py root@141.98.115.217:/opt/harbi_ganyan_backend/.../
ssh -i ~/.ssh/hg_vps_claude root@141.98.115.217 \
  "rm -rf /opt/harbi_ganyan_backend/{app,export,cron}/__pycache__ && systemctl restart harbi-ganyan-backend.service"
```
> **Önemli:** Python bytecode cache (`__pycache__`) bazen scp sonrası bayatlayabiliyor;
> deploy sonrası ilgili `__pycache__` klasörlerini silmek güvenli yoldur.

---

## 8. Tam Sistem Yedeği (bu oturumda alındı)

Çalışan sistemin tam yedeği alındı; hem VPS'te hem lokalde mevcut.

- **İçerik:** `/opt/harbi_ganyan_backend` (kod + .env + static + alembic + cron),
  `/opt/harbi_ganyan_engine` (motor + scriptler + veri klasörleri),
  PostgreSQL `pg_dump`, systemd unit dosyaları (`harbi-ganyan-*`).
  (Hariç: `.venv`, `__pycache__` — yeniden üretilebilir.)
- **VPS konumu:** `/opt/harbi_ganyan_yedek/` (arşiv + manifest).
- **Lokal konumu:** `E:\Ganyan Gemini\Yedek\`.
- **Geri yükleme:** Arşivi aç → `.venv` yeniden kur (`requirements.txt`) →
  `pg_restore`/`psql` ile DB yükle → systemd unit'leri kopyala → `systemctl daemon-reload`.

---

## 9. Açık / Sıradaki İşler

1. **Faz B** — Çekilen at takibi + yeniden tahmin (Bildirimler.txt madde 5-7). Bekliyor.
2. **Kurumsal mail (SMTP)** — Brevo iptal; hosting firmasıyla kurumsal mail görüşülecek.
   Sağlanınca `backend/.env`'e `HG_SMTP_*` girilecek.
3. **Google Play yayını** — avukatla hukuki sorumluluk görüşmesi bekleniyor.
   APK şu an debug keystore; release keystore + store listing gerekecek.
4. **Jokey/orijin CSV otomatik tazeleme** (şu an statik).

---

## 10. Hızlı Komut Hatırlatıcı

```bash
# SSH (çalışan anahtar)
ssh -i ~/.ssh/hg_vps_claude root@141.98.115.217

# Servis
systemctl restart harbi-ganyan-backend.service
systemctl list-timers 'harbi-ganyan-*'

# Manuel üretim (env hatırlatıcı — bkz. Bölüm 6)
# Migration
cd /opt/harbi_ganyan_backend && .venv/bin/python -m alembic -c alembic.ini current

# APK
cd app && flutter build apk --release   # flutter: C:\src\flutter\bin

# Kaynak (SSOT)
git checkout analiz/altili-aktarim-optim && git pull
```
