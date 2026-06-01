# Kapsamlı Sistem Analizi Raporu

Kapsam: 01.04.2026 - 30.05.2026. 31.05.2026 klasörü mevcut olsa da bu rapora dahil edilmedi.

## Veri Kapsamı

- Okunan tarih Tahminler dosyası: 60
- Okunan tarih Altili dosyası: 60
- Tahmin koşusu: 1068
- CSV ile kazananı eşleşen koşu: 1050
- Okunan altılı kupon kaydı: 678
- CSV ile eşleşen altılı kupon kaydı: 660
- Pegadrom AI TXT koşusu: 1087
- pegadrom_skorlar.json koşusu: 1028

## 5 Satırlı Tahmin Performansı

- İlk1: %38.0
- İlk3: %73.5
- İlk4: %84.0
- İlk5: %90.2
- 5 satır isabet: %90.4

## Alan Büyüklüğü Kırılımı

| Kırılım | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır |
|---|---:|---:|---:|---:|---:|---:|
| <=9 | 501 | %41.5 | %80.6 | %90.6 | %95.4 | %95.4 |
| 10-13 | 374 | %37.7 | %71.1 | %82.1 | %89.6 | %89.6 |
| 14+ | 175 | %28.6 | %58.3 | %69.1 | %76.6 | %77.7 |

## Koşu Grubu Kırılımı

| Kırılım | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır |
|---|---:|---:|---:|---:|---:|---:|
| maiden | 206 | %41.3 | %77.2 | %86.9 | %93.2 | %93.2 |
| sartli | 482 | %38.0 | %74.3 | %84.4 | %90.9 | %90.9 |
| handikap | 299 | %33.8 | %69.2 | %79.9 | %86.0 | %86.6 |
| kv_grup | 63 | %47.6 | %76.2 | %90.5 | %95.2 | %95.2 |

## Pist Kırılımı

| Kırılım | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır |
|---|---:|---:|---:|---:|---:|---:|
| Kum | 650 | %39.4 | %76.0 | %85.7 | %91.2 | %91.5 |
| Sentetik | 139 | %37.4 | %71.2 | %82.0 | %92.1 | %92.1 |
| Çim | 261 | %34.9 | %68.6 | %80.8 | %86.6 | %86.6 |

## Mesafe Kırılımı

| Kırılım | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır |
|---|---:|---:|---:|---:|---:|---:|
| kisa<=1400 | 520 | %38.5 | %72.7 | %83.1 | %90.0 | %89.8 |
| orta<=1800 | 211 | %32.7 | %70.1 | %80.1 | %86.7 | %88.2 |
| uzun>1800 | 319 | %40.8 | %77.1 | %88.1 | %92.8 | %92.8 |

## Kaynak Kırılımı

| Kırılım | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır |
|---|---:|---:|---:|---:|---:|---:|
| AGF+PEG_AKIS | 671 | %38.0 | %74.7 | %84.9 | %90.5 | %90.8 |
| AGF+PEG_AKIS+JOK | 373 | %37.8 | %71.3 | %82.3 | %89.8 | %89.8 |
| G+PEG_AKIS | 5 | %60.0 | %100.0 | %100.0 | %100.0 | %100.0 |
| G+PEG_AKIS+JOK | 1 | %0.0 | %0.0 | %0.0 | %0.0 | %0.0 |

## HAR Satırı Etkisi

- Top4 dışında kalan kazanan sayısı: 168
- HAR'ın bunları yakaladığı yarış: 67 (%39.9)
- 14+ sahalarda top4 dışı: 54, HAR yakalama: 15 (%27.8)
- <=13 sahalarda top4 dışı: 114, HAR yakalama: 52 (%45.6)

## Altılı Ganyan Performansı

| Kademe | Kupon | İsabet | İsabet % | Ort. maliyet | Top. maliyet | Top. dönüş | Net |
|---|---:|---:|---:|---:|---:|---:|---:|
| Simitci | 220 | 30 | %13.6 | 480 TL | 105492 TL | 365714 TL | +260222 TL |
| Harbi | 220 | 45 | %20.5 | 1547 TL | 340286 TL | 871048 TL | +530761 TL |
| Ortakli | 220 | 58 | %26.4 | 1930 TL | 424698 TL | 1082684 TL | +657987 TL |

### Altılı Genişlik ve Kayıp Analizi

| Kademe | En sık ayak genişlikleri | İlk kayıp genişliği | İlk kayıp alan segmenti |
|---|---|---|---|
| Simitci | 1:60, 2:564, 3:217, 4:378, 5:101 | 1:14, 2:91, 3:26, 4:50, 5:9 | 10-11:51, 12-13:30, 14+:31, 8-9:38, <=7:40 |
| Harbi | 1:60, 2:287, 3:132, 4:570, 5:257, 6:10, 7:4 | 1:15, 2:51, 3:16, 4:61, 5:28, 6:2, 7:2 | 10-11:38, 12-13:27, 14+:36, 8-9:35, <=7:39 |
| Ortakli | 1:60, 2:224, 3:154, 4:566, 5:294, 6:18, 7:4 | 1:17, 2:38, 3:18, 4:50, 5:33, 6:5, 7:1 | 10-11:30, 12-13:26, 14+:36, 8-9:34, <=7:36 |

## Pegadrom AI TXT Sinyal Gücü

