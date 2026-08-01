# -*- coding: utf-8 -*-

"""

Günlük pipeline orkestratörü (VDS cron) — v3 XGBoost motoru.



Akış:

  1) v3_export.build_day_payload(date)  → XGBoost walk-forward tahmin + altılı kupon

  2) import_to_db.import_payload()      → PostgreSQL



Modlar:

  python cron/daily_pipeline.py                   # yarının analizini üret (full)

  python cron/daily_pipeline.py 2026-06-03        # belirli gün (full)

  python cron/daily_pipeline.py --results-only    # son N günün sonucunu tazele

  python cron/daily_pipeline.py --export-only 2026-05-29 2026-05-30  # replay (no TJK)

  python cron/daily_pipeline.py --uret 2026-06-01 2026-06-15         # manuel tam üretim

  python cron/daily_pipeline.py --yayin-bildirim  # 18:00 ön tahmin bildirimi

  python cron/daily_pipeline.py --yenileme        # 30dk yenileme döngüsü

  python cron/daily_pipeline.py --live            # canlı sonuç takibi

  python cron/daily_pipeline.py --canli-takip     # jokey/giriş değişikliği takibi



systemd/crontab örnekleri: backend/cron/README.md

"""

from __future__ import annotations

import os

import sys

from datetime import datetime, timedelta, date

from pathlib import Path



BACKEND_DIR = Path(os.environ.get("HG_BACKEND_DIR") or Path(__file__).resolve().parents[1])

V3_ROOT = Path(os.environ.get("HG_V3_ROOT") or "/opt/harbi_ganyan_v3")



sys.path.insert(0, str(BACKEND_DIR))

sys.path.insert(0, str(BACKEND_DIR / "export"))

if str(V3_ROOT) not in sys.path:

    sys.path.insert(0, str(V3_ROOT))

if str(V3_ROOT / "src") not in sys.path:

    sys.path.insert(0, str(V3_ROOT / "src"))



from import_to_db import import_payload, ensure_schema, update_results_only  # noqa: E402

from app.db import SessionLocal  # noqa: E402

import json  # noqa: E402



RESULTS_REFRESH_GUN = 7

_SURDIREK_CACHE = V3_ROOT / "data" / "surdirek_cache.json"


def _surdirek_istatistik(all_items: list) -> dict:
    bucket_stats: dict[str, dict] = {}
    for x in all_items:
        if x.get("kazandi") is None:
            continue
        bk = x.get("bucket", "")
        if bk not in bucket_stats:
            bucket_stats[bk] = {"toplam": 0, "kazandi": 0}
        bucket_stats[bk]["toplam"] += 1
        if x["kazandi"]:
            bucket_stats[bk]["kazandi"] += 1
    bes_toplam  = sum(v["toplam"] for v in bucket_stats.values())
    bes_kazandi = sum(v["kazandi"] for v in bucket_stats.values())
    bes_yuzde   = round(100.0 * bes_kazandi / bes_toplam, 1) if bes_toplam else 0.0
    return {
        "toplam": bes_toplam, "kazandi": bes_kazandi, "yuzde": bes_yuzde,
        "bucketler": {
            bk: {"ad": bk, "toplam": bv["toplam"], "kazandi": bv["kazandi"],
                 "yuzde": round(100.0 * bv["kazandi"] / bv["toplam"], 1) if bv["toplam"] else 0.0}
            for bk, bv in bucket_stats.items()
        },
    }


