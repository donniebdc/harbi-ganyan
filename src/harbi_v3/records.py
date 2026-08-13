from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from .dates import parse_date
from .normalize import norm_text
from .paths import HORSE_CARDS_RAW_DIR, PROGRAM_RAW_DIR, RESULTS_RAW_DIR


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return default


def _name(obj: object) -> str:
    if isinstance(obj, dict):
        return str(obj.get("name") or obj.get("shortName") or "").strip()
    return ""


def _parse_grade_time(s: str) -> float:
    """'M.SS.HH' formatını toplam saniyeye çevirir. Boş/hatalı → 0.0."""
    if not s or not isinstance(s, str):
        return 0.0
    parts = s.strip().split(".")
    if len(parts) != 3:
        return 0.0
    try:
        return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100.0
    except (ValueError, IndexError):
        return 0.0


def _parse_sale_price(raw: object) -> float:
    """'900.000 TL' -> 900000.0, None/'' -> 0.0"""
    s = str(raw or "").replace(".", "").replace(",", "").replace("TL", "").replace("₺", "").strip()
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def _parse_best_grade(raw: object) -> dict:
    grade_str = ""
    at_current_hip = 0.0
    if isinstance(raw, dict):
        grade_str = str(raw.get("value") or "").strip()
        at_current_hip = 1.0 if raw.get("bestDegreeHippodrome") else 0.0
    secs = _parse_grade_time(grade_str)
    return {
        "best_grade_seconds": secs,
        "has_best_grade": 1.0 if secs > 0.0 else 0.0,
        "best_grade_at_current_hip": at_current_hip if secs > 0.0 else 0.0,
    }


def _extract_atkodu(training_video: object) -> str:
    text = str(training_video or "")
    query = re.search(r"Atkodu=(\d+)", text)
    if query:
        return query.group(1)
    mp4 = re.search(r"/(\d+)-(\d+)\.mp4(?:\?|$)", text)
    if mp4:
        return mp4.group(2)
    return ""


@lru_cache(maxsize=1)
def _unique_card_code_by_horse_name() -> dict[str, str]:
    """Recover AtKodu for program rows whose trainingVideo field is empty.

    The map is built only from already stored card files and only when a horse
    name maps to exactly one card code, so ambiguous names are ignored.
    """
    name_to_codes: dict[str, set[str]] = {}
    for path in HORSE_CARDS_RAW_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = norm_text((data.get("program_identity") or {}).get("horse_name") or "")
        if not name:
            continue
        name_to_codes.setdefault(name, set()).add(path.stem)
    return {name: next(iter(codes)) for name, codes in name_to_codes.items() if len(codes) == 1}


def _resolve_atkodu(training_video: object, horse_name: object) -> str:
    direct = _extract_atkodu(training_video)
    if direct:
        return direct
    return _unique_card_code_by_horse_name().get(norm_text(horse_name), "")


def distance_bucket(distance: int) -> str:
    if distance <= 1200:
        return "sprint"
    if distance <= 1600:
        return "mile"
    if distance <= 2100:
        return "middle"
    return "long"


@dataclass(frozen=True)
class HorseProgram:
    run_date: date
    hip: str
    race_no: int
    horse_no: int
    horse_name: str
    jockey_name: str
    trainer_name: str
    owner_name: str
    sire_name: str
    dam_sire_name: str
    equipment: str
    equipment_added: tuple[str, ...]
    equipment_removed: tuple[str, ...]
    age_text: str
    weight: float
    handicap: float
    kgs: float
    last20: float
    last6_places: tuple[int, ...]
    last6_tracks: tuple[str, ...]
    race_track: str
    race_distance: int
    race_type: str
    race_group: str
    start_box: int
    runner_count: int
    best_grade_seconds: float = 0.0
    has_best_grade: float = 0.0
    best_grade_at_current_hip: float = 0.0
    is_jockey_changed: bool = False
    overweight: float = 0.0
    foal_country: str = ""
    race_gender: str = ""
    race_prize_tl: float = 0.0
    race_course_changed: bool = False
    race_distance_changed: bool = False
    atkodu: str = ""
    is_stablemate: bool = False
    # ── Yeni: Going + Penetrometre ──
    going: str = ""
    penetrometer: float = 0.0
    # ── Yeni: Program API genisletme ──
    birthdate: date | None = None
    weight_loss: float = 0.0
    is_apprentice_horse: bool = False
    mother_name: str = ""
    father_of_father_name: str = ""
    mother_of_father_name: str = ""
    mother_of_mother_name: str = ""
    breeder_name: str = ""
    race_bonus_tl: float = 0.0
    race_hour_num: float = 0.0
    season_day: int = 0
    weather_temp: float = 0.0
    weather_humidity: float = 0.0
    sale_price: float = 0.0


