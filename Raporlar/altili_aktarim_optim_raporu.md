# Altılı 5-Satır Aktarım Optimizasyonu (temiz karşılaştırma)

Evren: **441** altılı (Harbi_Ganyan_Analiz tahmin + TJK JSON sonuç). Yalnız Ortaklı dağıtım modu değişir; Simitçi/Harbi sabit. İç içe kural korunur.

## 1. Teorik tavan
- 5 satır 6 ayağın TAMAMINDA kazananı buluyor: **236/441 (%53.5)** → mükemmel aktarımda 'herhangi biri 6/6' tavanı budur.
- 5 satır ayak dağılımı: 6/6=236, 5/6=149, 4/6=42, 3/6=12, 2/6=2

## 2. Adaylar — 'herhangi biri 6/6' (asıl ürün metriği)

| Aday | Herhangi biri 6/6 | Üretime göre net | Kazanılan | Kaybedilen | Ortaklı ort. bedel |
|---|---:|---:|---:|---:|---:|
| baseline (saf nested @2200) | 109/441 (%24.7) | -6 | +8 | -14 | 2000 TL |
| test3 @2200 | 107/441 (%24.3) | -8 | +4 | -12 | 1998 TL |
| test3 @2400 | 113/441 (%25.6) | -2 | +5 | -7 | 2355 TL |
| test3 @2500 (ÜRETİM/REF) | 115/441 (%26.1) | +0 | +0 | -0 | 2424 TL |
| test3 @2600 | 115/441 (%26.1) | +0 | +0 | -0 | 2436 TL |
| test3 @2800 | 118/441 (%26.8) | +3 | +4 | -1 | 2531 TL |
| test3 @3000 | 124/441 (%28.1) | +9 | +13 | -4 | 2950 TL |
| test3 @3200 | 124/441 (%28.1) | +9 | +12 | -3 | 3036 TL |
| sadece_ekle @2500 (churn) | 115/441 (%26.1) | +0 | +12 | -12 | 2387 TL |

## 3. Kademe bazlı 6/6

### Simitçi 6'lısı
| Aday | 6/6 | 5/6 | Ort. bedel |
|---|---:|---:|---:|
| baseline (saf nested @2200) | 59/441 (%13.4) | 148 | 589 TL |
| test3 @2200 | 59/441 (%13.4) | 148 | 589 TL |
| test3 @2400 | 59/441 (%13.4) | 148 | 589 TL |
| test3 @2500 (ÜRETİM/REF) | 59/441 (%13.4) | 148 | 589 TL |
| test3 @2600 | 59/441 (%13.4) | 148 | 589 TL |
| test3 @2800 | 59/441 (%13.4) | 148 | 589 TL |
| test3 @3000 | 59/441 (%13.4) | 148 | 589 TL |
| test3 @3200 | 59/441 (%13.4) | 148 | 589 TL |
| sadece_ekle @2500 (churn) | 59/441 (%13.4) | 148 | 589 TL |

### Harbi Ganyan 6'lısı
| Aday | 6/6 | 5/6 | Ort. bedel |
|---|---:|---:|---:|
| baseline (saf nested @2200) | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @2200 | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @2400 | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @2500 (ÜRETİM/REF) | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @2600 | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @2800 | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @3000 | 97/441 (%22.0) | 174 | 1555 TL |
| test3 @3200 | 97/441 (%22.0) | 174 | 1555 TL |
| sadece_ekle @2500 (churn) | 97/441 (%22.0) | 174 | 1555 TL |

### Ortaklı 6'lı
| Aday | 6/6 | 5/6 | Ort. bedel |
|---|---:|---:|---:|
| baseline (saf nested @2200) | 109/441 (%24.7) | 185 | 2000 TL |
| test3 @2200 | 107/441 (%24.3) | 189 | 1998 TL |
| test3 @2400 | 113/441 (%25.6) | 194 | 2355 TL |
| test3 @2500 (ÜRETİM/REF) | 115/441 (%26.1) | 195 | 2424 TL |
| test3 @2600 | 115/441 (%26.1) | 195 | 2436 TL |
| test3 @2800 | 118/441 (%26.8) | 191 | 2531 TL |
| test3 @3000 | 124/441 (%28.1) | 192 | 2950 TL |
| test3 @3200 | 124/441 (%28.1) | 197 | 3036 TL |
| sadece_ekle @2500 (churn) | 115/441 (%26.1) | 193 | 2387 TL |

## 4. Referans (üretim) Ortaklı 5/6 kayıplarının anatomisi

- 5/6 kalan Ortaklı kupon: **195**
- Kaçan kazanan 5-satırdaydı (genişletilebilir kayıp): **109 (%55.9)**
- Kaçan 5-satır slotu: DIŞI=86, YAZ=41, HAR=31, BOM=26, SUR=11
- Kaçan kazanan ANA-rank: #2=11, #3=41, #4=26, #5=32, #6=22, #7=24, #8=15, #9=7, #10=5, #11=9, #12=1, #13=1, #16=1
- Saha büyüklüğü: <=9=110, 14+=38, 10-11=28, 12-13=19
- Koşu tipi: sartli=87, handikap=63, maiden=23, kv_grup=22
- Skor farkı: >=25=68, <8=49, 15-25=45, 8-15=33

## 5. Karar ve Öneri

1. **Sabit bütçede strateji ~nötr.** 2500 TL'de test3 / sadece_ekle / test3_ekle hepsi ~115/441 (%26.1) veriyor; test3 zaten bütçeyi doldurduğu için ekleme stratejisinin yeri kalmıyor. Yani üretim, 2500 bütçesinin AFFORDABLE optimumuna zaten yakın.
2. **Asıl kaldıraç Ortaklı BÜTÇESİ.** İç içe kural korunarak (Ortaklı ⊇ Harbi) bütçe-isabet eğrisi: 2500→115, 2800→118 (+3, ~kayıpsız), 3000→**124 (+9)**, 3200→124 (doygun). Eğri 3000 TL'de doyuyor; ötesi katkı vermiyor.
3. **Teorik tavan (%53.5) ULAŞILAMAZ.** 6 ayağın tamamında genişliği kazanan-rankına çıkarmak çarpımsal maliyet yüzünden hiçbir bütçeye sığmaz. Gerçekçi tavan ~%28 (3000 TL, iç içe).
4. **Kayıpların %44'ü model tavanı.** 195 Ortaklı 5/6 kaybının 86'sında (%44.1) kazanan 5-satır DIŞI — bu kupon dağıtımıyla DEĞİL, ancak 5-satır/ana-skor modelini iyileştirerek çözülür.
5. **Sıradaki cephe = banko.** Kaçan ayakların önemli kısmı tek-at banko ayağı; zayıf banko üç kuponu birden öldürüyor. Global banko eşiği denemeleri (0.70/0.80) NET NEGATİF çıktı; hedefli (yalnız zayıf-favori + bol-bütçe Ortaklı'da banko ayağını 2'ye açma) ayrı test edilmeli.

**Üretim önerisi:** İç içe kural + test3 mantığı korunsun. Tek anlamlı kaldıraç bütçe; kullanıcı kararına göre Ortaklı üst bütçe **2500 → 3000 TL**'ye çıkarılırsa iç içe kuralı bozmadan %26.1 → ~%28.1 (+9 altılı / tüm aralık). 2800 TL ara seçenek (+3, ~kayıpsız). Kod altyapısı hazır: `build_nested_tiers(..., ortakli_mode='test3')` + KUPON_TIERS Ortaklı üst sınırı.