def _surdirek_update_live(today: date) -> None:
    """Bugünün tamamlanan koşularının sürdirek sonuçlarını anlık günceller."""
    results_path = V3_ROOT / "data" / "results_raw" / f"{today:%Y-%m-%d}.json"
    if not _SURDIREK_CACHE.exists() or not results_path.exists():
        return
    try:
        cache   = json.loads(_SURDIREK_CACHE.read_text(encoding="utf-8"))
        results = json.loads(results_path.read_text(encoding="utf-8"))
        updated = False
        newly_updated: list = []
        for item in cache.get("bugun", []):
            if item.get("kazandi") is not None:
                continue
            hip_d = results.get("hippodromes", {}).get(item["hip"].upper(), {})
            race  = hip_d.get("races", {}).get(str(item["race_no"]))
            if not race:
                continue
            order = race.get("order") or []
            if not order:
                continue
            w = order[0]
            kazandi = (w.get("horse_no") == item["horse_no"])
            item["kazandi"] = kazandi
            item["ganyan"]  = w.get("ganyan") if kazandi else None
            updated = True
            newly_updated.append(item)
        if updated:
            all_items = cache.get("bugun", []) + cache.get("gecmis", [])
            cache["istatistik"] = _surdirek_istatistik(all_items)
            _SURDIREK_CACHE.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[surdirek] {today}: kazandi/ganyan guncellendi.")
            iso_str = f"{today:%Y-%m-%d}"
            try:
                from app import bildirim_servis as _bs
                _db = SessionLocal()
                try:
                    for _item in newly_updated:
                        _basari = "Başarılı" if _item["kazandi"] else "Başarısız"
                        _anahtar = (f"{iso_str}|{_item['hip']}"
                                    f"|surdirek|k{_item['race_no']}|sonuc")
                        _mesaj = f"Günün Sürdirek Atı: {_item['horse_name']} {_basari}"
                        _bs.gonder(_db, _anahtar, _mesaj,
                                   {"tip": "surdirek_sonuc", "tarih": iso_str,
                                    "hipodrom": _item["hip"],
                                    "race_no": _item["race_no"],
                                    "kazandi": _item["kazandi"]},
                                   baslik="Günün Sürdirek Atı")
                    _db.commit()
                finally:
                    _db.close()
            except Exception as _ne:
                print(f"[surdirek] sonuc bildirim hatasi: {_ne}")
    except Exception as e:
        print(f"[surdirek] live guncelleme hatasi: {e}")


def _surdirek_bildirim_gonder(db, iso: str, hip: str) -> None:
    """Sürdirek freeze bildirimi: DB canonical daily_panel.surdirekler'den okur.

    Cache'e bakmaz; publication sonrasi DB commit edilmis canonical secimi kullanir.
    Boylece cache/DB tutarsizliginda bildirim DB ile her zaman uyumlu olur.
    """
    try:
        from app import bildirim_servis
        from app.models import Gun
        gun = db.query(Gun).filter(Gun.date == iso).first()
        if not gun or not gun.daily_panel:
            return
        dp = gun.daily_panel or {}
        for item in dp.get("surdirekler", []):
            if not isinstance(item, dict):
                continue
            if item.get("hip", "").upper() != hip.upper():
                continue
            race_no = item.get("kno") if item.get("kno") is not None else item.get("race_no")
            horse_no = item.get("at_no") if item.get("at_no") is not None else item.get("horse_no")
            horse_name = item.get("at") or item.get("horse_name") or ""
            if race_no is None or horse_no is None:
                continue
            anahtar = (f"{iso}|{hip}"
                       f"|surdirek|k{race_no}|yayin")
            mesaj = (f"Günün Sürdirek Atı: {hip} - "
                     f"{race_no}. Koşu - "
                     f"No {horse_no} - {horse_name}")
            bildirim_servis.gonder(db, anahtar, mesaj,
                                   {"tip": "surdirek_yayin", "tarih": iso,
                                    "hipodrom": hip,
                                    "race_no": race_no,
                                    "horse_no": horse_no,
                                    "horse_name": horse_name},
                                   baslik="Günün Sürdirek Atı")
    except Exception as _se:
        print(f"[surdirek] freeze bildirim hatasi: {_se}")