def eku_partners(horses: list[HorseProgram]) -> dict[int, list[int]]:
    """Bir kosudaki at listesinden eguri ortaklik haritasi cikarir.
    Donus: {at_no: [diger_eguri_ortaginin_at_no'lari]}. Eguri yoksa at_no haritada yer almaz."""
    groups: dict[str, list[int]] = {}
    for h in horses:
        if not h.is_stablemate or not h.owner_name:
            continue
        groups.setdefault(h.owner_name, []).append(h.horse_no)
    partners: dict[int, list[int]] = {}
    for group_horse_nos in groups.values():
        if len(group_horse_nos) < 2:
            continue  # tek at stablemate=1 ama esi yok (veri tutarsizligi, gormezden gel)
        for no in group_horse_nos:
            partners[no] = [n for n in group_horse_nos if n != no]
    return partners


@dataclass(frozen=True)
class RaceResult:
    run_date: date
    hip: str
    race_no: int
    winner_no: int
    order_by_no: dict[int, int]
    runner_count: int
    track: str
    distance: int
    winner_ganyan: float | None = None  # kazanan atın ganyan ikramiyesi
    ganyan_by_no: dict[int, float] = None  # {horse_no: ganyan}
    time_by_no: dict[int, float] = None  # {horse_no: bitiş süresi saniye}
    finish_order: tuple[dict, ...] = ()
    betting_results_text: str = ""
    betting_results: tuple[dict, ...] = ()


