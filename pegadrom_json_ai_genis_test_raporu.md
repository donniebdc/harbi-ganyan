# Pegadrom JSON AI Bloğu Geniş Kapsamlı Test Raporu

Bu rapor üretim algoritmasını değiştirmeden, günlük `Harbi_Ganyan_Analiz` tahmin dosyaları üzerinden çalıştırılmıştır.

## Veri Kapsamı
- Tahmin dosyası: 58
- Parse edilen koşu: 1028
- JSON + CSV + sonuç eşleşen koşu: 1004
- Eğitim: 2026-04-01 - 2026-05-15 (773 koşu)
- Holdout: 2026-05-16 - 2026-05-28 (231 koşu)
- pegadrom_skorlar.json koşu: 1028

## Baseline
| Evren | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır | 14+ 5 satır | HAR | HAR 14+ |
|---|---|---|---|---|---|---|---|---|---|
| train | 773 | %38.4 | %74.0 | %84.3 | %90.9 | %90.8 | %79.5 | 50/121 %41.3 | 10/37 %27.0 |
| holdout | 231 | %35.5 | %70.1 | %81.8 | %87.9 | %88.7 | %72.2 | 16/42 %38.1 | 3/13 %23.1 |

## Tekil JSON Sinyal Gücü - Holdout
| Sinyal | n | İlk1 | İlk3 | İlk4 | İlk5 | Bizim 5 dışı top2 win | AGF alt-yarı win | Akış5 dışı win |
|---|---|---|---|---|---|---|---|---|
| galop.skor|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.son|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.en_iyi|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.tempo|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.istikrar|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.pist_uyum|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.kayit|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| galop.galop_sayisi|missing_indicator | 231 | %27.3 | %63.6 | %75.8 | %82.7 | 0/72 %0.0 | 7/85 %8.2 | 2/83 %2.4 |
| ai.model|missing_indicator | 231 | %19.5 | %64.1 | %75.3 | %81.0 | 2/129 %1.6 | 10/155 %6.5 | 6/139 %4.3 |
| ai.veri|missing_indicator | 231 | %19.5 | %64.1 | %75.3 | %81.0 | 2/129 %1.6 | 10/155 %6.5 | 6/139 %4.3 |
| ai.galop|missing_indicator | 231 | %19.5 | %64.1 | %75.3 | %81.0 | 2/129 %1.6 | 10/155 %6.5 | 6/139 %4.3 |
| ai.hiz|missing_indicator | 231 | %19.5 | %64.1 | %75.3 | %81.0 | 2/129 %1.6 | 10/155 %6.5 | 6/139 %4.3 |
| ai.pist_mesafe|missing_indicator | 231 | %19.5 | %64.1 | %75.3 | %81.0 | 2/129 %1.6 | 10/155 %6.5 | 6/139 %4.3 |
| galop.kayit|raw_zero | 231 | %30.7 | %58.9 | %71.4 | %76.6 | 3/39 %7.7 | 11/83 %13.3 | 4/55 %7.3 |
| galop.kayit|neutral_missing | 231 | %30.7 | %58.0 | %71.0 | %76.6 | 3/39 %7.7 | 11/80 %13.8 | 4/55 %7.3 |
| galop.galop_sayisi|raw_zero | 231 | %30.7 | %58.9 | %71.4 | %76.6 | 3/39 %7.7 | 11/83 %13.3 | 4/55 %7.3 |
| galop.pist_uyum|raw_zero | 231 | %19.9 | %50.2 | %64.9 | %76.2 | 2/99 %2.0 | 9/135 %6.7 | 5/117 %4.3 |
| galop.galop_sayisi|neutral_missing | 231 | %25.1 | %54.1 | %66.7 | %74.5 | 2/102 %2.0 | 9/121 %7.4 | 4/113 %3.5 |
| ai.hiz|raw_zero | 231 | %20.8 | %48.1 | %61.9 | %74.0 | 6/142 %4.2 | 12/168 %7.1 | 5/146 %3.4 |
| ai.hiz|neutral_missing | 231 | %20.8 | %48.1 | %61.9 | %74.0 | 6/142 %4.2 | 12/168 %7.1 | 5/146 %3.4 |
| galop.pist_uyum|neutral_missing | 231 | %21.6 | %53.2 | %66.7 | %74.0 | 2/87 %2.3 | 9/119 %7.6 | 3/106 %2.8 |
| ai.model|raw_zero | 231 | %23.8 | %52.8 | %62.8 | %71.9 | 2/47 %4.3 | 6/88 %6.8 | 2/64 %3.1 |
| ai.model|neutral_missing | 231 | %23.8 | %52.8 | %62.8 | %71.9 | 2/47 %4.3 | 6/88 %6.8 | 2/64 %3.1 |
| ai.pist_mesafe|raw_zero | 231 | %19.9 | %45.5 | %58.0 | %68.8 | 4/104 %3.8 | 7/127 %5.5 | 5/119 %4.2 |
| ai.pist_mesafe|neutral_missing | 231 | %19.9 | %45.5 | %58.0 | %68.8 | 4/104 %3.8 | 7/127 %5.5 | 5/119 %4.2 |
| ai.galop|raw_zero | 231 | %13.9 | %41.1 | %55.8 | %67.1 | 3/152 %2.0 | 12/200 %6.0 | 4/162 %2.5 |
| ai.galop|neutral_missing | 231 | %13.9 | %41.1 | %55.8 | %67.1 | 3/152 %2.0 | 12/200 %6.0 | 4/162 %2.5 |
| galop.en_iyi|neutral_missing | 231 | %20.8 | %48.9 | %57.6 | %64.1 | 6/145 %4.1 | 14/181 %7.7 | 8/172 %4.7 |
| ai.veri|neutral_missing | 231 | %16.9 | %38.5 | %52.8 | %63.2 | 6/149 %4.0 | 12/174 %6.9 | 6/160 %3.8 |
| galop.en_iyi|raw_zero | 231 | %20.8 | %48.5 | %56.7 | %63.2 | 7/145 %4.8 | 14/183 %7.7 | 9/172 %5.2 |

