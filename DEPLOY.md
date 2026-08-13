# Harbi Ganyan v3 — VDS Deployment

Tarih: 2026-06-17
Konfigurasyon: v9 production

## Dizin Yapisi
/opt/harbi_ganyan_v3/
  v3_export.py          → backend'e tahmin + altili kupon export
  src/harbi_v3/         → XGBoost motoru (predictor, features, altili_coupons, vs.)
  data/                 → program_raw, results_raw, bulletin_raw, altili_windows_raw, horse_cards_raw

## VDS Python Ortami
- Python 3.10.12 (sistem)
- pip paketleri: xgboost 3.2, numpy 2.2, scikit-learn 1.7, scipy 1.15
- NOT: backend .venv ile izole; v3 icin ayrica venv gerekmez

## Cron
- 17:50 TR → yarinin tahmini (full scraping + uretim)
- 18:00 TR → on tahmin bildirimi
- 10:00-22:59 TR (her 5dk) → yenileme + final tahmin
- 07:00-23:59 TR (her 1dk) → canli sonuc takibi

## Model Konfigurasyonu (v9)
- XGBRanker rank:pairwise (120 feature)
- XGBClassifier top-5 (binary)
- Tip-bazli blend alpha + kalibreli puanlama
- Banko ayak (akilli tip-bazli secim)
- Standart 1800 TL sifirdan buyume
- Mini ⊆ Standart ⊆ Genis nesting garantili

## Guncelleme
Yerelden VDS'e kod guncelleme:
  scp -i hg_vps_claude v3_export.py root@141.98.115.217:/opt/harbi_ganyan_v3/
  scp -i hg_vps_claude src/harbi_v3/*.py root@141.98.115.217:/opt/harbi_ganyan_v3/src/harbi_v3/
