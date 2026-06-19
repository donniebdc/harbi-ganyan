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

OUT_DIR = BACKEND_DIR / "export" / "out"


def ensure_schema():
    Base.metadata.create_all(engine)
    _ensure_columns()


def _ensure_columns():
    """create_all mevcut tabloya sütun EKLEMEZ; yeni sütunları idempotent ALTER ile ekle.
    Postgres + SQLite uyumlu (inspector ile var/yok kontrolü)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    # (tablo, sütun, SQL tip) — yeni eklenen nullable sütunlar
    eklenecek = [
        ("gun", "son_analiz", "TIMESTAMP"),
        ("gun", "son_analiz_sebep", "VARCHAR(200)"),
        ("kosu", "ktip", "VARCHAR(40)"),          # koşu tipi (görünüm)
        ("kosu_bes", "jokey", "VARCHAR(40)"),     # kısa jokey adı
        ("kosu_bes", "apranti", "BOOLEAN"),       # apranti bayrağı
    ]
    for tablo, sutun, tip in eklenecek:
        try:
            mevcut = {c["name"] for c in insp.get_columns(tablo)}
        except Exception:
            continue  # tablo henüz yok (create_all yarattı sayılır)
        if sutun in mevcut:
            continue
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE {tablo} ADD COLUMN {sutun} {tip}'))
        print(f"[schema] {tablo}.{sutun} sütunu eklendi.")


def _get_or_create_gun(db, d: date) -> Gun:
    g = db.query(Gun).filter_by(date=d).one_or_none()
    if g is None:
        g = Gun(date=d)
        db.add(g)
        db.flush()
    return g


# ── Canlı dondurma eşikleri (look-ahead'i ve geçmiş koşu yeniden-üretimini engeller) ──
#   Bir koşu BAŞLADIKTAN sonra hiçbir yeniden-üretim onun ANALİZİNİ değiştiremez;
#   yalnız SONUÇ alanları (kazanan/ganyan/ikramiye/tuttu/net) güncellenir.
#   - Şehir ilk koşusu −30 dk: o şehrin 5-satır + altılı analizi DONAR (gün-seviyesi kilit).
#   - Her koşu −5 dk: o koşunun alt-bahis (Koşu Analizleri) analizi DONAR.
LOCK_5SAT_DK = 30
LOCK_ALT_DK = 5


def _now_tr() -> datetime:
    return datetime.utcnow() + timedelta(hours=3)  # VPS UTC -> TR (UTC+3, DST yok)


def _saat_dt(d: date, saat: str):
    """'14:30' + gün -> datetime; geçersizse None."""
    try:
        hh, mm = (saat or "").strip().split(":")[:2]
        return datetime(d.year, d.month, d.day, int(hh), int(mm))
    except Exception:
        return None


# ---- kayıt ekleyiciler (tam yazım + birleştirmede ortak) ----

def _add_kosu(db, gh_id: int, k: dict):
    kosu = Kosu(gh_id=gh_id, kno=k["kno"], pist=k.get("pist", ""),
                mesafe=str(k.get("mesafe", "")), saat=k.get("saat", ""),
                n_at=k.get("n_at"), race_type=k.get("race_type", ""),
                race_subtype=k.get("race_subtype", ""), ktip=k.get("ktip", ""),
                analiz_puanlari=k.get("analiz_puanlari") or None)
    db.add(kosu)
    db.flush()
    for i, b in enumerate(k.get("bes", [])):
        db.add(KosuBes(kosu_id=kosu.id, sira=i, slot=b["slot"], at_no=b["at_no"],
                       at=b.get("at", ""), ana=b.get("ana", 0.0),
                       jokey=b.get("jokey", ""), apranti=bool(b.get("apranti"))))
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
        ganyan=s.get("ikramiye"),  # ganyan kolonu = resmi ikramiye (kayıpta da)
        net=s.get("net"),
        kazanan=({"kombo": s.get("kazanan"), "adlar": s.get("adlar") or {}}
                 if b.get("sonuc") else None)))


def _bahis_sonuc_guncelle(row: KosuBahis, pb: dict):
    """DONMUŞ bir alt-bahis satırının yalnız SONUÇ alanlarını günceller (analiz dokunulmaz)."""
    if pb.get("sonuc") is None:
        return  # koşu henüz sonuçlanmadı -> dokunma
    s = pb.get("sonuc") or {}
    row.tuttu = s.get("tuttu")
    row.ganyan = s.get("ikramiye")
    row.net = s.get("net")
    row.kazanan = {"kombo": s.get("kazanan"), "adlar": s.get("adlar") or {}}


def _write_hip_full(db, gun_id: int, hp: dict) -> int:
    """Bir hipodromu sıfırdan yazar (tam yeniden-yazım). Döner: altılı sayısı."""
    gh = GunHipodrom(gun_id=gun_id, hipodrom=hp["hipodrom"], birim=hp["birim"])
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
    Döner: altılı sayısı."""
    race_dt = {}
    for k in hp.get("kosular", []):
        rt = _saat_dt(d, k.get("saat"))
        if rt is not None:
            race_dt[k["kno"]] = rt
    R_H = min(race_dt.values()) if race_dt else None
    hip_locked = R_H is not None and now_tr >= R_H - timedelta(minutes=LOCK_5SAT_DK)

    # --- Koşular (5-satır) ---
    mevcut_kosu = {k.kno: k for k in gh.kosular}
    for k in hp.get("kosular", []):
        ek = mevcut_kosu.get(k["kno"])
        if ek is None:
            _add_kosu(db, gh.id, k)
            continue
        if not hip_locked:
            # 5-satır henüz kilitlenmedi: bes + meta tazelenebilir
            for b in list(ek.bes):
                db.delete(b)
            db.flush()
            ek.pist = k.get("pist", ""); ek.mesafe = str(k.get("mesafe", ""))
            ek.saat = k.get("saat", ""); ek.n_at = k.get("n_at")
            ek.race_type = k.get("race_type", ""); ek.race_subtype = k.get("race_subtype", "")
            ek.ktip = k.get("ktip", "")
            ek.analiz_puanlari = k.get("analiz_puanlari") or None
            for i, b in enumerate(k.get("bes", [])):
                db.add(KosuBes(kosu_id=ek.id, sira=i, slot=b["slot"], at_no=b["at_no"],
                               at=b.get("at", ""), ana=b.get("ana", 0.0),
                               jokey=b.get("jokey", ""), apranti=bool(b.get("apranti"))))
        # sonuç her durumda güncellenir (kilitli koşuda da: yalnız sonuç akar)
        _set_kosu_sonuc(db, ek, k.get("sonuc"))

    # --- Altılılar (hip kilidine bağlı; gün-seviyesi) ---
    if hip_locked and gh.altililar:
        mevcut_alt = {a.idx: a for a in gh.altililar}
        for a in hp.get("altililar", []):
            ea = mevcut_alt.get(a["idx"])
            if ea is None:
                _add_altili(db, gh.id, a)
            else:
                _set_altili_sonuc(db, ea, a.get("sonuc"))
    else:
        for a in list(gh.altililar):
            db.delete(a)
        db.flush()
        for a in hp.get("altililar", []):
            _add_altili(db, gh.id, a)
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
            # analiz DONUK: yalnız sonuç alanlarını güncelle (tip eşleşmesiyle)
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


