# CLAUDE GECIS RAPORU - 2026-05-31

Bu rapor, Codex ile son turda yapılan değişiklikleri ve karar durumunu Claude'a devretmek için hazırlanmıştır.

## 1. Genel Durum

Proje kökü:

```text
D:\Ganyan Gemini
```

Aktif üretim dosyaları:

```text
ganyan_master.py
toplu_tahmin.py
motor/
Harbi_Ganyan_Analiz/
Pegadrom AI Analiz TXT/
CSV Sonuçlar/
pegadrom_skorlar.json
```

Mevcut üretim algoritması hâlâ şu ana mantıkla çalışıyor:

```text
AGF varsa:
ANA = AGF*0.40 + Pegadrom Akış*0.50 + Pegadrom Galop*0.10

AGF yoksa:
ANA = G*0.30 + Pegadrom Akış*0.70
```

Jokey sinyali yalnız 10-13 atlı koşularda ekleniyor:

```text
ANA += jokey_skoru * 100 * 0.20
```

HAR kuralı:

```text
14+ atlı koşu:
  top4 dışı adaylar içinden en iyi Pegadrom akış rank

13 ve altı:
  ANA sıralamasında 5. at
```

Bu turda üretim skoru değiştirilmedi. Yeni çalışmalar analiz/raporlama ve çıktı formatı üzerinedir.

## 2. Altılı Şablon Güncellemesi

Kullanıcının verdiği `C:\Users\aa\Documents\6lı şablon.txt` örneğine göre altılı TXT çıktı şablonu güncellendi.

Değişen dosyalar:

```text
motor/altili_uretim.py
motor/altili_kupon_v2.py
```

Yeni altılı başlık formatı:

```text
══════════════════════════════════════════════════════════════════════════════
🎰 BURSA — ALTILI GANYAN KUPONLARI
══════════════════════════════════════════════════════════════════════════════

🎲 1. ALTILI GANYAN (Koşular 1-6) 🎲

══════════════════════════════════════════════════════════════════════════════

  🎲 Simitçi 6'lısı 480 TL 🎲

  ──────────────────────────────────────────────────────────

    Koşu  1 ⚖️ açık              [4 at] 3-2-1-8          AT İSİMLERİ
```

Önemli:

- Algoritma, bütçe hesabı, banko/çıpa seçimi değiştirilmedi.
- Sadece TXT görsel şablonu değiştirildi.
- `ganyan_master.py` ve `toplu_tahmin.py` ortak `motor/altili_uretim.py` kullandığı için tekli ve toplu üretim aynı yeni formatı kullanır.

Doğrulama:

```text
python -m py_compile ganyan_master.py toplu_tahmin.py motor\altili_uretim.py motor\altili_kupon_v2.py
```

Başarılı geçti.

## 3. Banko Eşik Testi

Kullanıcının hipotezi:

> Daha cesur banko yazarsak diğer ayaklara daha fazla at ekleriz; acaba daha çok 6'lı bulur muyuz?

Bu hipotez mevcut 220 altılı evrende test edildi.

Rapor:

```text
banko_esik_test_raporu.md
```

Ana sonuç:

```text
Mevcut eşik 0.50:
  58 / 220 = %26.36

Korkusuz banko, eşik 0.00:
  45 / 220 = %20.45
```

Yani her yerde cesur banko yazmak 13 altılı kaybettiriyor.

Neden:

```text
0.00 eşikte banko doğruluğu: %45.91
0.50 eşikte banko doğruluğu: %61.67
```

Boşalan bütçe, yanlış bankonun kuponu öldürmesini telafi etmiyor.

En iyi test edilen karma eşik:

```text
Simitçi: 0.50
Harbi:   0.55
Ortaklı: 0.60
```

Sonuç:

```text
62 / 220 = %28.18
Mevcuda göre +4 altılı, +1.82 puan
```

Bu henüz üretime alınmadı. Karar girdisi olarak raporlandı.

## 4. Pegadrom JSON İçeriği İncelemesi

Kullanıcı `pegadrom_skorlar.json` içinde tam olarak ne olduğunu sordu. Dosya incelendi.

Dosya:

```text
pegadrom_skorlar.json
```

Özet:

```text
Koşu sayısı: 1028
Tarih aralığı: 2026-04-01 - 2026-05-28
Şehirler:
ADANA, ANKARA, ANTALYA, BURSA, DIYARBAKIR, ELAZIG,
ISTANBUL, IZMIR, KOCAELI, SANLIURFA

ai at kaydı: 9996
galop at kaydı: 9434
```

JSON yapısı:

