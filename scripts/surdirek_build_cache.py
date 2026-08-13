#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
surdirek_build_cache.py  v2
- Lokalson modeli bir kez yukler (yeniden egitim yok)
- HistoryMemory ilerleyerek guncellenir (hizli, O(n))
- Her gun/sehir icin surdirek secimini uretir
- results_raw ile kazandi/ganyan eslestirir
- /opt/harbi_ganyan_v3/data/surdirek_cache.json yazar
"""

from __future__ import annotations
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path("/opt/harbi_ganyan_v3")
sys.path.insert(0, str(ROOT / "src"))

DATA        = ROOT / "data"
RESULTS_DIR = DATA / "results_raw"
PROGRAM_DIR = DATA / "program_raw"
MODELS_DIR  = ROOT / "models"
CACHE_PATH  = DATA / "surdirek_cache.json"


def _load_results_day(day: date) -> dict:
    p = RESULTS_DIR / f"{day:%Y-%m-%d}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _kazandi_ganyan(results, hip, race_no, horse_no):
    if not results:
        return None, None
    hip_d = results.get("hippodromes", {}).get(hip.upper())
    if not hip_d:
        return None, None
    race = hip_d.get("races", {}).get(str(race_no))
    if not race:
        return None, None
    order = race.get("order") or []
    if not order:
        return None, None
    w = order[0]
    kazandi = (w.get("horse_no") == horse_no)
    return kazandi, (w.get("ganyan") if kazandi else None)


class _HorsePred:
    """Minimal duck-type for select_surdirek_multi."""
    def __init__(self, horse, norm_score, win_rate_past):
        self.horse = horse
        self.norm_score = norm_score
        self.win_rate_past = win_rate_past


class _RacePred:
    """Minimal duck-type for select_surdirek_multi."""
    def __init__(self, hip, race_no, horses, norm_score_gap, runner_count,
                 race_type="", race_group="",
                 surdirek_source_horse_no=None, surdirek_source_gap=0.0,
                 surdirek_source="production"):
        self.hip = hip
        self.race_no = race_no
        self.horses = horses
        self.norm_score_gap = norm_score_gap
        self.runner_count = runner_count
        self.race_type = race_type
        self.race_group = race_group
        self.surdirek_source_horse_no = surdirek_source_horse_no
        self.surdirek_source_gap = surdirek_source_gap
        self.surdirek_source = surdirek_source



def _surpriz_race_nos_for_day(day) -> set:
    """DB'den ilgili gun icin surpriz_radar kosu setini dondurur. Hata olursa bos set."""
    import os
    db_url = os.environ.get("HG_DATABASE_URL", "")
    if not db_url:
        print("[SURDIREK P1 UYARI] HG_DATABASE_URL tanimli degil — P1 surpriz cakisma kontrolu yapilmiyor! ""Cache P1 filtresi devre disi.", flush=True)
        return set()
    try:
        import sqlalchemy
        engine = sqlalchemy.create_engine(db_url, pool_pre_ping=True)
        with engine.connect() as conn:
            row = conn.execute(
                sqlalchemy.text("SELECT surpriz_radar FROM gun WHERE date = :d"),
                {"d": day},
            ).fetchone()
        if not row or not row[0]:
            return set()
        radar = row[0]
        result: set = set()
        for item in (radar.get("adaylar") or []):
            hip = (item.get("hip") or "").upper()
            kno = item.get("kno")
            if hip and kno is not None:
                result.add((hip, int(kno)))
        return result
    except Exception as exc:
        print(f"  [!] surpriz_radar sorgu hatasi {day}: {exc}", flush=True)
        return set()

