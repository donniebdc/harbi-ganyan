from __future__ import annotations

"""
v3_export.py — VDS backend icin tahmin export.

Backend'in bekledigi JSON formati:
{
  "date": "YYYY-MM-DD",
  "hipodromlar": [
    {
      "hipodrom": "ISTANBUL",
      "kosular": [{ "kno":..., "bes":[...], "analiz_puanlari":[...], "sonuc":null }]
    }
  ]
}

Kullanim (VDS'te):
    python v3_export.py                          # yarinin tahminini uret
    python v3_export.py 2026-06-18               # belirli tarih
    python v3_export.py 2026-06-18 2026-06-20    # tarih araligi
"""

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.altili_coupons import select_top_n
from harbi_v3.surdirek import MIN_GAP_THRESHOLD as _MIN_GAP
from harbi_v3.collect_program import collect_program_city, collect_program_day
from harbi_v3.confidence import confidence_label, race_type_bucket
from harbi_v3.normalize import norm_text
from harbi_v3.paths import ensure_dirs
from harbi_v3.predictor import RacePrediction, predict_for_date
from harbi_v3.race_difficulty import compute as compute_difficulty, to_dict as difficulty_to_dict
from harbi_v3.agf_radar import compute as compute_agf_radar, to_dict as agf_radar_to_dict, at_etiket_map
from harbi_v3.explain import compute as compute_explain, to_list as explain_to_list
from harbi_v3.daily_panel import compute as compute_panel, to_dict as panel_to_dict
from harbi_v3.agf_radar import SURPRIZ
from harbi_v3.surpriz_radar import compute as compute_surpriz_radar, to_dict as surpriz_radar_to_dict
from harbi_v3.records import eku_partners, load_program_day

def _percentile70(values: list[float]) -> float:
    """Kosu ici norm_score degerlerinden %70'lik dilim (numpy gerektirmez)."""
    n = len(values)
    if n == 0:
        return 0.0
    s = sorted(values)
    k = 0.70 * (n - 1)
    lo = int(k)
    hi = min(lo + 1, n - 1)
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def _compute_bad_single_no(race, surpriz_horse_nos: set[int]) -> int | None:
    """Phase 19: kosu basina max 1 Bu Ata Dikkat adayi.

    Hiyerarsi:
    A) Surdirek kosusu (norm_score_gap >= MIN_GAP) -> None
    B) Kosuda Surpriz Radari adayi varsa -> model rank en iyi surpriz aday
    C) Yoksa D5 havuzundan tek aday (rank<=2 AND norm_score>=p70)
    D) Hicbiri -> None
    """
    # A: Surdirek kosusu — BAD uretme
    if race.norm_score_gap >= _MIN_GAP:
        return None
    if len(race.horses) < 3:
        return None

    # B: Surpriz Radari adayi varsa o atı sec
    surpriz = [h for h in race.horses if h.horse.horse_no in surpriz_horse_nos]
    if surpriz:
        best = min(surpriz, key=lambda h: (h.rank, -h.norm_score, h.horse.horse_no))
        return best.horse.horse_no

    # C: D5 havuzundan tek aday
    norm_scores = [h.norm_score for h in race.horses]
    p70 = _percentile70(norm_scores)
    d5 = [h for h in race.horses if h.rank <= 2 and h.norm_score >= p70]
    if not d5:
        return None
    best_d5 = min(d5, key=lambda h: (h.rank, -h.norm_score, h.horse.horse_no))
    return best_d5.horse.horse_no


_SLOTS = [
    ("FAV", 1),   # Harbi Ganyan Favorisi
    ("SUR", 2),   # Kazanırsa Sürpriz Olmaz
    ("YAZ", 3),   # Plase
    ("BOM", 4),   # Bomba!
    ("HAR", 5),   # Harbi mi?
]