```json
"2026-04-01|ISTANBUL|1": {
  "ai": {
    "3": {
      "isim": "...",
      "model": 83,
      "veri": 91,
      "galop": 100,
      "hiz": 0,
      "pist_mesafe": 86
    }
  },
  "galop": {
    "2": {
      "isim": "2 - DİLBERAN",
      "skor": 100,
      "harf": "A+",
      "galop_sayisi": 6,
      "son": 77,
      "en_iyi": 100,
      "tempo": 100,
      "istikrar": 78,
      "pist_uyum": 67,
      "kayit": 100
    }
  }
}
```

Üretimde aktif kullanılan alan:

```text
galop.skor
```

Üretimde ana skor için doğrudan kullanılmayan ama JSON'da bulunan alanlar:

```text
ai.model
ai.veri
ai.galop
ai.hiz
ai.pist_mesafe

galop.son
galop.en_iyi
galop.tempo
galop.istikrar
galop.pist_uyum
galop.kayit
galop.galop_sayisi
```

Pegadrom AI TXT tarafında ise üretimde kritik olan alan:

```text
Pegadrom yarış akışı / flow_rank / flow_score
```

## 5. Pegadrom JSON AI Geniş Testi

Kullanıcı, `pegadrom_skorlar.json` içindeki `ai` ve galop alt alanlarının daha geniş test edilmesini istedi.

Yeni script eklendi:

```text
motor/pegadrom_json_ai_genis_test.py
```

Rapor üretildi:

```text
pegadrom_json_ai_genis_test_raporu.md
```

Önemli: Bu script üretim algoritmasını değiştirmez. Sadece offline analiz yapar.

### 5.1 Test Kapsamı

Eski `v5/v7` toplu arşivleri kullanılmadı.

Tahmin kaynağı:

```text
Harbi_Ganyan_Analiz/<GG-AA-YYYY>/*_Tahminler.txt
```

Eşleşme anahtarı:

```text
(tarih_iso, hipodrom_norm, koşu_no, at_no)
```

Test verisi:

```text
Tahmin dosyası: 58
Parse edilen koşu: 1028
JSON + CSV + sonuç eşleşen koşu: 1004
Eğitim: 2026-04-01 - 2026-05-15 = 773 koşu
Holdout: 2026-05-16 - 2026-05-28 = 231 koşu
Holdout altılı: 47
```

### 5.2 Test Edilen Alanlar

```text
ai.model
ai.veri
ai.galop
ai.hiz
ai.pist_mesafe

galop.skor
galop.son
galop.en_iyi
galop.tempo
galop.istikrar
galop.pist_uyum
galop.kayit
galop.galop_sayisi
```

Her alan üç varyantla test edildi:

```text
raw_zero
neutral_missing
missing_indicator
```

### 5.3 Baseline Holdout

```text
Holdout n: 231
İlk1: %35.5
İlk3: %70.1
İlk4: %81.8
İlk5: %87.9
5 satır: %88.7
14+ 5 satır: %72.2
HAR: 16/42 = %38.1
HAR 14+: 3/13 = %23.1
```

### 5.4 En İyi JSON Ağırlık Adayı

En iyi holdout adayı:

```text
M:0.30
Flow:0.50
galop.en_iyi|neutral_missing:0.05
galop.istikrar|neutral_missing:0.15
```

Sonuç:

```text
Holdout 5 satır:
  %89.6
  baseline'a göre +0.87 puan

Holdout 14+ 5 satır:
  %75.0
  baseline'a göre +2.78 puan
```

Bu aday kabul eşiğini geçti:

```text
Ana skor kabul eşiği:
  genel +0.3 puan veya 14+ +1.0 puan

Bu aday:
  genel +0.87
  14+ +2.78
```

### 5.5 HAR Testi

JSON alanları HAR için iyi çıkmadı.

En iyi HAR adayı bile baseline'dan kötü:

```text
galop.kayit|raw_zero
ΔHAR: -9.5 puan
```

Bu nedenle JSON AI/galop alanları HAR kuralına doğrudan eklenmemeli.

Mevcut HAR kuralı korunmalı:

```text
14+ -> top4 dışı en iyi Pegadrom akış rank
diğer -> ANA 5.
```

### 5.6 Banko Filtresi

Banko filtre testlerinde bazı alanlar küçük pozitif sinyal verdi ama örneklem/dengesizlik nedeniyle üretime almak için yeterli değil.

Örnek:

```text
ai.pist_mesafe|neutral_missing >= 85
54/132 = %40.9
top1 baseline'a göre +5.4 puan
```

Ancak bu doğrudan altılı kupon başarısına net ve yeterli yansımadı. Şimdilik üretime alınmadı.

### 5.7 Altılı Holdout

Baseline:

```text
3 kupondan biri:
10/47 = %21.3

Simitçi:
5/47 = %10.6

Harbi:
8/47 = %17.0

Ortaklı:
10/47 = %21.3
```

Bazı grid adayları:

