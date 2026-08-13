# -*- coding: utf-8 -*-
"""
stiller.py — Yenibeygir.com stiller sayfasindan kosu stili verisi parse eder.

Her at icin 4 blok halinde kosu stili dagilimi:
  1. Geriden takip
  2. Ortadan takip
  3. Uca yakin takip
  4. En uctan tempo (onder)

Kaynak: yenibeygir.com/{tarih}/{sehir}/{kosu_no}/stiller
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .paths import DATA_DIR

STILLER_RAW_DIR = DATA_DIR / "stiller_raw"


@dataclass
class StilEntry:
    """Bir atin kosu stili dagilimi."""
    horse_name: str
    total_races: int         # toplam analiz edilen kosu sayisi
    geriden: int = 0          # geriden takip sayisi
    ortadan: int = 0          # ortadan takip sayisi
    ucayan: int = 0           # uca yakin takip sayisi
    onder: int = 0            # en uctan tempo sayisi

    @property
    def geriden_pct(self) -> float:
        return self.geriden / self.total_races if self.total_races > 0 else 0.0

    @property
    def ortadan_pct(self) -> float:
        return self.ortadan / self.total_races if self.total_races > 0 else 0.0

    @property
    def ucayan_pct(self) -> float:
        return self.ucayan / self.total_races if self.total_races > 0 else 0.0

    @property
    def onder_pct(self) -> float:
        return self.onder / self.total_races if self.total_races > 0 else 0.0

    @property
    def dominant_style(self) -> int:
        """Baskin kosu stili (1-4). 0 = veri yok."""
        vals = [self.geriden, self.ortadan, self.ucayan, self.onder]
        if sum(vals) == 0:
            return 0
        return vals.index(max(vals)) + 1

    @property
    def style_entropy(self) -> float:
        """Stil cesitliligi. 0 = tek stilde kosuyor, 1 = tum stillerde esit."""
        import math
        vals = [self.geriden, self.ortadan, self.ucayan, self.onder]
        total = sum(vals)
        if total == 0:
            return 0.0
        probs = [v / total for v in vals if v > 0]
        if len(probs) <= 1:
            return 0.0
        return -sum(p * math.log(p) for p in probs) / math.log(4)


def parse_stiller_html(html: str) -> list[StilEntry]:
    """Stiller sayfasindan StilEntry listesini cikarir."""
    entries: list[StilEntry] = []

    # HTML entity temizligi
    html = html.replace("&#x131;", "i").replace("&#x130;", "I")
    html = html.replace("&#x15F;", "s").replace("&#xE7;", "c").replace("&#xC7;", "C")
    html = html.replace("&#xF6;", "o").replace("&#xFC;", "u").replace("&#x11F;", "g")
    html = html.replace("&#xD6;", "O").replace("&#xDC;", "U")
    html = html.replace("&#x2B;", "+")

    # Her tr'de at adi + AtStyle blogu var
    trs = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)

    for tr_html in trs:
        if 'AtStyle' not in tr_html:
            continue

        # At adi
        name_match = re.search(r'<a[^>]*>([^<]+)</a>', tr_html)
        if not name_match:
            continue
        horse_name = name_match.group(1).strip()

        # 4 alt bloktaki title degerlerini cikar: "X/Y (Z%)"
        titles = re.findall(r'title="([^"]+)"', tr_html)

        # Ilk title genelde ana blok (0/11), sonraki 4 blok alt stiller
        # Bazi durumlarda kilo degeri de title icine kacmis olabilir
        blocks = []
        for t in titles:
            m = re.match(r'(\d+)/(\d+)\s*\((\d+)%\)', t)
            if m:
                blocks.append((int(m.group(1)), int(m.group(2))))

        if len(blocks) < 4:
            continue

        # Ilk 4 blogu al (bazen 5+ title olabiliyor, ilki ana blok)
        if len(blocks) >= 5:
            blocks = blocks[1:5]
        elif len(blocks) == 4:
            pass  # tam 4 blok
        else:
            continue

        total = blocks[0][1]  # paydadan toplam yaris sayisi
        geriden, ortadan, ucayan, onder = blocks[0][0], blocks[1][0], blocks[2][0], blocks[3][0]

        entries.append(StilEntry(
            horse_name=horse_name,
            total_races=total,
            geriden=geriden,
            ortadan=ortadan,
            ucayan=ucayan,
            onder=onder,
        ))

    return entries


def save_stiller(entries: list[StilEntry], race_date: date, city: str, race_no: int) -> Path:
    """Stil verilerini JSON olarak kaydeder."""
    STILLER_RAW_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{race_date:%Y-%m-%d}_{city.upper()}_K{race_no}.json"
    path = STILLER_RAW_DIR / fname
    data = {
        "race_date": f"{race_date:%Y-%m-%d}",
        "city": city,
        "race_no": race_no,
        "entries": [
            {
                "horse_name": e.horse_name,
                "total_races": e.total_races,
                "geriden": e.geriden,
                "ortadan": e.ortadan,
                "ucayan": e.ucayan,
                "onder": e.onder,
            }
            for e in entries
        ],
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_stiller_file(path: Path) -> list[StilEntry]:
    """JSON dosyasindan StilEntry listesi yukler."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        StilEntry(
            horse_name=e.get("horse_name", ""),
            total_races=e.get("total_races", 0),
            geriden=e.get("geriden", 0),
            ortadan=e.get("ortadan", 0),
            ucayan=e.get("ucayan", 0),
            onder=e.get("onder", 0),
        )
        for e in data.get("entries", [])
    ]


def load_stiller_before(as_of: date) -> dict[str, list[StilEntry]]:
    """as_of tarihinden ONCEKI tum stil verilerini at adina gore gruplandirir."""
    from collections import defaultdict
    from datetime import datetime

    result: dict[str, list[StilEntry]] = defaultdict(list)
    if not STILLER_RAW_DIR.exists():
        return result

    for path in sorted(STILLER_RAW_DIR.glob("*.json")):
        stem = path.stem
        try:
            file_date = datetime.strptime(stem[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        if file_date <= as_of:
            for e in load_stiller_file(path):
                result[e.horse_name].append(e)

    return result
