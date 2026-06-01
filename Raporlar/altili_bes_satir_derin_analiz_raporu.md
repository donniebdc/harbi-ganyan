# Altılı 5 Satır Aktarım Derin Analizi

Kaynak evren: `Harbi_Ganyan_Analiz` tahminleri + `_Altili.txt` tanımları + `Sonuclar JSON` sonuçları.
`TahminSonuçları` TXT sanity: 119 dosya, 1308 kupon satırı; dağılım: 6/6=268, 5/6=495, 4/6=377, 3/6=125, 2/6=36, 1/6=4, 0/6=3
Toplam ölçülen altılı: **433**

## 1. Teorik Üst Sınır: 5 Satır Altılıyı Zaten Kapsıyor mu?

- 5 satırın 6 ayağın tamamında kazananı bulduğu altılı: **234 / 433 (%54.0)**
- 5 satırın en az 5 ayağı bulduğu altılı: **381 / 433 (%88.0)**
- 5 satır ayak dağılımı: 6/6=234, 5/6=147, 4/6=40, 3/6=10, 2/6=2

Yorum: 5 satır 6/6 kapsadığı halde kupon 6/6 değilse problem tahmin değil, kupon aktarım/dağıtım problemidir.

## 2. Mevcut Sistem: 5/6 Kalan Kuponların Anatomisi

### Simitçi 6'lısı
- Altılı: 433 | 6/6: **57 (%13.2)** | Ortalama bedel: 589 TL
- Doğru ayak dağılımı: 6/6=57, 5/6=146, 4/6=146, 3/6=62, 2/6=20, 1/6=2
- 5/6 kalan: **146**
- 5/6 kalanların içinde kaçan kazanan 5 satırdaydı: **98 (%67.1)**
- Bunların ayak genişliği kazanan ANA-rankından küçüktü: **98**
- Kaçan 5 satır slotu: 5SATIR_DISI=48, YAZ=33, BOM=30, HAR=27, SUR=8
- Kaçan ANA-rank: #2=8, #3=33, #4=30, #5=28, #6=9, #7=13, #8=10, #9=5, #10=2, #11=6, #13=1, #16=1
- Kaçan saha büyüklüğü: 10-11=31, <=9=73, 14+=31, 12-13=11
- Kaçan ayak banko liderdi: **36**

### Harbi Ganyan 6'lısı
- Altılı: 433 | 6/6: **95 (%21.9)** | Ortalama bedel: 1555 TL
- Doğru ayak dağılımı: 6/6=95, 5/6=172, 4/6=124, 3/6=34, 2/6=7, 1/6=1
- 5/6 kalan: **172**
- 5/6 kalanların içinde kaçan kazanan 5 satırdaydı: **105 (%61.0)**
- Bunların ayak genişliği kazanan ANA-rankından küçüktü: **105**
- Kaçan 5 satır slotu: 5SATIR_DISI=67, HAR=36, YAZ=36, BOM=23, SUR=10
- Kaçan ANA-rank: #2=10, #3=36, #4=23, #5=36, #6=14, #7=21, #8=14, #9=7, #10=2, #11=7, #13=1, #16=1
- Kaçan saha büyüklüğü: <=9=92, 14+=36, 10-11=30, 12-13=14
- Kaçan ayak banko liderdi: **54**

### Ortaklı 6'lı
- Altılı: 433 | 6/6: **107 (%24.7)** | Ortalama bedel: 2000 TL
- Doğru ayak dağılımı: 6/6=107, 5/6=183, 4/6=102, 3/6=33, 2/6=7, 1/6=1
- 5/6 kalan: **183**
- 5/6 kalanların içinde kaçan kazanan 5 satırdaydı: **111 (%60.7)**
- Bunların ayak genişliği kazanan ANA-rankından küçüktü: **111**
- Kaçan 5 satır slotu: 5SATIR_DISI=72, YAZ=39, HAR=35, BOM=26, SUR=11
- Kaçan ANA-rank: #2=11, #3=39, #4=26, #5=35, #6=14, #7=23, #8=16, #9=7, #10=3, #11=7, #13=1, #16=1
- Kaçan saha büyüklüğü: <=9=101, 14+=36, 10-11=31, 12-13=15
- Kaçan ayak banko liderdi: **65**

