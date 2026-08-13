from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

from .normalize import norm_text
from .paths import HORSE_CARDS_RAW_DIR
from .records import distance_bucket


TARGET_TYPES = ("sartli", "maiden", "handikap")

# ── Par-time katsayilari (tjktahmin.py'den, 51795 kayitlik arsivden turetilmis) ──
# Sehir anahtarlari norm_text() ciktisiyla (buyuk harf, ASCII) eslenir.
_CITY_FARK: dict[tuple[str, str], float] = {
    ("ADANA", "Ingiliz"): 1.84,   ("ADANA", "Arap"): 2.03,
    ("ANKARA", "Ingiliz"): 0.62,  ("ANKARA", "Arap"): 0.82,
    ("ANTALYA", "Ingiliz"): 0.64, ("ANTALYA", "Arap"): 0.78,
    ("BURSA", "Ingiliz"): 0.86,   ("BURSA", "Arap"): 0.70,
    ("DIYARBAKIR", "Ingiliz"): 12.28, ("DIYARBAKIR", "Arap"): 12.37,
    ("ELAZIG", "Ingiliz"): 7.95,  ("ELAZIG", "Arap"): 9.55,
    ("KOCAELI", "Ingiliz"): 1.46, ("KOCAELI", "Arap"): 1.36,
    ("ISTANBUL", "Ingiliz"): 0.00, ("ISTANBUL", "Arap"): 0.00,
    ("IZMIR", "Ingiliz"): 1.32,   ("IZMIR", "Arap"): 0.73,
    ("SANLIURFA", "Ingiliz"): 10.87, ("SANLIURFA", "Arap"): 13.55,
}
# Yuzey anahtarlari: horse_cards "cim"/"kum"/"sentetik"
_PIST_FARK: dict[tuple[str, str], float] = {
    ("kum", "Ingiliz"): 0.00,      ("kum", "Arap"): 0.00,
    ("cim", "Ingiliz"): -4.58,     ("cim", "Arap"): -5.64,
    ("sentetik", "Ingiliz"): -3.88, ("sentetik", "Arap"): -4.44,
}
_PAR_TIME: dict[str, dict[int, float]] = {
    "Ingiliz": {1200: 75.22, 1400: 89.68, 1600: 103.54, 1800: 118.92, 2000: 132.64},
    "Arap":    {1200: 85.10, 1400: 100.48, 1600: 115.65, 1800: 132.07, 2000: 147.64},
}

def _par_time(distance: int, irk: str) -> float:
    tbl = _PAR_TIME.get(irk, _PAR_TIME["Ingiliz"])
    pts = sorted(tbl.keys())
    if distance <= pts[0]:
        d0, d1 = pts[0], pts[1]
        return tbl[d0] + (distance - d0) * (tbl[d1] - tbl[d0]) / (d1 - d0)
    for i in range(len(pts) - 1):
        d0, d1 = pts[i], pts[i + 1]
        if distance <= d1:
            return tbl[d0] + (distance - d0) * (tbl[d1] - tbl[d0]) / (d1 - d0)
    d0, d1 = pts[-2], pts[-1]
    return tbl[d1] + (distance - d1) * (tbl[d1] - tbl[d0]) / (d1 - d0)

def _kalite_farki(derece_sn: float, hip: str, track: str, distance: int, irk: str) -> float | None:
    """Bir derece degerini Istanbul+Kum esdegerine gore kalite farkina cevirir.
    Negatif = par'dan hizli (iyi at). |diff| > 20 → aykiri, None dondurur."""
    if derece_sn <= 0:
        return None
    city_adj = _CITY_FARK.get((hip, irk), 0.0)
    pist_adj = _PIST_FARK.get((track, irk), 0.0)
    norm = derece_sn - city_adj - pist_adj
    diff = norm - _par_time(distance, irk)
    return None if abs(diff) > 20.0 else diff


@dataclass(frozen=True)
class CardRace:
    race_date: date
    hip: str
    distance: int
    distance_bucket: str
    track: str
    going: str
    penetrometer: float
    rank: int
    race_type: str
    jockey: str
    equipment: str
    derece_seconds: float = 0.0
    irk: str = "Ingiliz"


def _to_int(value: object) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _derece_to_seconds(value: object) -> float:
    """'1.17.31' veya '1.52.40' -> saniye cinsine cevirir."""
    text = str(value or "").strip().replace(",", ".")
    if not text or text in ("-", "0"):
        return 0.0
    parts = text.split(".")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 100
        return float(text)
    except (ValueError, TypeError):
        return 0.0


