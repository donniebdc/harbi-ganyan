# -*- coding: utf-8 -*-
"""
PEGADROM SONUÇ TOPLAYICI  (CSV yerine JSON sonuç arşivi)
================================================================================
Pegadrom `sonuclar` + `galoplar` sayfalarından yarış sonuçlarını çeker ve her
gün için tek bir JSON dosyasına yazar. Amaç: okunması zor CSV arşivinden
kurtulup, sistemi JSON sonuçlara bağlamak ve CSV'nin kapsamadığı tarihleri
(ör. 01.04.2026 öncesi) da kapsamak.

Köprü mantığı (at ismi anahtar DEĞİL):
  - program sayfası (.pgd-galop-runner): at_no (.pgd-galop-start) ↔ at_id (/at/ID) ↔ ad
  - sonuç sayfası  (.son-row): bitiş sırası, at_id, ad, derece, ganyan, eküri grubu
  - sonuç at_id  ->  program at_no   (id yoksa isim köprüsü yedek)

Pegadrom sonuç sayfaları altılı/ikili/üçlü ÖDEME tutarlarını içermez; bu arşiv
atbaşı ganyan + kazanan + eküri + alan büyüklüğü + tam varış sırası tutar.

Kullanım:
    python pegadrom_sonuc_topla.py 2026-02-01 2026-03-31
    python pegadrom_sonuc_topla.py 15.05.2026 15.05.2026 --force
    python pegadrom_sonuc_topla.py 2026-05-15 2026-05-15 --out "Sonuclar JSON"

Çıktı yapısı:
    Sonuclar JSON/
      2026-05-15.json
      2026-05-16.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup

# Kanıtlanmış oturum/başlık/menü mantığını tek yerden kullan (sürüklenmeyi önle).
import pegadrom_ai_txt_topla as P

BASE_URL = P.BASE_URL
DEFAULT_OUT = "Sonuclar JSON"
DEFAULT_DELAY = P.DEFAULT_DELAY

# Çıktı klasörü proje kökünde olsun (motor/ üstü).
PROJ_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Sonuç kart gövdesi (her koşunun varış tablosu) bu header ile lazy çekilir.
PARTIAL_HEADERS = {"X-PGD-Partial": "sonuc-card-body", "X-Requested-With": "XMLHttpRequest"}


def _norm_name(s: str) -> str:
    s = P.fold(s).upper()
    return re.sub(r"[^A-Z0-9]+", "", s)


def parse_kosu_kod(html: str) -> dict[int, str]:
    """Hip-seviyesi sonuç sayfasındaki kartlardan {koşu_no: kosu_kod} çıkarır.
    kosu_kod sıralı değildir (ör. 3. koşu = 225016), bu yüzden karttan okunur."""
    out: dict[int, str] = {}
    # data-kosu="N" ... data-body-url="...kosu_kod=KOD"
    for m in re.finditer(r'data-kosu="(\d+)"[^>]*>.*?kosu_kod=(\d+)', html, re.S):
        kno = int(m.group(1))
        if kno not in out:
            out[kno] = m.group(2)
    return out


def _parse_ganyan(s: str):
    """'2,30' -> 2.30 ; '1.234,56' -> 1234.56 ; boş -> None."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


# ── PROGRAM SAYFASI: at_no ↔ at_id ↔ ad ──────────────────────────────────────
def parse_program_atlar(html: str):
    """-> ({at_no: {'at_id','at'}}, {at_id: at_no}, {norm_ad: at_no})"""
    soup = BeautifulSoup(html, "lxml")
    atlar: dict[int, dict] = {}
    id2no: dict[int, int] = {}
    ad2no: dict[str, int] = {}
    for run in soup.select(".pgd-galop-runner"):
        st = run.select_one(".pgd-galop-start")
        a = run.select_one(".pgd-galop-runner-title a[href*='/at/']")
        if not st or not a:
            continue
        no = int(re.sub(r"\D", "", st.get_text()) or 0)
        if not no:
            continue
        m = re.search(r"/at/(\d+)", a.get("href", ""))
        at_id = int(m.group(1)) if m else 0
        name = P.clean(a.get_text())
        atlar[no] = {"at_id": at_id, "at": name}
        if at_id:
            id2no[at_id] = no
        if name:
            ad2no[_norm_name(name)] = no
    return atlar, id2no, ad2no


