# Banko Eşik Test Raporu

Test evreni: 01.04.2026 - 30.05.2026 arası mevcut üretilmiş altılı tahminleri.

Kaynaklar:
- `D:\Ganyan Gemini\v5_tahmin_01042026-30052026.txt`
- `D:\Ganyan Gemini\Harbi_Ganyan_Analiz`
- `D:\Ganyan Gemini\CSV Sonuçlar`
- `D:\Ganyan Gemini\motor\altili_kupon_v2.py`

Ölçülen ana metrik: Aynı şehir/gün için üretilen 3 altılı kuponundan herhangi biri 6'lıyı buluyor mu?

## Özet Karar

“Korkmadan her yerde banko yazalım, diğer ayaklara daha çok at ekleriz” hipotezi bu veri setinde çalışmadı.

Mevcut sistemde banko eşiği `0.50`. Bu eşikle 3 kupondan herhangi birinin tuttuğu oran:

| Senaryo | Tutan Altılı | Oran |
|---|---:|---:|
| Mevcut eşik `0.50` | 58 / 220 | %26.36 |
| Her güçlü lideri banko yap `0.00` | 45 / 220 | %20.45 |

Sonuç: korkusuz banko stratejisi 13 altılı kaybettiriyor.

Mutlak fark: -5.91 puan  
Göreli düşüş: yaklaşık -%22.4

## Neden Düşüyor?

Banko doğru değilse kupon o ayakta doğrudan ölüyor. Boşalan bütçeyle diğer ayaklara at eklemek bu kaybı telafi etmiyor.

| Banko Eşiği | Banko Sayısı | Banko Doğru | Banko İsabeti |
|---:|---:|---:|---:|
| 0.00 | 220 | 101 | %45.91 |
| 0.35 | 208 | 99 | %47.60 |
| 0.40 | 163 | 86 | %52.76 |
| 0.45 | 102 | 55 | %53.92 |
| 0.50 | 60 | 37 | %61.67 |
| 0.55 | 56 | 35 | %62.50 |
| 0.60 | 3 | 0 | %0.00 |

Eşik düştükçe banko görünürlüğü artıyor ama banko kalitesi bozuluyor. Mevcut `0.50` eşiği, az ama daha güvenilir banko üretiyor.

## Tek Tek Kupon Sonuçları

### Simitçi

| Banko Eşiği | Tutan | Oran | Ortalama Bütçe |
|---:|---:|---:|---:|
| 0.00 | 26 / 220 | %11.82 | 483 |
| 0.40 | 29 / 220 | %13.18 | 482 |
| 0.45 | 29 / 220 | %13.18 | 481 |
| 0.50 | 30 / 220 | %13.64 | 480 |
| 0.55 | 28 / 220 | %12.73 | 480 |
| 0.60 | 26 / 220 | %11.82 | 478 |

Simitçi için mevcut `0.50` en dengeli nokta.

### Harbi

| Banko Eşiği | Tutan | Oran | Ortalama Bütçe |
|---:|---:|---:|---:|
| 0.00 | 38 / 220 | %17.27 | 1534 |
| 0.40 | 42 / 220 | %19.09 | 1540 |
| 0.45 | 43 / 220 | %19.55 | 1541 |
| 0.50 | 45 / 220 | %20.45 | 1547 |
| 0.55 | 45 / 220 | %20.45 | 1546 |
| 0.60 | 49 / 220 | %22.27 | 1546 |

Harbi tarafında `0.60` daha çok altılı buluyor, fakat pratikte banko görünürlüğünü neredeyse kaldırıyor.

### Ortaklı

| Banko Eşiği | Tutan | Oran | Ortalama Bütçe |
|---:|---:|---:|---:|
| 0.00 | 45 / 220 | %20.45 | 1923 |
| 0.40 | 51 / 220 | %23.18 | 1930 |
| 0.45 | 55 / 220 | %25.00 | 1927 |
| 0.50 | 58 / 220 | %26.36 | 1930 |
| 0.55 | 59 / 220 | %26.82 | 1930 |
| 0.60 | 61 / 220 | %27.73 | 1926 |

Ortaklı kuponda eşiği yükseltmek daha iyi çalışıyor. Çünkü bu kuponun amacı banko göstermekten çok kapsama alanı oluşturmak olmalı.

## Üç Kupondan Herhangi Biri Tutar Mı?