def _surdirek_update_cache(picks: list, analysis_date: date, city: str | None = None) -> None:
    """Sürdirek tahminlerini cache'e yaz.

    city=None (tam gün): cache['bugun'] tümden replace.
    city=<HIP> (şehir bazlı): yalnız o şehrin eski kaydını çıkar, yeni pick'leri ekle,
      diğer şehirler korunur.
    """
    today = date.today()
    cutoff = (today - timedelta(days=30)).isoformat()
    if _SURDIREK_CACHE.exists():
        cache = json.loads(_SURDIREK_CACHE.read_text(encoding="utf-8"))
    else:
        cache = {"bugun": [], "gecmis": [], "istatistik": {"toplam": 0, "kazandi": 0, "yuzde": 0.0, "bucketler": {}}}
    # Mevcut bugun'u gecmise taşı (artık dün oldu)
    gecmis = cache.get("gecmis", []) + cache.get("bugun", [])
    gecmis = [x for x in gecmis if x.get("date", "") >= cutoff]
    if city:
        # Şehir bazlı merge: diğer şehirleri koru, sadece bu şehri güncelle
        old_bugun = cache.get("bugun", [])
        kept = [b for b in old_bugun if b.get("hip", "").upper() != city.upper()]
        cache["bugun"] = kept + picks
    else:
        cache["bugun"] = picks
    cache["gecmis"] = gecmis
    cache["updated_at"] = today.isoformat()
    all_items = cache["bugun"] + gecmis
    cache["istatistik"] = _surdirek_istatistik(all_items)
    _SURDIREK_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    _mode = f"merge:{city}" if city else "full"
    print(f"[surdirek] {analysis_date} ({_mode}): {len(picks)} secim cache'e yazildi.")





def _iso(d: date) -> str:

    return d.strftime("%Y-%m-%d")





def _ddmmyyyy(iso: str) -> str:

    y, m, dd = iso.split("-")

    return f"{dd}.{m}.{y}"





_GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]





def _gun_adi_tr(d: date) -> str:

    return _GUN_ADLARI[d.weekday()]





def _now_tr() -> datetime:

    return datetime.utcnow() + timedelta(hours=3)





def _son_analiz_yaz(iso: str, sebep: str):

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

    from app.models import Gun

    d = date.fromisoformat(iso)

    db = SessionLocal()

    try:

        gun = db.query(Gun).filter(Gun.date == d).one_or_none()

        if gun is not None:

            current = getattr(gun, 'tahmin_asamasi', None)

            if asama == 'on_tahmin' and current == 'final':

                return

            gun.tahmin_asamasi = asama

            db.commit()

    finally:

        db.close()





def _update_final_banner():

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





def run_full(iso: str, taze_pegadrom: bool = False, sebep: str = "Üretildi",

             freeze: bool = True, city: str | None = None):

    """v3 XGBoost tahmin üret + DB'ye yaz.



    Args:

        iso: Tarih (YYYY-MM-DD)

        taze_pegadrom: Pegadrom verisini tazele (kullanılmıyor)

        sebep: Son analiz sebebi

        freeze: True -> frozen merge, False -> tam yeniden yazım

        city: None -> tüm şehirler, \"ISTANBUL\" -> sadece o şehir

    """

    from v3_export import build_day_payload

    d = date.fromisoformat(iso)

    ensure_schema()

    city_label = f" ({city})" if city else ""

    print(f"[full] {iso}{city_label} v3 tahmin üretiliyor...")

    payload = build_day_payload(d, refresh=True, city=city)
    surdirek_picks = []
    if payload:
        surdirek_picks = payload.pop("_surdirek", [])

    print(f"[full] {iso}{city_label} DB'ye yazılıyor...")

    db = SessionLocal()

    try:

        n, pub_results = import_payload(db, payload, freeze=freeze)

        db.commit()

        print(f"[full] {iso}{city_label}: {n} altılı yazıldı.")

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()

    _son_analiz_yaz(iso, sebep)

    _set_tahmin_asamasi(iso, 'on_tahmin')

    # Sürdirek cache: canonical secimi cache'e yaz (tam gun -> replace, sehir -> merge)
    if surdirek_picks:
        try:
            _surdirek_update_cache(surdirek_picks, d, city=city)
        except Exception as _se:
            print(f"[surdirek] cache hatasi: {_se}")

    try:

        from canli_takip import mevcut_giris, snapshot_kaydet

        snapshot_kaydet(iso, mevcut_giris(iso))

    except Exception as e:

        print(f"[full] {iso} giriş snapshot hatası (devam): {e}")

    return pub_results