# ── SONUÇ SAYFASI: bitiş sırası + ganyan + eküri ──────────────────────────────
def parse_sonuc_satirlari(html: str):
    """-> [ {'sira','at_id','at','derece','ganyan','ekuri_grup'} ]  (tablo sırasıyla)"""
    soup = BeautifulSoup(html, "lxml")
    rows = []
    for idx, row in enumerate(soup.select(".son-tablo .son-row"), 1):
        a = row.select_one(".son-at-ad")
        if not a:
            continue
        m = re.search(r"/at/(\d+)", a.get("href", ""))
        at_id = int(m.group(1)) if m else 0
        name = P.clean(a.get_text())
        der = row.select_one(".son-derece")
        derece = P.clean(der.get_text()) if der else ""
        gny = row.select_one(".son-ganyan")
        ganyan = _parse_ganyan(gny.get_text()) if gny else None
        # bitiş sırası: 1-3 madalya, 4+ .son-sira-no; yoksa tablo sırası
        sira = idx
        sno = row.select_one(".son-sira-no")
        if sno and sno.get_text().strip().isdigit():
            sira = int(sno.get_text().strip())
        else:
            med = row.select_one(".son-medal")
            if med:
                cls = " ".join(med.get("class", []))
                mm = re.search(r"son-m(\d)", cls)
                if mm:
                    sira = int(mm.group(1))
        # eküri grubu
        grp = 0
        eg = row.select_one(".pgd-not-ekuri")
        if eg:
            mg = re.search(r"is-group-(\d+)", " ".join(eg.get("class", [])))
            grp = int(mg.group(1)) if mg else 1
        rows.append({"sira": sira, "at_id": at_id, "at": name,
                     "derece": derece, "ganyan": ganyan, "ekuri_grup": grp})
    return rows


# ── KOŞU BİRLEŞTİRME ──────────────────────────────────────────────────────────
def build_kosu(prog_html: str, res_html: str) -> dict | None:
    atlar, id2no, ad2no = parse_program_atlar(prog_html)
    rows = parse_sonuc_satirlari(res_html)
    if not rows:
        return None
    siralama = []
    ekuri_g = defaultdict(set)
    kazanan = None
    for r in rows:
        no = id2no.get(r["at_id"])
        if no is None:
            no = ad2no.get(_norm_name(r["at"]))
        siralama.append({"sira": r["sira"], "at_no": no, "at_id": r["at_id"],
                         "at": r["at"], "derece": r["derece"], "ganyan": r["ganyan"]})
        if r["ekuri_grup"] and no:
            ekuri_g[r["ekuri_grup"]].add(no)
        if r["sira"] == 1 and no:
            kazanan = no
    siralama.sort(key=lambda x: x["sira"])
    ekuri = [sorted(v) for v in ekuri_g.values() if len(v) >= 2]
    return {"n_at": len(atlar), "kazanan": kazanan, "ekuri": ekuri, "siralama": siralama}


