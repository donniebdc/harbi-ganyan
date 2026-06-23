# -*- coding: utf-8 -*-
"""
GÃ¼nlÃ¼k pipeline orkestratÃ¶rÃ¼ (VPS cron).

AkÄ±ÅŸ (vizyon: D-1 gÃ¼nÃ¼ 09:00'da D gÃ¼nÃ¼nÃ¼n analizleri Ã¼retilir):
  1) ganyan_master.GanyanMasterEngine().run(date)  â†’ Harbi_Ganyan_Analiz/<gÃ¼n> + TahminSonuÃ§larÄ±
     (pegadrom/TJK scraping dahil â€” AÄ GEREKTÄ°RÄ°R, VPS'te Ã§alÄ±ÅŸÄ±r)
  2) build_day_json â†’ yapÄ±sal JSON
  3) import_to_db   â†’ PostgreSQL/SQLite

Modlar:
  python backend/cron/daily_pipeline.py                 # yarÄ±nÄ±n analizini Ã¼ret (full)
  python backend/cron/daily_pipeline.py 2026-06-03      # belirli gÃ¼n (full)
  python backend/cron/daily_pipeline.py --results-only  # son N gÃ¼nÃ¼n sonucunu tazele + reimport
  python backend/cron/daily_pipeline.py --export-only 2026-05-29 2026-05-30  # scraping yok

systemd/crontab Ã¶rnekleri: backend/cron/README.md
"""
from __future__ import annotations
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

# Yol Ã§Ã¶zÃ¼mlemesi: yerelde monorepo (parents[2]); VPS'te motor ile backend ayrÄ±
# dizinlerde olduÄŸundan env ile override edilebilir (geriye uyumlu).
REPO_ROOT = Path(os.environ.get("HG_ENGINE_ROOT") or Path(__file__).resolve().parents[2])
BACKEND_DIR = Path(os.environ.get("HG_BACKEND_DIR") or (REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT))            # ganyan_master, kÃ¶k scriptler
sys.path.insert(0, str(REPO_ROOT / "motor"))  # motor modÃ¼lleri (tahmin_sonuc_karsilastir vb.)
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


_GUN_ADLARI = ["Pazartesi", "SalÄ±", "Ã‡arÅŸamba", "PerÅŸembe", "Cuma", "Cumartesi", "Pazar"]


def _gun_adi_tr(d: date) -> str:
    return _GUN_ADLARI[d.weekday()]


