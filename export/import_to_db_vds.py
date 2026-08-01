# -*- coding: utf-8 -*-
"""
Export JSON → PostgreSQL/SQLite import (idempotent).

Bir günün hipodrom bloklarını (date,hipodrom) bazında siler ve yeniden yazar; böylece
sonuçlar geldikçe aynı gün tekrar import edilebilir.

Kullanım:
    python backend/export/import_to_db.py 2026-05-15
    python backend/export/import_to_db.py 2026-05-01 2026-05-30
    python backend/export/import_to_db.py --all          # out/ altındaki tüm JSON'lar
"""
from __future__ import annotations
import os
import sys
import json
import glob
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.db import engine, SessionLocal, Base  # noqa: E402
from app.models import (  # noqa: E402
    Gun, GunHipodrom, Kosu, KosuBes, KosuSonuc,
    Altili, AltiliKademe, AltiliAyak, AltiliSonuc, KosuBahis,
)

try:
    from app.models import Surdirek
except ImportError:
    Surdirek = None

OUT_DIR = Path("/opt/harbi_ganyan_v3/data/export_out")
META_DIR = Path("/opt/harbi_ganyan_v3/data/meta")


def ensure_schema():
    Base.metadata.create_all(engine)
    _ensure_columns()


def _ensure_columns():
    """create_all mevcut tabloya sütun EKLEMEZ; yeni sütunları idempotent ALTER ile ekle.
    Postgres + SQLite uyumlu (inspector ile var/yok kontrolü)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    eklenecek = [
        ("gun",  "son_analiz",        "TIMESTAMP"),
        ("gun",  "son_analiz_sebep",  "VARCHAR(200)"),
        ("gun",  "daily_panel",       "JSONB"),
        ("kosu", "ktip",              "VARCHAR(40)"),
        ("kosu", "zorluk",            "JSONB"),
        ("kosu", "agf_radar",         "JSONB"),
        ("kosu", "aciklama_kartlari", "JSONB"),
        ("kosu_bes", "jokey",             "VARCHAR(40)"),
        ("kosu_bes", "apranti",           "BOOLEAN"),
        ("kosu_bes", "eku_partner_nos",   "JSON"),
    ]
    for tablo, sutun, tip in eklenecek:
        try:
            mevcut = {c["name"] for c in insp.get_columns(tablo)}
        except Exception:
            continue
        if sutun in mevcut:
            continue
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {tablo} ADD COLUMN {sutun} {tip}'))
        print(f"[schema] {tablo}.{sutun} sütunu eklendi.")

    # kosu sütun genişletme: TJK koşu tip adları VARCHAR(40) sınırını aşabiliyor
    _genislet = [
        ("kosu", "ktip",        "VARCHAR(200)"),
        ("kosu", "race_type",   "VARCHAR(100)"),
        ("kosu", "race_subtype","VARCHAR(100)"),
    ]
    dialect = engine.dialect.name
    for tablo, sutun, tip in _genislet:
        try:
            cols = {c["name"]: c for c in insp.get_columns(tablo)}
        except Exception:
            continue
        if sutun not in cols:
            continue
        max_len = getattr(cols[sutun]["type"], "length", None) or 0
        need = int(tip.split("(")[1].rstrip(")"))
        if max_len >= need:
            continue
        try:
            with engine.begin() as conn:
                if dialect == "postgresql":
                    conn.execute(text(
                        f"ALTER TABLE {tablo} ALTER COLUMN {sutun} TYPE {tip}"))
                # SQLite: ALTER COLUMN TYPE desteklemiyor, sessizce atla
            print(f"[schema] {tablo}.{sutun} -> {tip} genişletildi.")
        except Exception as exc:
            print(f"[schema] {tablo}.{sutun} genişletilemedi (devam): {exc}")


def _get_or_create_gun(db, d: date) -> Gun:
    g = db.query(Gun).filter_by(date=d).one_or_none()
    if g is None:
        g = Gun(date=d)
        db.add(g)
        db.flush()
    return g


# ── Canlı dondurma eşikleri ──────────────────────────────────────────────────
#   5-satır kilit: 1. altılı başlangıç koşusuna -30 dk (altılı-bazlı, VDS Sistem.txt).
#   Altılı kilit: her altılı kendi başlangıç koşusuna göre ayrı kilitlenir.
#   Alt-bahis kilit: her koşu -5 dk.
LOCK_5SAT_DK = 30
LOCK_ALT_DK = 5


def _now_tr() -> datetime:
    return datetime.utcnow() + timedelta(hours=3)


def _saat_dt(d: date, saat: str):
    """'14:30' + gün -> datetime; geçersizse None."""
    try:
        hh, mm = (saat or "").strip().split(":")[:2]
        return datetime(d.year, d.month, d.day, int(hh), int(mm))
    except Exception:
        return None


def _add_kosu(db, gh_id: int, k: dict):
    _sprint1 = {
        attr: val
        for attr, val in [
            ("zorluk",            k.get("zorluk")),
            ("agf_radar",         k.get("agf_radar")),
            ("aciklama_kartlari", k.get("aciklama_kartlari") or None),
        ]
        if hasattr(Kosu, attr)
    }
    kosu = Kosu(gh_id=gh_id, kno=k["kno"], pist=k.get("pist", ""),
                mesafe=str(k.get("mesafe", "")), saat=k.get("saat", ""),
                n_at=k.get("n_at"), race_type=k.get("race_type", ""),
                race_subtype=k.get("race_subtype", ""), ktip=k.get("ktip", ""), guven=k.get("guven", ""),
                analiz_puanlari=k.get("analiz_puanlari") or None,
                **_sprint1)
    db.add(kosu)
    db.flush()
    for i, b in enumerate(k.get("bes", [])):
        db.add(KosuBes(kosu_id=kosu.id, sira=i, slot=b["slot"], at_no=b["at_no"],
                       at=b.get("at", ""), ana=b.get("ana", 0.0),
                       jokey=b.get("jokey", ""), apranti=bool(b.get("apranti")),
                       eku_partner_nos=b.get("eku_partner_nos") or None))
    _set_kosu_sonuc(db, kosu, k.get("sonuc"))
    return kosu


def _set_kosu_sonuc(db, kosu: Kosu, s: dict | None):
    """KosuSonuc'u (varsa siler) yeniden yazar. s None ise dokunmaz."""
    if not s:
        return
    if kosu.sonuc is not None:
        db.delete(kosu.sonuc)
        db.flush()
    db.add(KosuSonuc(kosu_id=kosu.id, kazanan=s.get("kazanan"),
                     kazanan_ad=s.get("kazanan_ad", "") or "",
                     ganyan=s.get("ganyan"), bes_hit=s.get("bes_hit")))


