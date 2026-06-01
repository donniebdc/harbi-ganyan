# -*- coding: utf-8 -*-
"""
SONUÇ TXT ÜRETİCİ — `Sonuclar JSON` -> `Sonuçlar Txt` (okunabilir blok şablon)
================================================================================
Her günün JSON sonucunu, altılı ganyan blokları halinde okunabilir bir TXT
şablona çevirir (kullanıcı ŞABLON ÖRNEKLEM). Her altılı için:
  - 6 ayağın kazananı + o koşunun ganyan/ikili/sıralı ikili/çifte/üçlü ödemeleri,
  - "ALTILI GANYAN (Sonuçlar) : w1/.../w6  İKRAMİYE BEDELİ : ... TL",
  - varsa 5'Lİ/4'LÜ/3'LÜ/7'Lİ GANYAN, TABELA gibi büyük kombine ikramiyeler.

Kullanım:
    python sonuc_txt_uret.py                    # tüm Sonuclar JSON günleri
    python sonuc_txt_uret.py 2026-02-08          # tek gün
    python sonuc_txt_uret.py 2026-02-01 2026-02-28
"""
from __future__ import annotations
import os, sys, glob, json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from altili_lib import BASE

JSON_DIR = os.path.join(BASE, "Sonuclar JSON")
OUT_DIR = os.path.join(BASE, "Sonuçlar Txt")
CIZGI = "═" * 78

# Altılı özetinde (büyük kombine) gösterilecek bahisler; ayak satırında gösterilmez.
BIG = ["6'LI GANYAN", "5'Lİ GANYAN", "4'LÜ GANYAN", "7'Lİ GANYAN",
       "7'Lİ PLASE", "SIRALI 5", "TABELA"]
LABEL = {"SIRALI İKİLİ": "S. İKİLİ"}


def is_big(tip: str) -> bool:
    return any(s in tip for s in BIG)


def fmt_tutar(t) -> str:
    if t is None:
        return "?"
    return f"{t:.2f}".replace(".", ",")


def fmt_kalem(b: dict) -> str:
    tip = b.get("tip", ""); kombo = b.get("kombinasyon", ""); t = fmt_tutar(b.get("tutar"))
    if tip == "GANYAN":
        return f"GANYAN : {t} TL"
    return f"{LABEL.get(tip, tip)} : {kombo} - {t} TL"


def _altililar(kosular: dict):
    """JSON kosular'dan altılı tanımlarını (6'LI GANYAN'a göre) çıkarır."""
    out = []
    for kno_s, kv in kosular.items():
        try:
            kno = int(kno_s)
        except ValueError:
            continue
        for b in (kv.get("bahisler") or {}).get("kalemler") or []:
            if "6'LI GANYAN" in b.get("tip", ""):
                import re
                mi = re.match(r"\s*(\d+)\s*\.", b["tip"])
                idx = int(mi.group(1)) if mi else len(out) + 1
                out.append({"idx": idx, "last": kno,
                            "legs": list(range(kno - 5, kno + 1)),
                            "odeme": b.get("tutar")})
    out.sort(key=lambda a: a["last"])
    return out


def render_hip(hip_key: str, hd: dict, tarih_disp: str) -> list[str]:
    kosular = hd.get("kosular") or {}
    altililar = _altililar(kosular)
    if not altililar:
        return []
    L = [CIZGI, f"🎰 {hip_key} — ALTILI GANYAN SONUÇLARI | {tarih_disp}", CIZGI, ""]
    for alt in altililar:
        legs = alt["legs"]
        L.append(f"🎲 {alt['idx']}. ALTILI GANYAN (Koşular {legs[0]}-{legs[-1]}) 🎲")
        L.append("")
        L.append(CIZGI)
        L.append("")
        winners = []
        eksik = False
        for ai, kno in enumerate(legs, 1):
            kv = kosular.get(str(kno))
            if not kv:
                L.append(f"    Koşu {kno:>2} | {ai}. Ayak | (sonuç yok)")
                winners.append("?"); eksik = True; continue
            wno = kv.get("kazanan")
            wname = next((s.get("at", "") for s in kv.get("siralama", []) if s.get("sira") == 1), "")
            winners.append(str(wno) if wno else "?")
            small = [fmt_kalem(b) for b in (kv.get("bahisler") or {}).get("kalemler") or []
                     if not is_big(b.get("tip", ""))]
            L.append(f"    Koşu {kno:>2} | {ai}. Ayak | {wno} - {wname} | " + " | ".join(small))
        L.append("")
        L.append(f"🎲 {alt['idx']}. ALTILI GANYAN (Sonuçlar) : {'/'.join(winners)}"
                 f"\tİKRAMİYE BEDELİ : {fmt_tutar(alt['odeme'])} TL")
        # büyük kombine ikramiyeler (son ayak koşusundan, 6'LI hariç)
        son = kosular.get(str(alt["last"]), {})
        for b in (son.get("bahisler") or {}).get("kalemler") or []:
            tip = b.get("tip", "")
            if is_big(tip) and "6'LI GANYAN" not in tip:
                L.append(f"\t{tip} : {b.get('kombinasyon','')} - {fmt_tutar(b.get('tutar'))} TL")
        L.append("")
        L.append(CIZGI)
        L.append("")
    return L


def uret_gun(json_path: str) -> str | None:
    gun = json.load(open(json_path, encoding="utf-8"))
    tarih_iso = gun.get("tarih", "")
    try:
        tarih_disp = datetime.strptime(tarih_iso, "%Y-%m-%d").strftime("%d.%m.%Y")
    except ValueError:
        tarih_disp = tarih_iso
    bloklar = []
    for hip_key, hd in (gun.get("hipodromlar") or {}).items():
        bloklar += render_hip(hip_key, hd, tarih_disp)
    if not bloklar:
        return None
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"{tarih_iso}.txt")
    open(out_path, "w", encoding="utf-8").write("\n".join(bloklar).rstrip() + "\n")
    return out_path


def main():
    args = sys.argv[1:]
    files = sorted(glob.glob(os.path.join(JSON_DIR, "*.json")))
    if args:
        bas = args[0]; bit = args[1] if len(args) > 1 else bas
        files = [f for f in files if bas <= os.path.basename(f)[:-5] <= bit]
    yazilan = 0
    for f in files:
        p = uret_gun(f)
        if p:
            yazilan += 1
            print(f"yazıldı: {os.path.basename(p)}")
    print(f"\nTamamlandı. {yazilan} gün -> {OUT_DIR}")


if __name__ == "__main__":
    main()
