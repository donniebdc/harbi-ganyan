# -*- coding: utf-8 -*-
"""
Günlük pipeline orkestratörü (VPS cron).

Akış (vizyon: D-1 günü 09:00'da D gününün analizleri üretilir):
  1) ganyan_master.GanyanMasterEngine().run(date)  → Harbi_Ganyan_Analiz/<gün> + TahminSonuçları
     (pegadrom/TJK scraping dahil — AĞ GEREKTİRİR, VPS'te çalışır)
  2) build_day_json → yapısal JSON
  3) import_to_db   → PostgreSQL/SQLite

Modlar:
  python backend/cron/daily_pipeline.py                 # yarının analizini üret (full)
  python backend/cron/daily_pipeline.py 2026-06-03      # belirli gün (full)
  python backend/cron/daily_pipeline.py --results-only  # son N günün sonucunu tazele + reimport
  python backend/cron/daily_pipeline.py --export-only 2026-05-29 2026-05-30  # scraping yok

systemd/crontab örnekleri: backend/cron/README.md
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

# Yol çözümlemesi: yerelde monorepo (parents[2]); VPS'te motor ile backend ayrı
# dizinlerde olduğundan env ile override edilebilir (geriye uyumlu).
REPO_ROOT = Path(os.environ.get("HG_ENGINE_ROOT") or Path(__file__).resolve().parents[2])
BACKEND_DIR = Path(os.environ.get("HG_BACKEND_DIR") or (REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))            # ganyan_master, kök scriptler
sys.path.insert(0, str(REPO_ROOT / "motor"))  # motor modülleri (tahmin_sonuc_karsilastir vb.)
sys.path.insert(0, str(BACKEND_DIR))          # app
sys.path.insert(0, str(BACKEND_DIR / "export"))

from build_day_json import build_day, load_context, EXPORT_DIR  # noqa: E402
from import_to_db import import_payload, ensure_schema  # noqa: E402
from app.db import SessionLocal  # noqa: E402
import json  # noqa: E402

RESULTS_REFRESH_GUN = 7


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def _ddmmyyyy(iso: str) -> str:
    y, m, dd = iso.split("-")
    return f"{dd}.{m}.{y}"


def export_import(isos: list[str]):
    """Verilen günleri yapısal JSON'a çevirip DB'ye yazar (scraping yok)."""
    ensure_schema()
    ctx = load_context()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        for iso in isos:
            payload = build_day(iso, ctx)
            (EXPORT_DIR / f"{iso}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            n = import_payload(db, payload)
            db.commit()
            print(f"  export+import {iso}: {len(payload['hipodromlar'])} hipodrom, {n} altılı")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run_full(iso: str):
    """Tam pipeline: tahmin üret (scraping) + TahminSonuçları + export + import."""
    from ganyan_master import GanyanMasterEngine
    print(f"[full] {iso} analizleri üretiliyor...")
    GanyanMasterEngine().run(_ddmmyyyy(iso))
    print(f"[full] {iso} DB'ye yazılıyor...")
    export_import([iso])


def run_results_only(days: int = RESULTS_REFRESH_GUN):
    """Son N günün sonuçlarını tazele (scraping) + reimport — gün-içi periyodik iş."""
    from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret
    today = date.today()
    start = today - timedelta(days=days)
    isos = [_iso(start + timedelta(days=i)) for i in range((today - start).days + 1)]
    print(f"[results] {isos[0]}..{isos[-1]} sonuç tazeleniyor...")
    tahmin_sonuc_uret(isos[0], isos[-1], collect_results=True, force_results=True)
    export_import(isos)


def _bekleyen_var(iso: str) -> bool:
    """Bugün için: saati geçtiği hâlde ganyanı gelmemiş koşu VEYA son ayağı geçtiği
    hâlde ikramiyesi gelmemiş altılı var mı? (canlı poll'un scrape edip etmeyeceğini belirler)"""
    from datetime import datetime as _dt
    from app.models import Gun, GunHipodrom, Kosu, KosuSonuc, Altili, AltiliSonuc
    d = date.fromisoformat(iso)
    now_tr = _dt.utcnow() + timedelta(hours=3)  # VPS UTC -> TR (UTC+3, DST yok)

    def _saat_dt(saat: str):
        try:
            hh, mm = saat.strip().split(":")[:2]
            return now_tr.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        except Exception:
            return None

    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is None:
            return False
        gh_ids = [h.id for h in db.query(GunHipodrom).filter_by(gun_id=gun.id).all()]
        if not gh_ids:
            return False
        kosular = db.query(Kosu).filter(Kosu.gh_id.in_(gh_ids)).all()
        # Koşu: saat+6dk geçti ama ganyan yok -> bekleyen
        kno_saat = {}  # gh_id -> {kno: saat_dt}
        for k in kosular:
            rt = _saat_dt(k.saat)
            kno_saat.setdefault(k.gh_id, {})[k.kno] = rt
            if rt is not None and now_tr >= rt + timedelta(minutes=6):
                son = db.query(KosuSonuc).filter_by(kosu_id=k.id).one_or_none()
                if son is None or son.ganyan is None:
                    return True
        # Altılı: son ayak koşusu saat+8dk geçti ama ikramiye yok -> bekleyen
        for a in db.query(Altili).filter(Altili.gh_id.in_(gh_ids)).all():
            if not a.legs:
                continue
            rt = kno_saat.get(a.gh_id, {}).get(a.legs[-1])
            if rt is not None and now_tr >= rt + timedelta(minutes=8):
                son = db.query(AltiliSonuc).filter_by(altili_id=a.id).one_or_none()
                if son is None or son.ikramiye is None:
                    return True
        return False
    finally:
        db.close()


def run_live():
    """Canlı sonuç takibi (yarış saatlerinde 3dk'da bir). Bugün için bekleyen
    koşu/ikramiye varsa today'i yeniden scrape+import eder; yoksa hızlı çıkar.
    Timer tekrar tekrar ateşlediği için sonuç/ikramiye gelene kadar 'retry' olur."""
    today = date.today()
    iso = _iso(today)
    if not _bekleyen_var(iso):
        print(f"[live] {iso}: bekleyen koşu/ikramiye yok, atlandı.")
        return
    print(f"[live] {iso}: bekleyen sonuç/ikramiye var, tazeleniyor...")
    from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret
    tahmin_sonuc_uret(iso, iso, collect_results=True, force_results=True)
    export_import([iso])


def run_yayin_bildirim():
    """TR 18:00: yarının analizleri yayınlandıysa kullanıcılara bildirim oluşturur
    (uygulama-içi; FCM push Firebase hazır olunca eklenecek). Idempotent."""
    from datetime import datetime as _dt
    from app.models import Gun, Kullanici, Bildirim
    now_tr = _dt.utcnow() + timedelta(hours=3)
    yarin = now_tr.date() + timedelta(days=1)
    yarin_str = yarin.strftime("%d.%m.%Y")
    db = SessionLocal()
    try:
        if db.query(Gun).filter(Gun.date == yarin).first() is None:
            print(f"[yayin] {yarin}: analiz yok, bildirim atlandı.")
            return
        baslik = "Yeni Analizler Yayında!"
        mesaj = f"{yarin_str} günü için 5 satır ve 6'lı analizleri eklendi."
        if db.query(Bildirim).filter(Bildirim.mesaj == mesaj).first() is not None:
            print(f"[yayin] {yarin}: bildirim zaten gönderilmiş, atlandı.")
            return
        users = db.query(Kullanici).filter_by(aktif=True).all()
        hedef_idler = [u.id for u in users]
        for u in users:
            db.add(Bildirim(kullanici_id=u.id, baslik=baslik, mesaj=mesaj))
        db.commit()
        from app import fcm
        push_adet = fcm.kullanicilara_push(db, hedef_idler, baslik, mesaj, {"tip": "yayin"})
        print(f"[yayin] {yarin}: {len(users)} in-app, {push_adet} push gönderildi.")
    finally:
        db.close()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    argv = sys.argv[1:]
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]

    if "--export-only" in flags:
        start = args[0]
        end = args[1] if len(args) > 1 else start
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        export_import([_iso(s + timedelta(days=i)) for i in range((e - s).days + 1)])
    elif "--yayin-bildirim" in flags:
        run_yayin_bildirim()
    elif "--live" in flags:
        run_live()
    elif "--results-only" in flags:
        run_results_only()
    else:
        iso = args[0] if args else _iso(date.today() + timedelta(days=1))
        run_full(iso)


if __name__ == "__main__":
    main()