def _ensure_bulletin(day: date, force: bool = False) -> None:
    """atyarisi.com bulteni ceker. Bulten feature'lari (genel/guncel/saatli)
    icin gerekli. Hem lokal hem VDS ana tahmin yolunda otomatik calisir.
    force=True: mevcut dosyanin uzerine yeniden ceker (yenileme dongusunde kullanilir).
    Hata olursa sessizce devam eder (bulten 0 olarak kullanilir)."""
    from harbi_v3.paths import BULLETIN_RAW_DIR
    bulletin_path = BULLETIN_RAW_DIR / f"{day:%Y-%m-%d}.json"
    if bulletin_path.exists() and not force:
        return
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "scrape_bulletin", ROOT / "scripts" / "scrape_bulletin.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.scrape_day(day)
    except Exception as e:
        print(f"{day}: bulten cekilemedi ({e}), 0 ile devam")

def _pist_label(track: str) -> str:
    t = (track or "").strip()
    if not t:
        return "-"
    low = t.lower()
    if "cim" in low or "çim" in low:
        return "Çim"
    if "kum" in low:
        return "Kum"
    if "sentetik" in low:
        return "Sentetik"
    return t


def _ktip_label(race: RacePrediction) -> str:
    return (race.race_group or race.race_type or "-").strip()


def _subtype(race: RacePrediction) -> str:
    return race_type_bucket(race.race_type, race.race_group)


def _format_bes(race: RacePrediction) -> list[dict]:
    ranked = sorted(race.horses, key=lambda h: h.rank)
    partners = eku_partners([h.horse for h in ranked])
    top5 = select_top_n(ranked, partners, 5)
    out = []
    for slot_name, slot_rank in _SLOTS:
        if slot_rank <= len(top5):
            h = top5[slot_rank - 1]
            out.append({
                "slot": slot_name,
                "at_no": h.horse.horse_no,
                "at": h.horse.horse_name,
                "ana": round(h.norm_score, 1),
                "jokey": h.jockey_short or h.horse.jockey_name or "",
                "apranti": h.is_apprentice,
                "eku_partner_nos": partners.get(h.horse.horse_no, []),
            })
        else:
            out.append({
                "slot": slot_name, "at_no": 0, "at": "",
                "ana": 0.0, "jokey": "", "apranti": False,
                "eku_partner_nos": [],
            })
    return out


_GUVEN_MAP = {
    "Cok Yuksek Guven": "surdirekt",
    "Yuksek Guven": "yuksek_guvenli",
    "Orta Guven": "guvenli",
    "Dusuk Guven": "riskli",
}


def _guven_label(race: RacePrediction) -> str:
    bucket = race_type_bucket(race.race_type, race.race_group)
    raw = confidence_label(race.norm_score_gap, bucket)
    return _GUVEN_MAP.get(raw, "riskli")


def _format_analiz(
    race: RacePrediction,
    agf_etiketler: dict[int, str] | None = None,
    bu_ata_dikkat_no: int | None = None,
) -> list[dict]:
    partners = eku_partners([h.horse for h in race.horses])
    etiketler = agf_etiketler or {}
    out = []
    for h in sorted(race.horses, key=lambda hh: hh.rank):
        bad = (bu_ata_dikkat_no is not None and h.horse.horse_no == bu_ata_dikkat_no)
        out.append({
            "at_no": h.horse.horse_no,
            "at": h.horse.horse_name,
            "ana": round(h.norm_score, 1),
            "sira": h.rank,
            "jokey": h.jockey_short or h.horse.jockey_name or "",
            "apranti": h.is_apprentice,
            "eku_partner_nos": partners.get(h.horse.horse_no, []),
            "weight": round(h.horse.weight, 1),
            "handicap": round(h.horse.handicap, 1),
            "last6_places": list(h.horse.last6_places),
            "last6_tracks": list(h.horse.last6_tracks),
            "agf_etiket": etiketler.get(h.horse.horse_no),
            "bu_ata_dikkat": bad,
            "bu_ata_dikkat_etiket": "Bu Ata Dikkat" if bad else None,
            "bu_ata_dikkat_aciklama": (
                "Modelin öne çıkardığı, gözden kaçabilecek aday." if bad else None
            ),
            "market_context": None,
        })
    return out


