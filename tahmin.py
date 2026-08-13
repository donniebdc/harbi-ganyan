# -*- coding: utf-8 -*-
"""
tahmin.py — Harbi Ganyan v3 tahmin araci.

İnteraktif kullanim:
    python tahmin.py
    → Tarih sorar, hipodrom listeler, secime gore Tahminler/*.txt uretir.

Programatik kullanim (toplu.py, sonuc.py):
    from tahmin import run, parse_flexible_date, _file_stem
    written = run(day)              # tum sehirler
    written = run(day, hip="ANKARA")  # tek sehir

Cikti:
    Tahminler/DD_MM_YYYY_SEHIR.txt        (5'li satir)
    data/export_out/YYYY-MM-DD.json       (export, tum sehirler)
    data/export_out/YYYY-MM-DD_SEHIR.json (export, tek sehir)
"""

from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from harbi_v3.paths import META_DIR, TAHMINLER_DIR, ensure_dirs


def _import_scripts_tahmin():
    """scripts/tahmin.py'yi sys.path'i kirletmeden import eder."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_scripts_tahmin",
        ROOT / "scripts" / "tahmin.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_scripts_tahmin"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sessiz(fn, *args, **kwargs):
    with redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


# ── Tarih yardimcilari ──

def parse_flexible_date(raw: str) -> date | None:
    """'11.06.2026', '11-06-2026', '11062026', '2026-06-11' -> date | None"""
    raw = raw.strip()
    if not raw:
        return None
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%d%m%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# ── Dosya adi ──

def _file_stem(day: date, hip: str) -> str:
    return f"{day:%d_%m_%Y}_{hip.upper()}"


# ── Ana islev ──

def run(day: date, hip_filter: str | None = None, refresh_cards: bool = True) -> list[Path]:
    """Bir gunun tahminlerini uretir, Tahminler/*.txt yazar.

    Args:
        day: Tahmin tarihi
        hip_filter: None=tum sehirler, "ANKARA"=tek sehir
        refresh_cards: True ise prediction oncesi o gunun at kartlarini TJK'den
                       gunceller. Data leak yok: card_features(as_of=day) filtresinde
                       r.race_date < as_of zorunlu olarak uygulanir.

    Returns: yazilan txt yollari
    """
    from harbi_v3.predictor import predict_for_date
    from harbi_v3.records import load_program_day
    _st = _import_scripts_tahmin()
    format_hip_file = _st.format_hip_file
    build_meta = _st.build_meta
    _city_name = _st._city_name
    from v3_export import export_day

    ensure_dirs()

    # ── At karti guncelleme (quality_diff feature'lari icin) ──
    # Sadece bugun yarışacak atların kartları force=True ile yeniden çekilir.
    # Geri kalan 8000+ kart dokunulmaz. Toplam süre ~60-120sn.
    # DATA LEAK SAFETY: card_features(as_of=day) r.race_date < as_of filtresi
    # ZORUNLUDUR; kart icerigi ne kadar guncel olursa olsun sizinti olmaz.
    if refresh_cards:
        try:
            import importlib.util, sys as _sys
            _spec = importlib.util.spec_from_file_location(
                "_scrape_horse_cards",
                ROOT / "scripts" / "scrape_horse_cards.py",
            )
            _shc = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_shc)
            print(f"[kart-guncelle] {day} programindaki atlar guncelleniyor...")
            _shc.refresh_cards_for_day(day, verbose=True)
        except Exception as _e:
            print(f"[kart-guncelle] UYARI: at karti guncelleme basarisiz ({_e}), mevcut kartlarla devam ediliyor.")

    # ── VDS ANA MOTOR — lokal MIRROR ──
    # Lokal TJK/atyarisi'den HICBIR sey cekmez. VDS ne cektiyse (program, bulten,
    # at kartlari) ve hangi modeli egittiyse, hepsi _pull_models()
    # ile (models_pull + data_pull) baslangicta lokale cekilir. Burada sadece o veriyle
    # ayni motor calistirilir -> VDS ile birebir ayni tahmin. refresh=False ZORUNLU.

    # 5'li satir tahmini
    all_races = _sessiz(predict_for_date, day, city=hip_filter)
    if not all_races:
        return []

    from harbi_v3.surdirek import select_surdirek_multi

    # Sehire gore grupla
    hip_map: dict[str, list] = {}
    for race in all_races:
        hip_map.setdefault(race.hip, []).append(race)

    written: list[Path] = []
    for hip, races in sorted(hip_map.items()):
        surdireks = select_surdirek_multi(races)

        stem = _file_stem(day, hip)
        txt_path = TAHMINLER_DIR / f"{stem}.txt"

        content = format_hip_file(day, hip, races, surdirek=surdireks)
        txt_path.write_text(content, encoding="utf-8")
        written.append(txt_path)

        # meta.json (sonuc.py icin gerekli, data/meta/ altinda)
        meta = build_meta(day, hip, races)
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
        meta_path = META_DIR / f"{stem}_meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        # export JSON
        _sessiz(export_day, day, city=hip, refresh=False)

    # Birlesik export
    if len(hip_map) > 1:
        _sessiz(export_day, day, refresh=False)

    return written


# ── İnteraktif mod ──

def _tarih_al() -> date:
    # CLI argümanından tarih al (--local 2026-07-07 gibi)
    for arg in sys.argv[1:]:
        if not arg.startswith("--"):
            d = parse_flexible_date(arg)
            if d:
                return d
    while True:
        ham = input("Tarih (GG.AA.YYYY, bos=yarin): ").strip()
        if not ham:
            return date.today() + timedelta(days=1)
        d = parse_flexible_date(ham)
        if d:
            return d
        print("  Gecersiz. Ornek: 18.06.2026")


def _hipodrom_sec(day: date) -> list[str]:
    from harbi_v3.records import load_program_day

    iso = day.strftime("%Y-%m-%d")
    print(f"\n{iso} VDS'ten cekilen program okunuyor...")
    ensure_dirs()

    # Lokal TJK'den CEKMEZ — VDS'ten pull edilen (models_pull + data_pull) program
    # verisini okur. Boylece hipodrom/kosu listesi de VDS ile birebir ayni olur.
    data = load_program_day(day)
    hipodromlar = list(data.get("hippodromes", {}).keys())

    if not hipodromlar:
        print(f"  {iso}: VDS'te bu tarihe ait program yok (once VDS uretmeli).")
        return []

    print(f"\n{iso} - {len(hipodromlar)} hipodrom:\n")
    for i, hip in enumerate(hipodromlar, 1):
        hip_data = data["hippodromes"][hip]
        display = hip_data.get("display_name", hip)
        races = hip_data.get("details", {}).get("races", [])
        saat = races[0].get("hour", "?") if races else "?"
        print(f"  {i}. {display:15s}  {len(races)} kosu  (ilk: {saat})")

    print("\n  A. Tumu")
    print("  0. Iptal")

    # --all veya --hip argumani varsa interaktif secim atlaniyor
    if "--all" in sys.argv:
        print("  [--all] Tum hipodromlar secildi.")
        return hipodromlar
    for arg in sys.argv[1:]:
        if arg.startswith("--hip="):
            hip_arg = arg.split("=", 1)[1].upper()
            matched = [h for h in hipodromlar if h.upper() == hip_arg]
            if matched:
                return matched

    while True:
        secim = input(f"\nSecim (1-{len(hipodromlar)}/A/0): ").strip().upper()
        if secim == "0":
            return []
        if secim == "A":
            return hipodromlar
        try:
            idx = int(secim) - 1
            if 0 <= idx < len(hipodromlar):
                return [hipodromlar[idx]]
        except ValueError:
            pass
        print("  Gecersiz secim.")


def _pull_vds_tahmin(day: date) -> list[Path]:
    """VDS'teki o güne ait tahmin TXT dosyalarini lokale indirir.

    Normal modda (--local yok) tahmin URETILMEZ; VDS zaten bir gun onceden
    uretmistir. Bu fonksiyon o hazir dosyalari lokal Tahminler/ klasorune
    kopyalar. Boylece lokal ile VDS farki gorulebilir.

    Donus: indirilen lokal dosya yollari. VDS baglanamazsa bos liste.
    """
    import json as _json
    try:
        import paramiko
    except ImportError:
        print("  UYARI: paramiko yuklu degil, VDS'ten tahmin cekilemedi.")
        return []

    cfg_path = ROOT / "config" / "vds.json"
    if not cfg_path.exists():
        print("  UYARI: config/vds.json bulunamadi.")
        return []
    cfg = _json.loads(cfg_path.read_text(encoding="utf-8"))

    remote_dir = cfg.get("remote_tahminler_dir", "/opt/harbi_ganyan_v3/Tahminler")
    prefix = day.strftime("%d_%m_%Y")

    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(
            cfg["host"], port=cfg.get("port", 22),
            username=cfg["username"], password=cfg["password"],
            timeout=10,
        )
    except Exception as e:
        print(f"  UYARI: VDS baglantisi basarisiz ({e}), lokal dosyalar kullanilacak.")
        return []

    try:
        sftp = c.open_sftp()
        try:
            remote_files = sftp.listdir(remote_dir)
        except FileNotFoundError:
            print(f"  UYARI: VDS'te {remote_dir} bulunamadi.")
            c.close()
            return []

        matched = [f for f in remote_files if f.startswith(prefix) and f.endswith(".txt")]
        if not matched:
            print(f"  VDS'te {prefix}_*.txt yok (henuz uretilmemis olabilir).")
            c.close()
            return []

        ensure_dirs()
        written: list[Path] = []
        for fname in sorted(matched):
            remote_path = f"{remote_dir}/{fname}"
            # _vds.txt suffix ile kaydet (lokal ile karsilastirma icin)
            vds_fname = fname.replace(".txt", "_vds.txt")
            local_path = TAHMINLER_DIR / vds_fname
            sftp.get(remote_path, str(local_path))
            written.append(local_path)
            print(f"  [VDS] {fname} -> {vds_fname}")
        c.close()
        return written
    except Exception as e:
        print(f"  UYARI: VDS dosya indirme hatasi ({e}).")
        try:
            c.close()
        except Exception:
            pass
        return []


def _pull_models():
    """VDS'ten modelleri VE memory-besleyen veriyi sessizce çeker.

    VDS ana motordur. Lokal hem son egitilmis modeli hem de VDS'in geçmiş
    verisini (results_raw + program_raw + bulletin_raw) çeker; boylece
    walk-forward memory birebir ayni olur ve tahminler VDS ile eslesir.

    VDS modeli mevcut feature sayisiyla uyumsuzsa lokal egitime izin vermek
    icin modeli siler.
    """
    try:
        from models_pull import main as pull_main
        _sessiz(pull_main)
    except (Exception, SystemExit):
        pass  # VDS yoksa veya hata olursa sessizce devam et
    # VDS'in geçmiş verisini cek (memory birebir ayni olsun)
    try:
        from data_pull import main as data_main
        _sessiz(data_main)
    except (Exception, SystemExit):
        pass  # veri senkronu basarisizsa eldeki veriyle devam et
    # VDS modeli mevcut feature setiyle uyumlu mu kontrol et
    _validate_pulled_models()


def _validate_pulled_models():
    """VDS'ten cekilen model mevcut lokal feature setiyle uyumlu mu kontrol eder.

    VDS ana motordur; lokal onun AYNASIDIR. Uyumsuzluk = lokal kod (features.py /
    horse_cards.py) VDS ile senkron degil demektir. Bu durumda modeli silip lokalde
    YENIDEN EGITMEK yanlistir: VDS'ten FARKLI bir model uretir ve tahminler sessizce
    sapar (bu, gecmiste yasanan 164<->150 sapmasinin koku idi). Bu yuzden burada
    sessizce egitmek yerine NET HATA verilir.
    """
    import numpy as np
    from pathlib import Path
    from src.harbi_v3.features import FEATURE_NAMES

    models_dir = Path("models")
    lokalson = models_dir / "ranker_lokalson.json"
    if not lokalson.exists():
        return

    try:
        from xgboost import XGBRanker
        ranker = XGBRanker()
        ranker.load_model(str(lokalson))
        dummy = np.zeros((1, len(FEATURE_NAMES)), dtype=float)
        ranker.predict(dummy)
    except ValueError as e:
        if "Feature shape mismatch" in str(e):
            model_feat = getattr(ranker, "n_features_in_", "?")
            raise RuntimeError(
                "\n  ==================================================================\n"
                f"  VDS modeli {model_feat} feature, lokal kod {len(FEATURE_NAMES)} feature bekliyor.\n"
                "  Lokal kod (features.py / horse_cards.py) VDS ile SENKRON DEGIL.\n"
                "  Lokal AYNA oldugu icin burada yeniden EGITILMEZ (VDS'ten sapar).\n"
                "  Cozum: lokal src/harbi_v3 kodunu VDS ile esitle, sonra tekrar dene.\n"
                "  ==================================================================\n"
            ) from e
        raise
    except Exception:
        pass  # Dosya bozuksa sessizce devam et (predict_for_date karar verir)


def _local_ensure_data(day: date) -> None:
    """--local modunda eksik program, bulletin ve at kartlarini ceker.

    TASARIM: force=False kullanilir; data_pull.py VDS verisini lokale
    senkronladiktan sonra --local bu veriyle ayni tahmini uretmeli.
    force=True ile yeniden cekmek VDS'in kullandigi dosyalari ezerek
    lokal/VDS tahmin farkliligi yarat (at sayisi, gallop verisi, vs.).

    Eksik dosya varsa (data_pull oncesi soguk baslangic) TJK'dan cekilir;
    mevcut dosyaya dokunulmaz.
    """
    _st = _import_scripts_tahmin()

    # Program — force=False: data_pull.py senkronladiysa o versiyon kullanilir.
    # Dosya yoksa TJK'dan cekilir (soguk baslangic).
    try:
        _st._ensure_program(day, force=False)
    except Exception as e:
        print(f"  [program] UYARI: {e}")

    # Bulletin — ayni mantik: mevcut dosyaya dokunma.
    try:
        _st._ensure_bulletin(day, force=False)
    except Exception as e:
        print(f"  [bulten] UYARI: {e}")

    # At kartlari — ensure (eksik kartlari cek, mevcutlara dokunma).
    # data_pull.py horse_cards_raw'u senkronlayinca kartlar taze gelir;
    # refresh_cards_for_day bu kartlari ezerek gallop verisi farkliligi yaratirdi.
    try:
        import importlib.util
        _spec = importlib.util.spec_from_file_location(
            "_scrape_horse_cards",
            ROOT / "scripts" / "scrape_horse_cards.py",
        )
        _shc = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_shc)
        _shc.ensure_cards_for_day(day, verbose=True)
    except Exception as e:
        print(f"  [kart-kontrol] UYARI: {e}, mevcut kartlarla devam ediliyor.")


def main():
    import os
    local_mode = "--local" in sys.argv or os.environ.get("HG_LOCAL_MODE") == "1"

    print("=" * 55)
    print("  HARBI GANYAN v3 - Tahmin Araci")
    if local_mode:
        print("  [LOKAL MOD] Lokal tahmin uretimi")
    else:
        print("  [VDS MOD] VDS'ten hazir tahmin indirilir")
    print("=" * 55)

    day = _tarih_al()

    if not local_mode:
        # Normal mod: VDS'teki hazir tahmin dosyalarini indir ve goster.
        # VDS zaten bir gun onceden tahmin uretiyor; burada yeniden tahmin
        # uretilmez, sadece VDS ciktisi lokale kopyalanir.
        print(f"\nVDS'ten {day.strftime('%d.%m.%Y')} tahminleri indiriliyor...")
        written = _pull_vds_tahmin(day)
        if written:
            print(f"\nIndirildi ({len(written)} dosya):")
            for p in written:
                print(f"  -> {p.name}")
            print(f"\nDosyalar: Tahminler/")
        else:
            print("  Hic dosya indirilemedi. VDS'te bu tarihe ait tahmin yok olabilir.")
        return 0

    # --local mod: eksik verileri cek, sonra lokalde tahmin uret.
    print(f"\n{day.strftime('%d.%m.%Y')} icin eksik veriler kontrol ediliyor...")
    _local_ensure_data(day)

    secilen = _hipodrom_sec(day)
    if not secilen:
        print("Iptal.")
        return 0

    print(f"\n{'=' * 55}")
    print(f"  {day.strftime('%d.%m.%Y')} | {len(secilen)} sehrin tahmini uretiliyor...")
    print(f"{'=' * 55}")

    for hip in secilen:
        written = run(day, hip_filter=hip, refresh_cards=False)
        for p in written:
            print(f"  -> {p.name}")

    print(f"\nTamamlandi. Ciktilar: Tahminler/  ve  data/export_out/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
