"""
surdirek.py — Sehir bazli banko at (surdirek) secim motoru.

Filtre gecmisi (backtest 2026-07-05, holdout 2026-05-09..2026-07-03):
  - Baseline (max-gap):              %40.3
  - Bucket-weight production:        %44.5
  - Win source-policy (OOF):         %47.9
  - Filtreli win source-policy:      ~%51 (gap>=12, !handikap, other sadece gap>=20)

Uygulanan filtreler:
  1) Minimum gap: MIN_GAP_THRESHOLD alti secimler elenir.
  2) Handikap: sadece tum sehir handikap ise secilir.
  3) "other" bucket: gap < OTHER_MIN_GAP ise elenir (%25 isabet orani).
  4) Sartli + 9-11 at: orta penalti (backtest: %23.5, 12+'dan bile kotu).
  5) Sartli + 12+ at: agir penalti (backtest: %28.6).
  6) Tasra hipodrom + maiden + 9+ at: cok agir penalti (backtest ELAZIG: %19).
  7) Ikinci surdirek (multi): MULTI_MIN_GAP uzeri + guvenilir bucket varsa eklenir.

P1 (2026-07-10): Surpriz Radar cakismasi olan kosular secim havuzundan cikarilir.
  Garanti: tum eligible surpriz kosusundaysa hepsini kullan (en az 1 her sehir).
"""
from __future__ import annotations
from dataclasses import dataclass

# ── Filtre sabitleri ──────────────────────────────────────────────────────────
MIN_GAP_THRESHOLD: float = 12.0
OTHER_MIN_GAP: float = 20.0
HANDIKAP_GAP_THRESHOLD: float = 25.0
WIN_RATE_WEIGHT: float = 0.2

BUCKET_WEIGHTS: dict[str, float] = {
    "kv_grup":     1.3,
    "grup":        1.2,
    "sartli":      0.8,
    "sartli_arap": 0.65,
    "maiden":      0.6,
    "satis":       0.5,
    "other":       0.5,
    "handikap":    0.2,
}

LARGE_FIELD_RUNNER_THRESHOLD: int = 14
LARGE_FIELD_PENALTY: float = 0.5

SARTLI_MID_RUNNER: int = 9
SARTLI_MID_PENALTY: float = 0.55
SARTLI_LARGE_RUNNER: int = 12
SARTLI_LARGE_PENALTY: float = 0.35

TASRA_HIPS: frozenset[str] = frozenset({"elazig", "sanliurfa", "diyarbakir"})
TASRA_MAIDEN_LARGE_RUNNER: int = 9
TASRA_MAIDEN_PENALTY: float = 0.05

MULTI_MIN_GAP: float = 18.0

USE_SOURCE_POLICY: bool = True
_RELIABLE_BUCKETS = frozenset({"kv_grup", "grup", "sartli", "sartli_arap", "maiden"})


@dataclass
class SurdirekResult:
    hip: str
    race_no: int
    horse_no: int
    horse_name: str
    gap: float
    norm_score: float
    win_rate: float
    bucket: str
    runner_count: int = 0
    source: str = "production"
    is_fallback: bool = False
    fallback_reason: str = ""


def _is_eligible(c: dict, all_handikap: bool) -> bool:
    """Filtreleme kurallarini uygular. False donerse secim havuzuna girmiyor."""
    bucket = c["bucket"]
    gap = c["gap"]
    if gap < MIN_GAP_THRESHOLD:
        return False
    if bucket == "handikap" and not all_handikap:
        return False
    if bucket == "other" and gap < OTHER_MIN_GAP:
        return False
    return True


def _score(c: dict) -> float:
    """Secim skoru: gap * bucket_weight * runner_penalty."""
    bucket = c["bucket"]
    runner_count = c.get("runner_count", 0)
    hip = c.get("hip", "").lower()
    runner_penalty = LARGE_FIELD_PENALTY if runner_count >= LARGE_FIELD_RUNNER_THRESHOLD else 1.0
    if bucket == "sartli":
        if runner_count >= SARTLI_LARGE_RUNNER:
            runner_penalty *= SARTLI_LARGE_PENALTY
        elif runner_count >= SARTLI_MID_RUNNER:
            runner_penalty *= SARTLI_MID_PENALTY
    if bucket == "maiden" and runner_count >= TASRA_MAIDEN_LARGE_RUNNER and hip in TASRA_HIPS:
        runner_penalty *= TASRA_MAIDEN_PENALTY
    return c["gap"] * BUCKET_WEIGHTS.get(bucket, 1.0) * runner_penalty


