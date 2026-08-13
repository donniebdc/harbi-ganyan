from __future__ import annotations

"""
tahmin.py  –  Belirli bir gun icin 5'li satir tahmini uretir.

Kullanim:
    python tahmin.py 2026-06-14
    python tahmin.py 2026-06-14 --hip bursa
    python tahmin.py  (bugun)

Cikti: D:\\Harbi Ganyan v3\\Tahminler\\YYYY-MM-DD_Sehir.txt
       D:\\Harbi Ganyan v3\\Tahminler\\YYYY-MM-DD_Sehir_meta.json
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.altili_coupons import select_top_n

from harbi_v3.collect_program import collect_program_day
from harbi_v3.dates import parse_date
from harbi_v3.features import FEATURE_NAMES
from harbi_v3.horse_cards import A2_CARD_FEATURE_NAMES
from harbi_v3.paths import BULLETIN_RAW_DIR, META_DIR, PROGRAM_RAW_DIR, TAHMINLER_DIR, ensure_dirs
from harbi_v3.predictor import RacePrediction, predict_for_date
from harbi_v3.records import eku_partners

_LINE80 = "═" * 78
_LINE100 = "═" * 100

_SLOTS = [
    ("🎯 Harbi Ganyan Favorisi   ", 1),
    ("🔒 Kazanırsa Sürpriz Olmaz ", 2),
    ("✍️  Kupona Yazılabilir     ", 3),
    ("💣 Bomba!                  ", 4),
    ("❓ Harbi mi?               ", 5),
]


def _city_name(hip: str) -> str:
    return hip.upper().replace("_", " ")


def _file_stem(day: date, hip: str) -> str:
    return f"{day:%d_%m_%Y}_{hip.upper()}"


def _confidence_label(gap: float) -> str:
    if gap >= 28:
        return "🔥🔥 ÇOK YÜKSEK GÜVEN"
    if gap >= 18:
        return "🔥 YÜKSEK GÜVEN"
    if gap >= 10:
        return "📈 ORTA GÜVEN"
    return "📊 DÜŞÜK GÜVEN"


def _resolve_eku_top5(ranked, partners):
    """Eküri duyarlı ilk 5: bir atın eküri ortağı zaten seçilmişse atlanır."""
    return select_top_n(ranked, partners, 5)


def _format_race_header(race: RacePrediction) -> str:
    tip = race.race_type or "?"
    grup = race.race_group or ""
    pist = race.race_track or "?"
    mesafe = f"{race.race_distance}m" if race.race_distance else ""
    saat = f"⏰{race.race_hour}" if race.race_hour else ""
    at = f"{race.runner_count} at"
    conf = _confidence_label(race.norm_score_gap)
    parts = [p for p in [tip, f"{pist} {mesafe}".strip(), saat, at] if p]
    return f"┌─ \t{race.race_no}. KOŞU | {' | '.join(parts)} | {conf} (Fark:{race.norm_score_gap:.1f})"


def _format_one_race(race: RacePrediction,
                     surdirek_horse_no: int | None = None) -> list[str]:
    lines: list[str] = []
    lines.append(_format_race_header(race))
    lines.append("│")

    # ranked_by_rank[i] = horse at rank i+1
    ranked = sorted(race.horses, key=lambda h: h.rank)
    partners = eku_partners([h.horse for h in ranked])
    top5 = _resolve_eku_top5(ranked, partners)

    for label, slot_rank in _SLOTS:
        if slot_rank <= len(top5):
            h = top5[slot_rank - 1]
            no_str = f"No:{h.horse.horse_no:<4}"
            partner_nos = partners.get(h.horse.horse_no)
            eku_tag = f" [E: {', '.join(str(p) for p in partner_nos)}]" if partner_nos else ""
            sd_tag  = " ⭐ [SURDIREK]" if h.horse.horse_no == surdirek_horse_no else ""
            lines.append(f"│  \t\t{label}\t: {no_str}\t{h.horse.horse_name}{eku_tag}{sd_tag}")
        else:
            lines.append(f"│  \t\t{label}\t: -")

    lines.append("│")
    lines.append(_LINE100)
    lines.append(f"\t{race.race_no}. KOŞU | Kazanan | [?] - [?]")
    lines.append(_LINE100)
    lines.append("│")
    lines.append("│  \t\t📊 Analiz Puanları:")
    lines.append("│")

    avg_score = sum(h.norm_score for h in ranked) / len(ranked) if ranked else 0.0
    avg_inserted = False
    for idx, h in enumerate(ranked):
        no_name = f"{h.horse.horse_no}. {h.horse.horse_name}"
        score_str = f"Skor: {h.norm_score:5.1f}"
        lines.append(f"│      \t{no_name:<28}{score_str}")
        next_score = ranked[idx + 1].norm_score if idx + 1 < len(ranked) else None
        if not avg_inserted and h.norm_score >= avg_score and (next_score is None or next_score < avg_score):
            lines.append(f"│\t\t{'─' * 39}\t\tKoşu Ortalama Puanı: {avg_score:.1f}")
            avg_inserted = True

    if not avg_inserted:
        lines.append(f"│\t\t{'─' * 39}\t\tKoşu Ortalama Puanı: {avg_score:.1f}")

    lines.append("│")
    lines.append(_LINE80)
    return lines


def format_hip_file(target_date: date, hip: str, races: list[RacePrediction],
                    surdirek=None) -> str:
    """
    surdirek: SurdirekResult | list[SurdirekResult] | None — gunun banko ati/atlari.
    Liste verilirse birincisi ana surdirek, sonrakiler ek surdirek olarak gosterilir.
    Bu sehre ait kosularda ilgili slot'ta [SURDIREK] isareti eklenir.
    """
    # Normalize: tek nesne veya None -> listeye cevir
    if surdirek is None:
        sd_list: list = []
    elif isinstance(surdirek, list):
        sd_list = [s for s in surdirek if s and s.hip == hip]
    else:
        sd_list = [surdirek] if surdirek.hip == hip else []

    city = _city_name(hip)
    header = f"🐎 {target_date:%d.%m.%Y} {city} TAHMİN"
    out: list[str] = [_LINE80, header, _LINE80]

    if sd_list:
        out.append("")
        out.append("★" * 60)
        if len(sd_list) == 1:
            out.append(f"  GUNUN SURDIREK (BANKO) TAHMINI")
        else:
            out.append(f"  GUNUN SURDIREK TAHMINLERI ({len(sd_list)} at)")
        for i, sd in enumerate(sd_list):
            prefix = "  " if len(sd_list) == 1 else f"  {i+1}. "
            out.append(f"{prefix}{sd.race_no}. Kosu | No:{sd.horse_no} | {sd.horse_name}")
            out.append(f"  (Skor:{sd.norm_score:.1f}  Gap:{sd.gap:.1f}  WinRate:{sd.win_rate:.2f}  Source:{getattr(sd, 'source', 'production')})")
        out.append("★" * 60)

    out.append("")

    # race_no -> surdirek horse_no haritasi (isaretleme icin)
    sd_map: dict[int, int] = {sd.race_no: sd.horse_no for sd in sd_list}

    for race in sorted(races, key=lambda r: r.race_no):
        sd_no = sd_map.get(race.race_no)
        out.extend(_format_one_race(race, surdirek_horse_no=sd_no))
        out.append("")

    return "\n".join(out)


def build_meta(target_date: date, hip: str, races: list[RacePrediction]) -> dict:
    out = {
        "date": f"{target_date:%Y-%m-%d}",
        "hip": hip,
        "model": {
            "name": "Harbi Ganyan v3 A2 production ranker",
            "feature_count": len(FEATURE_NAMES),
            "a2_horse_card_features_enabled": True,
            "a2_feature_count": len(A2_CARD_FEATURE_NAMES),
            "leakage_rule": "training, memory and horse-card rows are strictly before prediction date",
        },
        "races": {},
    }
    for r in races:
        ranked = sorted(r.horses, key=lambda h: h.rank)
        partners = eku_partners([h.horse for h in ranked])
        top5 = _resolve_eku_top5(ranked, partners)
        out["races"][str(r.race_no)] = {
            "predicted_no": r.horses[0].horse.horse_no if r.horses else 0,
            "predicted_name": r.horses[0].horse.horse_name if r.horses else "",
            "top5_nos": [h.horse.horse_no for h in top5],
        }
    return out


def _ensure_program(target_date: date, force: bool = False) -> None:
    program_path = PROGRAM_RAW_DIR / f"{target_date:%Y-%m-%d}.json"
    if force and program_path.exists():
        print(f"  🔄 Program verisi yenileniyor (TJK'dan güncel liste çekiliyor)...", flush=True)
    elif not program_path.exists():
        print(f"  📥 Program verisi bulunamadı, çekiliyor...", flush=True)
    else:
        return
    result = collect_program_day(target_date, force=force)
    if not result:
        print(f"  ❌ Program verisi çekilemedi: {target_date:%d.%m.%Y}", flush=True)
    else:
        print(f"  ✅ Program verisi alındı.", flush=True)


def _ensure_bulletin(target_date: date, force: bool = False) -> None:
    import time as _time
    bulletin_path = BULLETIN_RAW_DIR / f"{target_date:%Y-%m-%d}.json"
    today = date.today()

    # Bugünün bülteni >2 saat eskiyse yeniden çek (VDS 20:30 AGF güncellemesini yakala).
    # Geçmiş tarihlerde bülten değişmez, gereksiz scrape yapma.
    stale = (
        target_date == today
        and bulletin_path.exists()
        and (_time.time() - bulletin_path.stat().st_mtime) > 2 * 3600
    )

    should_fetch = (
        not bulletin_path.exists()
        or stale
        or force
    )
    if not should_fetch:
        return

    if force:
        print(f"  🔄 Bülten verisi yenileniyor (güncel AGF için)...", flush=True)
    elif stale:
        print(f"  🔄 Bülten verisi güncelleniyor (>2 saat eski)...", flush=True)
    else:
        print(f"  📥 Bülten verisi bulunamadı, çekiliyor...", flush=True)

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "scrape_bulletin",
        Path(__file__).parent / "scrape_bulletin.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    ok = mod.scrape_day(target_date)
    if ok:
        print(f"  ✅ Bülten verisi alındı.", flush=True)
    else:
        print(f"  ⚠️  Bülten verisi alınamadı (0 olarak devam edilecek).", flush=True)


def run(target_date: date, hip_filter: str | None = None) -> list[Path]:
    from harbi_v3.surdirek import select_surdirek_multi

    ensure_dirs()
    print(f"📅 {target_date:%d.%m.%Y} tahmin hesaplaniyor...", flush=True)
    _ensure_program(target_date)
    _ensure_bulletin(target_date)
    all_races = predict_for_date(target_date)
    if not all_races:
        print("  ⚠️  Tahmin yok (veri eksik veya yetersiz egitim).")
        return []

    # Hipodromlara gore grupla
    hip_map: dict[str, list[RacePrediction]] = {}
    for race in all_races:
        if hip_filter and race.hip.lower() != hip_filter.lower():
            continue
        hip_map.setdefault(race.hip, []).append(race)

    written: list[Path] = []
    for hip, races in sorted(hip_map.items()):
        surdireks = select_surdirek_multi(races)
        for i, sd in enumerate(surdireks):
            label = "⭐ SURDIREK" if i == 0 else "⭐ EK SURDIREK"
            print(f"  {label} ({hip}): {sd.race_no}.Kosu "
                  f"No:{sd.horse_no} {sd.horse_name} "
                  f"(Gap:{sd.gap:.1f})")

        stem = _file_stem(target_date, hip)
        txt_path = TAHMINLER_DIR / f"{stem}.txt"
        meta_path = META_DIR / f"{stem}_meta.json"

        content = format_hip_file(target_date, hip, races, surdirek=surdireks)
        txt_path.write_text(content, encoding="utf-8")

        meta = build_meta(target_date, hip, races)
        if surdireks:
            primary = surdireks[0]
            meta["surdirek"] = {
                "hip":        primary.hip,
                "race_no":    primary.race_no,
                "horse_no":   primary.horse_no,
                "horse_name": primary.horse_name,
                "gap":        round(primary.gap, 2),
                "norm_score": round(primary.norm_score, 2),
                "win_rate":   round(primary.win_rate, 4),
                "bucket":     primary.bucket,
                "source":     getattr(primary, "source", "production"),
            }
            if len(surdireks) > 1:
                meta["surdirek_ek"] = [
                    {
                        "hip":        sd.hip,
                        "race_no":    sd.race_no,
                        "horse_no":   sd.horse_no,
                        "horse_name": sd.horse_name,
                        "gap":        round(sd.gap, 2),
                        "norm_score": round(sd.norm_score, 2),
                        "win_rate":   round(sd.win_rate, 4),
                        "bucket":     sd.bucket,
                        "source":     getattr(sd, "source", "production"),
                    }
                    for sd in surdireks[1:]
                ]
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        kosu_count = len(races)
        print(f"  ✅ {txt_path.name}  ({kosu_count} koşu)")
        written.append(txt_path)

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="5'li satır tahmin üreticisi")
    parser.add_argument("tarih", nargs="?", default=None, help="YYYY-MM-DD (default: bugun)")
    parser.add_argument("--hip", default=None, help="Sadece belirtilen hipodrom (opsiyonel)")
    args = parser.parse_args()

    if args.tarih:
        target_date = parse_date(args.tarih)
    else:
        target_date = date.today()

    written = run(target_date, hip_filter=args.hip)
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