def _infer_irk(grup: object) -> str:
    """Grup alanından ırk çıkarır: '3+A', '4A' → 'Arap'; '3+İ', '3İ' → 'Ingiliz'."""
    text = str(grup or "").upper().replace("İ", "I").replace("Ğ", "G")
    # Arap: sadece A harfi var, I yok (İngiliz için I)
    if re.search(r'\bA\b', text) or (text.endswith("A") and "I" not in text):
        return "Arap"
    return "Ingiliz"


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _race_type_bucket(value: object) -> str:
    text = str(value or "").lower()
    if "handikap" in text:
        return "handikap"
    if "maiden" in text:
        return "maiden"
    if "şart" in text or "sart" in text or "ÅŸart" in text:
        return "sartli"
    if "kv" in text or "grup" in text or "g1" in text or "g2" in text or "g3" in text:
        return "kv_grup"
    return "other"


def _parse_pist(value: object) -> tuple[str, str, float]:
    """Pist alanini ayristirir: (surface, going, penetrometer).

    Ornekler:
      "C:Normal 3.3"       -> ("cim", "normal", 3.3)
      "C:Biraz Yumusak 3.4" -> ("cim", "biraz_yumusak", 3.4)
      "K:Islak"             -> ("kum", "islak", 0.0)
      "K:Normal"            -> ("kum", "normal", 0.0)
      "K:Sulu"              -> ("kum", "sulu", 0.0)
      "S:Normal"            -> ("sentetik", "normal", 0.0)
      "S:Islak"             -> ("sentetik", "islak", 0.0)
    """
    text = str(value or "").strip()
    if not text:
        return ("unknown", "", 0.0)

    # Surface tespiti (ilk karakter veya "Sentetik")
    lower = text.lower()
    if "sentetik" in lower:
        surface = "sentetik"
    elif lower.startswith("ç") or lower.startswith("c"):
        surface = "cim"
    elif lower.startswith("k"):
        surface = "kum"
    else:
        surface = "unknown"

    # Going ve penetrometre ayristirma: "Normal 3.3" veya "Islak"
    if ":" in text:
        after_colon = text.split(":", 1)[1].strip()
    else:
        after_colon = text

    # Penetrometre degeri (opsiyonel, sadece cim pistte)
    penetrometer = 0.0
    parts = after_colon.rsplit(" ", 1)
    if len(parts) == 2:
        try:
            penetrometer = float(parts[1].replace(",", "."))
        except (ValueError, TypeError):
            penetrometer = 0.0
        going_raw = parts[0].strip()
    else:
        going_raw = after_colon.strip()

    # Going normalize: Turkce karakterler + tirnak temizligi
    going = (
        going_raw.lower()
        .replace("ı", "i").replace("ş", "s").replace("ç", "c")
        .replace("ğ", "g").replace("ü", "u").replace("ö", "o")
        .replace("â", "a").replace("î", "i")
        .replace(" ", "_")
    )
    if not going:
        going = ""

    return (surface, going, penetrometer)


def _track_bucket(value: object) -> str:
    """Geriye donuk uyumlu yuzey ayristirici — _parse_pist() wrapper."""
    surface, _, _ = _parse_pist(value)
    return surface


def _going_bucket(value: object) -> str:
    """Pist alanindan sadece going durumunu cikarir."""
    _, going, _ = _parse_pist(value)
    return going


def _get(row: dict, names: tuple[str, ...]) -> object:
    for name in names:
        if name in row:
            return row.get(name)
    return None


@lru_cache(maxsize=20000)
def load_card_races(atkodu: str) -> tuple[CardRace, ...]:
    path = HORSE_CARDS_RAW_DIR / f"{atkodu}.json"
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    races: list[CardRace] = []
    for row in data.get("history_rows") or []:
        race_date = _parse_date(_get(row, ("Tarih", "TARIH")))
        if not race_date:
            continue
        distance = _to_int(_get(row, ("Msf", "Mesafe")))
        rank = _to_int(_get(row, ("S", "Sira", "Sıra")))
        if rank <= 0:
            continue
        surface, going, penetrometer = _parse_pist(_get(row, ("Pist",)))
        irk = _infer_irk(_get(row, ("Grup",)))
        races.append(CardRace(
            race_date=race_date,
            hip=norm_text(_get(row, ("Şehir", "Åehir", "Sehir"))),
            distance=distance,
            distance_bucket=distance_bucket(distance),
            track=surface,
            going=going,
            penetrometer=penetrometer,
            rank=rank,
            race_type=_race_type_bucket(_get(row, ("Kcins", "K.cins", "Koşu Cinsi"))),
            jockey=norm_text(_get(row, ("Jokey",))),
            equipment=norm_text(_get(row, ("Takı", "TakÄ±", "Taki"))),
            derece_seconds=_derece_to_seconds(_get(row, ("Derece",))),
            irk=irk,
        ))
    return tuple(sorted(races, key=lambda r: r.race_date))


