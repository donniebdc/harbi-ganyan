from __future__ import annotations

from dataclasses import dataclass

from .confidence import CONFIDENCE_THRESHOLDS_BY_TYPE, DEFAULT_CONFIDENCE_THRESHOLDS, race_type_bucket
from .predictor import HorsePrediction, RacePrediction
from .records import eku_partners

# norm_text()-normalized hippodrome names that use the 1 TL birim fiyat (others use 1.25 TL).
DIYARBAKIR_ELAZIG = {"DIYARBAKIR", "ELAZIG"}

TIER_NAMES_AND_BUDGETS = [("Mini", 600.0), ("Standart", 1800.0), ("Geniş", 3200.0)]


def unit_price_for(hip: str) -> float:
    return 1.0 if hip in DIYARBAKIR_ELAZIG else 1.25


def select_top_n(
    ranked: list[HorsePrediction], partners: dict[int, list[int]], n: int
) -> list[HorsePrediction]:
    """Siralanmis listeden (en yuksek puandan) ilk n'i secer; bir atin eguri
    ortagi zaten secilmisse o at atlanir, siradaki farkli at terfi eder.
    tahmin.py:_resolve_eku_top5, n=5 ile bu fonksiyonu cagiran ince bir
    sarmalayicidir — mantik tek yerde."""
    selected: list[HorsePrediction] = []
    selected_nos: set[int] = set()
    for h in ranked:
        no = h.horse.horse_no
        if any(p in selected_nos for p in partners.get(no, [])):
            continue
        selected.append(h)
        selected_nos.add(no)
        if len(selected) == n:
            break
    return selected


def _confidence_priority(race: RacePrediction) -> tuple[int, float]:
    """Buyume sirasi anahtari: (guven_kademe_rank, gap). Once kademe artan
    (DUSUK=0 ilk buyur, COK_YUKSEK=3 son buyur), esitlikte kucuk gap once
    buyur."""
    bucket = race_type_bucket(race.race_type, race.race_group)
    cok_yuksek, yuksek, orta = CONFIDENCE_THRESHOLDS_BY_TYPE.get(bucket, DEFAULT_CONFIDENCE_THRESHOLDS)
    gap = race.norm_score_gap
    if gap >= cok_yuksek:
        rank = 3
    elif gap >= yuksek:
        rank = 2
    elif gap >= orta:
        rank = 1
    else:
        rank = 0
    return (rank, gap)


# Koşu tipi banko güvenilirliği (segment raporundaki favori isabet oranlarından)
_TYPE_BANKO_RELIABILITY = {
    "kv_grup": 1.00,   # %36.4 favori → en güvenilir banko
    "sartli":  0.85,   # %33.6 favori
    "other":   0.65,   # %28.8 favori
    "maiden":  0.55,   # %30.5 favori ama deneyimsiz at → riskli
    "handikap": 0.40,  # %26.8 favori → en riskli, bankodan kaçın
}


def _banko_score(leg: _Leg) -> float:
    """Bir ayagin banko (tek at) olmaya uygunluk skoru.

    Yüksek skor = banko için daha uygun.
    Düşük skor = banko riskli, esnek davranılmalı.
    """
    bucket = race_type_bucket(leg.race.race_type, leg.race.race_group)
    type_rel = _TYPE_BANKO_RELIABILITY.get(bucket, 0.50)
    conf_rank, gap = leg.priority_key

    # Saha boyutu cezası: büyük saha → daha riskli banko
    rc = leg.runner_count
    if rc <= 7:
        field_factor = 1.2
    elif rc <= 10:
        field_factor = 1.0
    elif rc <= 13:
        field_factor = 0.75
    else:
        field_factor = 0.50  # 14+ at → banko çok riskli

    # Handikap + büyük saha: neredeyse hiç banko yapma
    if bucket == "handikap" and rc >= 11:
        return -1.0  # asla banko seçilmez (diğer ayaklar öncelikli)

    # Maiden + DÜŞÜK/ORTA güven: banko yapma
    if bucket == "maiden" and conf_rank <= 1:
        return -0.5

    return type_rel * (1.0 + conf_rank / 3.0) * field_factor


@dataclass
class _Leg:
    race_no: int
    runner_count: int
    priority_key: tuple[int, float]
    race: RacePrediction


@dataclass
class LegSelection:
    race_no: int
    width: int
    runner_count: int
    horses: list[HorsePrediction]


@dataclass
class TierCoupon:
    tier_name: str
    budget_cap: float
    actual_cost: float
    legs: list[LegSelection]


@dataclass
class AltiliPoolCoupons:
    pool_index: int
    start_race: int
    tiers: list[TierCoupon]


def _cost_of(widths: dict[int, int], legs: list[_Leg], unit_price: float) -> float:
    product = 1.0
    for leg in legs:
        product *= widths[leg.race_no]
    return product * unit_price


