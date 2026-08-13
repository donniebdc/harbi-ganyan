from __future__ import annotations

"""
sonuc.py  –  Interaktif sonuc isleyici.

Calistirma:
    python sonuc.py

Tarih formatlari:
    11.06.2026  |  11-06-2026  |  11/06/2026  |  11062026  |  2026-06-11

Yapilan islemler:
  1. Tahminler/DD_MM_YYYY_*_meta.json oku (tahmin edilen atlar)
  2. data/results_raw/YYYY-MM-DD.json'dan kazananları cek
  3. Tahmin .txt dosyasinda:
     - [?] - [?] satirlarini kazanan bilgisiyle guncelle
     - 🎯 satirina ✅ veya ❌ ekle
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from harbi_v3.collect_results import collect_results_day
from harbi_v3.normalize import norm_text
from harbi_v3.paths import META_DIR, RESULTS_RAW_DIR, TAHMINLER_DIR, ensure_dirs
from harbi_v3.records import available_program_dates, load_program_day, parse_results
from tahmin import parse_flexible_date, _file_stem

ROOT_EXPORT = Path(__file__).resolve().parent / "data" / "export_out"


def _load_winners(target_date: date) -> dict[tuple[str, int], dict]:
    """(hip, race_no) -> {winner_no, winner_name, ganyan}"""
    results = parse_results(target_date)
    program_data = load_program_day(target_date)

    name_map: dict[tuple[str, int, int], str] = {}
    for hip, hip_data in (program_data.get("hippodromes") or {}).items():
        hip_norm = norm_text(hip)
        for race in (hip_data.get("details") or {}).get("races") or []:
            race_no = int(str(race.get("number") or "0").strip() or "0")
            if race_no <= 0:
                continue
            for horse in race.get("horses") or []:
                hno = int(str(horse.get("number") or "0").strip() or "0")
                if hno <= 0:
                    continue
                name_map[(hip_norm, race_no, hno)] = str(horse.get("name") or "").strip()

    out: dict[tuple[str, int], dict] = {}
    for (hip, race_no), result in results.items():
        wno = result.winner_no
        wname = name_map.get((hip, race_no, wno), "?")
        out[(hip, race_no)] = {
            "winner_no": wno,
            "winner_name": wname,
            "ganyan": result.winner_ganyan,
        }
    return out


def _strip_marks(line: str) -> str:
    """Satır sonundaki sonuç işaretlerini temizler (yeniden işlem için)."""
    for mark in ("\t\t🎉✅", "\t\t✅", "  🎉✅", "  ✅", "  ❌", " | 🎉✅", " | ✅", " | ❌"):
        if line.endswith(mark):
            return line[: -len(mark)]
    return line


def _load_altili_data(day: date, hip: str) -> dict | None:
    """Export JSON'dan bir şehrin altili kupon verisini yükler."""
    iso = f"{day:%Y-%m-%d}"
    stem = _file_stem(day, hip)
    for name in (f"{iso}_{hip.upper()}.json", f"{iso}.json"):
        path = ROOT_EXPORT / name
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for hp_data in data.get("hipodromlar", []):
                    if hp_data.get("hipodrom", "").upper() == hip.upper():
                        return hp_data
            except (json.JSONDecodeError, OSError):
                pass
    return None


def _load_altili_ikramiye(day: date, hip: str) -> dict[int, dict]:
    """results_raw'dan altili ikramiye bilgisini çıkarır.
    Dönüş: {pool_idx: {combo, value}}
    """
    import re as _re
    results_path = RESULTS_RAW_DIR / f"{day:%Y-%m-%d}.json"
    if not results_path.exists():
        return {}
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    ikramiye: dict[int, dict] = {}
    hip_data = (data.get("hippodromes") or {}).get(hip) or \
               (data.get("hippodromes") or {}).get(hip.upper())
    if not hip_data:
        return {}

    for race_data in (hip_data.get("races") or {}).values():
        for br in race_data.get("betting_results") or []:
            name = str(br.get("name", ""))
            m = _re.search(r"(\d+)\.\s*6'L[İI]\s+GANYAN", name)
            if m:
                idx = int(m.group(1))
                value_str = str(br.get("value", ""))
                try:
                    value = float(value_str.replace("TL", "").replace(".", "").replace(",", ".").strip())
                except (ValueError, AttributeError):
                    value = None
                ikramiye[idx] = {
                    "combo": str(br.get("combo", "")),
                    "value": value,
                    "value_str": value_str,
                    "name": name,
                }
    return ikramiye