def _add_altili(db, gh_id: int, a: dict):
    alt = Altili(gh_id=gh_id, idx=a["idx"], legs=a["legs"])
    db.add(alt)
    db.flush()
    for kd in a.get("kademeler", []):
        kademe = AltiliKademe(altili_id=alt.id, key=kd["key"], ad=kd["ad"],
                              bedel=kd["bedel"], komb=kd["komb"])
        db.add(kademe)
        db.flush()
        for ay in kd.get("ayaklar", []):
            db.add(AltiliAyak(kademe_id=kademe.id, kno=ay["kno"], width=ay["width"],
                              banko_lider=ay.get("banko_lider", False),
                              secilen=ay["secilen"],
                              secilen_atlar=ay.get("secilen_atlar")))
    _set_altili_sonuc(db, alt, a.get("sonuc"))
    return alt


def _set_altili_sonuc(db, alt: Altili, s: dict | None):
    if not s:
        return
    if alt.sonuc is not None:
        db.delete(alt.sonuc)
        db.flush()
    db.add(AltiliSonuc(altili_id=alt.id, winners=s["winners"],
                       ikramiye=s.get("ikramiye"), tier_hits=s["tier_hits"]))


def _add_bahis(db, gh_id: int, b: dict):
    s = b.get("sonuc") or {}
    db.add(KosuBahis(
        gh_id=gh_id, bas_kosu=b["bas_kosu"], tip=b["tip"], aile=b["aile"],
        ad=b["ad"], legs=b["legs"], kolonlar=b["kolonlar"],
        secim_atlar=b["secim_atlar"], kombinasyon=b["kombinasyon"],
        birim=b["birim"], kupon_bedeli=b["kupon_bedeli"], misli=b["misli"],
        max_butce=b["max_butce"],
        tuttu=s.get("tuttu"),
        ganyan=s.get("ikramiye"),
        net=s.get("net"),
        kazanan=({"kombo": s.get("kazanan"), "adlar": s.get("adlar") or {}}
                 if b.get("sonuc") else None)))