def _rate(count: int, total: int) -> float:
    return count / total if total else 0.0


def _stats(rows: list[CardRace]) -> tuple[int, float, float, float]:
    starts = len(rows)
    wins = sum(1 for r in rows if r.rank == 1)
    top3 = sum(1 for r in rows if r.rank <= 3)
    avg_inv = 0.0
    if starts:
        avg_inv = 1.0 / max(sum(r.rank for r in rows) / starts, 1.0)
    return starts, _rate(wins, starts), _rate(top3, starts), avg_inv


def card_features(
    atkodu: str,
    as_of: date,
    race_type: str,
    hip: str,
    track: str,
    dist_bucket: str,
    jockey: str,
    equipment: str,
    going: str = "",
    penetrometer: float = 0.0,
) -> tuple[dict[str, float], date | None]:
    rows = [r for r in load_card_races(atkodu) if r.race_date < as_of]
    out: dict[str, float] = {}
    starts, win, top3, avg_inv = _stats(rows)
    out["a2_card_has_history"] = 1.0 if starts else 0.0
    out["a2_card_starts"] = float(starts)
    out["a2_card_win_rate"] = win
    out["a2_card_top3_rate"] = top3
    out["a2_card_avg_rank_inv"] = avg_inv

    for target in TARGET_TYPES:
        t_rows = [r for r in rows if r.race_type == target]
        s, w, t3, inv = _stats(t_rows)
        out[f"a2_card_{target}_starts"] = float(s)
        out[f"a2_card_{target}_win_rate"] = w
        out[f"a2_card_{target}_top3_rate"] = t3

    scoped = {
        "race_type": [r for r in rows if r.race_type == race_type],
        "hip": [r for r in rows if r.hip == hip],
        "track": [r for r in rows if r.track == track],
        "distance": [r for r in rows if r.distance_bucket == dist_bucket],
        "jockey": [r for r in rows if r.jockey == jockey],
        "equipment": [r for r in rows if r.equipment == equipment],
    }
    for key, scoped_rows in scoped.items():
        s, w, t3, _ = _stats(scoped_rows)
        out[f"a2_card_{key}_starts"] = float(s)
        out[f"a2_card_{key}_win_rate"] = w
        out[f"a2_card_{key}_top3_rate"] = t3

    # ── Going-scoped features ──
    if going:
        going_rows = [r for r in rows if r.going == going]
        gs, gw, gt3, _ = _stats(going_rows)
        out["a2_card_going_starts"] = float(gs)
        out["a2_card_going_win_rate"] = gw
        out["a2_card_going_top3_rate"] = gt3

        # Going switch: son kosuya gore going degisimi
        if len(rows) >= 1:
            last_going = rows[-1].going
            out["a2_card_going_switch"] = 1.0 if (last_going and last_going != going) else 0.0
        else:
            out["a2_card_going_switch"] = 0.0
    else:
        out["a2_card_going_starts"] = 0.0
        out["a2_card_going_win_rate"] = 0.0
        out["a2_card_going_top3_rate"] = 0.0
        out["a2_card_going_switch"] = 0.0

    # ── Penetrometre features ──
    pen_values = [r.penetrometer for r in rows if r.penetrometer > 0.0]
    if pen_values:
        out["a2_card_avg_penetrometer"] = sum(pen_values) / len(pen_values)
    else:
        out["a2_card_avg_penetrometer"] = 0.0
    out["a2_card_penetrometer_delta"] = (
        penetrometer - out["a2_card_avg_penetrometer"]
        if penetrometer > 0.0 and out["a2_card_avg_penetrometer"] > 0.0
        else 0.0
    )

    recent = rows[-5:]
    s, w, t3, inv = _stats(recent)
    out["a2_card_recent5_starts"] = float(s)
    out["a2_card_recent5_win_rate"] = w
    out["a2_card_recent5_top3_rate"] = t3
    out["a2_card_recent5_avg_rank_inv"] = inv

    last_date = rows[-1].race_date if rows else None
    out["a2_card_days_since_last"] = float((as_of - last_date).days) if last_date else 0.0

    # ── Mesafe uyum skoru (optimal mesafe vs şimdiki mesafe) ──
    dist_buckets_seen: dict[str, list] = {}
    for r in rows:
        dist_buckets_seen.setdefault(r.distance_bucket, []).append(r)
    if len(dist_buckets_seen) >= 2:
        dist_wrs = {b: _stats(rs)[1] for b, rs in dist_buckets_seen.items()}
        best_dist_wr = max(dist_wrs.values())
        cur_dist_wr = dist_wrs.get(dist_bucket, 0.0)
        out["a2_card_distance_fitness_gap"] = cur_dist_wr - best_dist_wr  # <=0 (0=optimal mesafe)
    else:
        out["a2_card_distance_fitness_gap"] = 0.0

    # ── Par-time normalize kalite farki features ──
    # kalite_farki < 0 = par'dan hizli (iyi at), > 0 = yavas.
    # Feature olarak negatif yonde tutuyoruz: daha dusuk = daha iyi.
    kf_all = [kf for r in rows if (kf := _kalite_farki(r.derece_seconds, r.hip, r.track, r.distance, r.irk)) is not None]
    if kf_all:
        out["a2_card_avg_quality_diff"] = sum(kf_all) / len(kf_all)
        recent_kf = kf_all[-3:]
        out["a2_card_recent3_quality_diff"] = sum(recent_kf) / len(recent_kf)
        # Trend: son 3 ile onceki fark (negatif = iyilesme, pozitif = kotu gidiyor)
        if len(kf_all) >= 4:
            older_kf = kf_all[:-3]
            out["a2_card_quality_trend"] = (sum(recent_kf) / len(recent_kf)) - (sum(older_kf) / len(older_kf))
        else:
            out["a2_card_quality_trend"] = 0.0
        # Son galip kosudaki kalite farki (rank==1 olan en son)
        win_kf = [kf for r in rows if r.rank == 1 and (kf := _kalite_farki(r.derece_seconds, r.hip, r.track, r.distance, r.irk)) is not None]
        out["a2_card_best_quality_diff"] = min(win_kf) if win_kf else out["a2_card_avg_quality_diff"]
    else:
        out["a2_card_avg_quality_diff"] = 0.0
        out["a2_card_recent3_quality_diff"] = 0.0
        out["a2_card_quality_trend"] = 0.0
        out["a2_card_best_quality_diff"] = 0.0

    return out, last_date


