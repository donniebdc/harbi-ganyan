from __future__ import annotations

import re
import unicodedata
from pathlib import Path


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def fold(text: str | None) -> str:
    repl = {
        305: "i", 304: "I", 351: "s", 350: "S", 287: "g", 286: "G",
        252: "u", 220: "U", 246: "o", 214: "O", 231: "c", 199: "C",
    }
    text = "".join(repl.get(ord(ch), ch) for ch in clean(text))
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).upper()


def norm_city(text: str | None) -> str:
    return fold(text)


def parse_ai_txt(path: Path) -> dict[int, dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows: dict[int, dict] = {}
    flow: dict[int, dict] = {}
    in_flow = False
    in_ranking = False

    for line in text.splitlines():
        if line.startswith("2) YARIS AKISI"):
            in_flow = True
            in_ranking = False
            continue
        if line.startswith("3) KARAR OZETI"):
            in_flow = False
        if line.startswith("5) MODEL SIRALAMASI"):
            in_ranking = True
            in_flow = False
            continue
        if line.startswith("6) VERI DAYANAKLARI"):
            in_ranking = False

        if in_flow:
            match = re.match(
                r"Akış\s+(\d+)\s+\|\s+No\s+(\d+)\s+•\s+(.+?)\s+\|\s+(.+?)\s*/\s*Konum\s+(\d+)/100",
                line,
            )
            if match:
                no = int(match.group(2))
                flow[no] = {
                    "peg_flow_rank": int(match.group(1)),
                    "peg_flow_type": match.group(4).strip(),
                    "peg_flow_pos": float(match.group(5)),
                }

        if in_ranking:
            match = re.match(
                r"\s*(\d+)\s+(\d+)\s+(.+?)\s{2,}(.+?)\s{2,}"
                r"(Seri|Sprint|Orta|Ön grup)\s+(\d+)\s+(\d+)\s+(.+?)\s{2,}(.+?)\s*\|\s*Form:\s*(.*)$",
                line,
            )
            if match:
                no = int(match.group(2))
                signals = {}
                for sig in re.finditer(r"([^,]+?)\s+(\d+)/100", match.group(9)):
                    signals[sig.group(1).strip()] = float(sig.group(2))
                rows[no] = {
                    "peg_rank": int(match.group(1)),
                    "peg_model": float(match.group(6)),
                    "peg_veri": float(match.group(7)),
                    "peg_guven_label": match.group(8).strip(),
                    "peg_flow_type": match.group(5).strip(),
                    "peg_galop_reason": signals.get("Galop"),
                    "peg_hiz_reason": signals.get("Hız"),
                    "peg_pist_reason": signals.get("Pist/Mesafe"),
                    "peg_form_reason": signals.get("Form"),
                }

    field_size = max(len(rows), len(flow))
    for no, vals in flow.items():
        rows.setdefault(no, {}).update(vals)
    for no, vals in rows.items():
        rank = vals.get("peg_flow_rank")
        if rank and field_size > 1:
            vals["peg_flow_score"] = (field_size - rank) / (field_size - 1) * 100.0
        elif rank:
            vals["peg_flow_score"] = 100.0
        else:
            vals["peg_flow_score"] = None
    return rows


def load_ai_txt_root(root: str | Path) -> dict[str, dict[int, dict]]:
    root = Path(root)
    out: dict[str, dict[int, dict]] = {}
    if not root.exists():
        return out
    for path in root.rglob("kosu_*_ai_analiz.txt"):
        try:
            date = path.parts[-3]
            city = norm_city(path.parts[-2])
            race_no = int(re.search(r"kosu_(\d+)_", path.name).group(1))
        except Exception:
            continue
        key = f"{date}|{city}|{race_no}"
        out[key] = parse_ai_txt(path)
    return out