def _bahis_sonuc_guncelle(row: KosuBahis, pb: dict):
    if pb.get("sonuc") is None:
        return
    s = pb.get("sonuc") or {}
    row.tuttu = s.get("tuttu")
    row.ganyan = s.get("ikramiye")
    row.net = s.get("net")
    row.kazanan = {"kombo": s.get("kazanan"), "adlar": s.get("adlar") or {}}


def _upsert_surdirek(db, gh: GunHipodrom, sd: dict) -> None:
    """Meta JSON'daki sürdirek bilgisini DB'ye yazar (upsert)."""
    if not sd:
        return
    if not hasattr(gh, 'surdirek'):
        return
    if gh.surdirek is not None:
        s = gh.surdirek
    else:
        s = Surdirek(gh_id=gh.id)
        db.add(s)
    s.race_no = sd.get("race_no", 0)
    s.horse_no = sd.get("horse_no", 0)
    s.horse_name = sd.get("horse_name", "")
    s.gap = float(sd.get("gap", 0.0))
    s.norm_score = float(sd.get("norm_score", 0.0))
    s.win_rate = float(sd.get("win_rate", 0.0))
    s.bucket = sd.get("bucket", "")


def _load_meta_surdirek(d: date, hip: str) -> dict | None:
    """DD_MM_YYYY_HIP_meta.json dosyasından sürdirek alanını okur."""
    fname = META_DIR / f"{d:%d_%m_%Y}_{hip.upper()}_meta.json"
    if not fname.exists():
        return None
    try:
        data = json.loads(fname.read_text(encoding="utf-8"))
        return data.get("surdirek")
    except Exception:
        return None


def _write_hip_full(db, gun_id: int, hp: dict) -> int:
    """Bir hipodromu sıfırdan yazar (tam yeniden-yazım). Döner: altılı sayısı."""
    gh = GunHipodrom(gun_id=gun_id, hipodrom=hp["hipodrom"], birim=hp.get("birim", 0.0))
    db.add(gh)
    db.flush()
    for k in hp.get("kosular", []):
        _add_kosu(db, gh.id, k)
    for a in hp.get("altililar", []):
        _add_altili(db, gh.id, a)
    for b in hp.get("bahisler", []):
        _add_bahis(db, gh.id, b)
    return len(hp.get("altililar", []))


