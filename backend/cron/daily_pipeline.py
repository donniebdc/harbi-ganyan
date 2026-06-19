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


_GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def _gun_adi_tr(d: date) -> str:
    return _GUN_ADLARI[d.weekday()]


def export_import(isos: list[str], freeze: bool = True):
    """Verilen günleri yapısal JSON'a çevirip DB'ye yazar (scraping yok).

    freeze=True (varsayılan, CANLI-GÜVENLİ): import_payload zaman-bazlı dondurma uygular —
      başlamış/kilitli koşuların analizi korunur, yalnız sonuç güncellenir. Gün-içi
      yeniden-üretimin (canlı takip) geçmiş koşuları yeniden üretmesini engeller.
    freeze=False: bilinçli replay (manuel --uret / --export-only) — tam yeniden-yazım."""
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
            print(f"  export+import {iso}: {len(payload['hipodromlar'])} hipodrom, {n} altılı")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _now_tr() -> datetime:
    return datetime.utcnow() + timedelta(hours=3)  # VPS UTC -> TR (UTC+3, DST yok)


def _son_analiz_yaz(iso: str, sebep: str):
    """Gun.son_analiz / son_analiz_sebep günceller (reimport'ta korunur)."""
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
    """Gun.tahmin_asamasi yazar; 'final' bir kez set edilince geri alınmaz."""
    from app.models import Gun
    d = date.fromisoformat(iso)
    db = SessionLocal()
    try:
        gun = db.query(Gun).filter(Gun.date == d).one_or_none()
        if gun is not None:
            current = getattr(gun, 'tahmin_asamasi', None)
            if asama == 'on_tahmin' and current == 'final':
                return  # final'den geriye düşme
            gun.tahmin_asamasi = asama
            db.commit()
    finally:
        db.close()


def _update_final_banner():
    """on_tahmin günleri için: ilk koşudan 30 dk önce geçildiyse 'final' yap.
    (Update.txt madde 1: final tahmin koşudan yarım saat önce işlenir.)"""
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
                print(f"[banner] {gun.date}: final banner aktifleştirildi.")
        db.commit()
    finally:
        db.close()


def _baslamis_kosu_skip(iso: str) -> set:
    """DB'den BAŞLAMIŞ koşuları {(HIP_KODU_UPPER, kno)} olarak döner (Pegadrom force
    indirmede atlanacaklar). Hipodrom adı Pegadrom kodu için ASCII-upper'a katlanır
    (Elazığ->ELAZIG, İstanbul->ISTANBUL)."""
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
                if rt is not None and now_tr >= rt:  # koşu başladı/bitti
                    skip.add((kod, k.kno))
        return skip
    finally:
        db.close()


