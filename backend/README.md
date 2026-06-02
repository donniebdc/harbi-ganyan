# Harbi Ganyan — Backend (FastAPI)

Mevcut Python tahmin motorunu (`../motor`, `../ganyan_master.py`) yeniden kullanır;
yapısal JSON üretip PostgreSQL'e yazar ve mobil uygulamaya REST API sunar.

## Mimari
```
ganyan_master.run(date)  →  Harbi_Ganyan_Analiz/ + TahminSonuçları/
        │ (export/build_day_json.py)
        ▼
   yapısal JSON  →  (export/import_to_db.py)  →  PostgreSQL
                                                      │
                                              FastAPI (app/) → Flutter
```

## Kurulum
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# Üretim (Postgres):
export HG_DATABASE_URL="postgresql+psycopg2://hg:pass@localhost/harbiganyan"
python -m alembic -c backend/alembic.ini upgrade head

# Lokal geliştirme: HG_DATABASE_URL boş bırakılırsa SQLite (backend/harbiganyan.db).
```

## Veri yükleme
```bash
python backend/export/build_day_json.py 2026-02-01 2026-05-30   # JSON üret
python backend/export/import_to_db.py --all                     # DB'ye yaz
# veya tek adımda (scraping yok):
python backend/cron/daily_pipeline.py --export-only 2026-02-01 2026-05-30
```

## API sunucu
```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```
Uçlar:
- `GET /saglik`
- `GET /gunler?from=YYYY-MM-DD&to=YYYY-MM-DD` — Geçmiş Analizler özeti (varsayılan son 30 gün)
- `GET /gun/{YYYY-MM-DD}` — günün tam analizleri (5-satır + 3 kademe 6'lı + sonuçlar)

> Üyelik kilidi (Günün Analizleri = premium+) ve auth M2'de eklenecek.

## Dizinler
- `app/` — FastAPI (config, db, models, serialize, api/)
- `export/` — `build_day_json.py` (motor→JSON), `import_to_db.py` (JSON→DB)
- `cron/` — `daily_pipeline.py` + crontab/systemd örnekleri
- `alembic/` — migration'lar