def _update_altili_section(lines: list[str], hip: str, altili_data: dict | None,
                           winners: dict[tuple[str, int], dict],
                           ikramiye: dict[int, dict]) -> int:
    """Txt içindeki 6'lı ganyan bölümlerini sonuçlarla günceller."""
    altili_sonuc_re = re.compile(
        r"(🎰\s*\d+\.\s*ALTILI GANYAN\s*\((\d+)-(\d+)\.\s*Koşular\)\s*\t?Sonuçlar\s*:\s*)(.*)"
    )
    tier_header_re = re.compile(r"(┌─\s*)(Mini|Standart|Geniş)\s*(6'l[ıi]\s*.*)")
    leg_line_re = re.compile(r"(│\s*)(\d+)\.\s*Koşu\s*\t:\s*(.*)")
    horse_in_leg_re = re.compile(r"(\[?)(\d+)(\]?\s*✅?\s*)?(\S[^/]*?)(\s*(?=/|$))")

    altili_list = altili_data.get("altililar", []) if altili_data else []

    for i, line in enumerate(lines):
        # --- Sonuç satırı ---
        m = altili_sonuc_re.match(line)
        if not m:
            continue

        prefix = m.group(1)
        ilk = int(m.group(2))
        son = int(m.group(3))

        # Kazananları bul
        sonuclar = []
        for kno in range(ilk, son + 1):
            key = (hip, kno)
            wno = winners.get(key, {}).get("winner_no", 0) if key in winners else 0
            sonuclar.append(str(wno) if wno else "?")

        # Bu altılı havuzunu bul
        # Pool idx'i bul: "1. ALTILI GANYAN" → idx=1
        idx_m = re.search(r"(\d+)\.\s*ALTILI GANYAN", line)
        pool_idx = int(idx_m.group(1)) if idx_m else 1
        havuz = None
        for a in altili_list:
            if a.get("idx") == pool_idx:
                havuz = a
                break

        # İkramiye
        iki = ikramiye.get(pool_idx, {})
        iki_str = ""
        if iki.get("value") is not None:
            iki_str = f" | İkramiye : {iki['value_str']}"
        lines[i] = f"{prefix}{' / '.join(sonuclar)}{iki_str}  "

        if not havuz:
            continue

        # Tier'ları işle (sonraki satırlarda)
        for j in range(i + 1, len(lines)):
            tier_m = tier_header_re.match(lines[j])
            if tier_m:
                tier_name = tier_m.group(2)  # Mini, Standart, Geniş
                # Bu tier'ı havuzda bul
                tier_data = None
                for kd in havuz.get("kademeler", []):
                    if kd.get("ad", "").startswith(tier_name):
                        tier_data = kd
                        break

                if not tier_data:
                    continue

                # Doğru ayak sayısını hesapla
                correct_legs = 0
                for ayak in tier_data.get("ayaklar", []):
                    kno = ayak["kno"]
                    key = (hip, kno)
                    wno = winners.get(key, {}).get("winner_no", 0) if key in winners else 0
                    if wno and wno in ayak.get("secilen", []):
                        correct_legs += 1

                lines[j] = f"{tier_m.group(1)}{tier_name} {tier_m.group(3)} [ {correct_legs} / 6 ]"

                # Ayakları işle
                k = j + 1
                while k < len(lines) and lines[k].strip().startswith("│"):
                    leg_m = leg_line_re.match(lines[k])
                    if leg_m:
                        kno = int(leg_m.group(2))
                        key = (hip, kno)
                        wno = winners.get(key, {}).get("winner_no", 0) if key in winners else 0

                        # Bu ayak için tier data bul
                        ayak_data = None
                        for a in tier_data.get("ayaklar", []):
                            if a["kno"] == kno:
                                ayak_data = a
                                break

                        if ayak_data and wno:
                            secilen = ayak_data.get("secilen", [])
                            atlar_str = leg_m.group(3)
                            # Her atı kontrol et, kazanana [no] ✅ ekle
                            new_atlar = []
                            winner_found = False
                            for at_entry in ayak_data.get("secilen_atlar", []):
                                at_no = at_entry["at_no"]
                                at_name = at_entry["at"]
                                if at_no == wno:
                                    new_atlar.append(f"[{at_no}] ✅ {at_name}")
                                    winner_found = True
                                else:
                                    new_atlar.append(f"{at_no} {at_name}")

                            new_line = f"│  {kno}. Koşu \t: {' / '.join(new_atlar)}"
                            if not winner_found and wno:
                                new_line += " | ❌"
                            lines[k] = new_line
                        elif wno == 0:
                            pass  # Sonuç henüz yok, dokunma
                        else:
                            # Ayak data yok ama kazanan var → sonuç satırında ? kalır
                            pass
                    k += 1
            elif lines[j].startswith("🎰"):
                break  # sonraki altili havuzuna geçtik
            # ═══════════ vb. satırları yoksay, tier işlemeye devam et

    return 0