def _merge_hip_frozen(db, gh: GunHipodrom, hp: dict, d: date, now_tr: datetime) -> int:
    """DONDURMALI birleştirme: başlamış/kilitli koşuların ANALİZİ korunur, yalnız
    sonuç alanları güncellenir. Henüz kilitlenmemiş koşular tazelenir.
    Döner: altılı sayısı.

    5-satır kilit: 1. altılı başlangıç koşusuna -30 dk (VDS Sistem.txt).
    Altılı kilit: her altılı kendi başlangıç koşusuna göre ayrı kilitlenir."""
    race_dt = {}
    for k in hp.get("kosular", []):
        rt = _saat_dt(d, k.get("saat"))
        if rt is not None:
            race_dt[k["kno"]] = rt

    # 5-satır kilit: 1. altılı başlangıcına -30 dk; altılı yoksa ilk koşuya göre
    pick6_starts = hp.get("pick6_starts") or []  # [(idx, start_kno), ...]
    p6_sorted = sorted(pick6_starts, key=lambda x: x[0])
    if p6_sorted:
        first_p6_kno = p6_sorted[0][1]
        R_P6 = race_dt.get(first_p6_kno)
        hip_locked = R_P6 is not None and now_tr >= R_P6 - timedelta(minutes=LOCK_5SAT_DK)
    else:
        R_H = min(race_dt.values()) if race_dt else None
        hip_locked = R_H is not None and now_tr >= R_H.replace(tzinfo=now_tr.tzinfo) - timedelta(minutes=LOCK_5SAT_DK)

    # Altılı kilit eşikleri: her altılı için kendi başlangıç kono'sunun saati
    p6_lock_map = {}  # idx -> locked (bool)
    for idx, start_kno in p6_sorted:
        R_P6i = race_dt.get(start_kno)
        p6_lock_map[idx] = R_P6i is not None and now_tr >= R_P6i - timedelta(minutes=LOCK_5SAT_DK)

    # --- Koşular (5-satır) ---
    mevcut_kosu = {k.kno: k for k in db.query(Kosu).filter(Kosu.gh_id == gh.id).all()}
    for k in hp.get("kosular", []):
        ek = mevcut_kosu.get(k["kno"])
        if ek is None:
            _add_kosu(db, gh.id, k)
            continue
        if not hip_locked:
            db.query(KosuBes).filter(KosuBes.kosu_id == ek.id).delete(synchronize_session="fetch")
            db.flush()
            ek.pist = k.get("pist", ""); ek.mesafe = str(k.get("mesafe", ""))
            ek.saat = k.get("saat", ""); ek.n_at = k.get("n_at")
            ek.race_type = k.get("race_type", ""); ek.race_subtype = k.get("race_subtype", "")
            ek.ktip = k.get("ktip", "")
            ek.guven = k.get("guven", "")
            ek.analiz_puanlari = k.get("analiz_puanlari") or None
            for attr, val in [
                ("zorluk",            k.get("zorluk")),
                ("agf_radar",         k.get("agf_radar")),
                ("aciklama_kartlari", k.get("aciklama_kartlari") or None),
            ]:
                if hasattr(ek, attr):
                    setattr(ek, attr, val)
            for i, b in enumerate(k.get("bes", [])):
                db.add(KosuBes(kosu_id=ek.id, sira=i, slot=b["slot"], at_no=b["at_no"],
                               at=b.get("at", ""), ana=b.get("ana", 0.0),
                               jokey=b.get("jokey", ""), apranti=bool(b.get("apranti")),
                               eku_partner_nos=b.get("eku_partner_nos") or None))
        _set_kosu_sonuc(db, ek, k.get("sonuc"))

    # --- Altılılar (altılı-bazlı kilit) ---
    mevcut_alt = {a.idx: a for a in gh.altililar}
    payload_alt = {a["idx"]: a for a in hp.get("altililar", [])}

    for idx, a in payload_alt.items():
        ea = mevcut_alt.get(idx)
        alt_locked = p6_lock_map.get(idx, hip_locked)
        if ea is None:
            if not alt_locked:
                _add_altili(db, gh.id, a)
        elif alt_locked:
            _set_altili_sonuc(db, ea, a.get("sonuc"))
        else:
            db.delete(ea)
            db.flush()
            _add_altili(db, gh.id, a)

    for idx, ea in mevcut_alt.items():
        if idx not in payload_alt:
            alt_locked = p6_lock_map.get(idx, hip_locked)
            if not alt_locked:
                db.delete(ea)

    n_alt = len(hp.get("altililar", []))

    # --- Alt-bahisler (KOŞU-bazlı kilit: her koşu −5 dk) ---
    mevcut_bahis = {}
    for b in gh.bahisler:
        mevcut_bahis.setdefault(b.bas_kosu, []).append(b)
    payload_bahis = {}
    for b in hp.get("bahisler", []):
        payload_bahis.setdefault(b["bas_kosu"], []).append(b)
    for bk in set(mevcut_bahis) | set(payload_bahis):
        T = race_dt.get(bk)
        alt_locked = T is not None and now_tr >= T - timedelta(minutes=LOCK_ALT_DK)
        eski = mevcut_bahis.get(bk, [])
        yeni = payload_bahis.get(bk, [])
        if alt_locked and eski:
            by_tip = {b["tip"]: b for b in yeni}
            for row in eski:
                pb = by_tip.get(row.tip)
                if pb is not None:
                    _bahis_sonuc_guncelle(row, pb)
        else:
            for row in eski:
                db.delete(row)
            db.flush()
            for b in yeni:
                _add_bahis(db, gh.id, b)
    return n_alt


