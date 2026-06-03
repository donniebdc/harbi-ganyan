# Altılı (6'lı) Ganyan Kupon Farkı — VPS vs Lokal — 03.06.2026

**Soru:** VPS'te üretilmiş 03.06.2026 altılı kuponları ile lokalde üretilmiş aynı
gün kuponları neden farklı?

**Kısa cevap:** Algoritma/kod aynı (her iki tarafta `V3-OPT`, iç içe kademeler,
aynı hipodromlar/atlar). Kuponlar farklı çünkü **ANA skoru besleyen GİRDİ VERİSİ
iki çalıştırmada farklıydı**. Üç bağımsız sapma var; en büyüğü Pegadrom Yarış
Akışı'nın bayat (1 günlük) önbelleği.

---

## 1. Kanıt — İSTANBUL 1. Koşu (en net fark)

| At (No) | LOKAL ANA | LOKAL AKIS | LOKAL JOK | VPS ANA | VPS AKIS | VPS JOK |
|---|---:|---:|---:|---:|---:|---:|
| AĞIR OĞLUM (8) | **100.0** | **1** | 0.050 | 87.5 | **3** | 0.211 |
| ÇERKEZHAN (5) | 61.0 | 2 | 0.050 | 60.6 | 2 | 0.155 |
| CESURSOY (4) | 49.8 | **3** | 0.050 | **63.5** | **1** | 0.078 |

- **5 SATIR sırası değişti:**
  - LOKAL: FAV=AĞIR OĞLUM, **SUR=ÇERKEZHAN, YAZ=CESURSOY**
  - VPS:   FAV=AĞIR OĞLUM, **SUR=CESURSOY, YAZ=ÇERKEZHAN**
- Sonuç kupona yansıdı (Simitçi 1. Koşu):
  - LOKAL: `[2 at] 8-5` (CESURSOY 3. sıraya düştü, 2-genişliğe girmedi)
  - VPS:   `[3 at] 8-4-5` (CESURSOY 2. sırada, kupona girdi)

---

## 2. Üç sapmanın kök nedenleri

### (A) Pegadrom Yarış Akışı — BAYAT ÖNBELLEK (baskın neden)
Pegadrom AI TXT dosya zaman damgaları:
- **VPS:** `2026-06-02 11:49` → akış sırası: CESURSOY(1)…  (dünkü / "erken mod" snapshot)
- **LOKAL:** `2026-06-03 12:34` → akış sırası: AĞIR OĞLUM(1), ÇERKEZHAN(2), CESURSOY(3) (yarış günü snapshot)

Mekanizma: `pegadrom_ai_txt_topla.collect_range(..., force=False)` mevcut TXT'yi
**yeniden indirmez**. VPS, 03.06 verisini bir gün önceden (02.06) çekip önbelleğe
almıştı; 03.06 sabah cron'u o **bayat akış verisini yeniden kullandı**. Lokalde
03.06 TXT'si hiç yoktu → bugün **taze** indirildi → Pegadrom akış sıralaması
güncellenmişti. Pegadrom "Yarış Akışı" yarış günü yaklaştıkça değişiyor.

Akış sinyali ANA skorda **0.50 ağırlıkla** baskın olduğundan, bu yeniden sıralama
SUR/YAZ slotlarını çevirip kupon üyelerini/genişliklerini/bütçelerini değiştirdi.

### (B) AGF snapshot — küçük zaman farkı (minör)
AGF değerleri yakın ama birebir değil (AĞIR OĞLUM: lokal 56.3 vs VPS 55.1; ÇERKEZHAN
12.1 vs 11.5). İki çalıştırma atyarisi AGF'sini farklı anlarda çekmiş. Etkisi küçük.

### (C) Jokey indeksi — LOKALDE CSV ARŞİVİ YOK
- LOKAL: **tüm** atlarda `JOK:0.050` (tek değer = varsayılan). `CSV Sonuçlar`
  klasörü lokalde **mevcut değil** → `build_intelligence()` 0 CSV bulur → jokey
  indeksi boş → herkes 0.050 varsayılanını alır.
- VPS: gerçek jokey-şehir oranları (0.000–0.211 aralığı).

Not: Jokey düzeltmesi ANA skora **yalnızca 10–13 atlı sahalarda** eklenir
(`jok_ek=0.20`). İSTANBUL 1. Koşu 9 atlı olduğu için JOK bu koşuda ANA'yı
etkilemez; ama 10–13 atlı koşularda lokal ile VPS arasında ek sapma yaratır.

---

## 3. Genel etki (her iki hipodrom)

Şablon, hipodromlar, atlar, kademe yapısı (Simitçi ⊆ Harbi ⊆ Ortaklı), banko
mantığı — **hepsi aynı**. Farklılaşan: bazı koşularda kolon genişlikleri ve 2.–3.
sıradaki at seçimi, dolayısıyla kademe bütçeleri (ör. İSTANBUL Altılı-1 Simitçi:
VPS 540 TL vs lokal 600 TL; Harbi 1440 vs 1600; Ortaklı 2700 vs 2800). ELAZIĞ'da
da benzer küçük genişlik/üye kaymaları var; banko ayakları (ör. Koşu 4 banko=1/(4)
eküri) aynı kaldı.

---

## 4. Sonuç ve öneriler

Bu bir **bug değil**; iki ortam farklı veri snapshot'larıyla çalıştığı için beklenen
sonuç. Tutarlılık istiyorsak:

1. **Pegadrom akışını yarış günü tazele (önerilen).** Cron yarış günü üretiminde
   `force=True` ile (veya yalnızca o güne ait) Pegadrom TXT'yi yeniden indirsin;
   böylece üretim hep en güncel akışı kullanır. Aksi halde 1 gün önce çekilen bayat
   akış üretime girer.
2. **CSV arşivini lokale taşı (veya kabul et).** Lokalde `CSV Sonuçlar` yok →
   jokey sinyali lokalde pasif. 10–13 atlı koşularda VPS ile aynı çıktı istiyorsan
   arşivi lokale senkronla; istemiyorsan bu farkın 10–13 segmentinde normal
   olduğunu bil.
3. **Doğrulama/karşılaştırma hep aynı ortamda yapılmalı.** "VPS üretimi"
   referanssa, lokal yeniden-üretim onu birebir vermez (canlı AGF + Pegadrom akışı
   zamanla değişir). Geçmiş günleri yeniden üretmek tarihsel snapshot'ı geri
   getirmez.

**Tek cümle:** Kod aynı; fark, VPS'in **dünden kalma (bayat) Pegadrom akış
önbelleğini** kullanması + lokalde **CSV jokey arşivinin olmaması** + küçük AGF
zaman farkından kaynaklanıyor. Baskın etken Pegadrom akışıdır (`force=False`).
