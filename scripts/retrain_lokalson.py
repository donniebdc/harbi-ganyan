# -*- coding: utf-8 -*-
"""
retrain_lokalson.py  —  Yeni feature setiyle lokalson modelini sifirdan egitir.

Kullanim:
    python scripts/retrain_lokalson.py

Ne yapar:
  1. Tum mevcut veriden feature matrislerini _prebuild_matrices ile uretir (cache'e yazar).
  2. Cache'ten egitim datasini yukler.
  3. train_models() ile ranker + clf egitir, win/top2 classifier'lari ayrica egitir.
  4. models/ranker_lokalson.json + models/clf_lokalson.json + clf_win_lokalson.json + clf_top2_lokalson.json olarak kaydeder.

Geri donmek icin:
  models/backup_pre_klasman_signal1/ klasorunden kopyala.
"""
import sys, time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.features import FEATURE_NAMES
from harbi_v3.records import available_program_dates, parse_results
from harbi_v3.predictor import train_classifier, train_models
from harbi_v3.evaluation.cache import feature_set_hash
from harbi_v3.evaluation.harness import _prebuild_matrices, _load_matrix
from harbi_v3.paths import MODELS_DIR

NAMES = list(FEATURE_NAMES)
FHASH = feature_set_hash(NAMES)

def main():
    all_dates = sorted(available_program_dates())
    yesterday = date.today() - timedelta(days=1)
    train_dates = [d for d in all_dates if d <= yesterday]
    if not train_dates:
        print("Hata: egitim tarihi bulunamadi")
        sys.exit(1)

    train_start = train_dates[0]
    train_end   = train_dates[-1]
    print(f"Feature hash : {FHASH}")
    print(f"Feature sayisi: {len(NAMES)}")
    print(f"Egitim penceresi: {train_start} .. {train_end}  ({len(train_dates)} gun)")
    print()

    # 1. Feature matrislerini uret / cache'ten yukle
    t0 = time.time()
    print("Adim 1/3: Feature matrisleri olusturuluyor (ilk calistirmada yavas)...")
    _prebuild_matrices(all_dates, train_start, train_end, NAMES, FHASH)
    print(f"  -> {time.time()-t0:.0f}s")

    # 2. Egitim verisini topla
    t1 = time.time()
    print("Adim 2/3: Egitim verisi yukleniyor...")
    all_x, all_yr, all_yc, all_y_win, all_y_top2, all_g = [], [], [], [], [], []
    for d in train_dates:
        dm = _load_matrix(d, FHASH)
        results = parse_results(d)
        for race in dm["races"]:
            rws = [r for r in race["rows"] if r["has_result"]]
            if len(rws) < 2:
                continue
            result = results.get((race["key"][0], int(race["key"][1])))
            if not result:
                continue
            all_g.append(len(rws))
            for r in rws:
                rank = result.order_by_no.get(int(r["horse_no"]), 99)
                all_x.append(r["feat"])
                all_yr.append(r["y_rank"])
                all_yc.append(r["y_cls"])
                all_y_win.append(int(rank == 1))
                all_y_top2.append(int(1 <= rank <= 2))

    print(f"  -> {len(all_x)} satir, {len(all_g)} kos  ({time.time()-t1:.0f}s)")

    if not all_x:
        print("Hata: egitim satiri bulunamadi")
        sys.exit(1)

    # 3. Model egit
    t2 = time.time()
    print("Adim 3/3: Modeller egitiliyor...")
    ranker, clf = train_models(all_x, all_yr, all_yc, all_g)
    clf_win = train_classifier(all_x, all_y_win)
    clf_top2 = train_classifier(all_x, all_y_top2)
    print(f"  -> {time.time()-t2:.0f}s")

    # 4. Kaydet
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    ranker_path = MODELS_DIR / f"ranker_{today_str}.json"
    clf_path    = MODELS_DIR / f"clf_{today_str}.json"
    clf_win_path = MODELS_DIR / f"clf_win_{today_str}.json"
    clf_top2_path = MODELS_DIR / f"clf_top2_{today_str}.json"
    ranker_lok  = MODELS_DIR / "ranker_lokalson.json"
    clf_lok     = MODELS_DIR / "clf_lokalson.json"
    clf_win_lok = MODELS_DIR / "clf_win_lokalson.json"
    clf_top2_lok = MODELS_DIR / "clf_top2_lokalson.json"

    ranker.save_model(str(ranker_path))
    clf.save_model(str(clf_path))
    clf_win.save_model(str(clf_win_path))
    clf_top2.save_model(str(clf_top2_path))
    ranker.save_model(str(ranker_lok))
    clf.save_model(str(clf_lok))
    clf_win.save_model(str(clf_win_lok))
    clf_top2.save_model(str(clf_top2_lok))

    print()
    print(f"Kaydedildi:")
    print(f"  {ranker_path}")
    print(f"  {clf_path}")
    print(f"  {clf_win_path}")
    print(f"  {clf_top2_path}")
    print(f"  {ranker_lok}")
    print(f"  {clf_lok}")
    print(f"  {clf_win_lok}")
    print(f"  {clf_top2_lok}")
    print(f"Toplam sure: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