def update_results_only(db, target_date: date, results_data: dict) -> int:
    """TJK sonuç JSON'undan DB'deki KosuSonuc kayıtlarını günceller.
    BES, analiz_puanlari, altılı kademeleri dokunulmaz.
    Döner: güncellenen koşu sayısı."""
    gun = db.query(Gun).filter_by(date=target_date).one_or_none()
    if gun is None:
        return 0
    n = 0
    for hip_key, hip_data in results_data.get("hippodromes", {}).items():
        gh = db.query(GunHipodrom).filter_by(gun_id=gun.id, hipodrom=hip_key).one_or_none()
        if gh is None:
            continue
        kosu_map = {k.kno: k for k in gh.kosular}
        for race_no_str, race in hip_data.get("races", {}).items():
            try:
                race_no = int(race_no_str)
            except (ValueError, TypeError):
                continue
            winner = race.get("winner")
            if not winner:
                continue
            kosu = kosu_map.get(race_no)
            if kosu is None:
                continue
            ganyan = None
            kazanan_ad = ""
            for horse in race.get("order", []):
                if horse.get("horse_no") == winner:
                    ganyan = horse.get("ganyan")
                    kazanan_ad = horse.get("horse_name") or ""
                    break
            bes_hit = None
            if kosu.bes:
                bes_hit = any(b.at_no == winner for b in kosu.bes)
            _set_kosu_sonuc(db, kosu, {
                "kazanan": winner,
                "kazanan_ad": kazanan_ad,
                "ganyan": ganyan,
                "bes_hit": bes_hit,
            })
            n += 1
    return n


def import_payload(db, payload: dict, freeze: bool = True, now_tr: datetime | None = None) -> int:
    """Bir günün payload'unu yazar; yazılan altılı sayısını döner.

    freeze=True (varsayılan, CANLI-GÜVENLİ): mevcut bir (gün,hipodrom) için zaman-bazlı
      dondurma uygulanır — başlamış/kilitli koşuların ANALİZİ korunur, yalnız sonuç akar.
    freeze=False: bilinçli yeniden-üretim/replay — tam yeniden-yazım."""
    d = date.fromisoformat(payload["date"])
    gun = _get_or_create_gun(db, d)
    if now_tr is None:
        now_tr = _now_tr()
    if hasattr(gun, "daily_panel"):
        gun.daily_panel = payload.get("daily_panel")
        if hasattr(gun, "surpriz_radar"):
            gun.surpriz_radar = payload.get("surpriz_radar")
    n_alt = 0
    for hp in payload.get("hipodromlar", []):
        old = db.query(GunHipodrom).filter_by(gun_id=gun.id, hipodrom=hp["hipodrom"]).one_or_none()
        if old is None or not freeze:
            if old is not None:
                db.delete(old)
                db.flush()
            n_alt += _write_hip_full(db, gun.id, hp)
            # Yeni eklenen GH'nin surdirekini yaz
            gh = db.query(GunHipodrom).filter_by(gun_id=gun.id, hipodrom=hp["hipodrom"]).one_or_none()
        else:
            n_alt += _merge_hip_frozen(db, old, hp, d, now_tr)
            gh = old
        if gh is not None:
            sd = _load_meta_surdirek(d, hp["hipodrom"])
            if sd:
                _upsert_surdirek(db, gh, sd)
    return n_alt


def import_file(db, path: str, freeze: bool = True) -> int:
    payload = json.load(open(path, encoding="utf-8"))
    return import_payload(db, payload, freeze=freeze)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ensure_schema()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    if "--all" in flags or not args:
        files = sorted(glob.glob(str(OUT_DIR / "*.json")))
    else:
        from datetime import datetime as _dt
        start = _dt.strptime(args[0], "%Y-%m-%d")
        end = _dt.strptime(args[1], "%Y-%m-%d") if len(args) > 1 else start
        files = []
        cur = start
        while cur <= end:
            p = OUT_DIR / f"{cur.strftime('%Y-%m-%d')}.json"
            if p.exists():
                files.append(str(p))
            cur += timedelta(days=1)

    db = SessionLocal()
    total_alt = 0
    try:
        for fp in files:
            n = import_file(db, fp, freeze=False)
            total_alt += n
            db.commit()
            print(f"import: {os.path.basename(fp)}  ({n} altılı)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"\nTamamlandı. {len(files)} gün, {total_alt} altılı -> {engine.url}")


if __name__ == "__main__":
    main()
