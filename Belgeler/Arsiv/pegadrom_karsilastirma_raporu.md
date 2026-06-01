# Pegadrom 3'lü Karşılaştırma Raporu

## Veri Özeti

- CSV koşu sayısı: 1010
- v6 koşu sayısı: 1028
- Pegadrom koşu sayısı: 1028
- Üçlü eşleşen koşu sayısı: 1004
- Üçlü eşleşen at kaydı: 10028
- v6 at satırı çözümleme: 10185/10365 eşleşti

## A) Pegadrom Model vs v6

| Sistem | İlk1 / İlk3 / İlk4 | 5 satır |
|---|---:|---:|
| Pegadrom model | 23.0% / 51.7% / 61.7% (n=1004) | - |
| v6 ANA, aynı evren | 33.3% / 68.6% / 78.2% (n=1004) | 84.3% (n=1004) |
| v6 hedef/genel belge | - / 66.6% / 76.0% | 82.0% |

## B-C) Alt Sinyaller ve Galop Karşılaştırması

| Sinyal | İlk1 / İlk3 / İlk4 |
|---|---:|
| Pegadrom model | 23.0% / 51.7% / 61.7% (n=1004) |
| Pegadrom hız | 16.1% / 41.0% / 53.0% (n=932) |
| Pegadrom pist/mesafe | 17.3% / 44.8% / 56.0% (n=940) |
| Pegadrom AI galop | 13.3% / 39.0% / 49.7% (n=867) |
| Pegadrom galop sayfası | 15.0% / 38.6% / 48.9% (n=973) |
| Bizim v6 GLP | 13.9% / 38.9% / 52.3% (n=974) |

## D) Holdout Hibrit

- Eğitim koşusu: 699, test koşusu: 300
- Eğitimde seçilen ağırlıklar: v6_ana=0.9, peg_galop_skor=0.1
- Eğitim sonucu: İlk1 34.8%, İlk3 69.8%, İlk4 79.1%, 5 satır 86.7% (n=699)
- Test sonucu: İlk1 31.3%, İlk3 68.0%, İlk4 78.0%, 5 satır 83.3% (n=300)
- Aynı ağırlıkla tüm hibrit evren: İlk1 33.7%, İlk3 69.3%, İlk4 78.8%, 5 satır 85.7% (n=999)
- %82 eşiği: GEÇTİ

## E) Aday Model Karşılaştırması

| Model | İlk1 / İlk3 / İlk4 | 5 satır |
|---|---:|---:|
| v6 mevcut 5SATIR | - | 84.7% (n=999) |
| Sade hibrit top5 (ANA %90 + Peg galop %10) | 33.7% / 69.3% / 78.8% | 85.7% (n=999) |
| Satır bazlı hibrit | 33.4% / 69.0% / 78.7% | 82.9% (n=999) |

| Model | Farklı seçim | Ekstra yakaladı | Bozdu | Net katkı |
|---|---:|---:|---:|---:|
| Sade hibrit top5 | 603 | 38 | 28 | +10 |
| Satır bazlı hibrit | 708 | 31 | 49 | -18 |

## F) Grup Bazlı 5 Satır Katkısı

| Kırılım | Segment | v6 | Sade hibrit | Satır bazlı |
|---|---|---:|---:|---:|
| group | handikap | 81.1% (n=281) | 83.3% | 78.3% |
| group | kv_grup | 88.3% (n=60) | 90.0% | 90.0% |
| group | maiden | 85.6% (n=202) | 87.1% | 84.7% |
| group | sartli | 86.0% (n=456) | 86.0% | 84.0% |
| track | Kum | 84.8% (n=613) | 86.6% | 83.0% |
| track | Sentetik | 91.9% (n=135) | 89.6% | 88.9% |
| track | Çim | 80.5% (n=251) | 81.3% | 79.3% |
| distance | kisa<=1400 | 82.3% (n=496) | 84.1% | 82.1% |
| distance | orta<=1800 | 85.1% (n=201) | 84.1% | 80.1% |
| distance | uzun>1800 | 88.4% (n=302) | 89.4% | 86.1% |
| field_size | az<=7 | 95.8% (n=259) | 96.5% | 94.6% |
| field_size | kalabalik>=12 | 72.9% (n=303) | 74.9% | 72.9% |
| field_size | orta<=11 | 86.3% (n=437) | 86.7% | 82.8% |

## Sanity Check

- 2026-04-01|ELAZIG|1: CSV kazanan=[1], v6 at=7, Pegadrom at=7
- 2026-04-01|ELAZIG|2: CSV kazanan=[2], v6 at=6, Pegadrom at=6
- 2026-04-01|ELAZIG|3: CSV kazanan=[1], v6 at=11, Pegadrom at=11
- 2026-04-30|IZMIR|5: CSV kazanan=[4], v6 at=12, Pegadrom at=12
- 2026-04-30|IZMIR|6: CSV kazanan=[6], v6 at=10, Pegadrom at=11
- 2026-05-28|IZMIR|7: CSV kazanan=[5], v6 at=7, Pegadrom at=7
- 2026-05-28|IZMIR|8: CSV kazanan=[6], v6 at=14, Pegadrom at=14
- 2026-05-28|IZMIR|9: CSV kazanan=[7], v6 at=17, Pegadrom at=17

## Kısa Karar

Holdout testte hibrit 5 satır %82 üstüne çıktı; Pegadrom sinyalleri sınırlı ve seçici entegrasyon adayıdır.
Not: v6 metninde at numarası bulunmadığı için v6 at numarası, aynı koşudaki Pegadrom at-no/name listesinden geri kazanıldı; Pegadrom-CSV sonuç eşleşmesi isimle yapılmadı.
