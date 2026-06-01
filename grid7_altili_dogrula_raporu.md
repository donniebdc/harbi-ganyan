# grid7 Doğrulama — Tam Evren Altılı Backtest

- Eval koşu: 1004
- Altılı (baseline seen): 212
- Aralık: 2026-04-01 .. 2026-05-28
- Üretim kodu DEĞİŞTİRİLMEDİ; bu rapor karar girdisidir.

## grid7 tanımı
```
M:0.25 F:0.45 galop.en_iyi|neutral_missing:0.10 galop.istikrar|neutral_missing:0.15 galop.en_iyi|raw_zero:0.05
```

## 5-Satır (Tam Evren)
| Varyant | n | İlk1 | İlk3 | İlk4 | İlk5 | 5 satır | 14+ n | 14+ 5satır | HAR |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 1004 | %37.7 | %73.1 | %83.8 | %90.2 | %90.3 | 168 | %78.0 | 66/163 %40.5 |
| grid7 | 1004 | %35.0 | %74.8 | %84.2 | %90.7 | %90.8 | 168 | %79.8 | 67/159 %42.1 |
| g_light | 1004 | %36.6 | %75.4 | %84.7 | %90.8 | %90.8 | 168 | %78.6 | 62/154 %40.3 |
| g_heavy | 1004 | %35.0 | %73.5 | %83.2 | %89.6 | %90.1 | 168 | %79.8 | 70/169 %41.4 |

## Altılı (Tam Evren)
| Varyant | Kademe | İsabet | Çıpa doğru | Yanlış tek banko | Net | 3 kupondan biri |
|---|---|---|---|---|---|---|
| baseline | Simitçi 6'lısı | 27/212 %12.7 | 133/212 %62.7 | 23 | +206833 TL | 53/212 %25.0 |
| baseline | Harbi Ganyan 6'lısı | 42/212 %19.8 | 133/212 %62.7 | 23 | +485972 TL | 53/212 %25.0 |
| baseline | Ortaklı 6'lı | 53/212 %25.0 | 133/212 %62.7 | 23 | +596532 TL | 53/212 %25.0 |
| grid7 | Simitçi 6'lısı | 28/212 %13.2 | 132/212 %62.3 | 9 | +558522 TL | 50/212 %23.6 |
| grid7 | Harbi Ganyan 6'lısı | 43/212 %20.3 | 132/212 %62.3 | 9 | +431055 TL | 50/212 %23.6 |
| grid7 | Ortaklı 6'lı | 50/212 %23.6 | 132/212 %62.3 | 9 | +548721 TL | 50/212 %23.6 |
| g_light | Simitçi 6'lısı | 24/212 %11.3 | 128/212 %60.4 | 16 | +527986 TL | 50/212 %23.6 |
| g_light | Harbi Ganyan 6'lısı | 41/212 %19.3 | 128/212 %60.4 | 16 | +411566 TL | 50/212 %23.6 |
| g_light | Ortaklı 6'lı | 48/212 %22.6 | 128/212 %60.4 | 16 | +1816907 TL | 50/212 %23.6 |
| g_heavy | Simitçi 6'lısı | 26/212 %12.3 | 129/212 %60.8 | 8 | +511698 TL | 47/212 %22.2 |
| g_heavy | Harbi Ganyan 6'lısı | 38/212 %17.9 | 129/212 %60.8 | 8 | +427899 TL | 47/212 %22.2 |
| g_heavy | Ortaklı 6'lı | 47/212 %22.2 | 129/212 %60.8 | 8 | +569787 TL | 47/212 %22.2 |

## Özet
- Simitçi 6'lısı: baseline 27/212 -> grid7 28/212 (+1 altılı)
- Harbi Ganyan 6'lısı: baseline 42/212 -> grid7 43/212 (+1 altılı)
- Ortaklı 6'lı: baseline 53/212 -> grid7 50/212 (-3 altılı)
- Çıpa doğruluk (Harbi): baseline %62.7 -> grid7 %62.3