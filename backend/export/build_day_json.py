# -*- coding: utf-8 -*-
"""
Harbi Ganyan — Gün → Yapısal JSON Export
========================================
Mevcut tahmin motorunu (motor/) YENİDEN KULLANIR; TXT'yi yeniden parse etmez.
Bir gün için 5-satır tahminleri + 3 kademe iç-içe 6'lı kuponları + (varsa) sonuçları
yapısal JSON'a çevirir. Bu JSON, importer ile PostgreSQL'e yazılır ve FastAPI tarafından
"Günün Analizleri" / "Geçmiş Analizler" uçlarında servis edilir.

Üretim motorunu DEĞİŞTİRMEZ — yalnız çağırır.

Kullanım:
    python backend/export/build_day_json.py 2026-05-15            # tek gün, stdout
    python backend/export/build_day_json.py 2026-05-01 2026-05-30 # aralık, dosyalara
    python backend/export/build_day_json.py 2026-05-15 --verify   # TXT ile çapraz doğrula
"""
from __future__ import annotations

import os
import re
import sys
import json
import glob
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(os.environ.get("HG_ENGINE_ROOT") or Path(__file__).resolve().parents[2])
MOTOR = REPO_ROOT / "motor"
sys.path.insert(0, str(MOTOR))

# Mevcut motor fonksiyonları (değiştirilmez)
from altili_lib import BASE, norm_hip, birim_fiyat, load_results, winning_set  # noqa: E402
from altili_kupon_v2 import build_nested_tiers, KUPON_TIERS, load_cal  # noqa: E402
from kupon_kacan_analiz import derive_altililar, leg_from_race, _parse_one  # noqa: E402
from tahmin_sonuc_karsilastir import _raw_gun  # noqa: E402

# Koşu Analizleri (alt-bahis) üretimi + grading — backend/export içinde
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bahis_uretim as bahis  # noqa: E402

ANALIZ = os.path.join(BASE, "Harbi_Ganyan_Analiz")
EXPORT_DIR = Path(__file__).resolve().parent / "out"
SLOT_LABELS = ["FAV", "SUR", "YAZ", "BOM", "HAR"]
TIER_KEYS = {"Simitçi 6'lısı": "simitci", "Harbi Ganyan 6'lısı": "harbi", "Ortaklı 6'lı": "ortakli"}


def iso_to_dirname(iso: str) -> str:
    """2026-05-15 -> 15-05-2026 (Harbi_Ganyan_Analiz klasör adı)."""
    y, m, d = iso.split("-")
    return f"{d}-{m}-{y}"


def parse_day_races(iso: str):
    """O güne ait *_Tahminler.txt -> races[(iso,hip,kno)] + meta[(hip,kno)]={pist,mesafe,saat}."""
    races = {}
    meta = {}
    date_dir = os.path.join(ANALIZ, iso_to_dirname(iso))
    if not os.path.isdir(date_dir):
        return races, meta
    for path in glob.glob(os.path.join(date_dir, "*_Tahminler.txt")):
        _parse_one(path, races)  # motor parse (atlar, bes_nos, race_type...)
        # KO satırından pist/mesafe/saat (motor parse bunları atıyor) — ek geçiş
        for raw in open(path, encoding="utf-8", errors="replace").read().split("\n"):
            if not raw.startswith("KO:"):
                continue
            p = raw[3:].split("|")
            if len(p) < 7:
                continue
            try:
                kno = int(p[0])
            except ValueError:
                continue
            hip = norm_hip(p[1])
            meta[(hip, kno)] = {
                "pist": (p[5] if len(p) > 5 else "").strip(),
                "mesafe": (p[6] if len(p) > 6 else "").strip(),
                "saat": (p[7] if len(p) > 7 else "").strip(),
                "kaynak": (p[8] if len(p) > 8 else "").strip(),
                "bets": (p[9] if len(p) > 9 else "").strip(),  # Koşu Analizleri
            }
    # yalnız bu güne ait kayıtlar (parse_one iso'yu KO date'inden alır; teyit)
    races = {k: v for k, v in races.items() if k[0] == iso}
    return races, meta