def export_import(isos: list[str], freeze: bool = True):
    """Verilen gÃ¼nleri yapÄ±sal JSON'a Ã§evirip DB'ye yazar (scraping yok).

    freeze=True (varsayÄ±lan, CANLI-GÃœVENLÄ°): import_payload zaman-bazlÄ± dondurma uygular â€”
      baÅŸlamÄ±ÅŸ/kilitli koÅŸularÄ±n analizi korunur, yalnÄ±z sonuÃ§ gÃ¼ncellenir. GÃ¼n-iÃ§i
      yeniden-Ã¼retimin (canlÄ± takip) geÃ§miÅŸ koÅŸularÄ± yeniden Ã¼retmesini engeller.
    freeze=False: bilinÃ§li replay (manuel --uret / --export-only) â€” tam yeniden-yazÄ±m."""
    ensure_schema()
    ctx = load_context()
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        for iso in isos:
            payload = build_day(iso, ctx)
            (EXPORT_DIR / f"{iso}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            n = import_payload(db, payload, freeze=freeze)
            db.commit()
            print(f"  export+import {iso}: {len(payload['hipodromlar'])} hipodrom, {n} altÄ±lÄ±")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _now_tr() -> datetime:
    return datetime.utcnow() + timedelta(hours=3)  # VPS UTC -> TR (UTC+3, DST yok)


def _son_analiz_yaz(iso: str, sebep: str):
    """Gun.son_analiz / son_analiz_sebep gÃ¼nceller (reimport'ta korunur)."""
    from app.models import Gun
    d = date.fromisoformat(iso)
    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is not None:
            gun.son_analiz = _now_tr()
            gun.son_analiz_sebep = sebep
            db.commit()
    finally:
        db.close()


def _set_tahmin_asamasi(iso: str, asama: str):
    """Gun.tahmin_asamasi yazar; 'final' bir kez set edilince geri alÄ±nmaz."""
    from app.models import Gun
    d = date.fromisoformat(iso)
    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is not None:
            current = getattr(gun, 'tahmin_asamasi', None)
            if asama == 'on_tahmin' and current == 'final':
                return  # final'den geriye dÃ¼ÅŸme
            gun.tahmin_asamasi = asama
            db.commit()
    finally:
        db.close()


def _update_final_banner():
    """on_tahmin gÃ¼nleri iÃ§in: ilk koÅŸudan 30 dk Ã¶nce geÃ§ildiyse 'final' yap.
    (Update.txt madde 1: final tahmin koÅŸudan yarÄ±m saat Ã¶nce iÅŸlenir.)"""
    from app.models import Gun, GunHipodrom, Kosu
    now_tr = _now_tr()
    db = SessionLocal()
    try:
        pending = db.query(Gun).filter(Gun.tahmin_asamasi == 'on_tahmin').all()
        for gun in pending:
            first_race = None
            for gh in db.query(GunHipodrom).filter_by(gun_id=gun.id).all():
                for k in db.query(Kosu).filter_by(gh_id=gh.id).all():
                    rt = _saat_dt(k.saat, now_tr.replace(
                        year=gun.date.year, month=gun.date.month, day=gun.date.day))
                    if rt and (first_race is None or rt < first_race):
                        first_race = rt
            if first_race is None:
                continue
            if now_tr >= first_race - timedelta(minutes=30):
                gun.tahmin_asamasi = 'final'
                print(f"[banner] {gun.date}: final banner aktifleÅŸtirildi.")
        db.commit()
    finally:
        db.close()


def _baslamis_kosu_skip(iso: str) -> set:
    """DB'den BAÅLAMIÅ koÅŸularÄ± {(HIP_KODU_UPPER, kno)} olarak dÃ¶ner (Pegadrom force
    indirmede atlanacaklar). Hipodrom adÄ± Pegadrom kodu iÃ§in ASCII-upper'a katlanÄ±r
    (ElazÄ±ÄŸ->ELAZIG, Ä°stanbul->ISTANBUL)."""
    from pegadrom_ai_txt_topla import fold
    from app.models import Gun, GunHipodrom, Kosu
    d = date.fromisoformat(iso)
    now_tr = _now_tr()
    skip = set()
    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is None:
            return skip
        for gh in db.query(GunHipodrom).filter_by(gun_id=gun.id).all():
            kod = fold(gh.hipodrom).upper()
            for k in db.query(Kosu).filter_by(gh_id=gh.id).all():
                rt = _saat_dt(k.saat, now_tr)
                if rt is not None and now_tr >= rt:  # koÅŸu baÅŸladÄ±/bitti
                    skip.add((kod, k.kno))
        return skip
    finally:
        db.close()


def run_full(iso: str, taze_pegadrom: bool = False, sebep: str = "Ãœretildi",
             freeze: bool = True):
    """Tam pipeline: tahmin Ã¼ret + TahminSonuÃ§larÄ± + export + import.

    freeze=True (varsayÄ±lan, CANLI-GÃœVENLÄ°): import_payload zaman-bazlÄ± dondurma uygular.
    freeze=False: bilinÃ§li replay (tam yeniden-yazÄ±m). taze_pegadrom parametresi artÄ±k
    kullanÄ±lmÄ±yor (Pegadrom baÄŸÄ±mlÄ±lÄ±ÄŸÄ± kaldÄ±rÄ±ldÄ±)."""
    from ganyan_master import GanyanMasterEngine
    print(f"[full] {iso} analizleri Ã¼retiliyor...")
    GanyanMasterEngine().run(_ddmmyyyy(iso))
    print(f"[full] {iso} DB'ye yazÄ±lÄ±yor...")
    export_import([iso], freeze=freeze)
    _son_analiz_yaz(iso, sebep)
    _set_tahmin_asamasi(iso, 'on_tahmin')
    # Ãœretim anÄ±ndaki giriÅŸ tablosunu snapshot'la (canlÄ± takip diff referansÄ±).
    try:
        from canli_takip import mevcut_giris, snapshot_kaydet
        snapshot_kaydet(iso, mevcut_giris(iso))
    except Exception as e:
        print(f"[full] {iso} giriÅŸ snapshot hatasÄ± (devam): {e}")


def run_results_only(days: int = RESULTS_REFRESH_GUN):
    """Son N gÃ¼nÃ¼n sonuÃ§larÄ±nÄ± tazele (scraping) + reimport â€” gÃ¼n-iÃ§i periyodik iÅŸ."""
    from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret
    today = date.today()
    start = today - timedelta(days=days)
    isos = [_iso(start + timedelta(days=i)) for i in range((today - start).days + 1)]
    print(f"[results] {isos[0]}..{isos[-1]} sonuÃ§ tazeleniyor...")
    tahmin_sonuc_uret(isos[0], isos[-1], collect_results=True, force_results=True)
    export_import(isos)


def _bekleyen_var(iso: str) -> bool:
    """BugÃ¼n iÃ§in: saati geÃ§tiÄŸi hÃ¢lde ganyanÄ± gelmemiÅŸ koÅŸu VEYA son ayaÄŸÄ± geÃ§tiÄŸi
    hÃ¢lde ikramiyesi gelmemiÅŸ altÄ±lÄ± var mÄ±? (canlÄ± poll'un scrape edip etmeyeceÄŸini belirler)"""
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
        # KoÅŸu: saat+1dk geÃ§ti ama ganyan yok -> bekleyen (Update.txt madde 3:
        # sonuÃ§ tetiÄŸi koÅŸu saatinden 1 dk sonra ateÅŸlenmeye baÅŸlar)
        kno_saat = {}  # gh_id -> {kno: saat_dt}
        for k in kosular:
            rt = _saat_dt(k.saat)
            kno_saat.setdefault(k.gh_id, {})[k.kno] = rt
            if rt is not None and now_tr >= rt + timedelta(minutes=1):
                son = db.query(KosuSonuc).filter_by(kosu_id=k.id).one_or_none()
                if son is None or son.ganyan is None:
                    return True
        # AltÄ±lÄ±: son ayak koÅŸusu saat+2dk geÃ§ti ama ikramiye yok -> bekleyen
        for a in db.query(Altili).filter(Altili.gh_id.in_(gh_ids)).all():
            if not a.legs:
                continue
            rt = kno_saat.get(a.gh_id, {}).get(a.legs[-1])
            if rt is not None and now_tr >= rt + timedelta(minutes=2):
                son = db.query(AltiliSonuc).filter_by(altili_id=a.id).one_or_none()
                if son is None or son.ikramiye is None:
                    return True
        return False
    finally:
        db.close()


def run_live():
    """CanlÄ± sonuÃ§ takibi (yarÄ±ÅŸ saatlerinde her 5 dk). BugÃ¼n iÃ§in bekleyen
    koÅŸu/ikramiye varsa today'i yeniden scrape+import eder; yoksa hÄ±zlÄ± Ã§Ä±kar.
    AyrÄ±ca on_tahmin gÃ¼nlerini kontrol ederek zamanÄ± gelenleri 'final' yapar."""
    _update_final_banner()
    today = date.today()
    iso = _iso(today)
    if not _bekleyen_var(iso):
        print(f"[live] {iso}: bekleyen koÅŸu/ikramiye yok, atlandÄ±.")
        return
    print(f"[live] {iso}: bekleyen sonuÃ§/ikramiye var, tazeleniyor...")
    from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret
    tahmin_sonuc_uret(iso, iso, collect_results=True, force_results=True)
    export_import([iso])
    # Yeni sonuÃ§lanan koÅŸu/altÄ±lÄ±lar iÃ§in canlÄ± bildirim (madde 3-4). Ä°dempotent.
    from app import bildirim_servis
    db = SessionLocal()
    try:
        n = bildirim_servis.bildir_gun_sonuclari(db, iso)
        print(f"[live] {iso}: {n} yeni bildirim gÃ¶nderildi.")
    finally:
        db.close()


def run_yayin_bildirim():
    """TR 18:00: yarÄ±nÄ±n Ã–N TAHMÄ°NLERÄ° yayÄ±nlandÄ±ysa kullanÄ±cÄ±lara bildirim gÃ¶nderir
    (in-app + FCM push). Idempotent (GonderilenBildirim anahtarÄ±: '<iso>|yayin').
    Update.txt madde 1: 'GG.AA.YYYY <GÃ¼nAdÄ±> Ã–n Tahminleri YayÄ±nlandÄ±'."""
    from datetime import datetime as _dt
    from app.models import Gun
    from app import bildirim_servis
    now_tr = _dt.utcnow() + timedelta(hours=3)
    yarin = now_tr.date() + timedelta(days=1)
    iso = yarin.strftime("%Y-%m-%d")
    yarin_str = yarin.strftime("%d.%m.%Y")
    db = SessionLocal()
    try:
        if db.query(Gun).filter(Gun.date == yarin).first() is None:
            print(f"[yayin] {yarin}: analiz yok, bildirim atlandÄ±.")
            return
        baslik = "Ã–n Tahminler YayÄ±nda!"
        mesaj = f"{yarin_str} {_gun_adi_tr(yarin)} Ã–n Tahminleri YayÄ±nlandÄ±"
        if bildirim_servis.gonder(db, f"{iso}|yayin", mesaj,
                                  {"tip": "yayin", "tarih": iso}, baslik=baslik):
            print(f"[yayin] {yarin}: bildirim gÃ¶nderildi.")
        else:
            print(f"[yayin] {yarin}: zaten gÃ¶nderilmiÅŸ, atlandÄ±.")
        # GEÃ‡Ä°CÄ° KAPALI (Update.txt madde 2): alt-bahis algoritmasÄ± yenilenene kadar
        # VIP koÅŸu analizleri (alt oyunlar) yayÄ±n duyurusu gÃ¶nderilmiyor.
        # if bildirim_servis.bildir_kosu_analiz_yayin(db, iso):
        #     print(f"[yayin] {yarin}: VIP koÅŸu analizleri bildirimi gÃ¶nderildi.")
    finally:
        db.close()


def _saat_dt(saat: str, ref: datetime):
    """'14:30' -> ref gÃ¼nÃ¼nde 14:30 datetime. GeÃ§ersizse None."""
    try:
        hh, mm = saat.strip().split(":")[:2]
        return ref.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        return None


def _kosu_saatleri(iso: str) -> dict:
    """BugÃ¼n iÃ§in {hipodrom: {kno: kosu_dt_tr}} (her koÅŸunun saati)."""
    from app.models import Gun, GunHipodrom, Kosu
    d = date.fromisoformat(iso)
    now_tr = _now_tr()
    out = {}
    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is None:
            return out
        for gh in db.query(GunHipodrom).filter_by(gun_id=gun.id).all():
            knos = {}
            for k in db.query(Kosu).filter_by(gh_id=gh.id).all():
                rt = _saat_dt(k.saat, now_tr)
                if rt is not None:
                    knos[k.kno] = rt
            if knos:
                out[gh.hipodrom] = knos
        return out
    finally:
        db.close()


def _hash_eki(on: str, metin: str) -> str:
    import hashlib
    return on + hashlib.md5(metin.encode("utf-8")).hexdigest()[:8]


def run_canli_takip():
    """YarÄ±ÅŸ-Ã¶ncesi canlÄ± takip orkestratÃ¶rÃ¼ (her ~10 dk Ã§aÄŸrÄ±lÄ±r).

    Her hipodrom KENDÄ° koÅŸu saatlerine gÃ¶re (pencereler baÄŸÄ±msÄ±z):
      - T-3h: ilk koÅŸuya 3 saat kala gÃ¼nÃ¼ TAZE Pegadrom akÄ±ÅŸÄ±yla bir kez yeniden Ã¼retir.
      - GÃ¼n-seviyesi (5-satÄ±r/6'lÄ±, premium): T-3h'tan ilk koÅŸuya 10 dk kalana kadar
        30 dk'da bir + 10 dk kala son tarama.
      - Alt-bahis (KoÅŸu Analizleri, VIP): her koÅŸu kendi saatinden 5 dk Ã¶ncesine kadar
        taranÄ±r.
    TÃ¼m gÃ¼nÃ¼n gÃ¼ncel giriÅŸi TEK fetch ile alÄ±nÄ±r, hipodrom/koÅŸu-bazlÄ± diff'lenir. Jokey/
    koÅŸmaz/pist deÄŸiÅŸikliÄŸinde tÃ¼m gÃ¼n bir kez yeniden Ã¼retilir; gÃ¼n-seviyesi premium +
    alt-bahis VIP bildirimleri ayrÄ± gider. Hepsi marker'lÄ± â†’ tekrar tetiklenmez."""
    from app import bildirim_servis
    iso = _iso(date.today())
    now_tr = _now_tr()
    saatler = _kosu_saatleri(iso)  # {hip: {kno: dt}}
    if not saatler:
        print(f"[canli] {iso}: gÃ¼n/koÅŸu yok, atlandÄ±.")
        return

    UC = timedelta(hours=3)
    DK = lambda m: timedelta(minutes=m)  # noqa: E731
    t3_fire = {}    # hip -> True
    scan_due = {}   # hip -> set(marker anahtarlarÄ±)  (bu tick'te taranacak)
    db = SessionLocal()
    try:
        for hip, knos in saatler.items():
            R = min(knos.values())          # ilk koÅŸu
            Rlast = max(knos.values())      # son koÅŸu
            # T-3h penceresi: R-3h .. R
            if R - UC <= now_tr < R and not bildirim_servis.marker_var(db, f"{iso}|{hip}|t3_done"):
                t3_fire[hip] = True
            # Tarama penceresi: R-3h .. son koÅŸu-5dk (alt-bahis dahil), 30 dk slotlarÄ±
            if R - UC <= now_tr <= Rlast - DK(5):
                slot = int((now_tr - (R - UC)).total_seconds() // 1800)
                k = f"{iso}|{hip}|scan|{slot}"
                if not bildirim_servis.marker_var(db, k):
                    scan_due.setdefault(hip, set()).add(k)
            # GÃ¼n-seviyesi (5-satÄ±r/6'lÄ±) SON tarama: ilk koÅŸu-30dk civarÄ± (bir kez).
            # Bu noktadan sonra 5-satÄ±r/6'lÄ± analizi DONAR â€” bir daha Ã¼retilmez.
            if R - DK(35) <= now_tr <= R - DK(30):
                k = f"{iso}|{hip}|scan_final"
                if not bildirim_servis.marker_var(db, k):
                    scan_due.setdefault(hip, set()).add(k)
            # KoÅŸu-bazlÄ± son tarama: her koÅŸu kendi saati-5dk civarÄ± (bir kez)
            for kno, kt in knos.items():
                if kt - DK(8) <= now_tr <= kt - DK(5):
                    k = f"{iso}|{hip}|race_final|{kno}"
                    if not bildirim_servis.marker_var(db, k):
                        scan_due.setdefault(hip, set()).add(k)
    finally:
        db.close()

    if not t3_fire and not scan_due:
        print(f"[canli] {iso}: pencere dÄ±ÅŸÄ±, atlandÄ±.")
        return

    # Tarama: tÃ¼m gÃ¼nÃ¼n gÃ¼ncel giriÅŸini TEK seferde Ã§ek, hipodrom-bazlÄ± diff'le.
    degisimler = {}  # hip -> [degisim]
    if scan_due:
        from canli_takip import mevcut_giris, snapshot_yukle, diff as giris_diff
        yeni = mevcut_giris(iso)
        eski = snapshot_yukle(iso)
        if yeni and eski:
            for d in giris_diff(eski, yeni):
                if d["hip"] in scan_due:  # yalnÄ±z bu tick'te taranan hipodromlar
                    degisimler.setdefault(d["hip"], []).append(d)
        db = SessionLocal()
        try:
            for hip, keys in scan_due.items():
                for k in keys:
                    bildirim_servis.marker_yaz(db, k)
        finally:
            db.close()

    # Bildirim listeleri: gÃ¼n-seviyesi (premium) ve alt-bahis (VIP) ayrÄ±.
    premium_bildirim = []  # (hip, sebep, eki)
    vip_bildirim = []      # (hip, sebep, eki)
    for hip in t3_fire:
        premium_bildirim.append(
            (hip, "KoÅŸular Ã¶ncesi analizler tekrar gÃ¶zden geÃ§irildi", "t3"))
    for hip, ds in degisimler.items():
        if not ds:
            continue
        R = min(saatler[hip].values())
        # GÃ¼n-seviyesi (premium, 5-satÄ±r/6'lÄ±): YALNIZ ilk koÅŸu-30dk'dan Ã–NCE.
        # -30dk'dan sonra gÃ¼n-seviyesi analizi DONUK; yeniden Ã¼retilmez/bildirilmez.
        if now_tr <= R - DK(30):
            sebep = "; ".join(sorted({d["sebep"] for d in ds}))
            premium_bildirim.append(
                (hip, f"KoÅŸular Ã¶ncesi analizler yenilendi | Sebep: {sebep}",
                 _hash_eki("chg_", sebep)))
        # Alt-bahis (VIP): yalnÄ±z ilgili koÅŸu kendi saati-5dk'yÄ± GEÃ‡MEDÄ°YSE.
        alt = [d for d in ds
               if saatler[hip].get(d["kno"]) and now_tr <= saatler[hip][d["kno"]] - DK(5)]
        if alt:
            sebep = "; ".join(sorted({d["sebep"] for d in alt}))
            vip_bildirim.append(
                (hip, f"KoÅŸu Analizleri yenilendi | Sebep: {sebep}",
                 _hash_eki("alt_", sebep)))

    if not premium_bildirim and not vip_bildirim:
        print(f"[canli] {iso}: tarandÄ±, tetikleyici deÄŸiÅŸiklik yok.")
        return

    son_sebep = (premium_bildirim or vip_bildirim)[0][1]
    print(f"[canli] {iso}: yeniden Ã¼retim â€” "
          f"{len(premium_bildirim)} premium + {len(vip_bildirim)} VIP bildirim.")
    run_full(iso, taze_pegadrom=True, sebep=son_sebep)
    db = SessionLocal()
    try:
        for hip in t3_fire:
            bildirim_servis.marker_yaz(db, f"{iso}|{hip}|t3_done")
        for hip, sebep, eki in premium_bildirim:
            bildirim_servis.bildir_revize(db, iso, hip, sebep,
                                          anahtar_eki=eki, min_tier="premium")
        for hip, sebep, eki in vip_bildirim:
            bildirim_servis.bildir_revize(db, iso, hip, sebep, anahtar_eki=eki,
                                          min_tier="vip", baslik="KoÅŸu Analizleri GÃ¼ncellendi")
    finally:
        db.close()


def _hip_tahmin_hash(iso: str) -> dict:
    """Her hipodrom iÃ§in gÃ¼n-seviyesi tahmin iÃ§eriÄŸinin Ã¶zeti (md5).
    Kapsam: 5-satÄ±r slotlarÄ± + Analiz PuanlarÄ± + 6'lÄ± kademe/ayak seÃ§imleri.
    Yeniden-Ã¼retim Ã¶ncesi/sonrasÄ± karÅŸÄ±laÅŸtÄ±rÄ±larak 'deÄŸiÅŸti mi' tespit edilir."""
    import hashlib
    from app.models import Gun, GunHipodrom, Kosu, Altili
    d = date.fromisoformat(iso)
    out = {}
    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is None:
            return out
        for gh in db.query(GunHipodrom).filter_by(gun_id=gun.id).all():
            parcalar = []
            for k in sorted(db.query(Kosu).filter_by(gh_id=gh.id).all(),
                            key=lambda x: x.kno):
                bes = "|".join(f"{b.slot}:{b.at_no}" for b in k.bes)
                puan = json.dumps(k.analiz_puanlari or [], sort_keys=True)
                parcalar.append(f"K{k.kno}|{bes}|{puan}")
            for a in db.query(Altili).filter_by(gh_id=gh.id).all():
                for kd in a.kademeler:
                    ayak = ";".join(
                        f"{ay.kno}:{','.join(map(str, sorted(ay.secilen or [])))}"
                        for ay in sorted(kd.ayaklar, key=lambda x: x.kno))
                    parcalar.append(f"A{a.idx}|{kd.key}|{ayak}")
            out[gh.hipodrom] = hashlib.md5(
                "\n".join(parcalar).encode("utf-8")).hexdigest()
        return out
    finally:
        db.close()


def run_yenileme():
    """YarÄ±ÅŸ gÃ¼nÃ¼ 30 dk'lÄ±k yeniden-tahmin dÃ¶ngÃ¼sÃ¼ (Update.txt madde 1).

    Cron her 5 dk Ã§aÄŸÄ±rÄ±r (*/5 9-22); iÃ§eride iki tetik vardÄ±r:
      - SLOT: 09:00'dan itibaren 30 dk'lÄ±k slotlarda (09:00, 09:30, ...) gÃ¼n BÄ°R KEZ
        yeniden Ã¼retilir â€” ama yalnÄ±z en az bir ÅŸehir hÃ¢lÃ¢ 'aÃ§Ä±k' iken
        (now < o ÅŸehrin ilk koÅŸusu - 30 dk). Ãœretim sonrasÄ± aÃ§Ä±k ÅŸehirlerin tahmin
        Ã¶zeti deÄŸiÅŸse bile her slotta bildirim gitmez; 10:00 sonrasÄ± tek
        'Tahminler GÃ¼ncellendi' bildirimi gider.
      - FINAL: her ÅŸehrin ilk koÅŸusuna 30-35 dk kala o ÅŸehir iÃ§in SON Ã¼retim yapÄ±lÄ±r,
        'Final Tahminleri yayinlanmistir' bildirimi gider.
        SonrasÄ±nda import_to_db'nin
        ÅŸehir-bazlÄ± kilidi (LOCK_5SAT_DK=30) o ÅŸehri dondurur.
    TÃ¼m tetikler marker'lÄ±dÄ±r (idempotent)."""
    from app import bildirim_servis
    _update_final_banner()
    iso = _iso(date.today())
    now_tr = _now_tr()
    saatler = _kosu_saatleri(iso)
    if not saatler:
        print(f"[yenileme] {iso}: gÃ¼n/koÅŸu yok, atlandÄ±.")
        return
    DK = lambda m: timedelta(minutes=m)  # noqa: E731

    bas = now_tr.replace(hour=9, minute=0, second=0, microsecond=0)
    acik = {hip for hip, knos in saatler.items()
            if now_tr < min(knos.values()) - DK(30)}

    slot_key = None
    final_due = []  # [hip]
    db = SessionLocal()
    try:
        # SLOT tetiÄŸi: 09:00 sonrasÄ±, 30 dk'lÄ±k dilim baÅŸÄ±na bir kez, aÃ§Ä±k ÅŸehir varken
        if now_tr >= bas and acik:
            slot = int((now_tr - bas).total_seconds() // 1800)
            k = f"{iso}|yenileme|{slot}"
            if not bildirim_servis.marker_var(db, k):
                slot_key = k
        # FINAL tetiÄŸi: ÅŸehir ilk koÅŸusuna 35-45 dk kala bir kez tetiklenir;
        # Ã¼retim ~5-8 dk sÃ¼rdÃ¼ÄŸÃ¼nden import, R-30 ÅŸehir kilidinden Ã–NCE tamamlanÄ±r.
        for hip, knos in saatler.items():
            R = min(knos.values())
            if R - DK(45) <= now_tr < R - DK(35):
                if not bildirim_servis.marker_var(db, f"{iso}|{hip}|final_tahmin"):
                    final_due.append(hip)
    finally:
        db.close()

    if slot_key is None and not final_due:
        print(f"[yenileme] {iso}: tetik yok, atlandÄ±.")
        return

    onceki = _hip_tahmin_hash(iso)
    sebep = ("Final tahmin: " + ", ".join(final_due)) if final_due else "30dk yenileme"
    print(f"[yenileme] {iso}: Ã¼retim baÅŸlÄ±yor ({sebep})...")
    run_full(iso, sebep=sebep)  # freeze=True: kilitli ÅŸehirler korunur
    sonraki = _hip_tahmin_hash(iso)

    db = SessionLocal()
    try:
        if slot_key:
            bildirim_servis.marker_yaz(db, slot_key)
        for hip in final_due:
            bildirim_servis.marker_yaz(db, f"{iso}|{hip}|final_tahmin")
        # Final bildirimi: ÅŸehir bazlÄ±, deÄŸiÅŸiklik olmasa da gider (yayÄ±n duyurusu).
        for hip in final_due:
            mesaj = f"{_ddmmyyyy(iso)} | {hip} | Final Tahminleri yayinlanmistir"
            bildirim_servis.gonder(db, f"{iso}|{hip}|final_yayin", mesaj,
                                   {"tip": "final", "tarih": iso, "hipodrom": hip},
                                   baslik="Final Tahminleri YayÄ±nlandÄ±")
        # GÃ¼ncelleme bildirimi: 30 dk'lÄ±k her slotta bildirim yok. Sabah 10:00'dan
        # sonra, aÃ§Ä±k ÅŸehir varken ve bu run bir yenileme yaptÄ±ysa gÃ¼n baÅŸÄ±na tek
        # "Tahminler GÃ¼ncellendi" bildirimi gider.
        if slot_key:
            guncelleme_key = f"{iso}|guncelleme_1000"
            ondan_sonra = now_tr >= now_tr.replace(hour=10, minute=0, second=0, microsecond=0)
            if ondan_sonra and not bildirim_servis.marker_var(db, guncelleme_key):
                mesaj = f"{_ddmmyyyy(iso)} Tahminler GÃ¼ncellendi"
                bildirim_servis.gonder(db, guncelleme_key, mesaj,
                                       {"tip": "guncelleme", "tarih": iso},
                                       baslik="Tahminler GÃ¼ncellendi")
                degisen = [h for h in acik if onceki.get(h) != sonraki.get(h)]
                if degisen:
                    print(f"[yenileme] {iso}: 10:00 bildirimi, deÄŸiÅŸen ÅŸehirler: {', '.join(degisen)}")
                else:
                    print(f"[yenileme] {iso}: 10:00 bildirimi, iÃ§erik hash deÄŸiÅŸmedi.")
            else:
                print(f"[yenileme] {iso}: slot yenilendi, bildirim yok.")
    finally:
        db.close()


def _uyelik_expire_kontrol():
    """Suresi dolan Google Play aboneliklerini standart'a dusur."""
    from app.models import Kullanici, Uyelik
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        suresi_dolanlar = (
            db.query(Uyelik)
            .filter(
                Uyelik.kaynak == "google_play",
                Uyelik.aktif == True,  # noqa: E712
                Uyelik.expires_at != None,  # noqa: E711
                Uyelik.expires_at < now,
            ).all()
        )
        for u in suresi_dolanlar:
            u.aktif = False
            k = db.get(Kullanici, u.kullanici_id)
            if k:
                baska = db.query(Uyelik).filter(
                    Uyelik.kullanici_id == k.id,
                    Uyelik.aktif == True,  # noqa: E712
                    Uyelik.id != u.id,
                ).first()
                if not baska:
                    k.tier = "standart"
        db.commit()
        print(f"[expire] {len(suresi_dolanlar)} abonelik expire edildi.")
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
        # Manuel re-export = bilinÃ§li replay -> tam yeniden-yazÄ±m (dondurma yok).
        export_import([_iso(s + timedelta(days=i)) for i in range((e - s).days + 1)],
                      freeze=False)
    elif "--uret" in flags:
        # Manuel (admin paneli) tam Ã¼retim: tarih VEYA tarih aralÄ±ÄŸÄ± iÃ§in
        # engine + export + import. GeÃ§miÅŸ gÃ¼nlerin alt-bahislerini de doldurur.
        start = args[0]
        end = args[1] if len(args) > 1 else start
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        gunler = [s + timedelta(days=i) for i in range((e - s).days + 1)]
        print(f"[uret] {start}..{end} ({len(gunler)} gÃ¼n) manuel Ã¼retim baÅŸlÄ±yor...")
        for d in gunler:
            run_full(_iso(d), freeze=False)  # bilinÃ§li replay: tam yeniden-yazÄ±m
        print(f"[uret] TAMAMLANDI: {len(gunler)} gÃ¼n Ã¼retildi.")
    elif "--yayin-bildirim" in flags:
        run_yayin_bildirim()
    elif "--canli-takip" in flags:
        run_canli_takip()
    elif "--yenileme" in flags:
        run_yenileme()
    elif "--live" in flags:
        run_live()
    elif "--results-only" in flags:
        run_results_only()
    elif "--expire-uyelik" in flags:
        _uyelik_expire_kontrol()
    else:
        iso = args[0] if args else _iso(date.today() + timedelta(days=1))
        run_full(iso)


if __name__ == "__main__":
    main()


