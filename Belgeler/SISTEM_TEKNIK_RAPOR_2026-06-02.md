# HARBİ GANYAN — Sistem Teknik Operasyon Raporu

Son güncelleme: 02.06.2026
Amaç: Şu an **canlı çalışan** sistemin operasyon kılavuzu — VPS, servis, veritabanı,
admin panel, cron/bildirim sistemi, izleme ve restart işlemleri. Komutlar işlem
ağacı şeklinde, doğrudan çalıştırılabilir.

> Not: Hassas değerler (DB şifresi, JWT secret) bu belgeye YAZILMADI; hepsi VPS'te
> `/opt/harbi_ganyan_backend/.env` içindedir. Belge sadece komut/yol/akış içerir.

---

## 1. Sistem Haritası (genel bakış)

```
İNTERNET
  └─ Cloudflare (harbiganyan.com)
       └─ api.harbiganyan.com  →  VPS 141.98.115.217 (Ubuntu 22.04)
            └─ Nginx (443/SSL, Let's Encrypt)
                 └─ 127.0.0.1:8001  →  systemd: harbi-ganyan-backend.service
                      ├─ FastAPI (uvicorn)  →  /opt/harbi_ganyan_backend
                      ├─ PostgreSQL  →  DB: harbi_ganyan (localhost)
                      ├─ FCM push    →  firebase-sa.json (proje: harbi-ganyan)
                      └─ Cron pipeline → motor: /opt/harbi_ganyan_engine

NOT: Aynı VPS'te ayrı bir sistem daha var → betsignal.shop / baski-backend (port 8000).
     ASLA dokunma. Harbi Ganyan izole: port 8001.
```

---

## 2. VPS Erişim

```
├─ IP            : 141.98.115.217
├─ OS            : Ubuntu 22.04
├─ Kullanıcı     : root (yönetim) / harbiganyan (servis çalıştırma kullanıcısı)
└─ SSH
   ├─ Bağlan     : ssh root@141.98.115.217
   └─ Geçici key prosedürü (Claude/uzaktan erişim için):
      ├─ Yerelde üret : ssh-keygen -t ed25519 -f ~/.ssh/hg_temp -N ""
      ├─ VPS'e ekle   : (VPS'te) echo '<public_key>' >> ~/.ssh/authorized_keys
      ├─ Kullan       : ssh -i ~/.ssh/hg_temp root@141.98.115.217
      └─ İş bitince   : authorized_keys'ten ilgili satırı sil (güvenlik)
```

---

## 3. Servis Yönetimi (systemd)

Servis adı: `harbi-ganyan-backend.service` · Port: `127.0.0.1:8001` · Kullanıcı: `harbiganyan`

```
├─ Durum         : systemctl status harbi-ganyan-backend.service
├─ Aktif mi?     : systemctl is-active harbi-ganyan-backend.service
├─ Restart       : systemctl restart harbi-ganyan-backend.service
├─ Durdur/Başlat : systemctl stop|start harbi-ganyan-backend.service
├─ Boot'ta açık? : systemctl is-enabled harbi-ganyan-backend.service
└─ Config görüntüle: systemctl cat harbi-ganyan-backend.service
   ├─ WorkingDirectory = /opt/harbi_ganyan_backend
   ├─ EnvironmentFile  = /opt/harbi_ganyan_backend/.env
   └─ ExecStart        = .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

**Kod değişikliği sonrası standart akış:**
```
1) Dosyaları VPS'e kopyala (scp)   → bkz. §9
2) cd /opt/harbi_ganyan_backend
3) .venv/bin/python -m py_compile <değişen dosyalar>   # derleme kontrolü
4) (şema değiştiyse) .venv/bin/python -m alembic -c alembic.ini upgrade head
5) systemctl restart harbi-ganyan-backend.service
6) curl -s https://api.harbiganyan.com/saglik          # {"durum":"ok"} beklenir
```

---

## 4. Log / İzleme

```
├─ Servis logu (canlı)   : journalctl -u harbi-ganyan-backend.service -f
├─ Servis logu (son 100) : journalctl -u harbi-ganyan-backend.service -n 100 --no-pager
├─ Bugünün servis logu   : journalctl -u harbi-ganyan-backend.service --since today
└─ Cron pipeline logları : /var/log/harbiganyan/
   ├─ daily.log   → 09:00 yarının analiz üretimi
   ├─ yayin.log   → 18:00 yayın bildirimi
   └─ live.log    → gün içi canlı sonuç takibi + bildirim
      İzle: tail -f /var/log/harbiganyan/live.log