| Ortak Eşik | Simitçi | Harbi | Ortaklı | Herhangi Biri | Ortalama Toplam Bütçe |
|---:|---:|---:|---:|---:|---:|
| 0.00 | 26 | 38 | 45 | 45 / 220 = %20.45 | 3939 |
| 0.35 | 27 | 39 | 47 | 47 / 220 = %21.36 | 3935 |
| 0.40 | 29 | 42 | 51 | 51 / 220 = %23.18 | 3952 |
| 0.45 | 29 | 43 | 55 | 55 / 220 = %25.00 | 3949 |
| 0.50 | 30 | 45 | 58 | 58 / 220 = %26.36 | 3957 |
| 0.55 | 28 | 45 | 59 | 59 / 220 = %26.82 | 3955 |
| 0.60 | 26 | 49 | 61 | 61 / 220 = %27.73 | 3951 |

Sadece matematiksel isabet hedeflenirse `0.60` daha iyi. Fakat bu eşik banko sayısını neredeyse sıfıra indiriyor.

## Ürün Mantığına Göre En İyi Kombinasyonlar

### Seçenek 1: Dengeli ve Ürün Dostu

| Kupon | Banko Eşiği |
|---|---:|
| Simitçi | 0.50 |
| Harbi | 0.55 |
| Ortaklı | 0.55 |

Sonuç:

| Metrik | Değer |
|---|---:|
| Herhangi biri tutar | 59 / 220 |
| Oran | %26.82 |
| Mevcuda göre fark | +1 altılı, +0.45 puan |
| Banko görünürlüğü | korunur |

Bu seçenek küçük ama düşük riskli iyileştirme sağlar.

### Seçenek 2: İsabet Öncelikli

| Kupon | Banko Eşiği |
|---|---:|
| Simitçi | 0.50 |
| Harbi | 0.60 |
| Ortaklı | 0.60 |

Sonuç:

| Metrik | Değer |
|---|---:|
| Herhangi biri tutar | 61 / 220 |
| Oran | %27.73 |
| Mevcuda göre fark | +3 altılı, +1.36 puan |
| Banko görünürlüğü | Harbi/Ortaklı'da çok azalır |

Bu seçenek daha yüksek isabet verir ama “banko atı görme” ürün beklentisine zayıf cevap verir.

### Seçenek 3: Karma Strateji

| Kupon | Banko Eşiği |
|---|---:|
| Simitçi | 0.50 |
| Harbi | 0.55 |
| Ortaklı | 0.60 |

Sonuç:

| Metrik | Değer |
|---|---:|
| Herhangi biri tutar | 62 / 220 |
| Oran | %28.18 |
| Mevcuda göre fark | +4 altılı, +1.82 puan |
| Göreli iyileşme | yaklaşık +%6.9 |
| Kupon bazlı tutan | Simitçi 30, Harbi 45, Ortaklı 61 |

Bu testte en iyi sonuç veren kombinasyon budur. Simitçi ve Harbi tarafında banko görünürlüğü korunur; Ortaklı kupon ise daha kapsayıcı ve isabet odaklı çalışır.

## Önerilen Uygulama

Varsayılan öneri: Seçenek 3.

Yeni rol dağılımı:

| Kupon | Rol | Banko Politikası |
|---|---|---|
| Simitçi | ucuz ve net | güven varsa banko yaz |
| Harbi | dengeli ana kupon | güvenli bankoyu koru |
| Ortaklı | yakalama kuponu | bankoya daha zor izin ver, kapsamı artır |

Bu yaklaşım kullanıcı psikolojisini tamamen dışlamadan matematiksel isabeti artırıyor. “Her kupon banko göstersin” yerine “ucuz/dengeli kupon banko göstersin, geniş kupon 6'lıyı yakalamaya çalışsın” ayrımı daha doğru.

## Net Cevap

Eğer gerçekten korkmadan banko yazsaydık, daha çok 6'lı tutturmazdık. Oran düşerdi.

Daha iyi yol:
- Bankoyu tamamen kaldırmak değil.
- Bankoyu her yerde cesurca yazmak da değil.
- Kupon tipine göre banko eşiğini farklılaştırmak.

Önerilen yeni eşikler:

| Kupon | Yeni Eşik |
|---|---:|
| Simitçi | 0.50 |
| Harbi | 0.55 |
| Ortaklı | 0.60 |