A2_CARD_FEATURE_NAMES = [
    "a2_card_has_history",
    "a2_card_starts",
    "a2_card_win_rate",
    "a2_card_top3_rate",
    "a2_card_avg_rank_inv",
    "a2_card_sartli_starts",
    "a2_card_sartli_win_rate",
    "a2_card_sartli_top3_rate",
    "a2_card_maiden_starts",
    "a2_card_maiden_win_rate",
    "a2_card_maiden_top3_rate",
    "a2_card_handikap_starts",
    "a2_card_handikap_win_rate",
    "a2_card_handikap_top3_rate",
    "a2_card_race_type_starts",
    "a2_card_race_type_win_rate",
    "a2_card_race_type_top3_rate",
    "a2_card_hip_starts",
    "a2_card_hip_win_rate",
    "a2_card_hip_top3_rate",
    "a2_card_track_starts",
    "a2_card_track_win_rate",
    "a2_card_track_top3_rate",
    "a2_card_distance_starts",
    "a2_card_distance_win_rate",
    "a2_card_distance_top3_rate",
    "a2_card_jockey_starts",
    "a2_card_jockey_win_rate",
    "a2_card_jockey_top3_rate",
    "a2_card_equipment_starts",
    "a2_card_equipment_win_rate",
    "a2_card_equipment_top3_rate",
    "a2_card_recent5_starts",
    "a2_card_recent5_win_rate",
    "a2_card_recent5_top3_rate",
    "a2_card_recent5_avg_rank_inv",
    "a2_card_days_since_last",
    # Going (zemin durumu) features
    "a2_card_going_starts",
    "a2_card_going_win_rate",
    "a2_card_going_top3_rate",
    "a2_card_going_switch",
    # Penetrometre features
    "a2_card_avg_penetrometer",
    "a2_card_penetrometer_delta",
    # Par-time normalize kalite farki (tjktahmin katsayilari)
    "a2_card_avg_quality_diff",
    "a2_card_recent3_quality_diff",
    "a2_card_quality_trend",
    "a2_card_best_quality_diff",
    # Mesafe uyum skoru
    "a2_card_distance_fitness_gap",
]