## Ağırlık Grid Sonuçları
| Aday | Train 5 | Train 14+ | Holdout 5 | Δ5 | Holdout 14+ | Δ14+ | Holdout HAR |
|---|---|---|---|---|---|---|---|
| M:0.25|F:0.45|galop.skor|neutral_missing:0.15+galop.istikrar|neutral_missing:0.15 | %91.5 | %81.8 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 17/43 %39.5 |
| M:0.25|F:0.45|galop.skor|neutral_missing:0.15+galop.en_iyi|neutral_missing:0.00+galop.istikrar|neutral_missing:0.15 | %91.5 | %81.8 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 17/43 %39.5 |
| M:0.25|F:0.45|galop.skor|neutral_missing:0.15+galop.tempo|neutral_missing:0.00+galop.istikrar|neutral_missing:0.15 | %91.5 | %81.8 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 17/43 %39.5 |
| M:0.25|F:0.45|galop.skor|neutral_missing:0.15+galop.son|neutral_missing:0.00+galop.istikrar|neutral_missing:0.15 | %91.5 | %81.8 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 17/43 %39.5 |
| M:0.25|F:0.45|galop.skor|neutral_missing:0.15+galop.istikrar|neutral_missing:0.15+galop.en_iyi|raw_zero:0.00 | %91.5 | %81.8 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 17/43 %39.5 |
| M:0.40|F:0.45|galop.en_iyi|neutral_missing:0.05+galop.tempo|neutral_missing:0.05+galop.son|neutral_missing:0.05 | %91.5 | %81.8 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 18/45 %40.0 |
| M:0.25|F:0.45|galop.en_iyi|neutral_missing:0.10+galop.istikrar|neutral_missing:0.15+galop.en_iyi|raw_zero:0.05 | %91.5 | %81.1 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 15/41 %36.6 |
| M:0.35|F:0.40|galop.tempo|neutral_missing:0.05+galop.istikrar|neutral_missing:0.10+galop.en_iyi|raw_zero:0.10 | %91.5 | %81.1 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 18/44 %40.9 |
| M:0.35|F:0.40|galop.skor|neutral_missing:0.10+galop.istikrar|neutral_missing:0.10+galop.en_iyi|raw_zero:0.05 | %91.5 | %81.1 | %88.7 | +0.00 puan | %72.2 | +0.00 puan | 20/46 %43.5 |
| M:0.35|F:0.40|galop.en_iyi|neutral_missing:0.05+galop.tempo|neutral_missing:0.10+galop.istikrar|neutral_missing:0.10 | %91.5 | %81.1 | %87.9 | -0.87 puan | %66.7 | -5.56 puan | 17/45 %37.8 |
| M:0.35|F:0.40|galop.en_iyi|neutral_missing:0.10+galop.tempo|neutral_missing:0.05+galop.istikrar|neutral_missing:0.10 | %91.5 | %81.1 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 19/46 %41.3 |
| M:0.35|F:0.40|galop.en_iyi|neutral_missing:0.10+galop.istikrar|neutral_missing:0.10+galop.en_iyi|raw_zero:0.05 | %91.5 | %81.1 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 19/46 %41.3 |
| M:0.35|F:0.40|galop.tempo|neutral_missing:0.10+galop.istikrar|neutral_missing:0.10+galop.en_iyi|raw_zero:0.05 | %91.5 | %81.1 | %88.3 | -0.43 puan | %72.2 | +0.00 puan | 18/45 %40.0 |
| M:0.30|F:0.40|galop.skor|neutral_missing:0.10+galop.istikrar|neutral_missing:0.15+galop.en_iyi|raw_zero:0.05 | %91.3 | %81.8 | %87.9 | -0.87 puan | %75.0 | +2.78 puan | 15/43 %34.9 |
| M:0.40|F:0.45|galop.skor|neutral_missing:0.05+galop.en_iyi|neutral_missing:0.05+galop.son|neutral_missing:0.05 | %91.3 | %81.8 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 18/45 %40.0 |
| M:0.40|F:0.45|galop.skor|neutral_missing:0.10+galop.son|neutral_missing:0.05 | %91.3 | %81.8 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 18/45 %40.0 |
| M:0.40|F:0.45|galop.skor|neutral_missing:0.10+galop.en_iyi|neutral_missing:0.00+galop.son|neutral_missing:0.05 | %91.3 | %81.8 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 18/45 %40.0 |
| M:0.40|F:0.45|galop.skor|neutral_missing:0.10+galop.tempo|neutral_missing:0.00+galop.son|neutral_missing:0.05 | %91.3 | %81.8 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 18/45 %40.0 |
| M:0.25|F:0.45|galop.skor|neutral_missing:0.10+galop.son|neutral_missing:0.05+galop.istikrar|neutral_missing:0.15 | %91.3 | %81.8 | %88.7 | +0.00 puan | %75.0 | +2.78 puan | 14/40 %35.0 |
| M:0.40|F:0.45|galop.skor|neutral_missing:0.10+galop.son|neutral_missing:0.05+galop.istikrar|neutral_missing:0.00 | %91.3 | %81.8 | %88.3 | -0.43 puan | %69.4 | -2.78 puan | 18/45 %40.0 |