def _ganyan_map(raw_gun, hip_disp):
    """Sonuç JSON'undan koşu->ganyan ödemesi {kno:int -> ganyan:float}."""
    out = {}
    hd = (raw_gun.get("hipodromlar") or {}).get(hip_disp) or {}
    for kno_s, kv in (hd.get("kosular") or {}).items():
        for b in (kv.get("bahisler") or {}).get("kalemler") or []:
            if b.get("tip", "").strip().upper() == "GANYAN":
                try:
                    out[int(kno_s)] = b.get("tutar")
                except (ValueError, TypeError):
                    pass
    return out


def _ikramiye_for_last(raw_gun, hip_disp, last_kno):
    """Altılının son ayağındaki '6'LI GANYAN' ikramiye bedeli."""
    hd = (raw_gun.get("hipodromlar") or {}).get(hip_disp) or {}
    kv = (hd.get("kosular") or {}).get(str(last_kno)) or {}
    for b in (kv.get("bahisler") or {}).get("kalemler") or []:
        if "6'LI GANYAN" in b.get("tip", ""):
            return b.get("tutar")
    return None


def _kalemler_map(raw_gun, hip_disp):
    """Sonuç JSON'undan {kno:int -> kalemler[list]} (resmi bahis ödemeleri)."""
    out = {}
    hd = (raw_gun.get("hipodromlar") or {}).get(hip_disp) or {}
    for kno_s, kv in (hd.get("kosular") or {}).items():
        try:
            kno = int(kno_s)
        except (ValueError, TypeError):
            continue
        out[kno] = (kv.get("bahisler") or {}).get("kalemler") or []
    return out


def _bahis_sonuc(g: dict, idx: dict, no2ad: dict | None = None) -> dict | None:
    """grade() çıktısını payload 'sonuc' formatına çevirir.
    no2ad verilirse (yalnız PLASE) kazanan at_no -> ad eşlemesi 'adlar'a yazılır."""
    r = bahis.grade(g, idx)
    if r is None:
        return None
    kombo = r.get("kazanan_kombo") or []
    adlar = {}
    if no2ad:
        for col in kombo:
            for no in col:
                ad = no2ad.get(no)
                if ad:
                    adlar[str(no)] = ad
    return {"tuttu": r["tuttu"], "ikramiye": r.get("ikramiye"), "net": r["net"],
            "kazanan": kombo, "adlar": adlar}


def build_bahisler(iso, hip, knos, races, meta, kalemler_by_kno, finished):
    """Bir hipodromun Koşu Analizleri bloğu (tek-koşu + çok-ayak bahisleri).
    Döner: [bet payload...] (bas_kosu'ya göre sıralı)."""
    out = []
    knoset = set(knos)
    # ANA sıralı at listesi sağlayıcı (race atlar zaten ana-desc sıralı)
    def atlar_of(kno):
        r = races.get((iso, hip, kno))
        if not r or not r.get("atlar"):
            return None
        return [{"at_no": a["at_no"], "at": a.get("at", ""), "ana": a.get("ana", 0)}
                for a in r["atlar"]]

    for kno in sorted(knos):
        m = meta.get((hip, kno), {})
        bets_str = m.get("bets", "")
        if not bets_str:
            continue
        atlar = atlar_of(kno)
        # --- Tek-koşu bahisleri ---
        for code in bahis.tek_kosu_bahisleri(bets_str):
            if not atlar:
                continue
            g = bahis.uret_tek(code, atlar)
            if not g:
                continue
            sonuc = None
            if kno in finished:
                # PLASE kazanan atın adı gösterilir; diğer tek bahisler yalnız no.
                no2ad = ({a["at_no"]: a["at"] for a in atlar}
                         if code == "PLASE" else None)
                sonuc = _bahis_sonuc(g, bahis.kalemler_index(kalemler_by_kno.get(kno, [])),
                                     no2ad)
            out.append({
                "tip": g["tip"], "ad": g["ad"], "aile": "tek", "bas_kosu": kno,
                "legs": [kno], "kolonlar": g["kolonlar"], "secim_atlar": g["secim_atlar"],
                "kombinasyon": g["kombinasyon"], "birim": g["birim"],
                "kupon_bedeli": g["kupon_bedeli"], "misli": g["misli"],
                "max_butce": g["max_butce"], "sonuc": sonuc,
            })
        # --- Çok-ayak bahisleri (bu koşuda başlayan) ---
        for code in bahis.ayak_baslangic(bets_str):
            L = bahis.AYAK_UZUNLUK[code]
            legs_kno = list(range(kno, kno + L))
            if any(k not in knoset for k in legs_kno):
                continue  # ayaklar günde tam değil
            legs_atlar = [atlar_of(k) for k in legs_kno]
            if any(la is None for la in legs_atlar):
                continue
            g = bahis.uret_ayak(code, legs_atlar)
            if not g:
                continue
            last = legs_kno[-1]
            sonuc = None
            if all(k in finished for k in legs_kno):
                sonuc = _bahis_sonuc(g, bahis.kalemler_index(kalemler_by_kno.get(last, [])))
            out.append({
                "tip": g["tip"], "ad": g["ad"], "aile": "ayak", "bas_kosu": kno,
                "legs": legs_kno, "kolonlar": g["kolonlar"], "secim_atlar": g["secim_atlar"],
                "kombinasyon": g["kombinasyon"], "birim": g["birim"],
                "kupon_bedeli": g["kupon_bedeli"], "misli": g["misli"],
                "max_butce": g["max_butce"], "sonuc": sonuc,
            })
    out.sort(key=lambda b: (b["bas_kosu"], bahis.BET_SIRA.index(b["tip"])
                            if b["tip"] in bahis.BET_SIRA else 99))
    return out


