# Harbi Ganyan VPS Kurulum Notlari

Minimum ortam degiskenleri:

```bash
export HG_DATABASE_URL="postgresql+psycopg2://hg:GUCLU_DB_SIFRESI@localhost/harbiganyan"
export HG_JWT_SECRET="$(openssl rand -hex 32)"
export HG_CORS_ORIGINS="https://api.domaininiz.com"
```

Migration ve ilk admin:

```bash
python -m alembic -c backend/alembic.ini upgrade head
python backend/scripts/create_admin.py admin@domaininiz.com 'CokGucluAdminSifresi'
```

Admin paneli:

- `https://api.domaininiz.com/admin`
- Admin kullanici ekleyebilir/silebilir.
- Admin uyelik tier, aktiflik ve bitis tarihini yonetebilir.
- Haftalik gelir ozeti premium = 150 TL, VIP = 250 TL olarak hesaplanir.
- Admin uygulama ici bildirimleri tum kullanicilara, tier bazinda veya tek kullaniciya gonderebilir.

API servisi:

```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

Android build ornegi:

```bash
flutter build apk --dart-define=HG_API=https://api.domaininiz.com
```