## 3. Alternatif Kuralların Backtest Sonucu

Varyantlar:
- `mevcut`: bugün üretimdeki iç içe kupon + mevcut tier policy.
- `5satir_sira`: aynı ayak genişlikleri ve aynı bütçe; sadece seçilecek at sırası 5 satır öncelikli.
- `banko070` / `banko080`: banko güven eşiği 0.50 yerine 0.70 / 0.80; zayıf banko ayakları 2 ata çıkar.
- `banko070_5sira`: 0.70 banko eşiği + 5 satır öncelikli seçim sırası.
- `bagimsiz`: Simitçi/Harbi/Ortaklı kuponları iç içe değil, kendi bütçesinde ayrı kurulur.
- `bagimsiz_5sira`: bağımsız kupon + 5 satır öncelikli seçim.
- `icice_5satir_2200`: Simitçi ⊆ Harbi ⊆ Ortaklı korunur; bütçe yettikçe eksik 5 satır atları eklenir.
- `icice_5satir_2500`: aynı aktarım, Ortaklı üst bütçe 2200 yerine 2500 TL.
- `ortakli_2500_sadece_ekle`: mevcut Ortaklı 2200 kuponu aynen korunur; 2500 TL'ye kadar yalnız eksik 5 satır atları eklenir.
- `test1_banko_genis`: bir doğru banko yakalama varsayımına yaklaşmak için en güçlü ayak tek at; diğer ayaklara 5 satır aktarımı.
- `test2_banko_iki_fav`: en güçlü ayak banko, ikinci güçlü ayak maksimum 2 favori; kalan ayaklar geniş.
- `test3_tip_genis`: handikap/maiden/şartlı koşuları önce genişletir, sonra 5 satır aktarımı yapar.
- `_korumali`: çok güçlü küçük saha bankosu tek at kalır; diğer eksik 5 satır atları eklenir.
- `ortakli_floor`: Ortaklı kupona da Harbi'deki 5 satır tabanı açılır.
- `flow5_floor`: akış eşiği 3 yerine 5; 5 satır tabanı daha agresif.
- `risk5_5satir`: bütçe yettikçe riskli ayakları 5 ata yaklaştırır ve seçimi 5 satır öncelikli yapar.

### Simitçi 6'lısı
| Varyant | 6/6 | 5/6 | Ortalama bedel | Net 6/6 | Kazanılan | Kaybedilen |
|---|---:|---:|---:|---:|---:|---:|
| mevcut | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| 5satir_sira | 57/433 (%13.2) | 144 | 589 TL | +0 | +0 | -0 |
| banko070 | 54/433 (%12.5) | 142 | 589 TL | -3 | +7 | -10 |
| banko070_5sira | 54/433 (%12.5) | 140 | 589 TL | -3 | +7 | -10 |
| banko080 | 54/433 (%12.5) | 142 | 589 TL | -3 | +7 | -10 |
| bagimsiz | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| bagimsiz_5sira | 57/433 (%13.2) | 144 | 589 TL | +0 | +0 | -0 |
| icice_5satir_2200 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| icice_5satir_2200_korumali | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| icice_5satir_2500 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| icice_5satir_2500_korumali | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| ortakli_2500_sadece_ekle | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| ortakli_2500_sadece_ekle_korumali | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| test1_banko_genis_2500 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| test1_banko_genis_3000 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| test2_banko_iki_fav_2500 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| test2_banko_iki_fav_3000 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| test3_tip_genis_2500 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| test3_tip_genis_3000 | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| ortakli_floor | 57/433 (%13.2) | 146 | 589 TL | +0 | +0 | -0 |
| flow5_floor | 50/433 (%11.5) | 149 | 583 TL | -7 | +10 | -17 |
| risk5_5satir | 57/433 (%13.2) | 144 | 589 TL | +0 | +0 | -0 |