# ── TOPLAMA ───────────────────────────────────────────────────────────────────
def collect_range(start: datetime, end: datetime, out_dir: Path, delay: float, force: bool) -> None:
    import requests
    session = requests.Session()
    session.headers.update(P.HEADERS)
    out_dir.mkdir(parents=True, exist_ok=True)
    current = start
    gun_yazildi = gun_atlandi = kosu_yazildi = hata = 0

    while current <= end:
        date_iso = current.strftime("%Y-%m-%d")
        json_path = out_dir / f"{date_iso}.json"
        if json_path.exists() and not force:
            gun_atlandi += 1
            print(f"{date_iso}: var, atlandı")
            current += timedelta(days=1)
            continue
        try:
            menu_html = P.fetch_html(session, f"{BASE_URL}/galoplar?tarih={date_iso}")
            time.sleep(delay)
            hipodromlar = P.gunun_hipodromlari(menu_html)
        except Exception as exc:
            hata += 1
            print(f"{date_iso}: menü alınamadı: {exc}")
            current += timedelta(days=1)
            continue

        if not hipodromlar:
            print(f"{date_iso}: yerli hipodrom yok")
            current += timedelta(days=1)
            continue

        gun = {"tarih": date_iso, "hipodromlar": {}}
        print(f"{date_iso}: " + ", ".join(f"{h}({n})" for h, n in hipodromlar.items()))
        for hip, kosu_sayisi in hipodromlar.items():
            # Hip-seviyesi sonuç sayfası: koşu_no -> kosu_kod eşlemesi (kartlardan).
            try:
                hip_sonuc = P.fetch_html(session, f"{BASE_URL}/sonuclar?tarih={date_iso}&hip={hip}")
                time.sleep(delay)
                kod_map = parse_kosu_kod(hip_sonuc)
            except Exception as exc:
                hata += 1
                print(f"  {hip}: sonuç menüsü alınamadı: {exc}")
                continue

            kosular = {}
            for kno in range(1, kosu_sayisi + 1):
                kod = kod_map.get(kno)
                try:
                    # Program (tam alan: at_no <-> at_id) — koşu bazlı galoplar.
                    prog_html = P.fetch_html(session, f"{BASE_URL}/galoplar?tarih={date_iso}&hip={hip}&kosu={kno}")
                    time.sleep(delay)
                    # Varış tablosu — kosu_kod + partial header ile.
                    if kod:
                        res_html = session.get(
                            f"{BASE_URL}/sonuclar?tarih={date_iso}&hip={hip}&kosu_kod={kod}",
                            headers=PARTIAL_HEADERS, timeout=20).text
                    else:
                        res_html = P.fetch_html(session, f"{BASE_URL}/sonuclar?tarih={date_iso}&hip={hip}&kosu={kno}")
                    time.sleep(delay)
                    kv = build_kosu(prog_html, res_html)
                    if kv and kv.get("kazanan"):
                        kosular[str(kno)] = kv
                        kosu_yazildi += 1
                        print(f"  {hip} {kno}. koşu: kazanan No:{kv['kazanan']} ({kv['n_at']} at)")
                    else:
                        print(f"  {hip} {kno}. koşu: sonuç yok/eksik")
                except Exception as exc:
                    hata += 1
                    print(f"  {hip} {kno}. koşu: hata: {exc}")
            if kosular:
                gun["hipodromlar"][hip] = {"kosular": kosular}

        json_path.write_text(json.dumps(gun, ensure_ascii=False, indent=1), encoding="utf-8")
        gun_yazildi += 1
        current += timedelta(days=1)

    print("")
    print(f"Tamamlandı. Gün yazılan: {gun_yazildi}, gün atlanan: {gun_atlandi}, "
          f"koşu yazılan: {kosu_yazildi}, hata: {hata}")
    print(f"Çıktı klasörü: {out_dir.resolve()}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Pegadrom yarış sonuçlarını JSON olarak toplar.")
    ap.add_argument("baslangic", type=P.parse_date, help="Başlangıç: YYYY-MM-DD veya GG.AA.YYYY")
    ap.add_argument("bitis", type=P.parse_date, help="Bitiş: YYYY-MM-DD veya GG.AA.YYYY")
    ap.add_argument("--out", default=None, help=f"Çıktı klasörü (varsayılan: {DEFAULT_OUT})")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="İstekler arası bekleme (sn)")
    ap.add_argument("--force", action="store_true", help="Var olan JSON gününü yeniden yaz")
    args = ap.parse_args()
    if args.bitis < args.baslangic:
        raise SystemExit("Bitiş tarihi başlangıçtan önce olamaz.")
    out_dir = Path(args.out) if args.out else Path(PROJ_BASE) / DEFAULT_OUT
    collect_range(args.baslangic, args.bitis, out_dir, args.delay, args.force)


if __name__ == "__main__":
    main()