def _hip_disp_map(raw_gun):
    """norm_hip -> sonuç JSON'undaki görünen hipodrom anahtarı."""
    out = {}
    for k in (raw_gun.get("hipodromlar") or {}):
        out[norm_hip(k)] = k
    return out


def build_day(iso: str, ctx: dict) -> dict:
    """Bir günün tam yapısal payload'unu üretir."""
    races, meta = parse_day_races(iso)
    if not races:
        return {"date": iso, "hipodromlar": []}

    alt_map = ctx["alt_map"]
    results = ctx["results"]
    cal = ctx["cal"]
    raw_gun = _raw_gun(iso) or {}
    disp_map = _hip_disp_map(raw_gun)

    hips = sorted({k[1] for k in races})
    hip_payloads = []
    for hip in hips:
        hip_disp = disp_map.get(hip, hip)
        birim = birim_fiyat(hip)
        res = results.get((iso, hip))
        ganyan = _ganyan_map(raw_gun, hip_disp)
        finished = set(ganyan) | {
            int(s) for s in ((raw_gun.get("hipodromlar") or {}).get(hip_disp, {}).get("kosular") or {})
        }

        # --- Koşular (5-satır) ---
        kosu_list = []
        knos = sorted(k[2] for k in races if k[1] == hip)
        for kno in knos:
            r = races[(iso, hip, kno)]
            m = meta.get((hip, kno), {})
            no2 = {a["at_no"]: a for a in r["atlar"]}
            bes = []
            for i, no in enumerate(r.get("bes_nos") or []):
                if no is None:
                    continue
                a = no2.get(no, {})
                bes.append({"slot": SLOT_LABELS[i], "at_no": no,
                            "at": a.get("at", ""), "ana": round(a.get("ana", 0), 1)})
            kazanan = None
            if res:
                ws = winning_set(res, kno)
                kazanan = next((a["at_no"] for a in r["atlar"] if a["at_no"] in ws), None)
                if kazanan is None and ws:
                    kazanan = sorted(ws)[0]
            sonuc = None
            if kno in finished:
                bes_nos = {b["at_no"] for b in bes}
                kazanan_ad = no2.get(kazanan, {}).get("at", "") if kazanan is not None else ""
                sonuc = {
                    "kazanan": kazanan,
                    "kazanan_ad": kazanan_ad,
                    "ganyan": ganyan.get(kno),
                    "bes_hit": (kazanan in bes_nos) if kazanan is not None else None,
                }
            kosu_list.append({
                "kno": kno, "pist": m.get("pist", ""), "mesafe": m.get("mesafe", ""),
                "saat": m.get("saat", ""), "n_at": r.get("n_at"),
                "race_type": r.get("race_type", ""), "race_subtype": r.get("race_subtype", ""),
                "bes": bes, "sonuc": sonuc,
            })

        # --- Altılılar (3 kademe iç-içe kupon) ---
        alt_list = []
        for alt in alt_map.get((iso, hip), []):
            legs_kno = alt["legs"]
            legs = []
            ok = True
            for k in legs_kno:
                rr = races.get((iso, hip, k))
                if not rr or not rr["atlar"]:
                    ok = False
                    break
                legs.append(leg_from_race(rr))
            if not ok:
                continue
            kademeler = []
            tier_hits = {}
            for ad, lo, hi, plan, komb in build_nested_tiers(legs, KUPON_TIERS, birim, cal):
                ayaklar = []
                hits = 0
                fin = 0
                for p in plan:
                    sec = [a["at_no"] for a in p["secilen"]]
                    sec_atlar = [{"at_no": a["at_no"], "at": a.get("at", "")}
                                 for a in p["secilen"]]
                    is_fin = p["kno"] in finished
                    if is_fin and res:
                        fin += 1
                        if winning_set(res, p["kno"]) & set(sec):
                            hits += 1
                    ayaklar.append({"kno": p["kno"], "width": p.get("width", len(sec)),
                                    "banko_lider": bool(p.get("banko_lider")),
                                    "secilen": sec, "secilen_atlar": sec_atlar})
                key = TIER_KEYS.get(ad, ad)
                kademeler.append({"ad": ad, "key": key, "bedel": round(komb * birim, 2),
                                  "komb": komb, "ayaklar": ayaklar})
                tier_hits[key] = hits if fin == len(plan) else None
            last = legs_kno[-1]
            all_fin = all(k in finished for k in legs_kno)
            sonuc = None
            if all_fin and res:
                winners = [next((a["at_no"] for a in races[(iso, hip, k)]["atlar"]
                                 if a["at_no"] in winning_set(res, k)), None) for k in legs_kno]
                sonuc = {"winners": winners, "ikramiye": _ikramiye_for_last(raw_gun, hip_disp, last),
                         "tier_hits": tier_hits}
            alt_list.append({"idx": alt["idx"], "legs": legs_kno, "kademeler": kademeler,
                             "sonuc": sonuc})

        # --- Koşu Analizleri (alt-bahisler) ---
        kalemler_by_kno = _kalemler_map(raw_gun, hip_disp)
        bahisler = build_bahisler(iso, hip, knos, races, meta, kalemler_by_kno, finished)

        hip_payloads.append({"hipodrom": hip, "birim": birim,
                             "kosular": kosu_list, "altililar": alt_list,
                             "bahisler": bahisler})

    return {"date": iso, "hipodromlar": hip_payloads}