def run_results_only(days: int = RESULTS_REFRESH_GUN):

    """Son N günün sonuçlarını TJK'dan tazele + DB güncelle (yalnız sonuç alanları)."""

    from harbi_v3.collect_results import collect_results_day

    today = date.today()

    start = today - timedelta(days=days)

    ensure_schema()

    for i in range((today - start).days + 1):

        day = start + timedelta(days=i)

        iso = _iso(day)

        print(f"[results] {iso} sonuçlar tazeleniyor...")

        results_path = collect_results_day(day, force=True)

        if not results_path or not results_path.exists():

            print(f"[results] {iso}: sonuç yok, atlandı.")

            continue

        results_data = json.loads(results_path.read_text(encoding='utf-8'))

        db = SessionLocal()

        try:

            n = update_results_only(db, day, results_data)

            db.commit()

            print(f"[results] {iso}: {n} koşu sonucu güncellendi.")

        except Exception:

            db.rollback()

            raise

        finally:

            db.close()





def _bekleyen_var(iso: str) -> bool:

    """Bugün için: saati geçtiği hâlde ganyanı gelmemiş koşu VEYA son ayağı geçtiği

    hâlde ikramiyesi gelmemiş altılı var mı?"""

    from datetime import datetime as _dt

    from app.models import Gun, GunHipodrom, Kosu, KosuSonuc, Altili, AltiliSonuc

    d = date.fromisoformat(iso)

    now_tr = _dt.utcnow() + timedelta(hours=3)



    def _saat_dt_inner(saat: str):

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

        kno_saat = {}

        for k in kosular:

            rt = _saat_dt_inner(k.saat)

            kno_saat.setdefault(k.gh_id, {})[k.kno] = rt

            if rt is not None and now_tr >= rt:  # anlik kontrol

                son = db.query(KosuSonuc).filter_by(kosu_id=k.id).one_or_none()

                if son is None or son.ganyan is None:

                    return True

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

    """Canlı sonuç takibi (yarış saatlerinde her 1 dk). Bekleyen koşu varsa TJK'dan

    sonuçları çekip yalnız sonuç alanlarını günceller (XGBoost çalıştırmaz)."""

    _update_final_banner()

    today = date.today()

    iso = _iso(today)

    if not _bekleyen_var(iso):

        print(f"[live] {iso}: bekleyen koşu/ikramiye yok, atlandı.")

        return

    print(f"[live] {iso}: bekleyen sonuç var, tazeleniyor...")

    from harbi_v3.collect_results import collect_results_day

    results_path = collect_results_day(today, force=True)

    if results_path and results_path.exists():

        results_data = json.loads(results_path.read_text(encoding='utf-8'))

        ensure_schema()

        db = SessionLocal()

        try:

            n = update_results_only(db, today, results_data)

            db.commit()

            print(f"[live] {iso}: {n} koşu sonucu güncellendi.")

        except Exception:

            db.rollback()

            raise

        finally:

            db.close()

    # Sürdirek cache: tamamlanan koşuların kazandi/ganyan bilgisini güncelle
    try:
        _surdirek_update_live(today)
    except Exception as _se:
        print(f"[surdirek] live hatasi: {_se}")

    from app import bildirim_servis

    db = SessionLocal()

    try:

        n = bildirim_servis.bildir_gun_sonuclari(db, iso)

        print(f"[live] {iso}: {n} yeni bildirim gönderildi.")

    finally:

        db.close()





