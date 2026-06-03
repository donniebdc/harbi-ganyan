"""
Pegadrom AI Analiz TXT Toplayici
================================

Tarih araligindaki yerli kosularin Pegadrom ai-analiz sayfalarini ceker ve
her kosuyu okunabilir TXT olarak kaydeder.

Kullanim:
    python pegadrom_ai_txt_topla.py 2026-05-29 2026-05-29
    python pegadrom_ai_txt_topla.py 2026-05-01 2026-05-28 --out "Pegadrom AI TXT"
    python pegadrom_ai_txt_topla.py 29.05.2026 30.05.2026 --force

Cikti yapisi:
    Pegadrom AI Analiz TXT/
      2026-05-29/
        ISTANBUL/
          kosu_01_ai_analiz.txt
          kosu_02_ai_analiz.txt
        BURSA/
          kosu_01_ai_analiz.txt
        index.txt
"""

from __future__ import annotations

import argparse
import re
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://www.pegadrom.com"
DEFAULT_OUT = "Pegadrom AI Analiz TXT"
DEFAULT_DELAY = 0.8

TR_HIPODROMLAR = {
    "ISTANBUL", "ANKARA", "IZMIR", "BURSA", "ADANA", "ELAZIG",
    "DIYARBAKIR", "KOCAELI", "SANLIURFA", "BALIKESIR", "ANTALYA",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:151.0) "
        "Gecko/20100101 Firefox/151.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\xa0", " ")).strip()


def fold(text: str | None) -> str:
    repl = {
        305: "i", 304: "I", 351: "s", 350: "S", 287: "g", 286: "G",
        252: "u", 220: "U", 246: "o", 214: "O", 231: "c", 199: "C",
    }
    text = "".join(repl.get(ord(ch), ch) for ch in clean(text))
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def title_line(text: str, ch: str = "=") -> list[str]:
    return [text, ch * len(text)]