### Harbi Ganyan 6'lısı
| Varyant | 6/6 | 5/6 | Ortalama bedel | Net 6/6 | Kazanılan | Kaybedilen |
|---|---:|---:|---:|---:|---:|---:|
| mevcut | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| 5satir_sira | 96/433 (%22.2) | 168 | 1555 TL | +1 | +1 | -0 |
| banko070 | 93/433 (%21.5) | 164 | 1554 TL | -2 | +10 | -12 |
| banko070_5sira | 94/433 (%21.7) | 160 | 1554 TL | -1 | +11 | -12 |
| banko080 | 93/433 (%21.5) | 164 | 1554 TL | -2 | +10 | -12 |
| bagimsiz | 97/433 (%22.4) | 171 | 1556 TL | +2 | +10 | -8 |
| bagimsiz_5sira | 98/433 (%22.6) | 169 | 1556 TL | +3 | +11 | -8 |
| icice_5satir_2200 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| icice_5satir_2200_korumali | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| icice_5satir_2500 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| icice_5satir_2500_korumali | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| ortakli_2500_sadece_ekle | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| ortakli_2500_sadece_ekle_korumali | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| test1_banko_genis_2500 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| test1_banko_genis_3000 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| test2_banko_iki_fav_2500 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| test2_banko_iki_fav_3000 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| test3_tip_genis_2500 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| test3_tip_genis_3000 | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| ortakli_floor | 95/433 (%21.9) | 172 | 1555 TL | +0 | +0 | -0 |
| flow5_floor | 87/433 (%20.1) | 177 | 1557 TL | -8 | +8 | -16 |
| risk5_5satir | 96/433 (%22.2) | 168 | 1555 TL | +1 | +1 | -0 |

### Ortaklı 6'lı
| Varyant | 6/6 | 5/6 | Ortalama bedel | Net 6/6 | Kazanılan | Kaybedilen |
|---|---:|---:|---:|---:|---:|---:|
| mevcut | 107/433 (%24.7) | 183 | 2000 TL | +0 | +0 | -0 |
| 5satir_sira | 107/433 (%24.7) | 183 | 2000 TL | +0 | +1 | -1 |
| banko070 | 105/433 (%24.2) | 176 | 1996 TL | -2 | +10 | -12 |
| banko070_5sira | 105/433 (%24.2) | 175 | 1996 TL | -2 | +11 | -13 |
| banko080 | 105/433 (%24.2) | 176 | 1996 TL | -2 | +10 | -12 |
| bagimsiz | 111/433 (%25.6) | 189 | 1994 TL | +4 | +16 | -12 |
| bagimsiz_5sira | 109/433 (%25.2) | 191 | 1994 TL | +2 | +15 | -13 |
| icice_5satir_2200 | 107/433 (%24.7) | 183 | 2000 TL | +0 | +0 | -0 |
| icice_5satir_2200_korumali | 107/433 (%24.7) | 183 | 2000 TL | +0 | +0 | -0 |
| icice_5satir_2500 | 112/433 (%25.9) | 192 | 2388 TL | +5 | +12 | -7 |
| icice_5satir_2500_korumali | 112/433 (%25.9) | 192 | 2388 TL | +5 | +12 | -7 |
| ortakli_2500_sadece_ekle | 115/433 (%26.6) | 188 | 2391 TL | +8 | +8 | -0 |
| ortakli_2500_sadece_ekle_korumali | 115/433 (%26.6) | 188 | 2391 TL | +8 | +8 | -0 |
| test1_banko_genis_2500 | 88/433 (%20.3) | 178 | 2413 TL | -19 | +27 | -46 |
| test1_banko_genis_3000 | 88/433 (%20.3) | 178 | 2413 TL | -19 | +27 | -46 |
| test2_banko_iki_fav_2500 | 87/433 (%20.1) | 171 | 1499 TL | -20 | +26 | -46 |
| test2_banko_iki_fav_3000 | 87/433 (%20.1) | 171 | 1499 TL | -20 | +26 | -46 |
| test3_tip_genis_2500 | 114/433 (%26.3) | 168 | 2306 TL | +7 | +50 | -43 |
| test3_tip_genis_3000 | 121/433 (%27.9) | 176 | 2871 TL | +14 | +52 | -38 |
| ortakli_floor | 106/433 (%24.5) | 185 | 2002 TL | -1 | +0 | -1 |
| flow5_floor | 94/433 (%21.7) | 192 | 2005 TL | -13 | +8 | -21 |
| risk5_5satir | 107/433 (%24.7) | 183 | 2000 TL | +0 | +1 | -1 |