def load_context() -> dict:
    """Tüm arşivi bir kez tarayan bağlam (aralık export'unda tekrar tekrar taramamak için)."""
    return {"alt_map": derive_altililar(), "results": load_results(prefer="json"), "cal": load_cal()}


def _verify(iso: str, payload: dict):
    """Export edilen kademe 6/6 sayılarını TahminSonuçları TXT ile karşılaştır."""
    txt = os.path.join(BASE, "TahminSonuçları", f"{iso}.txt")
    if not os.path.exists(txt):
        print(f"[verify] {iso}: TXT yok, atlandı")
        return
    text = open(txt, encoding="utf-8", errors="replace").read()
    # İç-içe kural: "herhangi biri 6/6" == Ortaklı 6/6 == Ortaklı kademesi TUTTU
    txt_any6 = len(re.findall(r"Ortaklı 6'lı.*?TAHMİNİMİZ TUTTU", text))
    # export: herhangi biri 6/6 (Ortaklı 6 == nested herhangi)
    exp_any6 = 0
    for h in payload["hipodromlar"]:
        for a in h["altililar"]:
            s = a.get("sonuc")
            if s and max((v for v in s["tier_hits"].values() if v is not None), default=0) == 6:
                exp_any6 += 1
    print(f"[verify] {iso}: export herhangi-6/6={exp_any6} | TXT TUTTU-altılı≈{txt_any6}")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # Windows cp1254 konsolu için
    except Exception:
        pass
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return
    start = args[0]
    end = args[1] if len(args) > 1 else start
    ctx = load_context()
    cur = datetime.strptime(start, "%Y-%m-%d")
    last = datetime.strptime(end, "%Y-%m-%d")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    single = (start == end)
    while cur <= last:
        iso = cur.strftime("%Y-%m-%d")
        payload = build_day(iso, ctx)
        nhip = len(payload["hipodromlar"])
        nalt = sum(len(h["altililar"]) for h in payload["hipodromlar"])
        if single and "--stdout" in flags:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            out = EXPORT_DIR / f"{iso}.json"
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"yazıldı: {out.name}  ({nhip} hipodrom, {nalt} altılı)")
        if "--verify" in flags:
            _verify(iso, payload)
        cur += timedelta(days=1)


if __name__ == "__main__":
    main()