def parse_date(value: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise argparse.ArgumentTypeError("Tarih formati YYYY-MM-DD veya GG.AA.YYYY olmali.")


def fetch_html(session: requests.Session, url: str, timeout: int = 20) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.text


def gunun_hipodromlari(html: str) -> dict[str, int]:
    """
    Pegadrom menulerinden o gunun gercek Turkiye hipodromlarini ve kosu
    sayilarini cikarir. Gecersiz hipodrom denemelerini engellemek icin
    mutlaka menuden okuruz.

    Pegadrom menu markup'i degisebildigi icin regex yerine link tabanli
    saglam yontem: hip=XXX iceren <a> linklerini gez, link metnindeki
    'N kosu' ifadesinden kosu sayisini al. Yerli hipodromlari TR_HIPODROMLAR
    ile filtrele (yabanci/karma hipodromlar haric).
    """
    soup = BeautifulSoup(html, "lxml")
    sonuc: dict[str, int] = {}
    for a in soup.find_all("a", href=True):
        m = re.search(r"hip=([A-Za-z]+)", a["href"])
        if not m:
            continue
        hip = m.group(1).upper()
        if hip not in TR_HIPODROMLAR or hip in sonuc:
            continue
        km = re.search(r"(\d+)\s*ko[sşŞ]u", a.get_text(" "), re.IGNORECASE)
        if km:
            sonuc[hip] = int(km.group(1))
    return sonuc


def card_title_text(card) -> str:
    div = card.find("div", class_="pgd-ai-card-title", recursive=False)
    strong = div.find("strong", recursive=False) if div else None
    return clean(strong.get_text()) if strong else ""


def card_subtitle_text(card) -> str:
    div = card.find("div", class_="pgd-ai-card-title", recursive=False)
    span = div.find("span", recursive=False) if div else None
    return clean(span.get_text()) if span else ""


def card_by_title(soup: BeautifulSoup, title_ascii: str):
    wanted = fold(title_ascii)
    for card in soup.select(".pgd-ai-card"):
        if fold(card_title_text(card)) == wanted:
            return card
    return None


def safe_filename(text: str) -> str:
    text = fold(text).upper()
    text = re.sub(r"[^A-Z0-9_-]+", "_", text)
    return text.strip("_") or "DOSYA"


def parse_page_summary(soup: BeautifulSoup) -> list[str]:
    text = clean(soup.get_text(" "))
    lines = title_line("1) SAYFA OZETI", "-")
    summary_patterns = [
        ("Kosucu sayisi", r"AI analiz at (\d+) kosucu", fold(text), ""),
        ("Ortalama AI puani", r"Ortalama (\d+/100)", text, ""),
        ("Veri guveni", r"Veri (\d+/100)", text, ""),
        ("Katman sayisi", r"Katman (\d+) sinyal", text, " sinyal"),
    ]
    for label, pattern, source, suffix in summary_patterns:
        match = re.search(pattern, source, re.IGNORECASE)
        if match:
            lines.append(f"{label:<18}: {match.group(1)}{suffix}")
    selected = re.search(r"AI Seçili Koşu (.*?) Pegadrom Takvimi", text)
    if selected:
        lines.append(f"Secili kosu       : {selected.group(1)}")
    if len(lines) == 2:
        lines.append("Ozet alani bulunamadi.")
    return lines


def parse_flow_block(soup: BeautifulSoup) -> list[str]:
    lines = title_line("2) YARIS AKISI - TEMPO / KONUM", "-")
    flow = card_by_title(soup, "Yaris Akisi")
    if not flow:
        lines.append("Yaris akisi bulunamadi.")
        return lines
    for lane in flow.select(".pgd-ai-lane"):
        horse_el = lane.select_one(".pgd-ai-lane-title strong")
        meta_el = lane.select_one(".pgd-ai-lane-meta")
        rank_el = lane.select_one(".pgd-ai-rank")
        horse = clean(horse_el.get_text()) if horse_el else ""
        meta = clean(meta_el.get_text()) if meta_el else ""
        rank = clean(rank_el.get_text()) if rank_el else ""
        lines.append(f"{rank:8} | {horse:<30} | {meta}")
    return lines


def parse_decision_block(soup: BeautifulSoup) -> list[str]:
    lines = title_line("3) KARAR OZETI", "-")
    summary = card_by_title(soup, "Karar Ozeti")
    if not summary:
        lines.append("Karar ozeti bulunamadi.")
        return lines
    subtitle = card_subtitle_text(summary)
    if subtitle:
        lines.append(f"Genel: {subtitle}")
    for div in summary.select(".pgd-ai-lead-pair > div"):
        label = clean(div.select_one("span").get_text()) if div.select_one("span") else ""
        strong = clean(div.select_one("strong").get_text()) if div.select_one("strong") else ""
        small = clean(div.select_one("small").get_text()) if div.select_one("small") else ""
        lines.append(f"{label:<14}: {strong} ({small})")
    decisions = [clean(p.get_text()) for p in summary.select(".pgd-ai-decision p")]
    if decisions:
        lines.append("")
        lines.append("Karar notlari:")
        for idx, item in enumerate(decisions, 1):
            lines.append(f"{idx}. {item}")
    return lines


def parse_layers_block(soup: BeautifulSoup) -> list[str]:
    lines = title_line("4) 17 VERI KATMANI", "-")
    layers = card_by_title(soup, "17 Veri Katmani")
    if not layers:
        lines.append("Veri katmanlari bulunamadi.")
        return lines
    subtitle = card_subtitle_text(layers)
    if subtitle:
        lines.append(subtitle)
        lines.append("")
    for metric in layers.select(".pgd-ai-metric"):
        label_el = metric.select_one(".pgd-ai-metric-copy span")
        value_el = metric.select_one(".pgd-ai-metric-copy em")
        detail_el = metric.select_one(".pgd-ai-metric-copy small")
        target_el = metric.select_one(".pgd-ai-metric-score")
        label = clean(label_el.get_text()) if label_el else ""
        value = clean(value_el.get_text()) if value_el else ""
        detail = clean(detail_el.get_text()) if detail_el else ""
        target = target_el.get("data-target", "") if target_el else ""
        note = f" [{target}/100]" if target.isdigit() else ""
        lines.append(f"- {label:<20}: {value}{note}")
        if detail:
            lines.append(f"  Detay: {detail}")
    return lines


def parse_ranking_block(soup: BeautifulSoup) -> list[str]:
    lines = title_line("5) MODEL SIRALAMASI", "-")
    ranking = card_by_title(soup, "Model Siralamasi")
    if not ranking:
        lines.append("Model siralamasi bulunamadi.")
        return lines
    subtitle = card_subtitle_text(ranking)
    if subtitle:
        lines.append(subtitle)
        lines.append("")
    header = (
        f"{'Sira':<4} {'No':<3} {'At':<24} {'Jokey':<20} {'Akis':<9} "
        f"{'Model':>5} {'Veri':>5} {'Guven':<12}  Sinyaller / Son Form"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for idx, row in enumerate(ranking.select(".pgd-ai-row"), 1):
        no = clean(row.select_one(".pgd-ai-row-no").get_text()) if row.select_one(".pgd-ai-row-no") else ""
        horse = clean(row.select_one(".pgd-ai-row-title strong").get_text()) if row.select_one(".pgd-ai-row-title strong") else ""
        meta = clean(row.select_one(".pgd-ai-row-copy > span").get_text()) if row.select_one(".pgd-ai-row-copy > span") else ""
        if chr(8226) in meta:
            jockey, flow_type = [clean(x) for x in meta.split(chr(8226), 1)]
        else:
            jockey, flow_type = meta, ""
        reasons = ", ".join(clean(x.get_text()) for x in row.select(".pgd-ai-reasons span"))
        bars = {
            clean(span.select_one("small").get_text()): clean(span.select_one("em").get_text())
            for span in row.select(".pgd-ai-row-bars span")
            if span.select_one("small") and span.select_one("em")
        }
        chip = clean(row.select_one(".pgd-ai-chip").get_text()) if row.select_one(".pgd-ai-chip") else ""
        form = "-".join(clean(x.get_text()) for x in row.select(".pgd-ai-row-form .pgd-lineup-form-pill"))
        lines.append(
            f"{idx:<4} {no:<3} {horse:<24} {jockey:<20} {flow_type:<9} "
            f"{bars.get('Model', ''):>5} {bars.get('Veri', ''):>5} {chip:<12}  "
            f"{reasons} | Form: {form}"
        )
    return lines


def parse_evidence_block(soup: BeautifulSoup) -> list[str]:
    lines = title_line("6) VERI DAYANAKLARI - AT BAZLI", "-")
    evidence = card_by_title(soup, "Veri Dayanaklari")
    if not evidence:
        lines.append("Veri dayanaklari bulunamadi.")
        return lines
    notes = evidence.select(".pgd-ai-note")
    if not notes:
        lines.append("At bazli dayanak bulunamadi.")
        return lines
    for note in notes:
        strong = note.find("strong", recursive=False)
        span = note.find("span", recursive=False)
        horse = clean(strong.get_text()) if strong else ""
        summary = clean(span.get_text()) if span else ""
        lines.append(horse)
        if summary:
            lines.append(f"  Ozet: {summary}")
        for factor in note.select(".pgd-ai-factor"):
            label = clean(factor.select_one("small").get_text()) if factor.select_one("small") else ""
            value = clean(factor.select_one("em").get_text()) if factor.select_one("em") else ""
            desc = clean(factor.select_one("strong").get_text()) if factor.select_one("strong") else ""
            lines.append(f"  - {label:<12} {value:>3} | {desc}")
        lines.append("")
    return lines


def build_txt(html: str, url: str, date_iso: str, hip: str, kosu_no: int) -> str:
    soup = BeautifulSoup(html, "lxml")
    lines: list[str] = []
    lines += title_line("PEGADROM AI ANALIZ - OKUNABILIR VERI DOKUMU")
    lines.append(f"Kaynak URL: {url}")
    lines.append(f"Tarih/Hipodrom/Kosu: {date_iso} / {hip} / {kosu_no}")
    lines.append("")
    for block in [
        parse_page_summary,
        parse_flow_block,
        parse_decision_block,
        parse_layers_block,
        parse_ranking_block,
        parse_evidence_block,
    ]:
        lines.extend(block(soup))
        lines.append("")
    lines += title_line("7) KULLANILABILIR ALANLAR", "-")
    lines.append("- Model skoru ve veri guveni: ana aday siralamasi icin.")
    lines.append("- Yaris akisi / konum: tempo senaryosu ve onde giden-sprinter ayrimi icin.")
    lines.append("- 17 veri katmani: sinyal bazli model feature seti icin.")
    lines.append("- Veri dayanaklari: at bazli Pist/Mesafe, Galop, Form, Hiz, Jokey gibi ayrik feature kaynaklari icin.")
    lines.append("- Son form dizisi: yakin donem performans trendi ve pist tipi gecmisi icin.")
    return "\n".join(lines).rstrip() + "\n"


def collect_range(start: datetime, end: datetime, out_dir: Path, delay: float, force: bool,
                  skip: set | None = None) -> None:
    """skip: {(HIP_KODU_UPPER, kosu_no)} — force=True olsa bile bu koşuların MEVCUT
    TXT'si KORUNUR (yeniden indirilmez). Canlı yeniden-üretimde BAŞLAMIŞ koşuların
    koşu-sonrası Pegadrom verisinin motora sızmasını engeller (look-ahead koruması)."""
    skip = skip or set()
    session = requests.Session()
    session.headers.update(HEADERS)
    out_dir.mkdir(parents=True, exist_ok=True)
    current = start
    written = skipped = failed = 0

    while current <= end:
        date_iso = current.strftime("%Y-%m-%d")
        date_dir = out_dir / date_iso
        date_dir.mkdir(parents=True, exist_ok=True)
        index_lines = [f"Pegadrom AI Analiz TXT index - {date_iso}", ""]

        try:
            menu_url = f"{BASE_URL}/galoplar?tarih={date_iso}"
            menu_html = fetch_html(session, menu_url)
            time.sleep(delay)
            hipodromlar = gunun_hipodromlari(menu_html)
        except Exception as exc:
            failed += 1
            print(f"{date_iso}: menu alinamadi: {exc}")
            current += timedelta(days=1)
            continue

        if not hipodromlar:
            print(f"{date_iso}: yerli hipodrom bulunamadi")
            index_lines.append("Yerli hipodrom bulunamadi.")
            (date_dir / "index.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
            current += timedelta(days=1)
            continue

        print(f"{date_iso}: " + ", ".join(f"{h}({n})" for h, n in hipodromlar.items()))
        for hip, kosu_sayisi in hipodromlar.items():
            hip_dir = date_dir / safe_filename(hip)
            hip_dir.mkdir(parents=True, exist_ok=True)
            index_lines.append(f"{hip}: {kosu_sayisi} kosu")
            for kosu_no in range(1, kosu_sayisi + 1):
                txt_path = hip_dir / f"kosu_{kosu_no:02d}_ai_analiz.txt"
                # force olsa bile: dosya varsa ve (a) force kapalı VEYA (b) bu koşu
                # 'skip' (başlamış) ise -> mevcut TXT korunur.
                if txt_path.exists() and (not force or (hip.upper(), kosu_no) in skip):
                    skipped += 1
                    etiket = "donduruldu (basladi)" if force else "var, atlandi"
                    print(f"  {hip} {kosu_no}. kosu: {etiket}")
                    continue
                url = f"{BASE_URL}/ai-analiz?tarih={date_iso}&hip={hip}&kosu={kosu_no}"
                try:
                    html = fetch_html(session, url)
                    txt = build_txt(html, url, date_iso, hip, kosu_no)
                    txt_path.write_text(txt, encoding="utf-8")
                    written += 1
                    print(f"  {hip} {kosu_no}. kosu: yazildi")
                except Exception as exc:
                    failed += 1
                    err_path = hip_dir / f"kosu_{kosu_no:02d}_HATA.txt"
                    err_path.write_text(f"URL: {url}\nHATA: {exc}\n", encoding="utf-8")
                    print(f"  {hip} {kosu_no}. kosu: hata: {exc}")
                time.sleep(delay)
            index_lines.append("")

        (date_dir / "index.txt").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        current += timedelta(days=1)

    print("")
    print(f"Tamamlandi. Yazilan: {written}, atlanan: {skipped}, hata: {failed}")
    print(f"Cikti klasoru: {out_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pegadrom AI analiz sayfalarini TXT olarak toplar.")
    parser.add_argument("baslangic", type=parse_date, help="Baslangic tarihi: YYYY-MM-DD veya GG.AA.YYYY")
    parser.add_argument("bitis", type=parse_date, help="Bitis tarihi: YYYY-MM-DD veya GG.AA.YYYY")
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"Cikti klasoru (varsayilan: {DEFAULT_OUT})")
    parser.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="Istekler arasi bekleme saniyesi")
    parser.add_argument("--force", action="store_true", help="Var olan TXT dosyalarini yeniden yaz")
    args = parser.parse_args()

    start = args.baslangic
    end = args.bitis
    if end < start:
        raise SystemExit("Bitis tarihi baslangictan once olamaz.")

    collect_range(start, end, Path(args.out), args.delay, args.force)


if __name__ == "__main__":
    main()