## 3.1 Üç Kupondan Herhangi Biri Tuttu mu?

| Varyant | Herhangi biri 6/6 | Net | Kazanılan | Kaybedilen |
|---|---:|---:|---:|---:|
| mevcut | 107/433 (%24.7) | +0 | +0 | -0 |
| 5satir_sira | 107/433 (%24.7) | +0 | +1 | -1 |
| banko070 | 105/433 (%24.2) | -2 | +10 | -12 |
| banko070_5sira | 105/433 (%24.2) | -2 | +11 | -13 |
| banko080 | 105/433 (%24.2) | -2 | +10 | -12 |
| bagimsiz | 122/433 (%28.2) | +15 | +23 | -8 |
| bagimsiz_5sira | 121/433 (%27.9) | +14 | +23 | -9 |
| icice_5satir_2200 | 107/433 (%24.7) | +0 | +0 | -0 |
| icice_5satir_2200_korumali | 107/433 (%24.7) | +0 | +0 | -0 |
| icice_5satir_2500 | 112/433 (%25.9) | +5 | +12 | -7 |
| icice_5satir_2500_korumali | 112/433 (%25.9) | +5 | +12 | -7 |
| ortakli_2500_sadece_ekle | 115/433 (%26.6) | +8 | +8 | -0 |
| ortakli_2500_sadece_ekle_korumali | 115/433 (%26.6) | +8 | +8 | -0 |
| test1_banko_genis_2500 | 125/433 (%28.9) | +18 | +27 | -9 |
| test1_banko_genis_3000 | 125/433 (%28.9) | +18 | +27 | -9 |
| test2_banko_iki_fav_2500 | 125/433 (%28.9) | +18 | +26 | -8 |
| test2_banko_iki_fav_3000 | 125/433 (%28.9) | +18 | +26 | -8 |
| test3_tip_genis_2500 | 147/433 (%33.9) | +40 | +50 | -10 |
| test3_tip_genis_3000 | 149/433 (%34.4) | +42 | +52 | -10 |
| ortakli_floor | 106/433 (%24.5) | -1 | +0 | -1 |
| flow5_floor | 94/433 (%21.7) | -13 | +8 | -21 |
| risk5_5satir | 107/433 (%24.7) | +0 | +1 | -1 |

## 3.1B Kullanıcı İstediği 3 Özel Test