def run_yayin_bildirim():

    """TR 18:00: yarının ÖN TAHMİNLERİ yayınlandıysa kullanıcılara bildirim gönderir."""

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

    """Yarış-öncesi canlı takip orkestratörü (her ~10 dk çağrılır)."""

    from app import bildirim_servis

    iso = _iso(date.today())

    now_tr = _now_tr()

    saatler = _kosu_saatleri(iso)

    if not saatler:

        print(f"[canli] {iso}: gün/koşu yok, atlandı.")

        return



    UC = timedelta(hours=3)

    DK = lambda m: timedelta(minutes=m)  # noqa: E731

    t3_fire = {}

    scan_due = {}

    db = SessionLocal()

    try:

        for hip, knos in saatler.items():

            R = min(knos.values())

            Rlast = max(knos.values())

            if R - UC <= now_tr < R and not bildirim_servis.marker_var(db, f"{iso}|{hip}|t3_done"):

                t3_fire[hip] = True

            if R - UC <= now_tr <= Rlast - DK(5):

                slot = int((now_tr - (R - UC)).total_seconds() // 1800)

                k = f"{iso}|{hip}|scan|{slot}"

                if not bildirim_servis.marker_var(db, k):

                    scan_due.setdefault(hip, set()).add(k)

            if R - DK(35) <= now_tr <= R - DK(30):

                k = f"{iso}|{hip}|scan_final"

                if not bildirim_servis.marker_var(db, k):

                    scan_due.setdefault(hip, set()).add(k)

            for kno, kt in knos.items():

                if kt - DK(8) <= now_tr <= kt - DK(5):

                    k = f"{iso}|{hip}|race_final|{kno}"

                    if not bildirim_servis.marker_var(db, k):

                        scan_due.setdefault(hip, set()).add(k)

    finally:

        db.close()



    # Final tahmin: T-35..T-25 arasi degisiklik olmasa da calistir
    final_due = {}
    db2 = SessionLocal()
    try:
        for hip, knos in saatler.items():
            R = min(knos.values())
            if now_tr >= R - DK(35):  # T-30 civari final tetigi
                k = f"{iso}|{hip}|final_tahmin"
                if not bildirim_servis.marker_var(db2, k):
                    final_due[hip] = k
    finally:
        db2.close()

    if final_due:
        print(f"[canli] {iso}: final tetiklendi: " + ",".join(final_due.keys()))
        for hip, marker_k in final_due.items():
            sebep_hip = "Final tahmin: " + hip
            run_full(iso, sebep=sebep_hip, freeze=True, city=hip)
            db3 = SessionLocal()
            try:
                bildirim_servis.marker_yaz(db3, marker_k)
                mesaj = _ddmmyyyy(iso) + " | " + hip + " | Final Tahminleri yayinlandi"
                bildirim_servis.gonder(db3, f"{iso}|{hip}|final_yayin", mesaj,
                                       {"tip": "final", "tarih": iso, "hipodrom": hip},
                                       baslik="Final Tahminleri Yayinlandi")
                _surdirek_bildirim_gonder(db3, iso, hip)
            finally:
                db3.close()

    if not t3_fire and not scan_due and not final_due:

        print(f"[canli] {iso}: pencere dışı, atlandı.")

        return



    degisimler = {}

    if scan_due:

        from canli_takip import mevcut_giris, snapshot_yukle, diff as giris_diff

        yeni = mevcut_giris(iso)

        eski = snapshot_yukle(iso)

        if yeni and eski:

            for d in giris_diff(eski, yeni):

                if d["hip"] in scan_due:

                    degisimler.setdefault(d["hip"], []).append(d)

        db = SessionLocal()

        try:

            for hip, keys in scan_due.items():

                for k in keys:

                    bildirim_servis.marker_yaz(db, k)

        finally:

            db.close()



    premium_bildirim = []

    vip_bildirim = []

    for hip in t3_fire:

        premium_bildirim.append(

            (hip, "Koşular öncesi analizler tekrar gözden geçirildi", "t3"))

    for hip, ds in degisimler.items():

        if not ds:

            continue

        R = min(saatler[hip].values())

        if now_tr <= R - DK(30):

            sebep = "; ".join(sorted({d["sebep"] for d in ds}))

            premium_bildirim.append(

                (hip, f"Koşular öncesi analizler yenilendi | Sebep: {sebep}",

                 _hash_eki("chg_", sebep)))

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

    pub_results = run_full(iso, sebep=son_sebep) or []

    # FAIL-CLOSED: yalniz PUBLISHED + revision artti + content_hash degisti +
    # source_run_id mevcut + tum alanlar doluysa bildirim gonder.
    # Eksik/NO_CHANGE/FAILED_CANDIDATE/lock atlandi/exception -> bildirim YOK.
    _pub_ok: dict[str, bool] = {}
    for _pr in pub_results:
        if not isinstance(_pr, dict):
            continue
        _hip = _pr.get("hipodrom", "")
        _st = _pr.get("status", "")
        _prev_rev = _pr.get("prev_revision")
        _rev = _pr.get("revision")
        _prev_ch = _pr.get("prev_content_hash")
        _ch = _pr.get("content_hash")
        _run = _pr.get("source_run_id")
        _ok = (
            _st == "PUBLISHED"
            and _rev is not None
            and _prev_rev is not None
            and _rev != _prev_rev
            and _ch is not None
            and _prev_ch is not None
            and _ch != _prev_ch
            and _run is not None
        )
        _pub_ok[_hip] = _ok
        if not _ok:
            _reason = []
            if _st != "PUBLISHED": _reason.append(f"status={_st}")
            if _rev is None: _reason.append("rev=None")
            if _prev_rev is None: _reason.append("prev_rev=None")
            elif _rev == _prev_rev: _reason.append("rev_unchanged")
            if _ch is None: _reason.append("content_hash=None")
            if _prev_ch is None: _reason.append("prev_content_hash=None")
            elif _ch == _prev_ch: _reason.append("content_hash_unchanged")
            if _run is None: _reason.append("source_run_id=None")
            print(f"[canli] {iso}|{_hip}: bildirim atlandi ({', '.join(_reason)})")

    db = SessionLocal()

    try:

        for hip in t3_fire:

            bildirim_servis.marker_yaz(db, f"{iso}|{hip}|t3_done")

        for hip, sebep, eki in premium_bildirim:

            if _pub_ok.get(hip, False):
                bildirim_servis.bildir_revize(db, iso, hip, sebep,

                                              anahtar_eki=eki, min_tier="premium")

        for hip, sebep, eki in vip_bildirim:

            if _pub_ok.get(hip, False):
                bildirim_servis.bildir_revize(db, iso, hip, sebep, anahtar_eki=eki,

                                              min_tier="vip", baslik="Koşu Analizleri Güncellendi")

    finally:

        db.close()





def _hip_tahmin_hash(iso: str) -> dict:

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

    """Yarış günü 30 dk'lık yeniden-tahmin döngüsü (VDS Sistem.txt madde 2)."""

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

    final_due = []

    db = SessionLocal()

    try:

        if now_tr >= bas and acik:

            slot = int((now_tr - bas).total_seconds() // 1800)

            k = f"{iso}|yenileme|{slot}"

            if not bildirim_servis.marker_var(db, k):

                slot_key = k

        for hip, knos in saatler.items():

            R = min(knos.values())

            if now_tr >= R - DK(35):  # T-30 civari final tetigi

                if not bildirim_servis.marker_var(db, f"{iso}|{hip}|final_tahmin"):

                    final_due.append(hip)

    finally:

        db.close()



    if slot_key is None and not final_due:

        print(f"[yenileme] {iso}: tetik yok, atlandı.")

        return



    onceki = _hip_tahmin_hash(iso)



    # 1) Final due: şehir bazlı, her şehir kendi programını T-30'da son kez çeker

    if final_due:

        for hip in final_due:

            sebep_hip = f"Final tahmin: {hip}"

            print(f"[yenileme] {iso}: {sebep_hip} üretiliyor...")

            run_full(iso, sebep=sebep_hip, freeze=True, city=hip)



    # 2) Slot tetiği: tüm şehirler 30dk yenileme (final olmayan şehirler için)

    if slot_key:

        print(f"[yenileme] {iso}: 30dk yenileme üretiliyor...")

        run_full(iso, sebep="30dk yenileme")



    sonraki = _hip_tahmin_hash(iso)



    db = SessionLocal()

    try:

        if slot_key:

            bildirim_servis.marker_yaz(db, slot_key)

        for hip in final_due:

            bildirim_servis.marker_yaz(db, f"{iso}|{hip}|final_tahmin")

        for hip in final_due:

            mesaj = (f"{_ddmmyyyy(iso)} | {hip} | Final Tahminleri "

                     f"Analizleri yayınlanmıştır")

            bildirim_servis.gonder(db, f"{iso}|{hip}|final_yayin", mesaj,

                                   {"tip": "final", "tarih": iso, "hipodrom": hip},

                                   baslik="Final Tahminleri Yayınlandı")
            _surdirek_bildirim_gonder(db, iso, hip)

        if slot_key:

            ondan_sonra = now_tr >= now_tr.replace(hour=10, minute=0, second=0, microsecond=0)
            degisen = [h for h in acik if onceki.get(h) != sonraki.get(h)]
            if ondan_sonra and degisen:
                slot_no = slot_key.split("|")[-1]
                mesaj = f"{_ddmmyyyy(iso)} Tahminler Guncellendi ({chr(44).join(degisen)})"
                bildirim_servis.gonder(db, f"{iso}|guncelleme|{slot_no}", mesaj,
                                       {"tip": "guncelleme", "tarih": iso},
                                       baslik="Tahminler Guncellendi")
                print(f"[yenileme] {iso}: slot bildirimi, degisen: {chr(44).join(degisen)}")
            elif ondan_sonra:
                print(f"[yenileme] {iso}: slot yenilendi, degisiklik yok.")
            else:
                print(f"[yenileme] {iso}: slot yenilendi, 10:00 oncesi bildirim yok.")

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

        from v3_export import build_day_payload

        start = args[0]

        end = args[1] if len(args) > 1 else start

        s = datetime.strptime(start, "%Y-%m-%d").date()

        e = datetime.strptime(end, "%Y-%m-%d").date()

        ensure_schema()

        isos = [_iso(s + timedelta(days=i)) for i in range((e - s).days + 1)]

        for iso in isos:

            d = date.fromisoformat(iso)

            print(f"[export-only] {iso} yerel veriyle üretiliyor (TJK çekimi yok)...")

            payload = build_day_payload(d, refresh=False)

            db = SessionLocal()

            try:

                n, _ = import_payload(db, payload, freeze=False)

                db.commit()

                print(f"[export-only] {iso}: {n} altılı.")

            except Exception:

                db.rollback()

                raise

            finally:

                db.close()

    elif "--uret" in flags:

        start = args[0]

        end = args[1] if len(args) > 1 else start

        s = datetime.strptime(start, "%Y-%m-%d").date()

        e = datetime.strptime(end, "%Y-%m-%d").date()

        gunler = [s + timedelta(days=i) for i in range((e - s).days + 1)]

        print(f"[uret] {start}..{end} ({len(gunler)} gün) manuel üretim başlıyor...")

        for d in gunler:

            run_full(_iso(d), freeze=False)

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

