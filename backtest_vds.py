# -*- coding: utf-8 -*-
import sys, io, json, os
from contextlib import redirect_stdout
sys.path.insert(0, "/opt/harbi_ganyan_v3")
sys.path.insert(0, "/opt/harbi_ganyan_v3/src")
os.chdir("/opt/harbi_ganyan_v3")

def _s(fn, *a, **kw):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)

from datetime import date, timedelta
from harbi_v3.predictor import predict_for_date
from harbi_v3.paths import META_DIR, TAHMINLER_DIR, ensure_dirs
from scripts.tahmin import format_hip_file, build_meta, _file_stem
from v3_export import build_day_payload, export_day

start = date(2026,6,1)
end = date(2026,6,16)
ensure_dirs()

current = start
while current <= end:
    print("=" * 40)
    print(f"  {current:%d.%m.%Y}")
    print("=" * 40)
    try:
        all_races = _s(predict_for_date, current)
        if not all_races:
            print("  Tahmin uretilemedi")
            current += timedelta(days=1)
            continue

        payload = _s(build_day_payload, current, refresh=False)
        altili_by_hip = {}
        birim_by_hip = {}
        if payload:
            for hp_data in payload.get("hipodromlar", []):
                altili_by_hip[hp_data["hipodrom"]] = hp_data.get("altililar", [])
                birim_by_hip[hp_data["hipodrom"]] = hp_data.get("birim", 1.25)

        hip_map = {}
        for race in all_races:
            hip_map.setdefault(race.hip, []).append(race)

        for hip, races in sorted(hip_map.items()):
            stem = _file_stem(current, hip)
            txt_path = TAHMINLER_DIR / f"{stem}.txt"
            altililar = altili_by_hip.get(hip, [])
            birim = birim_by_hip.get(hip, 1.25)
            content = format_hip_file(current, hip, races, altililar=altililar, birim=birim)
            txt_path.write_text(content, encoding="utf-8")
            meta = build_meta(current, hip, races)
            (META_DIR / f"{stem}_meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            _s(export_day, current, city=hip)
            print(f"    {txt_path.name} ({len(races)} kosu)")

        if len(hip_map) > 1:
            _s(export_day, current)

    except Exception as e:
        import traceback
        print(f"  HATA: {e}")
        traceback.print_exc()

    current += timedelta(days=1)

print("\nBACKTEST TAMAMLANDI")
