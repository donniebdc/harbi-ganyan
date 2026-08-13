# -*- coding: utf-8 -*-
"""
gallop_raw.py — Yenibeygir.com galop verisi parse etme ve saklama.

Kullanim:
    from harbi_v3.gallop_raw import GallopEntry, parse_gallop_html, load_gallop_day

Veri kaynagi: yenibeygir.com/{tarih}/{sehir}/{kosu_no}/galoplar
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from .paths import DATA_DIR


GALLOP_RAW_DIR = DATA_DIR / "gallop_raw"


@dataclass
class GallopEntry:
    """Tek bir galop kaydi."""
    horse_name: str
    gallop_date: date
    city: str
    weight: float = 0.0
    jockey: str = ""
    distance_400: float = 0.0
    distance_600: float = 0.0
    distance_800: float = 0.0
    distance_1000: float = 0.0
    distance_1200: float = 0.0
    distance_1400: float = 0.0
    intensity: int = 0       # 0=CR, 1=R, 2=HC, 3=C, -1=Kenter
    track_type: str = ""     # "kum", "kum_ic", "kum_islak", "kum_nemli"
    horse_kodu: str = ""     # yenibeygir at kodu (linkten cikarilir)
    race_jockey: str = ""    # yaris gunu jokeyi (karsilastirma icin)


def _parse_date_tr(text: str) -> date | None:
    """GG.AA.YYYY veya YYYY-MM-DD -> date."""
    text = (text or "").strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _parse_gallop_time(text: str) -> float:
    """Galop suresini saniyeye cevirir.

    Formatlar:
      "24.0"   -> 24.0 sn (400m, 600m)
      "48.2"   -> 48.2 sn (800m)
      "1.02.4" -> 62.4 sn (800m, 1000m: dk.sn.salise)
      "1.16.5" -> 76.5 sn
    """
    text = (text or "").strip()
    if not text:
        return 0.0
    parts = text.split(".")
    if len(parts) == 2:
        # Tek haneli ondalik: "24.0" -> 24.0
        try:
            return float(text.replace(",", "."))
        except ValueError:
            return 0.0
    elif len(parts) == 3:
        # dk.sn.salise: "1.02.4" -> 60 + 2 + 0.4 = 62.4
        try:
            dk, sn, sl = parts
            return int(dk) * 60 + int(sn) + int(sl) / 10.0
        except (ValueError, IndexError):
            return 0.0
    return 0.0


def _parse_intensity(code: str) -> int:
    """Galop turu kodunu efor seviyesine cevirir.

    CR=0 (Cok Rahat), R=1 (Rahat), HC=2 (Hafif Calisarak), C=3 (Calisarak), Kenter=-1
    """
    code = (code or "").strip().upper()
    mapping = {
        "ÇR": 0, "CR": 0,
        "R": 1,
        "HÇ": 2, "HC": 2,
        "Ç": 3, "C": 3,
    }
    if "KENTER" in code:
        return -1
    return mapping.get(code, 0)


def _parse_track_type(text: str) -> str:
    """Pist bilgisini normalize eder.

    "Kum" -> "kum", "Kum-İç" -> "kum_ic", "Kum Islak" -> "kum_islak", etc.
    """
    text = (text or "").strip().lower()
    text = text.replace("ı", "i").replace("ş", "s").replace("ç", "c").replace("ğ", "g")
    text = text.replace("ü", "u").replace("ö", "o").replace("â", "a").replace("î", "i")
    if "ic" in text or "iç" in text:
        return "kum_ic"
    if "islak" in text:
        return "kum_islak"
    if "nemli" in text:
        return "kum_nemli"
    if "kum" in text:
        return "kum"
    return text or "kum"


def _extract_horse_code(href: str) -> str:
    """yenibeygir at linkinden at kodunu cikarir: /at/103187/lord-of-dragon -> 103187."""
    if not href:
        return ""
    m = re.search(r"/at/(\d+)/", href)
    return m.group(1) if m else ""


def parse_gallop_html(html: str, race_date: date | None = None) -> list[GallopEntry]:
    """yenibeygir.com galop sayfasindan GallopEntry listesini cikarir.

    HTML yapisi:
      - Header satiri: sutun isimleri
      - At baslik satiri: "1 AT_ADI Jokey (Kilo)"
      - Veri satirlari: "Tarih Sehir Kg GalopJokey 400 600 800 1000 [1200] [1400] Tur Pist"
    """
    entries: list[GallopEntry] = []

    # HTML entity'leri temizle
    html = html.replace("&#x131;", "i").replace("&#x130;", "I")
    html = html.replace("&#x15F;", "s").replace("&#xE7;", "c").replace("&#xC7;", "C")
    html = html.replace("&#xF6;", "o").replace("&#xFC;", "u")
    html = html.replace("&#x11F;", "g").replace("&#x15E;", "S").replace("&#x160;", "S")
    html = html.replace("&#xE2;", "a").replace("&#xEE;", "i")
    html = html.replace("&nbsp;", " ")
    # Kalan HTML entity'lerini decode et
    import html as _html_mod
    html = _html_mod.unescape(html)

    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    current_horse: dict = {"name": "", "kodu": "", "race_jockey": ""}

    for row_html in trs:
        # HTML tag'lerini temizle, text'i al
        text = re.sub(r'<[^>]+>', ' ', row_html)
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            continue

        # Link ara (at kodu icin)
        link_match = re.search(r'href="([^"]*)"', row_html)
        horse_kodu = ""
        if link_match:
            horse_kodu = _extract_horse_code(link_match.group(1))

        parts = text.split()

        # Header satirini atla
        if parts[0] == "Tarih":
            continue

        # At baslik satiri mi kontrol et: "[No] AT_ADI [Jokey] [(Kilo)]"
        # Format: "1 LORD OF DRAGON A.Mehdi Altin (58)"
        # Jokey ismi 1-3 kelime olabilir, parantez icinde kilo var
        first_is_number = parts[0].isdigit()

        if first_is_number and "(" in text:
            # Bu bir at baslik satiri. Link text'i at adini verir.
            # Ornek HTML: <a href="/at/104670/my-life-fire">MY LIFE FIRE</a> M.Kaya (60)
            link_text_match = re.search(r'<a[^>]*>([^<]+)</a>', row_html)
            if link_text_match:
                horse_name = link_text_match.group(1).strip()
            else:
                # Fallback: text parsing
                horse_name = " ".join(parts[1:])  # tamami

            # Jokey: link'ten sonraki text. Ornek: <a>...</a> A.Mehdi Altin (58)
            after_link = re.sub(r'<a[^>]*>.*?</a>', ' ', row_html)
            after_link = re.sub(r'<[^>]+>', ' ', after_link)
            after_link = re.sub(r'\s+', ' ', after_link).strip()
            # Parantez ve icindekini cikar (kilo)
            after_link = re.sub(r'\([^)]*\)', '', after_link).strip()
            race_jockey_from_text = after_link if after_link else ""

            current_horse = {
                "name": horse_name,
                "kodu": horse_kodu or current_horse.get("kodu", ""),
                "race_jockey": race_jockey_from_text,
            }
            continue

        # Veri satiri kontrolu: ilk eleman tarih formatinda mi?
        gallop_date = _parse_date_tr(parts[0])
        if not gallop_date:
            continue

        if len(parts) < 5:
            continue

        # Veri satiri: Tarih Sehir Kg [Jokey ...] [400] [600] [800] [1000] [Tur] [Pist]
        city = parts[1] if len(parts) > 1 else ""

        # Kilo: 3. pozisyon
        weight = 0.0
        try:
            weight = float(parts[2].replace(",", "."))
        except (ValueError, IndexError):
            pass

        # Jokey + mesafe sureleri + tur + pist ayrisimi
        # Jokey: 3. pozisyondan sonraki ilk sayisal degere kadar olan kisim
        remaining = parts[3:]

        jockey_parts = []
        numeric_vals: list[float] = []
        intensity_str = ""
        track_str = ""
        found_numeric = False

        for p in remaining:
            p_orig = p
            p_clean = p.upper().replace(",", ".")

            # Sayisal deger mi? (galop suresi)
            try:
                v = _parse_gallop_time(p_orig)
                if v > 0:
                    numeric_vals.append(v)
                    found_numeric = True
                    continue
            except (ValueError, TypeError):
                pass

            if not found_numeric:
                # Henuz sayisal deger bulunmadi, bu jokey adinin parcasi
                jockey_parts.append(p_orig)
            else:
                # Sayisal degerlerden sonra: tur veya pist
                if p_clean in ("CR", "ÇR", "R", "HC", "HÇ", "C", "Ç"):
                    intensity_str = p_clean
                elif "KENTER" in p_clean:
                    intensity_str = "KENTER"
                elif any(kw in p_clean.lower() for kw in ("kum",)):
                    track_str = p_clean
                elif "IC" in p_clean or "İÇ" in p_clean:
                    track_str = p_clean

        jockey = " ".join(jockey_parts)

        # Mesafe surelerini ata
        d400 = d600 = d800 = d1000 = d1200 = d1400 = 0.0
        sorted_v = sorted(numeric_vals)

        if sorted_v:
            d400 = sorted_v[0]
        for v in sorted_v[1:]:
            if v > d400 and v < 50 and d600 == 0:
                d600 = v
        for v in sorted_v[1:]:
            if v > d400 and (d600 == 0 or v > d600) and d800 == 0 and v >= 48:
                d800 = v
                break
        # 60+ sn: 800m (1.02.4) veya 1000m (1.16.5)
        large = [v for v in sorted_v if v >= 60]
        if large:
            for v in large:
                if d800 == 0 or (v > d800 and d1000 == 0):
                    if d800 == 0:
                        d800 = v
                    elif v > d800 and d1000 == 0:
                        d1000 = v

        intensity = _parse_intensity(intensity_str)
        track_type = _parse_track_type(track_str) if track_str else ""

        entries.append(GallopEntry(
            horse_name=current_horse.get("name", ""),
            gallop_date=gallop_date,
            city=city,
            weight=weight,
            jockey=jockey,
            distance_400=d400,
            distance_600=d600,
            distance_800=d800,
            distance_1000=d1000,
            distance_1200=d1200,
            distance_1400=d1400,
            intensity=intensity,
            track_type=track_type,
            horse_kodu=current_horse.get("kodu", ""),
            race_jockey=current_horse.get("race_jockey", ""),
        ))

    return entries


def save_gallops(entries: list[GallopEntry], race_date: date, city: str, race_no: int) -> Path:
    """Galop verilerini JSON olarak kaydeder."""
    GALLOP_RAW_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{race_date:%Y-%m-%d}_{city.upper()}_K{race_no}.json"
    path = GALLOP_RAW_DIR / fname
    data = {
        "race_date": f"{race_date:%Y-%m-%d}",
        "city": city,
        "race_no": race_no,
        "entries": [
            {
                "horse_name": e.horse_name,
                "gallop_date": f"{e.gallop_date:%Y-%m-%d}",
                "city": e.city,
                "weight": e.weight,
                "jockey": e.jockey,
                "distance_400": e.distance_400,
                "distance_600": e.distance_600,
                "distance_800": e.distance_800,
                "distance_1000": e.distance_1000,
                "distance_1200": e.distance_1200,
                "distance_1400": e.distance_1400,
                "intensity": e.intensity,
                "track_type": e.track_type,
                "horse_kodu": e.horse_kodu,
            }
            for e in entries
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_gallop_file(path: Path) -> list[GallopEntry]:
    """JSON dosyasindan GallopEntry listesi yukler."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = []
    for e in data.get("entries", []):
        entries.append(GallopEntry(
            horse_name=e.get("horse_name", ""),
            gallop_date=_parse_date_tr(e.get("gallop_date", "")) or date.today(),
            city=e.get("city", ""),
            weight=e.get("weight", 0.0),
            jockey=e.get("jockey", ""),
            distance_400=e.get("distance_400", 0.0),
            distance_600=e.get("distance_600", 0.0),
            distance_800=e.get("distance_800", 0.0),
            distance_1000=e.get("distance_1000", 0.0),
            distance_1200=e.get("distance_1200", 0.0),
            distance_1400=e.get("distance_1400", 0.0),
            intensity=e.get("intensity", 0),
            track_type=e.get("track_type", ""),
            horse_kodu=e.get("horse_kodu", ""),
        ))
    return entries


def load_gallop_day(day: date) -> list[GallopEntry]:
    """Belirli bir gune ait tum galop verilerini yukler."""
    all_entries = []
    if not GALLOP_RAW_DIR.exists():
        return all_entries
    prefix = f"{day:%Y-%m-%d}"
    for path in sorted(GALLOP_RAW_DIR.glob(f"{prefix}*.json")):
        all_entries.extend(load_gallop_file(path))
    return all_entries


def load_all_gallops_before(as_of: date) -> list[GallopEntry]:
    """as_of tarihinden ONCEKI tum galop verilerini yukler (walk-forward icin).

    Dosya tarihi <= as_of olan tum dosyalari yukler. Galop kayitlarinin
    kendi tarihleri as_of'tan once olmalidir (feature hesaplamasinda filtrelenir).
    """
    all_entries = []
    if not GALLOP_RAW_DIR.exists():
        return all_entries
    for path in sorted(GALLOP_RAW_DIR.glob("*.json")):
        stem = path.stem
        try:
            file_date = datetime.strptime(stem[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date <= as_of:
            all_entries.extend(load_gallop_file(path))
    return all_entries
