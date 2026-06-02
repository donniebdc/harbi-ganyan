# Koşu Analizleri Güncellemesi — Uygulama Planı

**Tarih:** 2026-06-03
**Kaynak belgeler:** `Güncelleme v3.txt`, `Bahis Türleri.txt`, `hukuki sorumluluklar.txt`
**Durum:** Tasarım onayı bekliyor

---

## ⚠️ Açık konu: Terminoloji (hukuki Q&A sonrası kesinleşecek)

`Bahis Türleri.txt` bahis jargonu kullanıyor (kupon, misli, TL, bütçe, ganyan).
`hukuki sorumluluklar.txt` bunların **kullanıcıya gösterilmemesini** öneriyor.

Bu plan **iki katmanı ayırıyor:**
- **Backend/engine iç isimlendirme** (kod, DB, log): teknik isimler serbest (`bahis_tip="GANYAN"`).
- **Kullanıcıya görünen metin** (label, bildirim): hukuki Q&A'da kesinleşecek, kodda tek bir `DISPLAY_AD` haritası ile yönetilecek.

Bu sayede hukuki karar değişse bile **sadece harita dosyası** güncellenir, tüm pipeline aynı kalır.

---

## Bölüm 1 — Otomatik Yenileme (auto-refresh)

**Sorun:** Sonuç işaretleri / `[]` kazanan işaretleri yalnızca kullanıcı pull-to-refresh yapınca geliyor; derin analizde kullanıcı yerini kaybediyor.

**Çözüm (mobile-only, backend değişmez):**
- `gunun_analizleri.dart` ve alt analiz ekranlarına:
  - `Timer.periodic` (canlı günlerde 60 sn) → provider invalidate.
  - `WidgetsBindingObserver` → app foreground'a dönünce 1 kez refresh.
- **Scroll korunması:** `invalidate` yerine veriyi yerinde güncelle (Riverpod `AsyncValue` üzerinden), `ScrollController.offset` korunur. Liste anahtarları stabil (`ValueKey(kno)`).
- Yenileme yalnızca **bugün + canlı** günlerde aktif; geçmiş günlerde timer kapalı.

---

## Bölüm 2 — Bildirimler Bloğu (çan ikonu + sayfa)

**Karar (önceki oturumdan):** 7. sekme değil, **çan ikonu** (AppBar'da) → ayrı sayfa.

### Backend
- Yeni tablo: `kullanici_bildirim` (her gönderilen bildirimin kalıcı kaydı):
  ```
  id, baslik, mesaj, data_json, tip, created_at
  ```
  (Cihaz bazlı değil; sistem geneli yayın bildirimleri için. VIP-özel olanlar `tip` ile ayrılır.)
- `bildirim_servis.gonder()` zaten her push'u idempotent gönderiyor → aynı noktada `kullanici_bildirim` satırı da yazılır.
- Yeni endpoint: `GET /bildirimler?limit=30` → en yeni → en eski, `created_at` ile.
- **Maksimum 30** (Güncelleme v3 net): sunucu `LIMIT 30` döndürür; istemci de 30'da tutar. (Not: özet ilk başta 50 yazılmıştı → **30'a** çekilecek.)

### Mobile
- AppBar'da çan ikonu (okunmamış sayısı rozet — opsiyonel, basit tutulabilir).
- Bildirimler sayfası: liste, en yeni üstte, her satırda **zaman bilgisi** ("14:32 · bugün" / "dün" / tarih).
- **Push deep-link:** bildirime tıklayınca → uygulama açılır → Bildirimler sayfasına gider → ilgili bildirim vurgulanır. (`data.route="bildirimler"` + opsiyonel `id`.)
- Tıklansın tıklanmasın tüm push'lar sayfada görünür (sunucudan çekilir, lokal FCM payload'a bağlı değil).

---

## Bölüm 3 — Koşu Analizleri (açılır-kapanır bahis analizleri)

### 3.1 Engine — yeni modül `motor/bahis_uretim.py`

Girdi: `ganyan_master.run()` çıktısı `kosu_verileri[kno]` + `race.get('bets')`.