```

---

## 5. Veritabanı (PostgreSQL)

```
├─ DB adı        : harbi_ganyan
├─ Kullanıcı     : harbi_ganyan
├─ Host          : localhost  (bağlantı string'i .env → HG_DATABASE_URL)
├─ psql ile gir  : sudo -u postgres psql harbi_ganyan
└─ Python ile hızlı sorgu (venv'den):
   cd /opt/harbi_ganyan_backend && .venv/bin/python - <<'PY'
   import sys; sys.path.insert(0,".")
   from app.db import SessionLocal
   from app import models as m
   db=SessionLocal()
   print("kullanıcı:", db.query(m.Kullanici).count())
   print("aktif:", db.query(m.Kullanici).filter_by(aktif=True).count())
   print("device_token:", db.query(m.DeviceToken).count())
   print("gün:", db.query(m.Gun).count())
   db.close()
   PY
```

**Migration (Alembic):**
```
├─ Mevcut sürüm  : .venv/bin/python -m alembic -c alembic.ini current
├─ Güncelle      : .venv/bin/python -m alembic -c alembic.ini upgrade head
├─ Geçmiş        : .venv/bin/python -m alembic -c alembic.ini history
└─ Güncel head   : b7e1c2f3a004 (kazanan_ad + gonderilen_bildirim)
```

---

## 6. Admin Panel

```
├─ URL           : https://api.harbiganyan.com/admin
├─ Admin hesabı  : admin@harbiganyan.app   (is_admin=True, tier=vip)
├─ Login akışı   : POST /auth/giris {email,sifre} → token → GET /auth/ben → is_admin kontrolü
├─ Yetki kontrolü: Sadece is_admin=True hesaplar panele girebilir
└─ Şifre sıfırlama (unutulursa, VPS'te):
   cd /opt/harbi_ganyan_backend && .venv/bin/python - <<'PY'
   import sys; sys.path.insert(0,".")
   from app.db import SessionLocal
   from app import models as m
   from app.security import hash_sifre
   db=SessionLocal()
   u=db.query(m.Kullanici).filter_by(email="admin@harbiganyan.app").one()
   u.sifre_hash=hash_sifre("YENI_GUCLU_SIFRE")   # <-- değiştir
   db.commit(); print("şifre güncellendi"); db.close()
   PY
```

**Admin API uçları** (panel bunları kullanır, hepsi `/admin/api` prefix + admin token):
```
├─ GET    /admin/api/ozet                 → haftalık gelir özeti
├─ GET    /admin/api/kullanicilar         → kullanıcı listesi
├─ POST   /admin/api/kullanicilar         → kullanıcı ekle
├─ PATCH  /admin/api/kullanicilar/{id}    → tier / üyelik / admin güncelle
├─ DELETE /admin/api/kullanicilar/{id}    → kullanıcı sil
└─ POST   /admin/api/bildirimler          → manuel bildirim gönder (in-app + push)
```

---

## 7. Bildirim Sistemi (FCM + in-app) — CANLI

```
├─ FCM yapılandırma
│  ├─ Service account : /opt/harbi_ganyan_backend/firebase-sa.json
│  ├─ env             : HG_FIREBASE_SA (.env'de)
│  ├─ Proje           : harbi-ganyan
│  └─ Kanal (Android) : harbi_ganyan_default
│
├─ Bildirim türleri (kaynak: cron/daily_pipeline.py + app/bildirim_servis.py)
│  ├─ Yayın bildirimi (18:00 TR)  → "GG.AA.YYYY tarihine dair analizler eklenmiştir"
│  ├─ Koşu sonucu (canlı)         → gayriresmi (kazanan belli, ganyan yok) → resmi (ganyan + 5'li ✓/✗)
│  └─ 6'lı sonucu (canlı)         → tier'lar (Simitçi/Harbi/Ortaklı) ✓/❌ + ikramiye
│
├─ İdempotency : gonderilen_bildirim tablosu (anahtar bazlı; aynı bildirim 2 kez gitmez,
│                reimport'tan bağımsız)
│
└─ Manuel tetikleme/test (VPS):
   cd /opt/harbi_ganyan_backend
   HG_ENGINE_ROOT=/opt/harbi_ganyan_engine HG_BACKEND_DIR=/opt/harbi_ganyan_backend \
     .venv/bin/python cron/daily_pipeline.py --yayin-bildirim
   # NOT: gerçek bildirim TÜM aktif kullanıcılara gider.
```

---

## 8. Cron Pipeline — CANLI

Crontab (root): `crontab -l` · Saatler **UTC** yazılır (TR = UTC+3, Türkiye'de DST yok).

```
├─ 06:00 UTC (09:00 TR)  daily_pipeline.py               → yarının analizleri (full, scraping)
│                                                          log: daily.log
├─ 15:00 UTC (18:00 TR)  daily_pipeline.py --yayin-bildirim → yayın bildirimi
│                                                          log: yayin.log
└─ */5 07-21 UTC (10-24 TR) daily_pipeline.py --live      → canlı sonuç takibi + bildirim
                                                            log: live.log

ZORUNLU env (cron satırlarında yazılı):
  HG_ENGINE_ROOT=/opt/harbi_ganyan_engine
  HG_BACKEND_DIR=/opt/harbi_ganyan_backend
  (motor modülleri ayrı dizinde olduğu için şart; eksikse build_day_json ImportError verir)

daily_pipeline.py modları:
  ├─ (argümansız)        → yarının analizini üret (full)
  ├─ 2026-06-03          → belirli günü üret (full)
  ├─ --live              → bugün için bekleyen koşu/ikramiye varsa scrape+import+bildir
  ├─ --yayin-bildirim    → yarının yayın bildirimi
  ├─ --results-only      → son 7 günün sonucunu tazele + reimport
  └─ --export-only A B   → A..B günlerini scraping YAPMADAN export+import (güvenli test)
```

```
├─ Cron servisi durum : systemctl is-active cron
├─ Crontab düzenle    : crontab -e
└─ Crontab listele    : crontab -l
```

---

## 9. Dizin Yapısı & Deploy

```
/opt/
├─ harbi_ganyan_backend/        ← FastAPI backend (servis buradan çalışır)
│  ├─ app/                      ← api/, models.py, fcm.py, bildirim_servis.py, serialize.py, config.py
│  ├─ alembic/versions/         ← migration'lar
│  ├─ cron/daily_pipeline.py    ← cron orkestratörü
│  ├─ export/                   ← build_day_json.py, import_to_db.py
│  ├─ .venv/                    ← Python sanal ortam (.venv/bin/python)
│  ├─ .env                      ← GİZLİ: DB url, firebase, cors (git'e girmez)
│  └─ firebase-sa.json          ← GİZLİ: FCM service account
│
└─ harbi_ganyan_engine/         ← Tahmin motoru (ganyan_master.py + motor/)
   ├─ ganyan_master.py          ← günlük tahmin motoru (scraping + 5 satır + 6'lı)
   ├─ motor/                    ← altili_kupon_v2, kupon_v3_engine, tahmin_sonuc_karsilastir...
   ├─ Harbi_Ganyan_Analiz/      ← üretilen analiz çıktıları
   └─ Sonuclar JSON/            ← TJK sonuç arşivi
```

**Deploy (yerel → VPS), git YOK, scp kullanılır:**
```
KEY=~/.ssh/hg_temp
DST=root@141.98.115.217:/opt/harbi_ganyan_backend
scp -i $KEY app/models.py app/bildirim_servis.py "$DST/app/"
scp -i $KEY app/api/content.py                    "$DST/app/api/"
scp -i $KEY cron/daily_pipeline.py                "$DST/cron/"
scp -i $KEY alembic/versions/<yeni_migration>.py  "$DST/alembic/versions/"
# sonra → §3 standart akış (compile → migrate → restart → saglik)
```

---

## 10. Nginx & SSL

```
├─ api.harbiganyan.com → ayrı server block (betsignal.shop'a dokunma)
├─ Upstream      : 127.0.0.1:8001
├─ Config testi  : nginx -t        (DEĞİŞİKLİK SONRASI MUTLAKA)
├─ Reload        : systemctl reload nginx
└─ SSL           : Let's Encrypt (certbot auto-renew aktif), domain api.harbiganyan.com
   └─ Sertifika  : certbot certificates
```

---

## 11. API Sağlık Kontrolleri

```
├─ Sağlık   : curl -s https://api.harbiganyan.com/saglik        → {"durum":"ok"}
├─ Günler   : curl -s https://api.harbiganyan.com/gunler
├─ İstatistik: curl -s https://api.harbiganyan.com/istatistik
└─ Admin    : curl -s -o /dev/null -w "%{http_code}" https://api.harbiganyan.com/admin → 200
```

---

## 12. Mobil Uygulama (Flutter)

```
├─ Kaynak        : app/ (Flutter)
├─ Production API: https://api.harbiganyan.com (config.dart default)
├─ Build (APK)   : flutter build apk --dart-define=HG_API=https://api.harbiganyan.com
├─ Çıktı         : app/build/app/outputs/flutter-apk/app-release.apk
└─ FCM           : firebase_messaging + flutter_local_notifications; token /auth/fcm-token ile kaydedilir
```

---

## 13. Acil Durum / Sık Sorun Çözümleri

```
├─ Backend yanıt vermiyor (502)
│  └─ systemctl status harbi-ganyan-backend.service → journalctl -u ... -n 100 → restart
│
├─ Bildirim gitmiyor
│  ├─ crontab -l (cron satırları var mı, env dolu mu?)
│  ├─ tail -f /var/log/harbiganyan/live.log  (hata var mı?)
│  ├─ FCM aktif mi? → .venv/bin/python -c "import sys;sys.path.insert(0,'.');from app.fcm import aktif;print(aktif())"
│  └─ device_token sayısı > 0 mı? (§5 sorgu)
│
├─ Cron "build_day_json ImportError"
│  └─ Cron satırında HG_ENGINE_ROOT / HG_BACKEND_DIR eksik → §8 env'i ekle
│
├─ Admin panele girilemiyor
│  ├─ URL doğru mu? (https://api.harbiganyan.com/admin)
│  ├─ /auth/giris 401 → şifre yanlış (§6 sıfırla)
│  └─ "admin değil" → hesabın is_admin=True mı? (§5 sorgu)
│
└─ Migration hatası
   └─ alembic current vs head karşılaştır; upgrade head çalıştır
```