### En İyi Holdout Adayı
- Aday: `M:0.35|F:0.40|galop.en_iyi|neutral_missing:0.05+galop.istikrar|neutral_missing:0.10+galop.en_iyi|raw_zero:0.10`
- Holdout 5 satır: %89.2 (+0.43 puan)
- Holdout 14+ 5 satır: %75.0 (+2.78 puan)

## HAR Kullanım Yeri Testi
| HAR özelliği | Holdout HAR | Δ HAR | Holdout HAR 14+ |
|---|---|---|---|
| galop.kayit|raw_zero | 12/42 %28.6 | -9.5 puan | 0/13 %0.0 |
| galop.galop_sayisi|raw_zero | 12/42 %28.6 | -9.5 puan | 0/13 %0.0 |
| galop.kayit|neutral_missing | 12/42 %28.6 | -9.5 puan | 0/13 %0.0 |
| galop.skor|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.son|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.en_iyi|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.tempo|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.istikrar|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.pist_uyum|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.kayit|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.galop_sayisi|missing_indicator | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.galop_sayisi|neutral_missing | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| ai.model|missing_indicator | 9/42 %21.4 | -16.7 puan | 0/13 %0.0 |
| ai.veri|missing_indicator | 9/42 %21.4 | -16.7 puan | 0/13 %0.0 |
| ai.galop|missing_indicator | 9/42 %21.4 | -16.7 puan | 0/13 %0.0 |
| ai.hiz|missing_indicator | 9/42 %21.4 | -16.7 puan | 0/13 %0.0 |
| ai.pist_mesafe|missing_indicator | 9/42 %21.4 | -16.7 puan | 0/13 %0.0 |
| galop.pist_uyum|raw_zero | 8/42 %19.0 | -19.0 puan | 1/13 %7.7 |
| galop.pist_uyum|neutral_missing | 9/42 %21.4 | -16.7 puan | 1/13 %7.7 |
| galop.istikrar|raw_zero | 11/42 %26.2 | -11.9 puan | 2/13 %15.4 |