def build_day_payload(day: date, refresh: bool = True, city: str | None = None) -> dict | None:
    """Tek gun icin tum hipodromlarin (veya tek sehrin) tahmin payload'unu uretir.

    Args:
        day: Tahmin yapilacak tarih
        refresh: True -> program verisini tazele
        city: None -> tum sehirler, \"ISTANBUL\" -> sadece o sehir
    """
    ensure_dirs()

    # Veri cekme SADECE refresh=True (VDS ana motor). refresh=False ise lokal AYNA:
    # hicbir sey scrape edilmez, sadece data_pull ile VDS'ten cekilen veri kullanilir.
    # Bulten de buna dahildir; aksi halde lokal atyarisi'nden taze bulten ceker ve
    # VDS'in (farkli zamanda cektigi veya hic cekmedigi) bulteninden sapar.
    if refresh:
        _ensure_bulletin(day, force=True)
        if city:
            collect_program_city(day, city, force=True)
        else:
            collect_program_day(day, force=True)

    # Tahmin uret (walk-forward, leakage-free)
    all_races = predict_for_date(day, city=city)
    if not all_races:
        print(f"{day}: tahmin uretilemedi")
        return None

    # AGF verisi — tum kosular icin bir kez yuklenir; yoksa bos dict (sistem kırılmaz)
    try:
        import sys as _sys
        _scripts_dir = str(ROOT / "scripts")
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        from scrape_agf import load_agf, scrape_day as scrape_agf_day
        if refresh:
            scrape_agf_day(day, force=True)
        agf_data = load_agf(day)
    except Exception:
        agf_data = {}

    # Hipodrom bazinda grupla
    races_by_hip: dict[str, list[RacePrediction]] = {}
    for race in all_races:
        races_by_hip.setdefault(race.hip, []).append(race)

    # daily_panel icin birikim yapilari
    _panel_agf:   dict[tuple[str, int], object] = {}
    _panel_diff:  dict[tuple[str, int], object] = {}
    _panel_guven: dict[tuple[str, int], str]    = {}
    _panel_surpriz: set[tuple[str, int]]        = set()

    hipodromlar = []
    for hip_display in sorted(races_by_hip):
        races = races_by_hip[hip_display]

        # Kosular
        kosular = []
        for race in sorted(races, key=lambda r: r.race_no):
            key = (race.hip, race.race_no)

            try:
                agf_radar_result = compute_agf_radar(race, agf_data)
                agf_radar = agf_radar_to_dict(agf_radar_result)
                _etiket_map = at_etiket_map(agf_radar_result)
                _panel_agf[key] = agf_radar_result
                # Surpriz etiketli at varsa kosuyu isaretle
                if any(a.etiket == SURPRIZ for a in agf_radar_result.at_infolar):
                    _panel_surpriz.add(key)
            except Exception:
                agf_radar_result = None
                agf_radar = None
                _etiket_map = {}

            try:
                _zorluk_result = compute_difficulty(race)
                zorluk = difficulty_to_dict(_zorluk_result)
                _panel_diff[key] = _zorluk_result
            except Exception:
                _zorluk_result = None
                zorluk = None

            try:
                _guven_str = _guven_label(race)
                _panel_guven[key] = _guven_str
                aciklama_kartlari = explain_to_list(
                    compute_explain(race, agf_radar_result, _zorluk_result, guven=_guven_str)
                )
            except Exception:
                aciklama_kartlari = []

            # Phase 19: Surpriz horse nos — SURPRIZ etiketli atlar
            _surpriz_nos: set[int] = {
                no for no, et in _etiket_map.items() if et == SURPRIZ
            }
            # Phase 19: max 1 BAD per race (hiyerarsi uygulandi)
            _bad_no = _compute_bad_single_no(race, _surpriz_nos)
            kosular.append({
                "kno": race.race_no,
                "pist": _pist_label(race.race_track),
                "mesafe": str(race.race_distance) if race.race_distance else "",
                "saat": race.race_hour or "",
                "n_at": race.runner_count,
                "race_type": _subtype(race),
                "race_subtype": _subtype(race),
                "ktip": _ktip_label(race),
                "guven": _guven_label(race),
                "bes": _format_bes(race),
                "analiz_puanlari": _format_analiz(
                    race,
                    agf_etiketler=_etiket_map,
                    bu_ata_dikkat_no=_bad_no,
                ),
                "zorluk": zorluk,
                "agf_radar": agf_radar,
                "aciklama_kartlari": aciklama_kartlari,
                "sonuc": None,
            })

        hipodromlar.append({
            "hipodrom": hip_display,
            "kosular": kosular,
        })

    # Bu Ata Dikkat — hipodromlar gezilerek D5 at listesi toplaniyor
    _bad_kosular: list[dict] = []
    for hip_data in hipodromlar:
        for kosu_data in hip_data["kosular"]:
            bad_ats = [
                {"at_no": a["at_no"], "at": a["at"]}
                for a in kosu_data["analiz_puanlari"]
                if a.get("bu_ata_dikkat")
            ]
            if bad_ats:
                _bad_kosular.append({
                    "hip": hip_data["hipodrom"],
                    "kno": kosu_data["kno"],
                    "atlar": bad_ats,
                })

    # daily_panel — tum kosular islendikten sonra uret
    try:
        panel_result = compute_panel(
            races=all_races,
            agf_results=_panel_agf,
            difficulty_results=_panel_diff,
            guven_map=_panel_guven,
            surpriz_race_keys=_panel_surpriz,
        )
        daily_panel = panel_to_dict(panel_result)["daily_panel"]
    except Exception:
        daily_panel = None

    # surpriz_radar — tum kosular islendikten sonra uret
    try:
        surpriz_result = compute_surpriz_radar(
            races=all_races,
            agf_results=_panel_agf,
            difficulty_results=_panel_diff,
        )
        surpriz_radar = surpriz_radar_to_dict(surpriz_result)
    except Exception:
        surpriz_radar = None

    # D5 listesini daily_panel'e ekle (yoksa standalone olarak koy)
    if daily_panel is not None:
        daily_panel["bu_ata_dikkat_kosular"] = _bad_kosular
    else:
        daily_panel = {"bu_ata_dikkat_kosular": _bad_kosular}

    # V54: Sehir bazli surdirek garantisi.
    # daily_panel.surdirek sadece "Cok Yuksek Guven" (surdirekt) kosularda doluyor.
    # O guven esigini gecen kosu yoksa null kaliyor ve Flutter SurdirekEkrani bosaliyor.
    # select_surdirek_multi gap>=12 + fallback garantisi ile her sehir icin surdireki secer.
    # Secilen surerikler meta JSON'a yazilir → import_to_db → Surdirek tablosu → API → Flutter.
    from harbi_v3.surdirek import select_surdirek_multi as _select_surdirek_multi
    from harbi_v3.confidence import race_type_bucket as _rtb
    _META_DIR = ROOT / "data" / "meta"
    _META_DIR.mkdir(parents=True, exist_ok=True)
    _city_surdirekler: dict = {}  # hip -> SurdirekResult

    for _hip_display, _city_races in races_by_hip.items():
        _sd_list = _select_surdirek_multi(
            _city_races, max_count=2, surpriz_race_nos=_panel_surpriz
        )
        if not _sd_list:
            continue
        _city_surdirekler[_hip_display] = _sd_list[0]

        # Meta JSON yaz — import_to_db_vds.py bu dosyadan Surdirek tablosunu doldurur
        _stem = f"{day:%d_%m_%Y}_{_hip_display.upper()}"
        _meta_path = _META_DIR / f"{_stem}_meta.json"
        _meta: dict = {}
        if _meta_path.exists():
            try:
                _meta = json.loads(_meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        _p = _sd_list[0]
        _meta["surdirek"] = {
            "race_no":    _p.race_no,
            "horse_no":   _p.horse_no,
            "horse_name": _p.horse_name,
            "gap":        round(_p.gap, 2),
            "norm_score": round(_p.norm_score, 2),
            "win_rate":   round(_p.win_rate, 2),
            "bucket":     _p.bucket,
        }
        if len(_sd_list) > 1:
            _meta["surdirek_ek"] = [
                {
                    "race_no":    _s.race_no,
                    "horse_no":   _s.horse_no,
                    "horse_name": _s.horse_name,
                    "gap":        round(_s.gap, 2),
                    "norm_score": round(_s.norm_score, 2),
                    "win_rate":   round(_s.win_rate, 2),
                    "bucket":     _s.bucket,
                }
                for _s in _sd_list[1:]
            ]
        _meta_path.write_text(
            json.dumps(_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            f"[v54] {_hip_display} R{_p.race_no} {_p.horse_name} "
            f"gap={_p.gap:.1f} meta yazildi"
        )

    # daily_panel'e surdirekler listesi ekle (sehir bazli, Flutter surdirekler panel icin)
    if daily_panel is not None:
        daily_panel["surdirekler"] = [
            {
                "hip":         _hip,
                "kno":         _sd.race_no,
                "at_no":       _sd.horse_no,
                "at":          _sd.horse_name,
                "gap":         round(_sd.gap, 1),
                "bucket":      _sd.bucket,
                "is_fallback": _sd.is_fallback,
            }
            for _hip, _sd in _city_surdirekler.items()
        ]
        # daily_panel.surdirek null ise en yuksek gap'li sehiri fallback olarak doldur
        if daily_panel.get("surdirek") is None and _city_surdirekler:
            _bh, _bsd = max(_city_surdirekler.items(), key=lambda x: x[1].gap)
            _race_obj = next(
                (r for r in races_by_hip.get(_bh, []) if r.race_no == _bsd.race_no),
                None,
            )
            if _race_obj:
                daily_panel["surdirek"] = {
                    "hip":            _bh,
                    "kno":            _bsd.race_no,
                    "race_type":      _rtb(_race_obj.race_type or "", _race_obj.race_group or ""),
                    "n_at":           _bsd.runner_count,
                    "guven":          _guven_label(_race_obj),
                    "zorluk_kodu":    None,
                    "zorluk_puani":   0.0,
                    "norm_score_gap": round(_bsd.gap, 1),
                    "agf_model_uyum": None,
                    "at_no":          _bsd.horse_no,
                    "at":             _bsd.horse_name,
                    "v54_fallback":   True,
                }
                print(
                    f"[v54] daily_panel.surdirek fallback: {_bh} R{_bsd.race_no} "
                    f"{_bsd.horse_name} gap={_bsd.gap:.1f}"
                )

    return {
        "date": f"{day:%Y-%m-%d}",
        "premium_schema_version": "sprint1_v1",
        "hipodromlar": hipodromlar,
        "daily_panel": daily_panel,
        "surpriz_radar": surpriz_radar,
    }


def export_day(day: date, out_dir: Path | None = None, city: str | None = None, refresh: bool = True) -> Path | None:
    """Tek gunun payload'unu JSON olarak disari yazar.

    Args:
        day: Tahmin yapilacak tarih
        out_dir: Cikti dizini (None = data/export_out)
        city: None -> tum sehirler, \"ISTANBUL\" -> sadece o sehir
        refresh: True -> TJK'den taze program ceker, False -> mevcut veriyi kullanir
    """
    if out_dir is None:
        out_dir = ROOT / "data" / "export_out"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = build_day_payload(day, city=city, refresh=refresh)
    if payload is None:
        return None
    suffix = f"_{city}" if city else ""
    out_path = out_dir / f"{day:%Y-%m-%d}{suffix}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{day}: export -> {out_path}")
    return out_path


def main():
    today = date.today()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}

    city = None
    for flag in flags:
        if flag.startswith("--city="):
            city = flag.split("=", 1)[1].strip().upper()
        elif flag == "--city":
            print("Kullanim: python v3_export.py [tarih] [--city=ISTANBUL]")
            return 1

    if len(args) >= 1:
        from harbi_v3.dates import parse_date
        try:
            d = parse_date(args[0])
        except (ValueError, TypeError):
            print(f"Gecersiz tarih: {args[0]}")
            return 1
        export_day(d, city=city)
    else:
        # Yarının tahminini uret (varsayilan)
        export_day(today + timedelta(days=1), city=city)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