```text
grid5:
3 kupondan biri 11/47 = %23.4
Harbi 9/47 = %19.1
Ortaklı 10/47 = %21.3

grid6:
3 kupondan biri 11/47 = %23.4
```

Yani holdout altılıda +1 altılı görünür. Ancak holdout altılı sayısı sadece 47 olduğu için doğrudan üretim kararı için zayıf örneklem kabul edilmeli.

### 5.8 Karar

Üretim algoritması değiştirilmedi.

Rapor kararı:

```text
Ana skor kabul eşiği: GEÇTİ
HAR: GEÇMEDİ
Altılı: zayıf pozitif, düşük örneklem
```

Öneri:

```text
En iyi JSON adayı doğrudan ana algoritmaya alınmamalı.
Önce "gölge mod / canlı izleme" olarak mevcut tahminle yan yana üretilmeli.
```

## 6. Üretime Alınmayan Adaylar

Bu turda aşağıdakiler üretime alınmadı:

```text
1. Banko eşikleri:
   Simitçi 0.50 / Harbi 0.55 / Ortaklı 0.60

2. JSON ana skor adayı:
   M 0.30 + Flow 0.50 + galop.en_iyi 0.05 + galop.istikrar 0.15

3. JSON banko filtresi:
   ai.pist_mesafe veya galop tempo/en_iyi eşikleri
```

Bunlar karar girdisi olarak raporlandı.

## 7. Son Durumda Önerilen Yol

Claude devam edecekse önerilen sırayla ilerlemeli:

### A. Gölge Mod Ekle

Mevcut üretim skoru korunur.

Tahmin dosyalarına veya ayrı rapora ikinci skor eklenir:

```text
ANA_BASE
ANA_JSON_SHADOW
```

Gölge formül:

```text
AGF/G market: 0.30
Pegadrom Akış: 0.50
galop.en_iyi neutral_missing: 0.05
galop.istikrar neutral_missing: 0.15
```

Not:

- AGF yoksa market olarak `G` kullanılmalı.
- Toplam ağırlık 1.00.
- Jokey segment eklemesi mevcut mantıkla ayrıca uygulanabilir.

### B. Günlük Canlı İzleme Raporu

Her yeni gün için mevcut skor ve JSON shadow skor yan yana izlenmeli:

```text
baseline 5 satır
json_shadow 5 satır
baseline altılı
json_shadow altılı
farklı seçilen atlar
hangi at kazandı
```

### C. Üretime Alma Kuralı

En az 2-3 hafta yeni veri sonrası:

```text
JSON shadow 5 satır >= baseline +0.3 puan
veya
14+ segment >= baseline +1.0 puan
ve
altılı herhangi-biri metriği düşmüyor
```

Bu sağlanırsa ana skora alınabilir.

### D. HAR'a JSON Eklenmemeli

Mevcut test JSON HAR adaylarının kötü olduğunu gösterdi.

HAR tarafında mevcut akış-rank kuralı korunmalı.

### E. Altılı Eşikleri Ayrı Ele Alınmalı

Banko eşikleri için önceki en iyi karma öneri:

```text
Simitçi: 0.50
Harbi:   0.55
Ortaklı: 0.60
```

Ama bu da ayrı bir üretim kararıdır. JSON shadow ile karıştırılmamalı.

## 8. Teknik Notlar

Yeni script runtime:

```text
python motor\pegadrom_json_ai_genis_test.py
```

Çalışma süresi:

```text
Yaklaşık 4-5 dakika
```

Neden uzun:

```text
7854 ağırlık grid adayı
1004 koşu
tekil sinyal, HAR, banko, altılı holdout testleri
```

Optimizasyon yapıldı:

- Tüm grid adayları sadece eğitimde taranıyor.
- Holdout yalnız eğitimde ilk 200 adaya uygulanıyor.
- Altılı yalnız baseline + ilk 8 grid adayı için çalışıyor.

## 9. Dikkat Edilecek Noktalar

1. `Harbi_Ganyan_Analiz` artık ana tahmin arşividir. Eski `v5/v7` dosyalarına güvenilmemeli.
2. `pegadrom_skorlar.json` 29-30 Mayıs'ı kapsamıyor; bu nedenle JSON test aralığı 28 Mayıs'ta bitiyor.
3. `Pegadrom AI Analiz TXT` ile `pegadrom_skorlar.json` farklı kaynak katmanlarıdır:
   - TXT: akış/model reason parser
   - JSON: ai + ayrı galop skor arşivi
4. JSON `ai.model` tek başına güçlü çıkmadı.
5. JSON'dan anlamlı aday galop alt parçaları:
   - `galop.en_iyi`
   - `galop.istikrar`
6. JSON HAR kuralına sokulmamalı.
7. Üretim algoritması son turda değiştirilmedi.

