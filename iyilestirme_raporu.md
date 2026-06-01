# HARBİ GANYAN — İYİLEŞTİRME RAPORU (01.04–30.05.2026)

Tarih: 31.05.2026
Kaynak: `v5_tahmin_01042026-30052026.txt` (1068 koşu) + CSV sonuçları (28.05'e kadar).
Eşleşen koşu: **1010**. Eşleşen altılı: **212**. Tüm metrikler **eküri-kredili**.

---

## 1. 5 Satır Performansı

| Metrik | Oran |
|---|---:|
| İlk1 (favori kazandı) | %37.9 |
| İlk3 | %73.6 |
| İlk4 | %84.0 |
| İlk5 | %90.2 |
| **5-SATIR isabet** (kazanan 5 atımızdan biri) | **%90.4** |

Sistem v7 seviyesini koruyor (%90). **Eküri katkısı +0.4 puan** (4 koşuda 5-satır yalnızca
eküri ortağı sayesinde tuttu) — küçük ama bedava ve doğru çalışıyor.

### Segment kırılımı (asıl bulgu)

| Alan | n | İlk1 | İlk3 | İlk4 | İlk5 | 5-satır |
|---|---:|---:|---:|---:|---:|---:|
| ≤9 at | 481 | %41 | %80 | %90 | %95 | **%95** |
| 10-13 at | 360 | %38 | %71 | %82 | %90 | %90 |
| **14+ at** | 169 | %29 | %59 | %70 | %77 | **%78** |

**14+ kalabalık sahalar sistemin en zayıf halkası** — 5-satır %78 (≤9'da %95). Bu yapısal
tavan iki kez (sinyal fizibilitesi + ağırlık taraması) kırılamadı; kamuya açık veri AGF/akış
tarafından zaten fiyatlanmış durumda.

> Not: AGF'siz koşu yalnızca 6 (mobil erken mod canlı test edilmedi); kaynak kırılımı anlamsız.

---

## 2. Altılı Ganyan Kupon Performansı

Akıllı banko (eşik 0.50), hipodrom birim fiyatlı, eküri-kredili:

(14+ banko cezası uygulandıktan sonraki final rakamlar)

| Kademe | İsabet | Ort. Maliyet | Top. Dönüş | Net |
|---|---:|---:|---:|---:|
| Simitçi (200-500₺) | %12.3 | 480₺ | 275.940₺ | +174.192₺ |
| Harbi Ganyan (1200-1600₺) | %20.3 | 1.544₺ | 859.875₺ | +532.542₺ |
| **Ortaklı (1600-2000₺)** | **%26.9** | 1.927₺ | 1.209.754₺ | **+801.137₺** |

Üç kademede de **net pozitif**. Daha büyük kademe (Ortaklı) hem isabeti hem ROI'yi
yükseltiyor — ama getiri **nadir büyük ödemelerle** geliyor (yüksek varyans; 212 altılının
~57'si tutuyor, kâr birkaç büyük vuruşta yoğunlaşıyor).

### Banko/çıpa doğruluğu

- Çıpa ayağı (tek-at banko ya da 2-at çıpa) kazananı içerme: **%64.2** (eküri-kredili,
  14+ cezası sonrası; ceza öncesi %63.2).
- Segment: ≤7 **%69**, 8-9 %62, 10-11 %65, 12-13 %61. Banko artık 14+ sahalara neredeyse
  hiç düşmüyor (24→5 ayak) — kalabalık ayak banko lider yapılmıyor.
- **Kuponların ~%36'sı tek başına çıpa ayağında ölüyor** — en büyük tek kayıp kaynağı.

### Banko politikası karşılaştırması (Harbi kademesi)

| Politika | İsabet | Net | Tek-at banko doğruluğu |
|---|---:|---:|---:|
| Tam zorunlu | %18.4 | +286.516₺ | %48 |
| **Akıllı banko (eşik .50)** | %19.8 | **+515.617₺** | %63 |
| Bankosuz | %19.8 | +254.887₺ | — |

Akıllı banko hem en yüksek net hem doğru banko dengesini veriyor — seçim doğrulandı.

---

## 3. Nerede Kan Kaybediyoruz?

1. **Çıpa ayağı (%37 kupon ölümü)** — favori-kazanma özünde ~yazı-tura; en güçlü ayakta
   bile %63 tavan. Bu, altılı isabetinin birincil sınırı.
2. **14+ kalabalık sahalar** — hem 5-satır (%78) hem banko (%50) burada düşük. Bir altılıda
   tek bir 14+ ayak bile kuponu ciddi zayıflatıyor.
3. **Yüksek varyans** — kâr birkaç büyük ödemede; kısa vadede uzun kayıp serileri olası.

---

## 4. İyileştirme Önerileri (kanıt seviyeleriyle)

### Uygulanan (bu raporla)
- **A. Eküri görünür etiket** — kupon banko/ayak satırlarında "eküri: … kapsanır" notu
  (`format_coupon`). Veri+mantık zaten vardı; artık görünür. Yeniden-üretim scripti silindi
  (motorlar zaten doğru kuponu üretiyor).
- **B. Banko seçiminde 14+ alan cezası** — `banko_score` 14+ sahalara -25 ceza uygular;
  zayıf-banko olasılığı yüksek kalabalık ayağı banko lider yapmaktan kaçınır.
  Test (212 altılı, Harbi): isabet %19.3→**%19.8**, net +469k→**+486k** (marjinal pozitif).

### Test edilmeye değer (sonraki toplu testte ölç)
- **C. Ortaklı kademesini "ciddi oyun" varsayılanı yap** — en iyi isabet/ROI (%27.4).
  Simitçi düşük-bütçe/deneme; Harbi orta.
- **D. 14+ ayaklarda minimum genişlik 6-7** — cov eğrisi 14+ için g=6→%83, g=7→%87
  gösteriyor; bütçe elverdiğinde bu ayakları öncelikli genişlet.
- **E. AGF-kapılı tek-banko** — `fav AGF≥50` koşullarında favori-kazanma daha yüksek;
  tek-at banko'yu yalnızca AGF lideri + yüksek AGF'de aç, aksi halde çıpa.

### Yapısal sınır (yeni sinyal gerektirir)
- **F. 14+ tavanı** mevcut sinyallerle (AGF, akış, galop, jokey) kırılamıyor — kanıtlandı.
  Kırmak için kalabalığın fiyatlamadığı veri gerekir (sabah galop/padok/son dakika), CSV'de yok.

---

## 5. Özet

- 5-satır **%90.4**, altılı her kademede **net pozitif**, Ortaklı en verimli.
- En büyük kayıp kaynağı **çıpa ayağı (%37)** ve **14+ sahalar** — ikisi de favori-kazanma
  ve kalabalık tavanına dayanıyor.
- Eküri sistemi doğru çalışıyor (+0.4p, marjinal ama bedava).
- Uygulanan: eküri etiket + 14+ banko cezası. Sonraki toplu testte C/D/E ölçülmeli.