| Test | Herhangi biri 6/6 | Net | Kazanılan | Kaybedilen | Ortaklı ort. bedel |
|---|---:|---:|---:|---:|---:|
| Test 1 - banko + diğer ayaklar geniş 2500 | 125/433 (%28.9) | +18 | +27 | -9 | 2413 TL |
| Test 1 - banko + diğer ayaklar geniş 3000 | 125/433 (%28.9) | +18 | +27 | -9 | 2413 TL |
| Test 2 - banko + başka ayak 2 favori 2500 | 125/433 (%28.9) | +18 | +26 | -8 | 1499 TL |
| Test 2 - banko + başka ayak 2 favori 3000 | 125/433 (%28.9) | +18 | +26 | -8 | 1499 TL |
| Test 3 - handikap/maiden/şartlı geniş 2500 | 147/433 (%33.9) | +40 | +50 | -10 | 2306 TL |
| Test 3 - handikap/maiden/şartlı geniş 3000 | 149/433 (%34.4) | +42 | +52 | -10 | 2871 TL |

## 3.1A Grid Test: Ortaklı Bütçe + 5 Satır Aktarım Oranlaması

Bu grid mevcut Ortaklı kuponu bozmadan yalnız eksik 5 satır atlarını ekler. Simitçi ve Harbi aynen kalır.
Test edilenler: bütçe 2200/2300/2400/2500/2600/2800/3000, 5 farklı slot profili, risk katsayısı 0/0.5/1/1.5, ayak başı ekleme limiti 1/2/sınırsız, banko koruma açık/kapalı.

| Sıra | Bütçe | Profil | Risk | Ayak ek limiti | Banko koruma | Herhangi biri | Ortaklı | Ort. bedel | Net | Kazanılan | Kaybedilen |
|---:|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | 3000 | favori_oncelik | 0.5 | 1 | hayır | 127/433 (%29.3) | 127/433 | 2773 TL | +20 | +20 | -0 |
| 2 | 3000 | favori_oncelik | 0.5 | 1 | evet | 127/433 (%29.3) | 127/433 | 2773 TL | +20 | +20 | -0 |
| 3 | 3000 | favori_oncelik | 0.5 | 2 | hayır | 127/433 (%29.3) | 127/433 | 2773 TL | +20 | +20 | -0 |
| 4 | 3000 | favori_oncelik | 0.5 | 2 | evet | 127/433 (%29.3) | 127/433 | 2773 TL | +20 | +20 | -0 |
| 5 | 3000 | favori_oncelik | 0.5 | sınırsız | hayır | 127/433 (%29.3) | 127/433 | 2773 TL | +20 | +20 | -0 |
| 6 | 3000 | favori_oncelik | 0.5 | sınırsız | evet | 127/433 (%29.3) | 127/433 | 2773 TL | +20 | +20 | -0 |
| 7 | 3000 | yaz_bom_har | 0 | 1 | hayır | 126/433 (%29.1) | 126/433 | 2804 TL | +19 | +19 | -0 |
| 8 | 3000 | yaz_bom_har | 0 | 1 | evet | 126/433 (%29.1) | 126/433 | 2804 TL | +19 | +19 | -0 |
| 9 | 3000 | yaz_bom_har | 0 | 2 | hayır | 126/433 (%29.1) | 126/433 | 2804 TL | +19 | +19 | -0 |
| 10 | 3000 | yaz_bom_har | 0 | 2 | evet | 126/433 (%29.1) | 126/433 | 2804 TL | +19 | +19 | -0 |
| 11 | 3000 | yaz_bom_har | 0 | sınırsız | hayır | 126/433 (%29.1) | 126/433 | 2804 TL | +19 | +19 | -0 |
| 12 | 3000 | yaz_bom_har | 0 | sınırsız | evet | 126/433 (%29.1) | 126/433 | 2804 TL | +19 | +19 | -0 |
| 13 | 3000 | dengeli | 0 | 1 | hayır | 126/433 (%29.1) | 126/433 | 2809 TL | +19 | +19 | -0 |
| 14 | 3000 | dengeli | 0 | 1 | evet | 126/433 (%29.1) | 126/433 | 2809 TL | +19 | +19 | -0 |
| 15 | 3000 | dengeli | 0 | 2 | hayır | 126/433 (%29.1) | 126/433 | 2809 TL | +19 | +19 | -0 |