def _update_txt(txt_path: Path, meta: dict, winners: dict[tuple[str, int], dict], altili_data: dict | None = None, ikramiye: dict[int, dict] | None = None) -> int:
    """
    .txt dosyasini in-place gunceller. Idempotent: mevcut isaretleri
    once temizler, sonra dogru sekilde yeniden uygular.

    Emoji mantığı:
      🎉✅  — kazanan tam favorimiz (🎯 Harbi Ganyan Favorisi)
      ✅   — kazanan 5'li satırımızda (pozisyon 2-5); işaret o atın satırına gider
      ❌   — yalnızca Kazanan satırına (slot satırlarına ❌ konmaz)
    """
    hip = meta["hip"]
    races_meta: dict[str, dict] = meta.get("races", {})

    # Mevcut işaretleri temizle; Kazanan satırını da sıfırla
    raw_lines = txt_path.read_text(encoding="utf-8").splitlines()
    lines = [_strip_marks(ln) for ln in raw_lines]
    # Kazanan satırını tamamen sıfırla (horse bilgisi de içerebilir)
    kazanan_re_full = re.compile(r"(\s*)(\d+)\. KOŞU \| Kazanan \| \[[^\]]*\] - \[[^\]]*\].*")
    lines = [
        f"{m.group(1)}{m.group(2)}. KOŞU | Kazanan | [?] - [?]"
        if (m := kazanan_re_full.match(ln)) else ln
        for ln in lines
    ]

    updated_count = 0
    winner_pattern = re.compile(r"(\s*)(\d+)\. KOŞU \| Kazanan \| \[(\?|[0-9]+)\] - \[\??[^\]]*\]")
    slot_emoji_re = re.compile(r"[🎯🔒✍️💣❓]")
    horse_no_re = re.compile(r"No:(\d+)")
    score_line_re = re.compile(r"^(.*?)(\d+)\.\s.*Skor:\s*[\d.]+\s*$")

    # Her koşu için: (status, winner_no)
    race_status: dict[int, tuple[str, int]] = {}
    for race_no_s, rmeta in races_meta.items():
        race_no = int(race_no_s)
        key = (hip, race_no)
        if key not in winners:
            continue
        wno = winners[key]["winner_no"]
        predicted_no = rmeta.get("predicted_no", 0)
        top5 = rmeta.get("top5_nos", [])
        if wno == predicted_no:
            race_status[race_no] = ("fav", wno)
        elif wno in top5:
            race_status[race_no] = ("top5", wno)
        else:
            race_status[race_no] = ("miss", wno)

    new_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # --- Kazanan satırı ---
        m = winner_pattern.match(line)
        if m:
            indent = m.group(1)
            race_no = int(m.group(2))
            key = (hip, race_no)
            if key in winners:
                info = winners[key]
                wno = info["winner_no"]
                wname = info["winner_name"]
                ganyan = info.get("ganyan")
                ganyan_str = f" | Ganyan: {ganyan:.2f} TL" if ganyan is not None else ""
                status, _ = race_status.get(race_no, ("miss", 0))
                mark = "🎉✅" if status == "fav" else ("✅" if status == "top5" else "❌")
                new_lines.append(
                    f"{indent}{race_no}. KOŞU | Kazanan | [{wno}] - [{wname}]{ganyan_str} | {mark}"
                )
                updated_count += 1
                i += 1
                continue

        # --- Slot satırları (🎯🔒✍️💣❓) ---
        # Sadece KAZANAN atın satırına işaret koyulur; diğerlerine hiçbir şey.
        if slot_emoji_re.search(line) and "No:" in line:
            race_no = _find_current_race_no(new_lines)
            if race_no is not None and (hip, race_no) in winners:
                m2 = horse_no_re.search(line)
                if m2:
                    slot_hno = int(m2.group(1))
                    status, wno = race_status.get(race_no, ("miss", 0))
                    if slot_hno == wno:
                        mark = "🎉✅" if "🎯" in line else "✅"
                        new_lines.append(line + f"  {mark}")
                        i += 1
                        continue

        # --- Analiz Puanları skor satırları ---
        # Kazanan atın skor sıralamasındaki satırına, 5'li satırda olup olmadığına
        # bakılmaksızın işaret koyulur (kullanıcı kazananın tam sırasını görür).
        m3 = score_line_re.match(line)
        if m3:
            race_no = _find_current_race_no(new_lines)
            if race_no is not None and (hip, race_no) in winners:
                row_hno = int(m3.group(2))
                status, wno = race_status.get(race_no, ("miss", 0))
                if row_hno == wno:
                    mark = "🎉✅" if status == "fav" else "✅"
                    new_lines.append(line + f"\t\t{mark}")
                    i += 1
                    continue

        new_lines.append(line)
        i += 1

    # ---- 6'lı ganyan sonuç işleme ----
    if altili_data:
        _update_altili_section(new_lines, hip, altili_data, winners, ikramiye or {})

    txt_path.write_text("\n".join(new_lines), encoding="utf-8")
    return updated_count