def import_payload(db, payload: dict, freeze: bool = True, now_tr: datetime | None = None) -> int:
    """Bir günün payload'unu yazar; yazılan altılı sayısını döner.

    freeze=True (varsayılan, CANLI-GÜVENLİ): mevcut bir (gün,hipodrom) için zaman-bazlı
      dondurma uygulanır — başlamış/kilitli koşuların ANALİZİ korunur, yalnız sonuç akar.
      Böylece gün-içi yeniden-üretim (canlı takip) geçmiş/biten koşulara DOKUNAMAZ
      (look-ahead engeli). Sonuç-tazeleme akışı (run_live/run_results) için de doğru
      davranıştır: analiz sabit kalır, sadece sonuçlar güncellenir.
    freeze=False: bilinçli yeniden-üretim/replay (manuel --uret / --export-only) — tam
      yeniden-yazım (mevcut (gün,hipodrom) silinip yeniden yazılır).
    """
    d = date.fromisoformat(payload["date"])
    gun = _get_or_create_gun(db, d)
    if now_tr is None:
        now_tr = _now_tr()
    n_alt = 0
    for hp in payload.get("hipodromlar", []):
        old = db.query(GunHipodrom).filter_by(gun_id=gun.id, hipodrom=hp["hipodrom"]).one_or_none()
        if old is None or not freeze:
            # tam yeniden-yazım (yeni hipodrom veya bilinçli replay)
            if old is not None:
                db.delete(old)
                db.flush()
            n_alt += _write_hip_full(db, gun.id, hp)
        else:
            n_alt += _merge_hip_frozen(db, old, hp, d, now_tr)
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
        start = datetime.strptime(args[0], "%Y-%m-%d")
        end = datetime.strptime(args[1], "%Y-%m-%d") if len(args) > 1 else start
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
            # Manuel CLI import = bilinçli replay -> tam yeniden-yazım.
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