En iyi grid: bütçe **3000 TL**, profil **favori_oncelik**, risk katsayısı **0.5**, ayak ek limiti **1**, banko koruma **kapalı**.
2500 TL ve altı en iyi grid: bütçe **2500 TL**, profil **surpriz_agir**, risk katsayısı **0.5**, ayak ek limiti **1**, banko koruma **kapalı** -> 115/433 (%26.6), net +8, kayıp 0.

## 3.2 Tarih Segmenti Kontrolü

Ana adaylar için dönem kırılımı. Amaç tek döneme aşırı uyumu ayırmak.

| Dönem | Mevcut herhangi biri | Sadece ekle 2500 | En iyi grid | Grid fark | Bağımsız referans | 5 satır teorik 6/6 |
|---|---:|---:|---:|---:|---:|---:|
| Şubat-Mart | 45/195 (%23.1) | 49/195 (%25.1) | 58/195 (%29.7) | +13 | 53/195 (%27.2) | 100/195 (%51.3) |
| Nisan | 31/116 (%26.7) | 32/116 (%27.6) | 35/116 (%30.2) | +4 | 33/116 (%28.4) | 72/116 (%62.1) |
| Mayıs 1-15 | 16/62 (%25.8) | 17/62 (%27.4) | 18/62 (%29.0) | +2 | 18/62 (%29.0) | 33/62 (%53.2) |
| Mayıs 16-30 | 15/60 (%25.0) | 17/60 (%28.3) | 16/60 (%26.7) | +1 | 18/60 (%30.0) | 29/60 (%48.3) |

## 4. Örnek 5/6 Kaçışlar

### Simitçi 6'lısı
- 2026-02-01 ADANA alt#2 K8: kazanan No:2, 5satir=HAR, ANA#5, width=3, n_at=11, fark=37.2, banko=False
- 2026-02-01 IZMIR alt#2 K7: kazanan No:4, 5satir=SUR, ANA#2, width=1, n_at=4, fark=41.4, banko=True
- 2026-02-02 BURSA alt#2 K5: kazanan No:12, 5satir=HAR, ANA#5, width=4, n_at=14, fark=18.2, banko=False
- 2026-02-03 ANTALYA alt#1 K6: kazanan No:8, 5satir=BOM, ANA#4, width=2, n_at=8, fark=27.6, banko=True
- 2026-02-03 ANTALYA alt#2 K6: kazanan No:8, 5satir=BOM, ANA#4, width=3, n_at=8, fark=27.6, banko=False
- 2026-02-06 BURSA alt#1 K1: kazanan No:3, 5satir=DIŞI, ANA#6, width=4, n_at=11, fark=37.6, banko=False
- 2026-02-07 ADANA alt#2 K8: kazanan No:8, 5satir=DIŞI, ANA#11, width=4, n_at=17, fark=12.9, banko=False
- 2026-02-07 ISTANBUL alt#2 K6: kazanan No:9, 5satir=HAR, ANA#5, width=3, n_at=11, fark=4.4, banko=False
- 2026-02-09 BURSA alt#1 K5: kazanan No:2, 5satir=YAZ, ANA#3, width=2, n_at=11, fark=1.8, banko=False
- 2026-02-10 ADANA alt#2 K5: kazanan No:1, 5satir=BOM, ANA#4, width=3, n_at=11, fark=8.1, banko=False