def run_full(iso: str, taze_pegadrom: bool = False, sebep: str = "Üretildi",
             freeze: bool = True):
    """Tam pipeline: tahmin üret + TahminSonuçları + export + import.

    freeze=True (varsayılan, CANLI-GÜVENLİ): import_payload zaman-bazlı dondurma uygular.
    freeze=False: bilinçli replay (tam yeniden-yazım). taze_pegadrom parametresi artık
    kullanılmıyor (Pegadrom bağımlılığı kaldırıldı)."""
    from ganyan_master import GanyanMasterEngine
    print(f"[full] {iso} analizleri üretiliyor...")
    GanyanMasterEngine().run(_ddmmyyyy(iso))
    print(f"[full] {iso} DB'ye yazılıyor...")
    export_import([iso], freeze=freeze)
    _son_analiz_yaz(iso, sebep)
    _set_tahmin_asamasi(iso, 'on_tahmin')
    # Üretim anındaki giriş tablosunu snapshot'la (canlı takip diff referansı).
    try:
        from canli_takip import mevcut_giris, snapshot_kaydet
        snapshot_kaydet(iso, mevcut_giris(iso))
    except Exception as e:
        print(f"[full] {iso} giriş snapshot hatası (devam): {e}")


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
        # Koşu: saat+1dk geçti ama ganyan yok -> bekleyen (Update.txt madde 3:
        # sonuç tetiği koşu saatinden 1 dk sonra ateşlenmeye başlar)
        kno_saat = {}  # gh_id -> {kno: saat_dt}
        for k in kosular:
            rt = _saat_dt(k.saat)
            kno_saat.setdefault(k.gh_id, {})[k.kno] = rt
            if rt is not None and now_tr >= rt + timedelta(minutes=1):
                son = db.query(KosuSonuc).filter_by(kosu_id=k.id).one_or_none()
                if son is None or son.ganyan is None:
                    return True
        # Altılı: son ayak koşusu saat+2dk geçti ama ikramiye yok -> bekleyen
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
    """Canlı sonuç takibi (yarış saatlerinde her 5 dk). Bugün için bekleyen
    koşu/ikramiye varsa today'i yeniden scrape+import eder; yoksa hızlı çıkar.
    Ayrıca on_tahmin günlerini kontrol ederek zamanı gelenleri 'final' yapar."""
    _update_final_banner()
    today = date.today()
    iso = _iso(today)
    if not _bekleyen_var(iso):
        print(f"[live] {iso}: bekleyen koşu/ikramiye yok, atlandı.")
        return
    print(f"[live] {iso}: bekleyen sonuç/ikramiye var, tazeleniyor...")
    from tahmin_sonuc_karsilastir import uret_aralik as tahmin_sonuc_uret
    tahmin_sonuc_uret(iso, iso, collect_results=True, force_results=True)
    export_import([iso])
    # Yeni sonuçlanan koşu/altılılar için canlı bildirim (madde 3-4). İdempotent.
    from app import bildirim_servis
    db = SessionLocal()
    try:
        n = bildirim_servis.bildir_gun_sonuclari(db, iso)
        print(f"[live] {iso}: {n} yeni bildirim gönderildi.")
    finally:
        db.close()


def run_yayin_bildirim():
    """TR 18:00: yarının ÖN TAHMİNLERİ yayınlandıysa kullanıcılara bildirim gönderir
    (in-app + FCM push). Idempotent (GonderilenBildirim anahtarı: '<iso>|yayin').
    Update.txt madde 1: 'GG.AA.YYYY <GünAdı> Ön Tahminleri Yayınlandı'."""
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
            print(f"[yayin] {yarin}: analiz yok, bildirim atlandı.")
            return
        baslik = "Ön Tahminler Yayında!"
        mesaj = f"{yarin_str} {_gun_adi_tr(yarin)} Ön Tahminleri Yayınlandı"
        if bildirim_servis.gonder(db, f"{iso}|yayin", mesaj,
                                  {"tip": "yayin", "tarih": iso}, baslik=baslik):
            print(f"[yayin] {yarin}: bildirim gönderildi.")
        else:
            print(f"[yayin] {yarin}: zaten gönderilmiş, atlandı.")
        # GEÇİCİ KAPALI (Update.txt madde 2): alt-bahis algoritması yenilenene kadar
        # VIP koşu analizleri (alt oyunlar) yayın duyurusu gönderilmiyor.
        # if bildirim_servis.bildir_kosu_analiz_yayin(db, iso):
        #     print(f"[yayin] {yarin}: VIP koşu analizleri bildirimi gönderildi.")
    finally:
        db.close()


def _saat_dt(saat: str, ref: datetime):
    """'14:30' -> ref gününde 14:30 datetime. Geçersizse None."""
    try:
        hh, mm = saat.strip().split(":")[:2]
        return ref.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
    except Exception:
        return None