## Banko Güven Filtresi - Holdout
| Filtre | Eşik | Doğru/toplam | Top1 baseline'a göre |
|---|---|---|---|
| ai.model|missing_indicator | 50 | 2/2 %100.0 | +64.5 puan |
| ai.veri|missing_indicator | 50 | 2/2 %100.0 | +64.5 puan |
| ai.galop|missing_indicator | 50 | 2/2 %100.0 | +64.5 puan |
| ai.hiz|missing_indicator | 50 | 2/2 %100.0 | +64.5 puan |
| ai.pist_mesafe|missing_indicator | 50 | 2/2 %100.0 | +64.5 puan |
| ai.pist_mesafe|neutral_missing | 85 | 54/132 %40.9 | +5.4 puan |
| galop.tempo|neutral_missing | 85 | 33/81 %40.7 | +5.2 puan |
| galop.en_iyi|neutral_missing | 85 | 32/83 %38.6 | +3.1 puan |
| ai.galop|neutral_missing | 85 | 23/60 %38.3 | +2.8 puan |
| galop.galop_sayisi|neutral_missing | 70 | 44/116 %37.9 | +2.4 puan |
| galop.skor|neutral_missing | 85 | 33/88 %37.5 | +2.0 puan |
| galop.en_iyi|raw_zero | 85 | 34/91 %37.4 | +1.9 puan |
| galop.istikrar|raw_zero | 60 | 65/174 %37.4 | +1.9 puan |
| galop.son|raw_zero | 60 | 56/150 %37.3 | +1.8 puan |
| galop.son|neutral_missing | 75 | 38/102 %37.3 | +1.8 puan |
| ai.pist_mesafe|raw_zero | 80 | 65/175 %37.1 | +1.6 puan |
| galop.tempo|raw_zero | 85 | 33/90 %36.7 | +1.2 puan |
| ai.model|neutral_missing | 85 | 58/159 %36.5 | +1.0 puan |
| ai.model|raw_zero | 85 | 69/190 %36.3 | +0.8 puan |
| ai.veri|raw_zero | 60 | 62/172 %36.0 | +0.5 puan |