### Harbi Ganyan 6'lısı
- 2026-02-01 IZMIR alt#2 K7: kazanan No:4, 5satir=SUR, ANA#2, width=1, n_at=4, fark=41.4, banko=True
- 2026-02-02 BURSA alt#2 K5: kazanan No:12, 5satir=HAR, ANA#5, width=4, n_at=14, fark=18.2, banko=False
- 2026-02-03 ANTALYA alt#1 K6: kazanan No:8, 5satir=BOM, ANA#4, width=2, n_at=8, fark=27.6, banko=True
- 2026-02-04 SANLIURFA alt#1 K4: kazanan No:1, 5satir=DIŞI, ANA#6, width=2, n_at=6, fark=3.9, banko=False
- 2026-02-05 ANTALYA alt#2 K7: kazanan No:6, 5satir=HAR, ANA#5, width=4, n_at=11, fark=5.8, banko=False
- 2026-02-05 IZMIR alt#1 K5: kazanan No:1, 5satir=HAR, ANA#5, width=4, n_at=5, fark=18.1, banko=False
- 2026-02-06 BURSA alt#1 K1: kazanan No:3, 5satir=DIŞI, ANA#6, width=4, n_at=11, fark=37.6, banko=False
- 2026-02-07 ADANA alt#2 K8: kazanan No:8, 5satir=DIŞI, ANA#11, width=5, n_at=17, fark=12.9, banko=False
- 2026-02-07 ISTANBUL alt#2 K6: kazanan No:9, 5satir=HAR, ANA#5, width=4, n_at=11, fark=4.4, banko=False
- 2026-02-09 BURSA alt#1 K5: kazanan No:2, 5satir=YAZ, ANA#3, width=2, n_at=11, fark=1.8, banko=False

### Ortaklı 6'lı
- 2026-02-01 IZMIR alt#2 K7: kazanan No:4, 5satir=SUR, ANA#2, width=1, n_at=4, fark=41.4, banko=True
- 2026-02-02 BURSA alt#1 K2: kazanan No:2, 5satir=SUR, ANA#2, width=1, n_at=5, fark=51.0, banko=True
- 2026-02-02 BURSA alt#2 K5: kazanan No:12, 5satir=HAR, ANA#5, width=4, n_at=14, fark=18.2, banko=False
- 2026-02-03 ANTALYA alt#1 K6: kazanan No:8, 5satir=BOM, ANA#4, width=2, n_at=8, fark=27.6, banko=True
- 2026-02-04 SANLIURFA alt#1 K4: kazanan No:1, 5satir=DIŞI, ANA#6, width=2, n_at=6, fark=3.9, banko=False
- 2026-02-05 IZMIR alt#1 K5: kazanan No:1, 5satir=HAR, ANA#5, width=4, n_at=5, fark=18.1, banko=False
- 2026-02-06 BURSA alt#1 K1: kazanan No:3, 5satir=DIŞI, ANA#6, width=5, n_at=11, fark=37.6, banko=False
- 2026-02-07 ADANA alt#2 K8: kazanan No:8, 5satir=DIŞI, ANA#11, width=6, n_at=17, fark=12.9, banko=False
- 2026-02-07 ISTANBUL alt#2 K6: kazanan No:9, 5satir=HAR, ANA#5, width=4, n_at=11, fark=4.4, banko=False
- 2026-02-09 BURSA alt#1 K5: kazanan No:2, 5satir=YAZ, ANA#3, width=2, n_at=11, fark=1.8, banko=False

## 5. Algoritmik Karar

1. Üretim değişikliği sadece pozitif holdout/backtest veren varyantla yapılmalı; negatif varyantlar üretime alınmamalı.
2. Kullanıcı ürün kuralı gereği üretim adayı `bagimsiz` değil; Simitçi ⊆ Harbi ⊆ Ortaklı kuralını koruyan `icice_5satir_*` varyantlarıdır.
3. En güvenli üretim adayı `ortakli_2500_sadece_ekle` olmalıdır: mevcut Ortaklı kuponu bozmaz, sadece bütçe artışını eksik 5 satır atlarına harcar.
4. Banko eşiği varyantları tek başına negatifse banko güven eşiği artırılmamalı; bunun yerine üst kuponda eksik 5 satır atı bütçe-içi eklenmelidir.
5. Kör `flow5_floor` gibi agresif akış genişletmeleri kazandırdığı kuponlardan fazlasını kaybettiriyorsa üretime alınmamalı.