1. **Bahis tespiti:** `bets` string'i parse → o koşuda hangi bahis tipleri açık.
   - `altili_uretim._fold_bets()` deseni (TR→ASCII upper) yeniden kullanılır.
   - Tek-koşu bahisleri (GANYAN, İKİLİ, SIRALI İKİLİ, ÜÇLÜ BAHİS, PLASE, TABELA...) → ilgili koşuya.
   - Çok-ayaklı ("BU KOŞUDAN BAŞLAR": ÇİFTE, 3'LÜ/4'LÜ/5'Lİ/6'LI/7'Lİ GANYAN) → ayrı ele alınır (6'lı zaten mevcut bloktan geliyor; çakışma olmasın diye 6'lı buradan **hariç** tutulur).
2. **Seçim türetme:** her bahis tipi için `atlar_sirali` (ANA skoru sıralı) üzerinden **tek öneri** (max bütçeye sığan):
   - Plase → ilk 1-2; İkili → ilk N; Üçlü → ilk M; Tabela → ilk 4; vb.
   - Kombinasyon `Bahis Türleri.txt` formülleriyle hesaplanır, `birim × kombinasyon ≤ max_bütçe` olacak şekilde N seçilir.
   - **Misli = floor(max_bütçe / kupon_bedeli)** (iç hesap; kullanıcıya gösterimi hukuki Q&A'ya bağlı).
3. Çıktı: `bahis_bloku[kno] = [{tip, secim_atlar:[...], kombinasyon, birim, kupon_bedeli, misli}]`.

### 3.2 Backend — model ailesi + migration

`Kosu → KosuBahis → KosuBahisSonuc` hiyerarşisi (`KosuBes`/`KosuSonuc` deseni birebir):
```
KosuBahis:      id, kosu_id, tip, secim_json, kombinasyon, birim, kupon_bedeli, misli
KosuBahisSonuc: id, kosu_bahis_id, tuttu(bool), kazanan_json, ganyan(numeric), net_kazanc(numeric)
```
- Alembic migration (yeni head, down_revision = `b7e1c2f3a004`).
- `build_day_json.py` → `bahisler` bloğu eklenir.
- `import_to_db.py` → idempotent delete-rewrite içine `KosuBahis` eklenir.

### 3.3 Canlı derecelendirme (grading)

- `tjk_sonuc_topla.build_kosu()` → `siralama` (varış sırası) + `bahisler.kalemler` (TJK resmi ödemeler).
- Grading: bizim `secim_json` vs `siralama` → tuttu mu? Tuttuysa TJK `kalemler`'den resmi ganyan → `net_kazanc = ganyan × misli`.
- `bildirim_servis`'e yeni üretici: her koşu-bahis sonucu → **VIP'lere** bildirim (idempotent `GonderilenBildirim` anahtarı: `bahis:{gun}:{hip}:{kno}:{tip}`).

### 3.4 İstatistik (per-bahis-türü)

- `content._donem_istatistik()` deseni → bahis türü bazında: toplam kupon parası, toplam kazanç, net, isabet oranı.
- Yeni endpoint `GET /istatistik/bahis` (VIP-gated).

### 3.5 API erişim

- Tüm Koşu Analizleri detay endpoint'leri **VIP-only** (`require_vip` deseni).
- `GET /gun/{date}/bahisler` → koşu bazlı bahis analizleri (açılır menü verisi).

### 3.6 Mobile

- Koşu Analizleri ekranı: koşu satırları → tıklayınca **açılır-kapanır** (ExpansionTile) → o koşunun bahis analizleri.
- Her bahis: seçilen atlar, (canlıda) `[]` kazanan işaretleri, tuttuysa net kazanç.
- VIP değilse kilitli görünüm.
- Auto-refresh (Bölüm 1) burada da geçerli, scroll korunur.

---

## Sıralama önerisi (uygulama sırası)

1. **Bölüm 1** (auto-refresh) — küçük, mobile-only, anında değer.
2. **Bölüm 2** (bildirimler bloğu) — backend tablo + endpoint + mobile sayfa.
3. **Bölüm 3** (Koşu Analizleri) — en büyük; engine→backend→grading→mobile.
4. Terminoloji haritası → **hukuki Q&A sonrası** kesinleşir, en sona.

---

## Net karar gereken noktalar (kullanıcıya)

1. Limit 30 onayı (özet 50 diyordu → 30'a çekiyorum). ✔ Güncelleme v3 net: 30.
2. 6'lı'yı bahis bloğundan hariç tutuyorum (mevcut blok zaten var) — onay?
3. İstatistik: tutar (TL) gösterimi hukuki Q&A'ya bağlı — şimdilik backend hesaplar, gösterim sonra.