| Sinyal | n | İlk1 | İlk3 | İlk4 | İlk5 |
|---|---:|---:|---:|---:|---:|
| PegTXT akış rank | 1044 | %33.3 | %73.2 | %81.8 | %87.5 |
| PegTXT galop reason | 420 | %28.3 | %67.4 | %79.5 | %88.1 |
| PegTXT hiz reason | 450 | %35.1 | %72.2 | %83.6 | %91.3 |
| PegTXT model | 1038 | %22.6 | %52.1 | %61.3 | %71.7 |
| PegTXT pist/mesafe reason | 812 | %20.4 | %51.8 | %64.2 | %74.8 |
| PegTXT veri | 1038 | %14.7 | %39.3 | %51.3 | %63.2 |

## pegadrom_skorlar.json Sinyal Gücü

| Sinyal | n | İlk1 | İlk3 | İlk4 | İlk5 |
|---|---:|---:|---:|---:|---:|
| JSON ai.galop | 398 | %28.4 | %69.1 | %80.2 | %88.2 |
| JSON ai.hiz | 421 | %35.9 | %74.1 | %84.3 | %91.4 |
| JSON ai.model | 957 | %23.7 | %54.2 | %63.8 | %73.5 |
| JSON ai.pist_mesafe | 754 | %21.4 | %54.2 | %66.8 | %77.1 |
| JSON galop.skor | 900 | %16.2 | %41.8 | %52.8 | %63.1 |

## Ana Skor ve pegadrom_skorlar.json Matematiği

Üretimde kullanılan matematik per koşu min-max normalizasyonuna dayanır. Puanlar ham değerle değil, aynı koşudaki atlar arasındaki göreli konumla skora girer.

```text
AGF varsa:
  ANA = norm(AGF)*0.40 + norm(Pegadrom Akış)*0.50 + norm(Pegadrom Galop Nötr)*0.10

AGF yoksa:
  ANA = norm(G)*0.30 + norm(Pegadrom Akış)*0.70

10-13 atlı sahada:
  ANA += 0.20 * jokey_skoru * 100
```

Pegadrom galopta `PEGGLP=0` veya eksik değer ceza olarak kullanılmıyor; formül içinde `50` nötr değere çevrilip sonra normalize ediliyor.

| Bileşen | Ortalama top1 katkısı | Ortalama kazanan katkısı |
|---|---:|---:|
| AGF_katki | 37.03 | 24.29 |
| G_katki | 0.13 | 0.10 |
| Flow_katki | 46.10 | 39.41 |
| PegGalop_katki | 6.21 | 5.74 |
| JOK_katki | 1.08 | 1.01 |
| base | 89.47 | 69.54 |
| recon | 90.55 | 70.55 |

- Rekonstrüksiyon ortalama mutlak hata: 0.034 puan. Bu, rapordaki ANA ile formülün uyumlu olduğunu gösterir.
- Tahmin at kayıtlarında PEGGLP sıfır/eksik görünen kayıt: 1710 / 10615 (%16.1). Bu kayıtlar formülde nötr 50 kabul edilir.

## Temel Bulgular

1. 5 satır genel başarı %90 bandında korunuyor; asıl zayıf halka 14+ sahalar.
2. Pegadrom akış sinyali, hem TXT hem JSON tarafında model/galop/hız/pist sinyallerinden daha yararlı ana taşıyıcıdır.
3. Galop puanı düşük ağırlıkla doğru yerde; tek başına güçlü seçim motoru değil.
4. Altılıda büyük kademe daha yüksek isabet ve net getiri veriyor, ancak varyans yüksek; kâr az sayıda büyük ödeme ile geliyor.
5. İlk kayıp analizi kupon kayıplarının önemli kısmının dar genişlikli ayaklarda ve 14+ segmentinde yoğunlaştığını gösteriyor.

## Daha İsabetli Altılı Sistematiği İçin Yol Haritası

### 1. Ortaklı kademeyi ciddi oyun varsayılanı yap
Ortaklı kademe en yüksek isabet ve net getiriyi üretiyor. Simitçi deneme/ekonomik, Harbi orta, Ortaklı ana öneri olarak konumlandırılmalı.

### 2. 14+ ayaklarda minimum genişlik politikası test et
Kalibrasyon eğrisi 14+ sahalarda 6-7 ata çıkmanın kapsama oranını belirgin artırdığını gösteriyor. Bütçe elveriyorsa 14+ ayaklar önce genişletilmeli; ancak bu değişiklik aynı backtest evreninde tekrar ölçülmeli.

### 3. Tek-at bankoyu AGF kapısına bağla
Tek-at banko sadece favori hem AGF lideri hem de AGF eşiği yüksek olduğunda açılmalı. Diğer durumlarda 2-at çıpa daha rasyonel.

### 4. Kupon hedefini beklenen kapsama üzerinden optimize et
Sadece bütçe bandı değil, altılının ayak yapısı kullanılmalı: içinde 14+ ayak varsa genişlik önceliği, düşük alanlı ve yüksek farkı olan ayak varsa daraltma uygulanmalı.

### 5. Pegadrom akış ilk5 ve yüksek ganyan kesişimini ayrı etiketle
14+ sahalarda kazananı yakalamak için mevcut ana skor yetmiyor. Akış ilk5 içinde olup ana skorda geride kalan ve piyasanın düşük yazdığı atlar ayrı 'geniş kupon adayı' olarak işaretlenmeli.

### 6. Yeni veri gelince kalibrasyonu zorunlu yenile
CSV arşivi büyüdükçe `motor/altili_kalibrasyon.py`, ardından `motor/altili_backtest.py` ve bu kapsamlı analiz tekrar çalıştırılmalı.