## Altılı Holdout Backtest
| Varyant | Kademe | İsabet | Ort. bütçe | Net | Çıpa doğru | Yanlış tek banko | 3 kupondan biri |
|---|---|---|---|---|---|---|---|
| baseline | Simitçi 6'lısı | 5/47 %10.6 | 484 TL | +14146 TL | 34/47 %72.3 | 2 | 10/47 %21.3 |
| baseline | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1544 TL | +143792 TL | 34/47 %72.3 | 2 | 10/47 %21.3 |
| baseline | Ortaklı 6'lı | 10/47 %21.3 | 1933 TL | +171115 TL | 34/47 %72.3 | 2 | 10/47 %21.3 |
| grid1 | Simitçi 6'lısı | 5/47 %10.6 | 483 TL | +20519 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid1 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1544 TL | +208570 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid1 | Ortaklı 6'lı | 9/47 %19.1 | 1934 TL | +191212 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid2 | Simitçi 6'lısı | 5/47 %10.6 | 483 TL | +20519 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid2 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1544 TL | +208570 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid2 | Ortaklı 6'lı | 9/47 %19.1 | 1934 TL | +191212 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid3 | Simitçi 6'lısı | 5/47 %10.6 | 483 TL | +20519 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid3 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1544 TL | +208570 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid3 | Ortaklı 6'lı | 9/47 %19.1 | 1934 TL | +191212 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid4 | Simitçi 6'lısı | 5/47 %10.6 | 483 TL | +20519 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid4 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1544 TL | +208570 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid4 | Ortaklı 6'lı | 9/47 %19.1 | 1934 TL | +191212 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid5 | Simitçi 6'lısı | 5/47 %10.6 | 483 TL | +20519 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid5 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1544 TL | +208570 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid5 | Ortaklı 6'lı | 9/47 %19.1 | 1934 TL | +191212 TL | 34/47 %72.3 | 1 | 9/47 %19.1 |
| grid6 | Simitçi 6'lısı | 5/47 %10.6 | 483 TL | +14166 TL | 33/47 %70.2 | 2 | 10/47 %21.3 |
| grid6 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1549 TL | +143539 TL | 33/47 %70.2 | 2 | 10/47 %21.3 |
| grid6 | Ortaklı 6'lı | 9/47 %19.1 | 1929 TL | +172073 TL | 33/47 %70.2 | 2 | 10/47 %21.3 |
| grid7 | Simitçi 6'lısı | 9/47 %19.1 | 483 TL | +212034 TL | 36/47 %76.6 | 1 | 13/47 %27.7 |
| grid7 | Harbi Ganyan 6'lısı | 12/47 %25.5 | 1546 TL | +239821 TL | 36/47 %76.6 | 1 | 13/47 %27.7 |
| grid7 | Ortaklı 6'lı | 13/47 %27.7 | 1934 TL | +223514 TL | 36/47 %76.6 | 1 | 13/47 %27.7 |
| grid8 | Simitçi 6'lısı | 6/47 %12.8 | 483 TL | +164772 TL | 32/47 %68.1 | 2 | 8/47 %17.0 |
| grid8 | Harbi Ganyan 6'lısı | 8/47 %17.0 | 1540 TL | +141608 TL | 32/47 %68.1 | 2 | 8/47 %17.0 |
| grid8 | Ortaklı 6'lı | 8/47 %17.0 | 1928 TL | +123356 TL | 32/47 %68.1 | 2 | 8/47 %17.0 |

## Karar
- Ana skor kabul eşiği: GEÇTİ
- En iyi HAR adayı: `galop.kayit|raw_zero` ΔHAR -9.5 puan
- Üretim koduna otomatik değişiklik yapılmadı; bu rapor karar girdisidir.

Öneri: En iyi holdout adayı üretim dışı ikinci bir canlı izleme modunda denenebilir; doğrudan ana algoritmaya almadan önce yeni günlerde doğrulama gerekir.