def _grow_round_robin(legs: list[_Leg], budget: float, unit_price: float) -> dict[int, int]:
    """Her ayak K=1'den baslar. Oncelik sirasiyla (en belirsiz once) her turda
    +1 denenir, butceyi asmiyorsa kalir; tum ayaklar maksimuma ulasana veya
    bir tam tur hic buyume olmayana kadar tekrar edilir."""
    widths = {leg.race_no: 1 for leg in legs}
    ordered = sorted(legs, key=lambda leg: leg.priority_key)
    progress = True
    while progress:
        progress = False
        for leg in ordered:
            if widths[leg.race_no] >= leg.runner_count:
                continue
            widths[leg.race_no] += 1
            if _cost_of(widths, legs, unit_price) <= budget:
                progress = True
            else:
                widths[leg.race_no] -= 1
    return widths


def _shrink_round_robin(
    legs: list[_Leg], budget: float, unit_price: float, start_widths: dict[int, int],
    reverse_priority: bool = True,
) -> dict[int, int]:
    """start_widths'tan baslar, butceye sigana kadar kucultur.

    reverse_priority=True (varsayilan): en guvenli ayaklar once kucultulur
      (banko ayaklari feda et, surpriz ayaklari genis tut — Mini icin ideal).

    reverse_priority=False: en belirsiz ayaklar once kucultulur
      (banko ayaklari koru, surpriz ayaklarda risk al — Standart icin ideal).

    Sadece kucultur — asla buyutmez, nested (alt kume) garantisi korunur."""
    widths = dict(start_widths)
    ordered = sorted(legs, key=lambda leg: leg.priority_key, reverse=reverse_priority)
    while _cost_of(widths, legs, unit_price) > budget:
        shrank_any = False
        for leg in ordered:
            if widths[leg.race_no] <= 1:
                continue
            widths[leg.race_no] -= 1
            shrank_any = True
            if _cost_of(widths, legs, unit_price) <= budget:
                break
        if not shrank_any:
            break
    final_cost = _cost_of(widths, legs, unit_price)
    if final_cost > budget:
        raise RuntimeError(
            f"Butceye sigamadi: tum ayaklar K=1'e indi ama maliyet ({final_cost:.2f}) "
            f"hala butceyi ({budget}) asiyor — birim fiyat cok yuksek olabilir."
        )
    return widths


def build_pool_coupons(
    pool_index: int,
    start_race: int,
    races_by_no: dict[int, RacePrediction],
    unit_price: float,
) -> AltiliPoolCoupons | None:
    legs: list[_Leg] = []
    for race_no in range(start_race, start_race + 6):
        race = races_by_no.get(race_no)
        if race is None:
            return None
        legs.append(_Leg(
            race_no=race_no,
            runner_count=len(race.horses),
            priority_key=_confidence_priority(race),
            race=race,
        ))

    # Banko ayak: tip-bazli guvenilirlik + guven araligi + saha boyutu
    # ile en uygun ayak secilir. Handikap/buyuk saha → bankodan kacin.
    banko_leg = max(legs, key=_banko_score)
    banko_rno = banko_leg.race_no
    free_legs = [leg for leg in legs if leg.race_no != banko_rno]

    # 5 serbest ayak uzerinden buyut/kucult
    genis_free = _grow_round_robin(free_legs, 3200.0, unit_price)
    standart_raw = _grow_round_robin(free_legs, 1800.0, unit_price)
    standart_free = {rno: min(standart_raw[rno], genis_free[rno]) for rno in genis_free}
    mini_free = _shrink_round_robin(free_legs, 600.0, unit_price, standart_free)

    # Tam width haritasi: banko ayak K=1
    genis_widths = {**genis_free, banko_rno: 1}
    standart_widths = {**standart_free, banko_rno: 1}
    mini_widths = {**mini_free, banko_rno: 1}

    for leg in legs:
        rno = leg.race_no
        if not (mini_widths[rno] <= standart_widths[rno] <= genis_widths[rno]):
            raise RuntimeError(
                f"Nesting ihlali: kosu {rno} mini={mini_widths[rno]} "
                f"standart={standart_widths[rno]} genis={genis_widths[rno]}"
            )

    tier_widths = [("Mini", 600.0, mini_widths), ("Standart", 1800.0, standart_widths), ("Geniş", 3200.0, genis_widths)]
    tiers: list[TierCoupon] = []
    for tier_name, budget_cap, widths in tier_widths:
        leg_selections: list[LegSelection] = []
        for leg in legs:
            ranked = sorted(leg.race.horses, key=lambda h: h.rank)
            partners = eku_partners([h.horse for h in ranked])
            width = widths[leg.race_no]
            chosen = select_top_n(ranked, partners, width)
            leg_selections.append(LegSelection(
                race_no=leg.race_no, width=width, runner_count=leg.runner_count, horses=chosen,
            ))
        actual_cost = _cost_of(widths, legs, unit_price)
        tiers.append(TierCoupon(
            tier_name=tier_name, budget_cap=budget_cap, actual_cost=actual_cost, legs=leg_selections,
        ))

    return AltiliPoolCoupons(pool_index=pool_index, start_race=start_race, tiers=tiers)
