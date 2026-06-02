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


def _get_or_create_gun(db, d: date) -> Gun:
    g = db.query(Gun).filter_by(date=d).one_or_none()
    if g is None:
        g = Gun(date=d)
        db.add(g)
        db.flush()
    return g


def import_payload(db, payload: dict) -> int:
    """Bir günün payload'unu yazar; yazılan altılı sayısını döner."""
    d = date.fromisoformat(payload["date"])
    gun = _get_or_create_gun(db, d)
    n_alt = 0
    for hp in payload.get("hipodromlar", []):
        # idempotent: aynı (gün,hipodrom) varsa sil
        old = db.query(GunHipodrom).filter_by(gun_id=gun.id, hipodrom=hp["hipodrom"]).one_or_none()
        if old is not None:
            db.delete(old)
            db.flush()
        gh = GunHipodrom(gun_id=gun.id, hipodrom=hp["hipodrom"], birim=hp["birim"])
        db.add(gh)
        db.flush()

        for k in hp.get("kosular", []):
            kosu = Kosu(gh_id=gh.id, kno=k["kno"], pist=k.get("pist", ""),
                        mesafe=str(k.get("mesafe", "")), saat=k.get("saat", ""),
                        n_at=k.get("n_at"), race_type=k.get("race_type", ""),
                        race_subtype=k.get("race_subtype", ""))
            db.add(kosu)
            db.flush()
            for i, b in enumerate(k.get("bes", [])):
                db.add(KosuBes(kosu_id=kosu.id, sira=i, slot=b["slot"], at_no=b["at_no"],
                               at=b.get("at", ""), ana=b.get("ana", 0.0)))
            s = k.get("sonuc")
            if s:
                db.add(KosuSonuc(kosu_id=kosu.id, kazanan=s.get("kazanan"),
                                 kazanan_ad=s.get("kazanan_ad", "") or "",
                                 ganyan=s.get("ganyan"), bes_hit=s.get("bes_hit")))

        for a in hp.get("altililar", []):
            alt = Altili(gh_id=gh.id, idx=a["idx"], legs=a["legs"])
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
            s = a.get("sonuc")
            if s:
                db.add(AltiliSonuc(altili_id=alt.id, winners=s["winners"],
                                   ikramiye=s.get("ikramiye"), tier_hits=s["tier_hits"]))
            n_alt += 1

        # --- Koşu Analizleri (alt-bahisler) ---
        for b in hp.get("bahisler", []):
            s = b.get("sonuc") or {}
            db.add(KosuBahis(
                gh_id=gh.id, bas_kosu=b["bas_kosu"], tip=b["tip"], aile=b["aile"],
                ad=b["ad"], legs=b["legs"], kolonlar=b["kolonlar"],
                secim_atlar=b["secim_atlar"], kombinasyon=b["kombinasyon"],
                birim=b["birim"], kupon_bedeli=b["kupon_bedeli"], misli=b["misli"],
                max_butce=b["max_butce"],
                tuttu=s.get("tuttu"), ganyan=s.get("ganyan"),
                net=s.get("net"), kazanan=s.get("kazanan")))
    return n_alt


def import_file(db, path: str) -> int:
    payload = json.load(open(path, encoding="utf-8"))
    return import_payload(db, payload)


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
            n = import_file(db, fp)
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