def _build_candidates(all_races: list) -> tuple[list[dict], list[dict]]:
    """Ham kosu listesinden production ve source aday listelerini toplar."""
    from .confidence import race_type_bucket
    production: list[dict] = []
    source: list[dict] = []
    for race in all_races:
        if not race.horses:
            continue
        top = race.horses[0]
        bucket = race_type_bucket(race.race_type, race.race_group)
        base = {
            "hip":          race.hip,
            "race_no":      race.race_no,
            "bucket":       bucket,
            "runner_count": race.runner_count,
        }
        production.append({
            **base,
            "horse_no":   top.horse.horse_no,
            "horse_name": top.horse.horse_name,
            "gap":        race.norm_score_gap,
            "norm_score": top.norm_score,
            "win_rate":   top.win_rate_past,
            "source":     "production",
        })
        source_hno = getattr(race, "surdirek_source_horse_no", None)
        source_gap = float(getattr(race, "surdirek_source_gap", 0.0) or 0.0)
        if USE_SOURCE_POLICY and source_hno and source_gap > 0.0:
            source_pred = next(
                (h for h in race.horses if h.horse.horse_no == source_hno), None
            )
            if source_pred:
                source.append({
                    **base,
                    "horse_no":   source_pred.horse.horse_no,
                    "horse_name": source_pred.horse.horse_name,
                    "gap":        source_gap,
                    "norm_score": source_pred.norm_score,
                    "win_rate":   source_pred.win_rate_past,
                    "source":     getattr(race, "surdirek_source", "source"),
                })
    return production, source


def select_surdirek_multi(
    all_races: list,
    max_count: int = 2,
    surpriz_race_nos: set | None = None,
) -> list[SurdirekResult]:
    """
    Sehirdeki tum kosular icin en iyi 1-2 surdirek atini secer.

    Parametre:
        all_races: list[RacePrediction]  (predictor.py'den, tek sehir)
        max_count: maksimum surdirek sayisi (varsayilan 2)
        surpriz_race_nos: set[(hip, race_no)] — bu kosular normal havuzdan cikarilir (P1).

    Donus:
        list[SurdirekResult] — her zaman en az 1 eleman (sehirde kosu varsa).

    Garanti: Filtreler hicbir adayi gecirmese bile en iyi skoru olan aday
             fallback olarak secilir. Her sehir mutlaka 1 surdirek alir.
    """
    if not all_races:
        return []

    production, source = _build_candidates(all_races)
    candidates = source if source else production
    if not candidates:
        return []

    all_handikap = all(c["bucket"] == "handikap" for c in candidates)
    eligible = [c for c in candidates if _is_eligible(c, all_handikap)]

    # P1: Surpriz Radar cakismasi olan kosulari secim havuzundan cikar
    surpriz = surpriz_race_nos or set()
    if surpriz and eligible:
        eligible_no_surpriz = [c for c in eligible if (c["hip"], c["race_no"]) not in surpriz]
        if eligible_no_surpriz:
            eligible = eligible_no_surpriz
        else:
            # Tum eligible adaylar surpriz kosusunda — garanti icin aynen kullan
            _hip = eligible[0].get("hip", "?")
            print(f"[SURDIREK P1] {_hip}: tum eligible surpriz kosusunda, garantiyle seciliyor.", flush=True)

    # Siralama: source policy varsa gap'e gore, yoksa skora gore
    use_source = bool(source)
    sort_key = (lambda c: c["gap"]) if use_source else _score

    if not eligible:
        # Fallback: filtreler hepsini eledi; en iyi skoru olan adayi sec.
        non_handi = [c for c in candidates if c["bucket"] != "handikap"]
        fallback_pool = non_handi if non_handi else candidates
        # P1: fallback havuzundan da once surprizsiz adayi sec
        _fallback_reason = "fallback_gap"
        if surpriz:
            no_surpriz_fb = [c for c in fallback_pool if (c["hip"], c["race_no"]) not in surpriz]
            if no_surpriz_fb:
                fallback_pool = no_surpriz_fb
                _fallback_reason = "fallback_p1"
                print(
                    f"[SURDIREK P1 FALLBACK] {fallback_pool[0].get('hip', '?')}: "
                    f"gap filtresi eledi, surprizsiz fallback kullanildi.",
                    flush=True,
                )
            elif fallback_pool:
                _fallback_reason = "fallback_gap_surpriz_all"
                print(
                    f"[SURDIREK P1 FALLBACK] {fallback_pool[0].get('hip', '?')}: "
                    f"surprizsiz aday yok, garantiyle surpriz kosusundan seciyor.",
                    flush=True,
                )
        best_fallback = max(fallback_pool, key=sort_key)
        if best_fallback["gap"] < MIN_GAP_THRESHOLD:
            print(
                f"[SURDIREK FALLBACK-GAP] {best_fallback.get('hip', '?')}: "
                f"R{best_fallback.get('race_no')} gap={best_fallback['gap']:.2f} < "
                f"MIN_GAP({MIN_GAP_THRESHOLD}), fallback-gap secimi.",
                flush=True,
            )
        result = SurdirekResult(**best_fallback)
        result.is_fallback = True
        result.fallback_reason = _fallback_reason
        return [result]

    sorted_elig = sorted(eligible, key=sort_key, reverse=True)

    results: list[SurdirekResult] = []
    seen_races: set = set()

    for c in sorted_elig:
        if len(results) >= max_count:
            break
        race_key = (c["hip"], c["race_no"])
        if race_key in seen_races:
            continue
        if results and (c["gap"] < MULTI_MIN_GAP or c["bucket"] not in _RELIABLE_BUCKETS):
            continue
        seen_races.add(race_key)
        results.append(SurdirekResult(**c))

    return results


def select_surdirek(all_races: list) -> SurdirekResult | None:
    """Geriye donuk uyumluluk icin tekil surdirek secimi."""
    results = select_surdirek_multi(all_races, max_count=1)
    return results[0] if results else None
