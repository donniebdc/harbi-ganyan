# -*- coding: utf-8 -*-
"""Koşu Analizleri (alt oyunlar / alt tahminler) → okunabilir TXT.

Alt oyunlar motorun ana TXT çıktısında YOKTUR; bültenin 'bets' alanından
export aşamasında (build_day_json.build_day) hesaplanır. Bu modül o payload'u
in-memory üretir ve `TahminSonuçları/<iso>_alt_tahmin.txt` olarak yazar — yani
ana `TahminSonuçları/<iso>.txt` dosyasının tam yanına.

ganyan_master.py ve toplu_tahmin.py, tahmin ürettikten sonra bu modülü çağırır.

CLI:
    python alt_tahmin_yaz.py 2026-06-03              # tek gün
    python alt_tahmin_yaz.py 2026-05-01 2026-05-30   # aralık
Çıktı: TahminSonuçları/<iso>_alt_tahmin.txt
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_day_json as bdj  # noqa: E402
from altili_lib import BASE  # noqa: E402

TAHMIN_SONUC_DIR = Path(BASE) / "TahminSonuçları"


# ── Biçimleme ──────────────────────────────────────────────────────────────
def _tl(x) -> str:
    try:
        return f"{float(x):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return "-"


def _kolon_str(kolonlar, legs, aile) -> list[str]:
    """Her kolon/ayak için 'etiket: a / b / c' satırları."""
    out = []
    tek_kolon = len(kolonlar) <= 1
    for i, nos in enumerate(kolonlar):
        if aile == "ayak":
            et = f"{legs[i]}. koşu" if i < len(legs) else f"ayak {i+1}"
        elif tek_kolon:
            et = "seçim"
        else:
            et = f"{i+1}. kolon"
        out.append(f"{et:>9}: " + " / ".join(str(n) for n in nos))
    return out


def _sonuc_satir(sonuc: dict | None) -> list[str]:
    """sonuc bloğu → ANALİZ BAŞARILI/BAŞARISIZ + İKRAMİYE/KAZANÇ satırları."""
    if not sonuc:
        return ["        (sonuç bekleniyor)"]
    if sonuc.get("tuttu"):
        out = ["        ✔ ANALİZ BAŞARILI"]
        ik = sonuc.get("ikramiye")
        if ik is not None:
            out.append(f"        İKRAMİYE: {_tl(ik)} TL")
        net = sonuc.get("net")
        if net is not None:
            out.append(f"        KAZANÇ : {_tl(net)} TL")
        return out
    out = ["        ✘ ANALİZ BAŞARISIZ"]
    ik = sonuc.get("ikramiye")
    if ik is not None:
        out.append(f"        İKRAMİYE (resmi): {_tl(ik)} TL")
    return out


def format_payload(d: dict, iso: str) -> str:
    """build_day payload'unu (veya out/<iso>.json) okunabilir metne çevirir."""
    satir = [f"KOŞU ANALİZLERİ (ALT OYUNLAR) — {iso}", "=" * 60, ""]
    toplam = 0
    bos = True
    for h in d.get("hipodromlar", []):
        bahisler = h.get("bahisler", [])
        if not bahisler:
            continue
        bos = False
        satir.append(f"### {h['hipodrom']}  ({len(bahisler)} alt oyun)")
        satir.append("")
        gruplar: dict[int, list] = {}
        for b in bahisler:
            gruplar.setdefault(b["bas_kosu"], []).append(b)
        for kno in sorted(gruplar):
            satir.append(f"  -- {kno}. Koşu --")
            for b in gruplar[kno]:
                toplam += 1
                yer = (f" (koşu {b['legs'][0]}-{b['legs'][-1]})"
                       if b.get("aile") == "ayak" and len(b.get("legs", [])) > 1 else "")
                satir.append(f"    • {b['ad']}{yer}")
                for kl in _kolon_str(b["kolonlar"], b.get("legs", []), b.get("aile", "tek")):
                    satir.append(f"        {kl}")
                tutar = b["kupon_bedeli"] * b["misli"]
                satir.append(f"        {b['kombinasyon']} kombinasyon × "
                             f"{b['misli']} misli = {_tl(tutar)} TL "
                             f"(birim {_tl(b['birim'])}, maks {b['max_butce']} TL)")
                satir.extend(_sonuc_satir(b.get("sonuc")))
            satir.append("")
        satir.append("")
    if bos:
        satir.append("(Bu güne ait alt oyun bulunamadı — bülten 'bets' alanı boş "
                     "ya da o gün için tahmin üretilmemiş.)")
    satir.append(f"TOPLAM: {toplam} alt oyun")
    return "\n".join(satir)


# ── Yazıcı ─────────────────────────────────────────────────────────────────
def yaz_alt_tahmin(iso: str, ctx: dict | None = None,
                   out_dir: Path | None = None) -> Path | None:
    """Bir gün için TahminSonuçları/<iso>_alt_tahmin.txt üretir.

    ctx verilmezse build_day_json.load_context() ile yüklenir (aralıkta bir kez
    yükleyip tekrar tekrar geçmek için ctx'i dışarıdan ver).
    Döner: yazılan dosya yolu (alt oyun yoksa yine de boş-bilgi dosyası yazar).
    """
    if ctx is None:
        ctx = bdj.load_context()
    out_dir = out_dir or TAHMIN_SONUC_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = bdj.build_day(iso, ctx)
    metin = format_payload(payload, iso)
    hedef = out_dir / f"{iso}_alt_tahmin.txt"
    hedef.write_text(metin, encoding="utf-8")
    return hedef


def yaz_aralik(bas_iso: str, bit_iso: str | None = None) -> list[Path]:
    """Tarih aralığı için alt_tahmin dosyalarını üretir (ctx bir kez yüklenir)."""
    bas = datetime.strptime(bas_iso, "%Y-%m-%d")
    bit = datetime.strptime(bit_iso, "%Y-%m-%d") if bit_iso else bas
    ctx = bdj.load_context()
    yazilan = []
    cur = bas
    while cur <= bit:
        iso = cur.strftime("%Y-%m-%d")
        p = yaz_alt_tahmin(iso, ctx)
        if p:
            yazilan.append(p)
        cur += timedelta(days=1)
    return yazilan


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return
    bas = sys.argv[1]
    bit = sys.argv[2] if len(sys.argv) > 2 else None
    for p in yaz_aralik(bas, bit):
        print(f"yazıldı: {p}")


if __name__ == "__main__":
    main()