def _find_current_race_no(preceding_lines: list[str]) -> int | None:
    race_header = re.compile(r"┌─.*?(\d+)\. KOŞU")
    for line in reversed(preceding_lines):
        m = race_header.search(line)
        if m:
            return int(m.group(1))
    return None


def _meta_stem_to_date(filename: str) -> date | None:
    """DD_MM_YYYY_*_meta.json -> date"""
    m = re.match(r"(\d{2})_(\d{2})_(\d{4})_", filename)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    # eski format: YYYY-MM-DD_*
    m2 = re.match(r"(\d{4})-(\d{2})-(\d{2})_", filename)
    if m2:
        try:
            return date(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
        except ValueError:
            pass
    return None


def _find_meta_files(target_date: date) -> list[Path]:
    """data/meta/ altından DD_MM_YYYY_*_meta.json dosyalarını bulur."""
    pattern = f"{target_date:%d_%m_%Y}_*_meta.json"
    return sorted(META_DIR.glob(pattern))


def ask_date() -> date:
    program_dates = set(available_program_dates())
    while True:
        raw = input("\nSonuç tarihi (ör: 11.06.2026 / 11-06-2026 / 11062026): ").strip()
        if not raw:
            continue
        d = parse_flexible_date(raw)
        if d is None:
            print("  ⚠️  Geçersiz format. Tekrar deneyin.")
            continue
        if d not in program_dates:
            print(f"  ⚠️  {d:%d.%m.%Y} için program verisi yok.")
            continue
        return d


def ask_city(meta_files: list[Path], target_date: date) -> list[Path]:
    """Meta dosyalarından şehir seçimi; boş giriş → hepsi."""
    if not meta_files:
        return []

    hips = []
    for f in meta_files:
        try:
            meta = json.loads(f.read_text(encoding="utf-8"))
            hips.append((meta.get("hip", f.stem), f))
        except Exception:
            hips.append((f.stem, f))

    print(f"\n{target_date:%d.%m.%Y} tarihindeki tahmin dosyaları:")
    for i, (hip, _) in enumerate(hips, 1):
        print(f"  {i}. {hip.upper()}")
    print("  (Enter = tüm şehirler)")

    raw = input("Şehir numarası (virgülle birden fazla, ör: 1,3): ").strip()
    if not raw:
        return meta_files

    selected: list[Path] = []
    for part in raw.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(hips):
                selected.append(hips[idx][1])
        except ValueError:
            pass
    return selected if selected else meta_files


def run(target_date: date, hip_filter: str | None = None) -> int:
    ensure_dirs()
    meta_files = _find_meta_files(target_date)
    if not meta_files:
        print(f"  ⚠️  {target_date:%d.%m.%Y} için tahmin dosyası bulunamadı.")
        return 1

    results_path = RESULTS_RAW_DIR / f"{target_date:%Y-%m-%d}.json"
    had_results = results_path.exists()
    if not collect_results_day(target_date, force=True) and not had_results:
        print(f"  ⚠️  {target_date:%d.%m.%Y} için sonuç verisi alınamadı (koşular henüz bitmemiş olabilir).")
        return 1

    winners = _load_winners(target_date)
    if not winners:
        print(f"  ⚠️  {target_date:%d.%m.%Y} için sonuç verisi bulunamadı.")
        return 1

    total_updated = 0
    for meta_path in meta_files:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        hip = meta.get("hip", "")
        if hip_filter and norm_text(hip) != norm_text(hip_filter):
            continue
        # txt yolu: Tahminler/ altında, meta ile aynı stem
        txt_name = meta_path.name.replace("_meta.json", ".txt")
        txt_path = TAHMINLER_DIR / txt_name
        if not txt_path.exists():
            print(f"  ⚠️  {txt_path.name} bulunamadı, atlandı.")
            continue
        altili_data = _load_altili_data(target_date, hip)
        ikramiye = _load_altili_ikramiye(target_date, hip)
        updated = _update_txt(txt_path, meta, winners, altili_data=altili_data, ikramiye=ikramiye)
        total_updated += updated
        print(f"  ✅ {txt_path.name}  ({updated} koşu güncellendi)")

    return 0 if total_updated > 0 else 1


def main() -> int:
    import os
    local_mode = "--local" in sys.argv or os.environ.get("HG_LOCAL_MODE") == "1"

    print("=" * 60)
    print("  SONUÇ İŞLEYİCİ")
    if local_mode:
        print("  [LOKAL MOD] TJK sonuç çekme devre disi")
    print("=" * 60)

    target_date = ask_date()

    meta_files = _find_meta_files(target_date)
    if not meta_files:
        print(f"\n  ⚠️  {target_date:%d.%m.%Y} için hiç tahmin dosyası yok.")
        print("  Önce tahmin.py ile tahmin oluşturun.")
        return 1

    selected_metas = ask_city(meta_files, target_date)

    results_path = RESULTS_RAW_DIR / f"{target_date:%Y-%m-%d}.json"
    had_results = results_path.exists()

    if local_mode:
        if not had_results:
            print(f"\n  ⚠️  {target_date:%d.%m.%Y} için lokal sonuç dosyası yok (data/results_raw/).")
            return 1
        print(f"  📂 Lokal sonuç dosyası kullaniliyor.", flush=True)
    else:
        print(f"  📥 Sonuç verisi {'tazeleniyor' if had_results else 'bulunamadı, çekiliyor'}...", flush=True)
        result = collect_results_day(target_date, force=True)
        if result:
            print(f"  ✅ Sonuç verisi güncel.", flush=True)
        elif not had_results:
            print(f"\n  ⚠️  {target_date:%d.%m.%Y} için sonuç verisi alınamadı (koşular henüz bitmemiş olabilir).")
            return 1
        else:
            print(f"  ⚠️  Sonuç verisi tazelenemedi, mevcut (eski) dosya kullanılacak.")

    winners = _load_winners(target_date)
    if not winners:
        print(f"\n  ⚠️  {target_date:%d.%m.%Y} için sonuç verisi bulunamadı.")
        return 1

    total_updated = 0
    for meta_path in selected_metas:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        hip = meta.get("hip", "")
        txt_name = meta_path.name.replace("_meta.json", ".txt")
        txt_path = TAHMINLER_DIR / txt_name
        if not txt_path.exists():
            print(f"  ⚠️  {txt_path.name} bulunamadı, atlandı.")
            continue
        altili_data = _load_altili_data(target_date, hip)
        ikramiye = _load_altili_ikramiye(target_date, hip)
        updated = _update_txt(txt_path, meta, winners, altili_data=altili_data, ikramiye=ikramiye)
        total_updated += updated
        print(f"  ✅ {txt_path.name}  ({updated} koşu güncellendi)")

    if total_updated == 0:
        print("  ⚠️  Güncellenecek koşu bulunamadı (sonuçlar zaten işlenmiş olabilir).")
        return 1

    print(f"\nToplam {total_updated} koşu güncellendi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