def build_cache(days_back=30):
    import numpy as np
    from xgboost import XGBRanker, XGBClassifier
    from harbi_v3.features import FEATURE_NAMES, HistoryMemory, feature_rows_for_day, add_intrarace_ranks
    from harbi_v3.bulletin import inject_bulletin_rows
    from harbi_v3.records import parse_results, parse_program_horses, available_program_dates
    from harbi_v3.predictor import score_races, _RANKER_PARAMS, _CLASSIFIER_PARAMS
    from harbi_v3.surdirek import select_surdirek_multi
    from harbi_v3.confidence import race_type_bucket

    names = FEATURE_NAMES

    # Lokalson modelleri yukle
    ranker   = XGBRanker(**_RANKER_PARAMS)
    clf      = XGBClassifier(**_CLASSIFIER_PARAMS)
    clf_win  = XGBClassifier(**_CLASSIFIER_PARAMS)

    ranker.load_model(str(MODELS_DIR / "ranker_lokalson.json"))
    clf.load_model(str(MODELS_DIR / "clf_lokalson.json"))
    clf_win_path = MODELS_DIR / "clf_win_lokalson.json"
    if clf_win_path.exists():
        clf_win.load_model(str(clf_win_path))
    print("Modeller yuklendi.", flush=True)

    today     = date.today()
    start_day = today - timedelta(days=days_back)

    # HistoryMemory: backfill baslangicina kadar tum tarihi besle
    memory    = HistoryMemory()
    all_dates = available_program_dates(PROGRAM_DIR)
    for day in all_dates:
        if day >= start_day:
            break
        results = parse_results(day)
        feature_rows_for_day(day, memory, program_dir=PROGRAM_DIR)  # memory besle
        programs = parse_program_horses(day, PROGRAM_DIR)
        for key, race_result in results.items():
            horses = programs.get(key)
            if horses:
                memory.update_race(horses, race_result.order_by_no, race_result.time_by_no)
    print(f"Memory hazir: {start_day} oncesi beslendi.", flush=True)

    all_items: list[dict] = []
    bucket_stats: dict[str, dict] = {}

    for day in all_dates:
        if day < start_day or day > today:
            continue
        is_today = (day == today)

        # Feature uretimi
        target_rows = feature_rows_for_day(day, memory, program_dir=PROGRAM_DIR)
        inject_bulletin_rows(target_rows, day)
        add_intrarace_ranks(target_rows)

        if not target_rows:
            if not is_today:
                results_obj = parse_results(day)
                programs = parse_program_horses(day, PROGRAM_DIR)
                for key, rr in results_obj.items():
                    horses = programs.get(key)
                    if horses:
                        memory.update_race(horses, rr.order_by_no, rr.time_by_no)
            continue

        target_programs = parse_program_horses(day, PROGRAM_DIR)
        program_lookup = {}
        for (hip, rno), horses in target_programs.items():
            for h in horses:
                program_lookup[(hip, rno, h.horse_no)] = h

        target_races: dict = defaultdict(list)
        for row in target_rows:
            target_races[(row["hip"], int(row["race_no"]))].append(row)

        # Skor
        race_raw = {}
        race_source_probs = {}
        for (hip, rno) in sorted(target_races):
            rows = sorted(target_races[(hip, rno)], key=lambda r: int(r["horse_no"]))
            X = np.array([[float(r["features"].get(n, 0.0) or 0.0) for n in names] for r in rows], dtype=float)
            if X.shape[0] < 2:
                continue
            try:
                rscores = ranker.predict(X).tolist()
                cprobs  = clf.predict_proba(X)[:, 1].tolist()
                sprobs  = clf_win.predict_proba(X)[:, 1].tolist()
            except Exception as e:
                print(f"  [!] {day} {hip} R{rno} skor hatasi: {e}", flush=True)
                continue
            race_raw[(hip, rno)] = (rows, rscores, cprobs)
            race_source_probs[(hip, rno)] = sprobs

        if not race_raw:
            if not is_today:
                results_obj = parse_results(day)
                programs = parse_program_horses(day, PROGRAM_DIR)
                for key, rr in results_obj.items():
                    horses = programs.get(key)
                    if horses:
                        memory.update_race(horses, rr.order_by_no, rr.time_by_no)
            continue

        norm_scores = score_races(race_raw, program_lookup, names)

        # RacePrediction listesi
        all_races: list[RacePrediction] = []
        for (hip, rno) in sorted(race_raw):
            rows, rscores, cprobs = race_raw[(hip, rno)]
            ns      = norm_scores.get((hip, rno), [0.0] * len(rows))
            sprobs_r = race_source_probs.get((hip, rno), [0.0] * len(rows))
            hp0     = program_lookup.get((hip, rno, int(rows[0]["horse_no"])))
            bucket  = race_type_bucket(hp0.race_type if hp0 else "", hp0.race_group if hp0 else "")
            runner_count = len(rows)

            sorted_rows_ns = sorted(zip(rows, ns), key=lambda x: -x[1])
            horses_pred = [
                _HorsePred(
                    horse=program_lookup.get((hip, rno, int(r["horse_no"]))),
                    norm_score=s,
                    win_rate_past=float(r["features"].get("horse_win_rate_past") or 0.0),
                )
                for r, s in sorted_rows_ns
                if program_lookup.get((hip, rno, int(r["horse_no"])))
            ]
            if not horses_pred:
                continue

            gap = sorted_rows_ns[0][1] - sorted_rows_ns[1][1] if len(sorted_rows_ns) > 1 else 0.0
            winner_sprob = max(zip(rows, sprobs_r), key=lambda x: x[1])

            rp = _RacePred(
                hip=hip, race_no=rno,
                horses=horses_pred,
                norm_score_gap=round(gap, 2),
                runner_count=runner_count,
                race_type=hp0.race_type if hp0 else "",
                race_group=hp0.race_group if hp0 else "",
                surdirek_source_horse_no=int(winner_sprob[0]["horse_no"]),
                surdirek_source_gap=winner_sprob[1] * 30.0,
                surdirek_source="clf_win",
            )
            all_races.append(rp)

        # Sehire gore surdirek sec
        hip_map: dict[str, list] = {}
        for rp in all_races:
            hip_map.setdefault(rp.hip, []).append(rp)

        results_raw = {} if is_today else _load_results_day(day)
        surpriz_set = _surpriz_race_nos_for_day(day)

        for hip, races in sorted(hip_map.items()):
            sds = select_surdirek_multi(races, max_count=2, surpriz_race_nos=surpriz_set)
            for sd in sds:
                kazandi, ganyan = _kazandi_ganyan(results_raw, sd.hip, sd.race_no, sd.horse_no)
                item = {
                    "date":           f"{day:%Y-%m-%d}",
                    "hip":            sd.hip,
                    "race_no":        sd.race_no,
                    "horse_no":       sd.horse_no,
                    "horse_name":     sd.horse_name,
                    "gap":            round(sd.gap, 2),
                    "norm_score":     round(sd.norm_score, 2),
                    "win_rate":       round(sd.win_rate, 4),
                    "bucket":         sd.bucket,
                    "bucket_ad":      sd.bucket,
                    "kazandi":        kazandi,
                    "ganyan":         ganyan,
                    "source":         sd.source,
                    "is_fallback":    sd.is_fallback,
                    "fallback_reason": sd.fallback_reason,
                }
                all_items.append(item)
                bk = sd.bucket
                if bk not in bucket_stats:
                    bucket_stats[bk] = {"toplam": 0, "kazandi": 0}
                if kazandi is not None:
                    bucket_stats[bk]["toplam"] += 1
                    if kazandi:
                        bucket_stats[bk]["kazandi"] += 1

        # Memory guncelle
        if not is_today:
            results_obj = parse_results(day)
            programs = parse_program_horses(day, PROGRAM_DIR)
            for key, rr in results_obj.items():
                horses = programs.get(key)
                if horses:
                    memory.update_race(horses, rr.order_by_no, rr.time_by_no)

        k = sum(1 for x in all_items if x["date"] == f"{day:%Y-%m-%d}" and x.get("kazandi"))
        t = sum(1 for x in all_items if x["date"] == f"{day:%Y-%m-%d}" and x.get("kazandi") is not None)
        n = sum(1 for x in all_items if x["date"] == f"{day:%Y-%m-%d}")
        print(f"  {day}: {n} secim, {k}/{t} kazandi", flush=True)

    today_str = today.isoformat()
    bugun  = [x for x in all_items if x["date"] == today_str]
    gecmis = sorted(
        [x for x in all_items if x["date"] != today_str],
        key=lambda x: x["date"], reverse=True
    )

    bes_toplam  = sum(v["toplam"] for v in bucket_stats.values())
    bes_kazandi = sum(v["kazandi"] for v in bucket_stats.values())
    bes_yuzde   = round(100.0 * bes_kazandi / bes_toplam, 1) if bes_toplam else 0.0
    bucket_out  = {
        bk: {
            "ad": bk, "toplam": bv["toplam"], "kazandi": bv["kazandi"],
            "yuzde": round(100.0 * bv["kazandi"] / bv["toplam"], 1) if bv["toplam"] else 0.0
        }
        for bk, bv in bucket_stats.items()
    }

    cache = {
        "updated_at": today_str,
        "bugun":  bugun,
        "gecmis": gecmis,
        "istatistik": {
            "toplam":    bes_toplam,
            "kazandi":   bes_kazandi,
            "yuzde":     bes_yuzde,
            "bucketler": bucket_out,
        },
    }
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nCache yazildi: {CACHE_PATH}")
    print(f"Bugun: {len(bugun)}, Gecmis: {len(gecmis)}, Toplam isabet: {bes_kazandi}/{bes_toplam} = %{bes_yuzde}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    args = ap.parse_args()
    build_cache(days_back=args.days)
