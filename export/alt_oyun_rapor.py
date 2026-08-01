# -*- coding: utf-8 -*-
"""out/<date>.json içindeki alt oyunları okunabilir TXT'ye döker.

Biçimleme tek merkezden gelir: alt_tahmin_yaz.format_payload (drift olmasın diye).
Bu script export edilmiş JSON'dan (out/<date>.json) çalışır; canlı üretim için
alt_tahmin_yaz.py kullan (o build_day ile in-memory üretir).

Kullanım:
  python build_day_json.py 2026-06-03     # önce export (out/<date>.json)
  python alt_oyun_rapor.py 2026-06-03      # sonra okunabilir TXT
Çıktı: out/<date>_alt_oyunlar.txt
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from alt_tahmin_yaz import format_payload  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"


def rapor(iso: str) -> str:
    f = OUT / f"{iso}.json"
    if not f.exists():
        return (f"[!] {f} yok. Önce export et:\n"
                f"    python build_day_json.py {iso}")
    d = json.loads(f.read_text(encoding="utf-8"))
    return format_payload(d, iso)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return
    iso = sys.argv[1]
    metin = rapor(iso)
    out = OUT / f"{iso}_alt_oyunlar.txt"
    out.write_text(metin, encoding="utf-8")
    print(metin[:1500])
    print(f"\n... yazıldı: {out}")


if __name__ == "__main__":
    main()