def load_program_day(day: date, program_dir: Path = PROGRAM_RAW_DIR) -> dict:
    """Bir güne ait program verisini yükler.

    Önce birleşik dosyayı ({date}.json) dener.
    Yoksa şehir bazlı dizinden ({date}/*.json) tüm şehirleri birleştirir.
    """
    path = program_dir / f"{day:%Y-%m-%d}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    # Şehir bazlı dizinden birleştir
    city_dir = program_dir / f"{day:%Y-%m-%d}"
    if city_dir.is_dir():
        merged: dict = {}
        for city_path in sorted(city_dir.glob("*.json")):
            try:
                city_data = json.loads(city_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if merged:
                # İlk şehirden sonra gelenleri birleştir
                merged.setdefault("hippodromes", {}).update(
                    city_data.get("hippodromes", {})
                )
            else:
                merged = city_data
        if merged:
            return merged
    return {}


def load_program_city(day: date, city: str, program_dir: Path = PROGRAM_RAW_DIR) -> dict:
    """Tek bir şehrin program verisini yükler.

    Önce {date}/{CITY}.json dosyasını dener.
    Yoksa birleşik dosyadan o şehri çıkarır.
    """
    city_norm = city.upper()
    city_path = program_dir / f"{day:%Y-%m-%d}" / f"{city_norm}.json"
    if city_path.exists():
        return json.loads(city_path.read_text(encoding="utf-8"))

    # Birleşik dosyadan çıkar
    full = load_program_day(day, program_dir)
    if full and city_norm in full.get("hippodromes", {}):
        return {
            "date": full.get("date", f"{day:%Y-%m-%d}"),
            "source": full.get("source", ""),
            "hippodromes": {city_norm: full["hippodromes"][city_norm]},
        }
    return {}


def load_result_day(day: date, results_dir: Path = RESULTS_RAW_DIR) -> dict:
    path = results_dir / f"{day:%Y-%m-%d}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def available_program_dates(program_dir: Path = PROGRAM_RAW_DIR) -> list[date]:
    """Eğitim için kullanılabilir program tarihlerini döndürür.

    Hem birleşik dosyaları ({date}.json) hem de şehir bazlı dizinleri
    ({date}/) tarar.
    """
    dates: set[date] = set()
    for path in sorted(program_dir.glob("*.json")):
        try:
            dates.add(parse_date(path.stem))
        except ValueError:
            continue
    for path in sorted(program_dir.glob("*")):
        if not path.is_dir():
            continue
        try:
            dates.add(parse_date(path.name))
        except ValueError:
            continue
    return sorted(dates)


def parse_program_horses(day: date, program_dir: Path = PROGRAM_RAW_DIR) -> dict[tuple[str, int], list[HorseProgram]]:
    data = load_program_day(day, program_dir)
    out: dict[tuple[str, int], list[HorseProgram]] = {}
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        details = hip_data.get("details") or {}
        for race in details.get("races") or []:
            race_no = _to_int(race.get("number"))
            if race_no <= 0:
                continue
            horses = race.get("horses") or []
            # Race seviyesi alanlar (her at satırına kopyalanır)
            race_gender = str(race.get("gender") or "").strip()
            prizes = race.get("prizes") or []
            race_prize_tl = 0.0
            if isinstance(prizes, list) and prizes:
                try:
                    race_prize_tl = float(prizes[0])
                except (TypeError, ValueError):
                    race_prize_tl = 0.0
            bonuses = race.get("bonuses") or []
            race_bonus_tl = 0.0
            if isinstance(bonuses, list) and bonuses:
                try:
                    race_bonus_tl = float(bonuses[0])
                except (TypeError, ValueError):
                    race_bonus_tl = 0.0
            race_course_changed = bool(str(race.get("raceCourseChanged") or "").strip())
            race_distance_changed = bool(str(race.get("distanceChanged") or "").strip())
            # ── Going + Penetrometre: raceCourseType'ten yuzeyi al, raceCourse[] array'inden eslesen status/weight'i bul ──
            race_course_type = str(race.get("raceCourseType") or "").strip()
            race_going = ""
            race_penetrometer = 0.0
            # Hippodrome-level program verisinden raceCourse array'ini al
            program = hip_data.get("program") or {}
            for rc in (program.get("raceCourse") or []):
                if str(rc.get("type") or "").strip() == race_course_type:
                    race_going = str(rc.get("status") or "").strip()
                    race_penetrometer = _to_float(rc.get("weight"))
                    break
            # ── Hava durumu + sezon bilgisi ──
            weather = program.get("weather") or {}
            weather_temp = _to_float(weather.get("temperature"))
            weather_humidity = _to_float(weather.get("humidity"))
            season_day = _to_int(program.get("totalDay"))
            # ── Race hour ──
            race_info = program.get("raceInfo") or {}
            race_hour_str = str(race_info.get("hour") or race.get("hour") or "0").strip()
            race_hour_num = 0.0
            if ":" in race_hour_str:
                try:
                    h, m = race_hour_str.split(":", 1)
                    race_hour_num = float(h) + float(m) / 60.0
                except (ValueError, TypeError):
                    pass
            rows = []
            running_horses = [h for h in horses if _to_int(h.get("number")) > 0 and h.get("status") is not False]
            for horse in running_horses:
                no = _to_int(horse.get("number"))
                equipment_changes = horse.get("equipmentChanges") or {}
                parents = horse.get("parents") or {}
                jockey_obj = horse.get("jockey") or {}
                # ── Dogum tarihi ──
                birth_epoch = horse.get("birthdateEpoch")
                birthdate = None
                if birth_epoch:
                    try:
                        birthdate = datetime.fromtimestamp(int(birth_epoch)).date()
                    except (ValueError, TypeError, OSError):
                        pass
                # ── Kilo indirimi ──
                weight_loss_raw = str(horse.get("weightLoss") or "").strip()
                weight_loss = _to_float(weight_loss_raw) if weight_loss_raw else 0.0
                rows.append(HorseProgram(
                    run_date=day,
                    hip=norm_text(hip),
                    race_no=race_no,
                    horse_no=no,
                    horse_name=str(horse.get("name") or "").strip(),
                    jockey_name=_name(horse.get("jockey")),
                    trainer_name=_name(horse.get("coach")),
                    owner_name=_name(horse.get("owner")),
                    sire_name=_name(parents.get("father")),
                    dam_sire_name=_name(parents.get("fatherOfMother")),
                    equipment=str(horse.get("equipment") or "").strip(),
                    equipment_added=tuple(str(x).strip() for x in (equipment_changes.get("added") or []) if str(x).strip()),
                    equipment_removed=tuple(str(x).strip() for x in (equipment_changes.get("removed") or []) if str(x).strip()),
                    age_text=str(horse.get("age") or "").strip(),
                    weight=_to_float(horse.get("weight")),
                    handicap=_to_float(horse.get("handicap")),
                    kgs=_to_float(horse.get("kgs")),
                    last20=_to_float(horse.get("last20")),
                    last6_places=tuple(_to_int(x.get("result")) for x in (horse.get("last6") or []) if isinstance(x, dict)),
                    last6_tracks=tuple(str(x.get("raceCourseType") or "").strip() for x in (horse.get("last6") or []) if isinstance(x, dict)),
                    race_track=race_course_type,
                    race_distance=_to_int(race.get("distance")),
                    race_type=str(race.get("typeDescription") or "").strip(),
                    race_group=str(race.get("groupName") or race.get("name") or "").strip(),
                    start_box=_to_int(horse.get("start")),
                    runner_count=len(running_horses),
                    is_jockey_changed=bool(jockey_obj.get("isJockeyChanged", False)),
                    overweight=_to_float(horse.get("overweight")),
                    foal_country=str(horse.get("foal") or "").strip(),
                    race_gender=race_gender,
                    race_prize_tl=race_prize_tl,
                    race_course_changed=race_course_changed,
                    race_distance_changed=race_distance_changed,
                    atkodu=_resolve_atkodu(horse.get("trainingVideo"), horse.get("name")),
                    is_stablemate=bool(_to_int(horse.get("stablemate"))),
                    # Yeni alanlar
                    going=race_going,
                    penetrometer=race_penetrometer,
                    birthdate=birthdate,
                    weight_loss=weight_loss,
                    is_apprentice_horse=bool(horse.get("apprenticeFLG", False)),
                    mother_name=_name(parents.get("mother")),
                    father_of_father_name=_name(parents.get("fatherOfFather")),
                    mother_of_father_name=_name(parents.get("motherOfFather")),
                    mother_of_mother_name=_name(parents.get("motherOfMother")),
                    breeder_name=_name(horse.get("breeder")),
                    race_bonus_tl=race_bonus_tl,
                    race_hour_num=race_hour_num,
                    season_day=season_day,
                    weather_temp=weather_temp,
                    weather_humidity=weather_humidity,
                    sale_price=_parse_sale_price(horse.get("salePrice")),
                    **_parse_best_grade(horse.get("bestGrade")),
                ))
            if rows:
                out[(norm_text(hip), race_no)] = rows
    return out


def parse_results(day: date, results_dir: Path = RESULTS_RAW_DIR) -> dict[tuple[str, int], RaceResult]:
    data = load_result_day(day, results_dir)
    out = {}
    for hip, hip_data in (data.get("hippodromes") or {}).items():
        for race_no_s, race in (hip_data.get("races") or {}).items():
            race_no = _to_int(race_no_s)
            order_by_no = {}
            ganyan_by_no: dict[int, float] = {}
            time_by_no: dict[int, float] = {}
            finish_order: list[dict] = []
            winner_ganyan = None
            for row in race.get("order") or []:
                horse_no = _to_int(row.get("horse_no"))
                rank = _to_int(row.get("rank"))
                if horse_no and rank:
                    order_by_no[horse_no] = rank
                g = row.get("ganyan")
                if horse_no and g is not None:
                    try:
                        ganyan_by_no[horse_no] = float(g)
                    except (TypeError, ValueError):
                        pass
                t_sec = _parse_grade_time(str(row.get("time") or ""))
                if horse_no and t_sec > 0.0:
                    time_by_no[horse_no] = t_sec
                if horse_no and rank:
                    finish_order.append({
                        "rank": rank,
                        "horse_no": horse_no,
                        "horse_name": str(row.get("horse_name") or "").strip(),
                        "time": str(row.get("time") or "").strip(),
                        "ganyan": ganyan_by_no.get(horse_no),
                    })
            winner = _to_int(race.get("winner"))
            if winner and winner in ganyan_by_no:
                winner_ganyan = ganyan_by_no[winner]
            if race_no and winner:
                out[(norm_text(hip), race_no)] = RaceResult(
                    run_date=day,
                    hip=norm_text(hip),
                    race_no=race_no,
                    winner_no=winner,
                    order_by_no=order_by_no,
                    runner_count=_to_int(race.get("runner_count")),
                    track=str(race.get("track") or "").strip(),
                    distance=_to_int(race.get("distance")),
                    winner_ganyan=winner_ganyan,
                    ganyan_by_no=ganyan_by_no,
                    time_by_no=time_by_no,
                    finish_order=tuple(sorted(finish_order, key=lambda r: int(r.get("rank") or 99))),
                    betting_results_text=str(race.get("betting_results_text") or "").strip(),
                    betting_results=tuple(race.get("betting_results") or ()),
                )
    return out