def _kosu_saatleri(iso: str) -> dict:
    """Bugün için {hipodrom: {kno: kosu_dt_tr}} (her koşunun saati)."""
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
    """Yarış-öncesi canlı takip orkestratörü (her ~10 dk çağrılır).

    Her hipodrom KENDİ koşu saatlerine göre (pencereler bağımsız):
      - T-3h: ilk koşuya 3 saat kala günü TAZE Pegadrom akışıyla bir kez yeniden üretir.
      - Gün-seviyesi (5-satır/6'lı, premium): T-3h'tan ilk koşuya 10 dk kalana kadar
        30 dk'da bir + 10 dk kala son tarama.
      - Alt-bahis (Koşu Analizleri, VIP): her koşu kendi saatinden 5 dk öncesine kadar
        taranır.
    Tüm günün güncel girişi TEK fetch ile alınır, hipodrom/koşu-bazlı diff'lenir. Jokey/
    koşmaz/pist değişikliğinde tüm gün bir kez yeniden üretilir; gün-seviyesi premium +
    alt-bahis VIP bildirimleri ayrı gider. Hepsi marker'lı → tekrar tetiklenmez."""
    from app import bildirim_servis
    iso = _iso(date.today())
    now_tr = _now_tr()
    saatler = _kosu_saatleri(iso)  # {hip: {kno: dt}}
    if not saatler:
        print(f"[canli] {iso}: gün/koşu yok, atlandı.")
        return

    UC = timedelta(hours=3)
    DK = lambda m: timedelta(minutes=m)  # noqa: E731
    t3_fire = {}    # hip -> True
    scan_due = {}   # hip -> set(marker anahtarları)  (bu tick'te taranacak)
    db = SessionLocal()
    try:
        for hip, knos in saatler.items():
            R = min(knos.values())          # ilk koşu
            Rlast = max(knos.values())      # son koşu
            # T-3h penceresi: R-3h .. R
            if R - UC <= now_tr < R and not bildirim_servis.marker_var(db, f"{iso}|{hip}|t3_done"):
                t3_fire[hip] = True
            # Tarama penceresi: R-3h .. son koşu-5dk (alt-bahis dahil), 30 dk slotları
            if R - UC <= now_tr <= Rlast - DK(5):
                slot = int((now_tr - (R - UC)).total_seconds() // 1800)
                k = f"{iso}|{hip}|scan|{slot}"
                if not bildirim_servis.marker_var(db, k):
                    scan_due.setdefault(hip, set()).add(k)
            # Gün-seviyesi (5-satır/6'lı) SON tarama: ilk koşu-30dk civarı (bir kez).
            # Bu noktadan sonra 5-satır/6'lı analizi DONAR — bir daha üretilmez.
            if R - DK(35) <= now_tr <= R - DK(30):
                k = f"{iso}|{hip}|scan_final"
                if not bildirim_servis.marker_var(db, k):
                    scan_due.setdefault(hip, set()).add(k)
            # Koşu-bazlı son tarama: her koşu kendi saati-5dk civarı (bir kez)
            for kno, kt in knos.items():
                if kt - DK(8) <= now_tr <= kt - DK(5):
                    k = f"{iso}|{hip}|race_final|{kno}"
                    if not bildirim_servis.marker_var(db, k):
                        scan_due.setdefault(hip, set()).add(k)
    finally:
        db.close()

    if not t3_fire and not scan_due:
        print(f"[canli] {iso}: pencere dışı, atlandı.")
        return

    # Tarama: tüm günün güncel girişini TEK seferde çek, hipodrom-bazlı diff'le.
    degisimler = {}  # hip -> [degisim]
    if scan_due:
        from canli_takip import mevcut_giris, snapshot_yukle, diff as giris_diff
        yeni = mevcut_giris(iso)
        eski = snapshot_yukle(iso)
        if yeni and eski:
            for d in giris_diff(eski, yeni):
                if d["hip"] in scan_due:  # yalnız bu tick'te taranan hipodromlar
                    degisimler.setdefault(d["hip"], []).append(d)
        db = SessionLocal()
        try:
            for hip, keys in scan_due.items():
                for k in keys:
                    bildirim_servis.marker_yaz(db, k)
        finally:
            db.close()

    # Bildirim listeleri: gün-seviyesi (premium) ve alt-bahis (VIP) ayrı.
    premium_bildirim = []  # (hip, sebep, eki)
    vip_bildirim = []      # (hip, sebep, eki)
    for hip in t3_fire:
        premium_bildirim.append(
            (hip, "Koşular öncesi analizler tekrar gözden geçirildi", "t3"))
    for hip, ds in degisimler.items():
        if not ds:
            continue
        R = min(saatler[hip].values())
        # Gün-seviyesi (premium, 5-satır/6'lı): YALNIZ ilk koşu-30dk'dan ÖNCE.
        # -30dk'dan sonra gün-seviyesi analizi DONUK; yeniden üretilmez/bildirilmez.
        if now_tr <= R - DK(30):
            sebep = "; ".join(sorted({d["sebep"] for d in ds}))
            premium_bildirim.append(
                (hip, f"Koşular öncesi analizler yenilendi | Sebep: {sebep}",
                 _hash_eki("chg_", sebep)))
        # Alt-bahis (VIP): yalnız ilgili koşu kendi saati-5dk'yı GEÇMEDİYSE.
        alt = [d for d in ds
               if saatler[hip].get(d["kno"]) and now_tr <= saatler[hip][d["kno"]] - DK(5)]
        if alt:
            sebep = "; ".join(sorted({d["sebep"] for d in alt}))
            vip_bildirim.append(
                (hip, f"Koşu Analizleri yenilendi | Sebep: {sebep}",
                 _hash_eki("alt_", sebep)))

    if not premium_bildirim and not vip_bildirim:
        print(f"[canli] {iso}: tarandı, tetikleyici değişiklik yok.")
        return

    son_sebep = (premium_bildirim or vip_bildirim)[0][1]
    print(f"[canli] {iso}: yeniden üretim — "
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
                                          min_tier="vip", baslik="Koşu Analizleri Güncellendi")
    finally:
        db.close()


def _hip_tahmin_hash(iso: str) -> dict:
    """Her hipodrom için gün-seviyesi tahmin içeriğinin özeti (md5).
    Kapsam: 5-satır slotları + Analiz Puanları + 6'lı kademe/ayak seçimleri.
    Yeniden-üretim öncesi/sonrası karşılaştırılarak 'değişti mi' tespit edilir."""
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
    """Yarış günü 30 dk'lık yeniden-tahmin döngüsü (Update.txt madde 1).

    Cron her 5 dk çağırır (*/5 9-22); içeride iki tetik vardır:
      - SLOT: 09:00'dan itibaren 30 dk'lık slotlarda (09:00, 09:30, ...) gün BİR KEZ
        yeniden üretilir — ama yalnız en az bir şehir hâlâ 'açık' iken
        (now < o şehrin ilk koşusu - 30 dk). Üretim sonrası açık şehirlerin tahmin
        özeti değişse bile her slotta bildirim gitmez; 10:00 sonrası tek
        'Tahminler Güncellendi' bildirimi gider.
      - FINAL: her şehrin ilk koşusuna 30-35 dk kala o şehir için SON üretim yapılır,
        'Final Tahminleri ve 6'lı Ganyan Analizleri yayınlanmıştır' bildirimi gider.
        Sonrasında import_to_db'nin
        şehir-bazlı kilidi (LOCK_5SAT_DK=30) o şehri dondurur.
    Tüm tetikler marker'lıdır (idempotent)."""
    from app import bildirim_servis
    _update_final_banner()
    iso = _iso(date.today())
    now_tr = _now_tr()
    saatler = _kosu_saatleri(iso)
    if not saatler:
        print(f"[yenileme] {iso}: gün/koşu yok, atlandı.")
        return
    DK = lambda m: timedelta(minutes=m)  # noqa: E731

    bas = now_tr.replace(hour=9, minute=0, second=0, microsecond=0)
    acik = {hip for hip, knos in saatler.items()
            if now_tr < min(knos.values()) - DK(30)}

    slot_key = None
    final_due = []  # [hip]
    db = SessionLocal()
    try:
        # SLOT tetiği: 09:00 sonrası, 30 dk'lık dilim başına bir kez, açık şehir varken
        if now_tr >= bas and acik:
            slot = int((now_tr - bas).total_seconds() // 1800)
            k = f"{iso}|yenileme|{slot}"
            if not bildirim_servis.marker_var(db, k):
                slot_key = k
        # FINAL tetiği: şehir ilk koşusuna 35-45 dk kala bir kez tetiklenir;
        # üretim ~5-8 dk sürdüğünden import, R-30 şehir kilidinden ÖNCE tamamlanır.
        for hip, knos in saatler.items():
            R = min(knos.values())
            if R - DK(45) <= now_tr < R - DK(35):
                if not bildirim_servis.marker_var(db, f"{iso}|{hip}|final_tahmin"):
                    final_due.append(hip)
    finally:
        db.close()

    if slot_key is None and not final_due:
        print(f"[yenileme] {iso}: tetik yok, atlandı.")
        return

    onceki = _hip_tahmin_hash(iso)
    sebep = ("Final tahmin: " + ", ".join(final_due)) if final_due else "30dk yenileme"
    print(f"[yenileme] {iso}: üretim başlıyor ({sebep})...")
    run_full(iso, sebep=sebep)  # freeze=True: kilitli şehirler korunur
    sonraki = _hip_tahmin_hash(iso)

    db = SessionLocal()
    try:
        if slot_key:
            bildirim_servis.marker_yaz(db, slot_key)
        for hip in final_due:
            bildirim_servis.marker_yaz(db, f"{iso}|{hip}|final_tahmin")
        # Final bildirimi: şehir bazlı, değişiklik olmasa da gider (yayın duyurusu).
        for hip in final_due:
            mesaj = (f"{_ddmmyyyy(iso)} | {hip} | Final Tahminleri ve 6'lı Ganyan "
                     f"Analizleri yayınlanmıştır")
            bildirim_servis.gonder(db, f"{iso}|{hip}|final_yayin", mesaj,
                                   {"tip": "final", "tarih": iso, "hipodrom": hip},
                                   baslik="Final Tahminleri Yayınlandı")
        # Güncelleme bildirimi: 30 dk'lık her slotta bildirim yok. Sabah 10:00'dan
        # sonra, açık şehir varken ve bu run bir yenileme yaptıysa gün başına tek
        # "Tahminler Güncellendi" bildirimi gider.
        if slot_key:
            guncelleme_key = f"{iso}|guncelleme_1000"
            ondan_sonra = now_tr >= now_tr.replace(hour=10, minute=0, second=0, microsecond=0)
            if ondan_sonra and not bildirim_servis.marker_var(db, guncelleme_key):
                mesaj = f"{_ddmmyyyy(iso)} Tahminler Güncellendi"
                bildirim_servis.gonder(db, guncelleme_key, mesaj,
                                       {"tip": "guncelleme", "tarih": iso},
                                       baslik="Tahminler Güncellendi")
                degisen = [h for h in acik if onceki.get(h) != sonraki.get(h)]
                if degisen:
                    print(f"[yenileme] {iso}: 10:00 bildirimi, değişen şehirler: {', '.join(degisen)}")
                else:
                    print(f"[yenileme] {iso}: 10:00 bildirimi, içerik hash değişmedi.")
            else:
                print(f"[yenileme] {iso}: slot yenilendi, bildirim yok.")
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
        # Manuel re-export = bilinçli replay -> tam yeniden-yazım (dondurma yok).
        export_import([_iso(s + timedelta(days=i)) for i in range((e - s).days + 1)],
                      freeze=False)
    elif "--uret" in flags:
        # Manuel (admin paneli) tam üretim: tarih VEYA tarih aralığı için
        # engine + export + import. Geçmiş günlerin alt-bahislerini de doldurur.
        start = args[0]
        end = args[1] if len(args) > 1 else start
        s = datetime.strptime(start, "%Y-%m-%d").date()
        e = datetime.strptime(end, "%Y-%m-%d").date()
        gunler = [s + timedelta(days=i) for i in range((e - s).days + 1)]
        print(f"[uret] {start}..{end} ({len(gunler)} gün) manuel üretim başlıyor...")
        for d in gunler:
            run_full(_iso(d), freeze=False)  # bilinçli replay: tam yeniden-yazım
        print(f"[uret] TAMAMLANDI: {len(gunler)} gün üretildi.")
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
    else:
        iso = args[0] if args else _iso(date.today() + timedelta(days=1))
        run_full(iso)


if __name__ == "__main__":
    main()
