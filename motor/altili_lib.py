# -*- coding: utf-8 -*-
"""
ALTILI BACKTEST — ORTAK KÜTÜPHANE
================================================================================
İki kaynağı eşleştirir:
  (1) v5 tahmin arşivi (KO:/5SATIR:/ATNO: satırları) — her koşunun ANA-skor sıralı
      tam at dökümü, AGF, akış rank, alt-grup, fark.
  (2) CSV sonuç arşivi — gerçek kazananlar (GANYAN), altılı ayak tanımları ve
      altılı ödemeleri (N. 6'LI GANYAN), eküri kayıtları.

Eşleştirme anahtarı: (tarih, hipodrom_norm, koşu_no, at_no). At ismi anahtar değil.
"""
import os, re, glob, json
from datetime import datetime

# Proje kök klasörü = bu dosyanın bulunduğu 'motor' klasörünün üstü.
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOTOR = os.path.dirname(os.path.abspath(__file__))

# ── normalizasyon ────────────────────────────────────────────────────────────
def norm_hip(s):
    if not s: return ""
    s = re.sub(r'#U([0-9A-Fa-f]{4})', lambda x: chr(int(x.group(1),16)), s)
    return s.upper().translate(str.maketrans("ğüşıöçĞÜŞİÖÇİ","gusiocGUSIOCI")).strip()

# Altılı ganyan birim fiyatı (TL/kombinasyon) — hipodroma göre.
BIRIM_125 = {"ISTANBUL","ANKARA","IZMIR","ADANA","BURSA","KOCAELI","ANTALYA"}
BIRIM_100 = {"SANLIURFA","ELAZIG","DIYARBAKIR"}
def birim_fiyat(hip):
    """Normalize edilmiş hipodrom adına göre altılı birim fiyatı."""
    h = norm_hip(hip)
    if h in BIRIM_100: return 1.00
    return 1.25   # varsayılan (İstanbul/Ankara/İzmir/Adana/Bursa/Kocaeli/Antalya)

# ── EKÜRİ (stablemate) ───────────────────────────────────────────────────────
# Bültende eküri atlar `stablemate>0` bayrağıyla işaretlenir; aynı sahip altında
# gruplanır. Eküri = bahis için kuplajlı: birini yazmak diğerini de kapsar.
def ekuri_gruplari(atlar, no="at_no", sm="stablemate", ow="owner"):
    """atlar listesinden eküri gruplarını (at_no kümeleri) çıkarır."""
    from collections import defaultdict
    g = defaultdict(list)
    for a in atlar:
        if (a.get(sm) or 0) > 0 and a.get(ow):
            g[a[ow]].append(a[no])
    return [set(v) for v in g.values() if len(v) >= 2]

def ekuri_ortaklari(no, gruplar):
    """Bir at_no'nun eküri ortakları (kendisi hariç)."""
    s = set()
    for grp in gruplar:
        if no in grp:
            s |= (grp - {no})
    return s

def ekuri_serialize(gruplar):
    """[{1,7},{12,14}] -> '1-7|12-14' (parse-edilebilir çıktı için)."""
    return "|".join("-".join(str(x) for x in sorted(g)) for g in gruplar)

def ekuri_parse(s):
    """'1-7|12-14' -> [{1,7},{12,14}]."""
    out = []
    for grp in (s or "").split("|"):
        grp = grp.strip()
        if not grp: continue
        nums = {int(x) for x in grp.split("-") if x.strip().isdigit()}
        if len(nums) >= 2: out.append(nums)
    return out

# ── v5 TAHMİN ARŞİVİ PARSE ───────────────────────────────────────────────────
def parse_tahmin_arsiv(path):
    """-> races[(tarih_iso, hip_norm, kno)] = {
            'hip_disp', 'tarih', 'ag','alt','pist','mesafe','kaynak',
            'atlar': [ {at_no, at, ana, agf, flow_rank, flow_score, peg_model} ... ]  # ANA azalan
            'n_at', 'fark' }
    """
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    races = {}
    cur = None
    for ln in lines:
        if ln.startswith("KO:"):
            p = ln[3:].split("|")
            # kno|hip|tarih|ag|alt|pist|mesafe|saat|kaynak
            kno = int(p[0]); hip_disp = p[1]; tarih = p[2]
            ag = p[3]; alt = p[4]; pist = p[5]; mesafe = int(p[6]) if p[6].isdigit() else 0
            kaynak = p[8] if len(p) > 8 else ""
            ti = datetime.strptime(tarih, "%d.%m.%Y").strftime("%Y-%m-%d")
            key = (ti, norm_hip(hip_disp), kno)
            cur = {"hip_disp": hip_disp, "tarih": tarih, "tarih_iso": ti, "kno": kno,
                   "ag": ag, "alt": alt, "pist": pist, "mesafe": mesafe,
                   "kaynak": kaynak, "atlar": [], "ekuri": []}
            races[key] = cur
        elif ln.startswith("EKURI:") and cur is not None:
            cur["ekuri"] = ekuri_parse(ln[6:].strip())
        elif ln.startswith("ATNO:") and cur is not None:
            d = {}
            for tok in ln.split("|"):
                if ":" not in tok: continue
                k, v = tok.split(":", 1)
                d[k] = v
            try:
                cur["atlar"].append({
                    "at_no": int(d.get("ATNO", 0)),
                    "at": d.get("AT", ""),
                    "ana": float(d.get("ANA", 0)),
                    "agf": float(d.get("AGF", 0)),
                    "flow_rank": int(d.get("AKIS", 0)),
                    "flow_score": float(d.get("AKS", 0)),
                    "peg_model": float(d.get("PEGMOD", 0)),
                })
            except Exception:
                pass
    for key, r in races.items():
        r["atlar"].sort(key=lambda x: x["ana"], reverse=True)
        r["n_at"] = len(r["atlar"])
        r["fark"] = (r["atlar"][0]["ana"] - r["atlar"][1]["ana"]) if len(r["atlar"]) >= 2 else 100.0
    return races

# ── CSV SONUÇ ARŞİVİ PARSE ───────────────────────────────────────────────────
RE_KOSU   = re.compile(r"(\d+)\.\s*Kosu\s*:")
RE_GANYAN = re.compile(r"(?<![A-Za-zÇĞİÖŞÜçğıöşü'])GANYAN\((\d+)\)")  # düz ganyan = kazanan (3'LÜ/6'LI/5'Lİ hariç)
RE_ALTILI = re.compile(r"(\d+)\.\s*6'?L[İIı]\s*GANYAN\(([^)]*)\)\s*:\s*([\d.]+,\d+)")
RE_EKURI  = re.compile(r"\((\d+)\)[^,\]]*", )  # eküri grubundaki numaralar

def _parse_payout(s):
    # "17.651,18" -> 17651.18
    return float(s.replace(".", "").replace(",", "."))

def parse_csv_sonuc(path):
    """-> {
        'hip_norm','tarih_iso',
        'kazanan': {kno: winner_no},
        'ekuri':   {kno: [ [grup_no,...], ... ]},
        'altililar': [ {'idx':int,'last':kno,'legs':[kno...],'odeme':float} ],
        'n_at': {kno: alan_buyuklugu}  (CSV'deki koşan at sayısı)
       }  ya da None
    """
    fname = os.path.basename(path)
    parts = fname.split("-")
    if len(parts) < 2: return None
    try:
        tarih_iso = datetime.strptime(parts[0], "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        return None
    hip_norm = norm_hip(parts[1])
    try:
        lines = open(path, encoding="utf-8-sig").read().split("\n")
    except Exception:
        return None

    kazanan = {}; ekuri = {}; altililar = []; n_at = {}; sonuc_say = {}
    cur_k = None; in_rows = False
    for raw in lines:
        line = raw.strip().replace("\r", "")
        mk = RE_KOSU.search(line)
        if mk and ". Kosu :" in line:
            cur_k = int(mk.group(1)); in_rows = False
            n_at.setdefault(cur_k, 0)
            continue
        if "At No;At İsmi" in line:
            in_rows = True; continue
        if "GANYAN(" in line or "İKİLİ(" in line:
            in_rows = False
        # at satırı sayımı (alan büyüklüğü)
        if in_rows and cur_k is not None:
            p = line.split(";")
            if len(p) >= 14 and p[0].strip().isdigit():
                n_at[cur_k] = n_at.get(cur_k, 0) + 1
        # kazanan (düz ganyan)
        if cur_k is not None and cur_k not in kazanan:
            mg = RE_GANYAN.search(line)
            if mg:
                kazanan[cur_k] = int(mg.group(1))
        # eküri
        if "eküri" in line.lower() and cur_k is not None:
            grp = [int(x) for x in re.findall(r"\((\d+)\)", line.split("eküri")[0])]
            if grp:
                ekuri.setdefault(cur_k, []).append(grp)
        # altılı tanımı + ödeme (son ayağın footer'ında)
        for ma in RE_ALTILI.finditer(line):
            idx = int(ma.group(1)); odeme = _parse_payout(ma.group(3))
            last = cur_k
            if last is None: continue
            legs = list(range(last - 5, last + 1))
            altililar.append({"idx": idx, "last": last, "legs": legs, "odeme": odeme})
    if not kazanan:
        return None
    return {"hip_norm": hip_norm, "tarih_iso": tarih_iso,
            "kazanan": kazanan, "ekuri": ekuri,
            "altililar": altililar, "n_at": n_at}

def load_all_csv(dirs=None):
    if dirs is None:
        dirs = [os.path.join(BASE, "CSV Sonuçlar", "NİSAN"),
                os.path.join(BASE, "CSV Sonuçlar", "MAYIS")]
    out = {}
    files = []
    for d in dirs:
        files += glob.glob(os.path.join(d, "*.csv"))
    for fp in files:
        r = parse_csv_sonuc(fp)
        if r:
            out[(r["tarih_iso"], r["hip_norm"])] = r
    return out

# ── JSON SONUÇ ARŞİVİ (Pegadrom) ─────────────────────────────────────────────
# pegadrom_sonuc_topla.py çıktısı: Sonuclar JSON/<tarih>.json
#   {tarih, hipodromlar:{HIP:{kosular:{"N":{n_at,kazanan,ekuri:[[no..]],siralama:[...]}}}}}
# load_all_csv ile AYNI şekli döndürür (drop-in). Fark: Pegadrom sonuç sayfaları
# altılı/ikili/üçlü ÖDEME tutarı vermez -> altililar=[] (kupon ROI'si CSV'ye özgü).
JSON_SONUC_DIR = os.path.join(BASE, "Sonuclar JSON")

def parse_json_sonuc(path):
    """Tek günlük JSON dosyasını {(tarih_iso,hip_norm): csv_uyumlu_obj} olarak döndürür."""
    try:
        gun = json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}
    tarih_iso = gun.get("tarih", "")
    out = {}
    for hip, hd in (gun.get("hipodromlar") or {}).items():
        hip_norm = norm_hip(hip)
        kazanan = {}; ekuri = {}; n_at = {}; kazanan_ad = {}; siralama = {}; altililar = []; berabere = {}
        for kno_s, kv in (hd.get("kosular") or {}).items():
            try:
                kno = int(kno_s)
            except ValueError:
                continue
            if kv.get("kazanan"):
                kazanan[kno] = kv["kazanan"]
            if kv.get("ekuri"):
                ekuri[kno] = [list(g) for g in kv["ekuri"]]
            # Berabere (dead-heat): birden çok GANYAN kazananı -> hepsi kazanan kümesinde.
            kzl = kv.get("kazananlar") or []
            if len(kzl) > 1:
                berabere[kno] = list(kzl)
            n_at[kno] = kv.get("n_at", 0)
            siralama[kno] = kv.get("siralama") or []
            for s in siralama[kno]:
                if s.get("sira") == 1:
                    kazanan_ad[kno] = s.get("at", "")
            # Altılı ödemesi (TJK feed): son ayak koşusunun bahisler'inde "6'LI GANYAN".
            for b in ((kv.get("bahisler") or {}).get("kalemler") or []):
                tip = b.get("tip", "")
                if "6'LI GANYAN" in tip or "6’LI GANYAN" in tip:
                    mi = re.match(r"\s*(\d+)\s*\.", tip)
                    idx = int(mi.group(1)) if mi else (len(altililar) + 1)
                    altililar.append({"idx": idx, "last": kno,
                                      "legs": list(range(kno - 5, kno + 1)),
                                      "odeme": b.get("tutar") or 0.0})
        if kazanan:
            out[(tarih_iso, hip_norm)] = {
                "hip_norm": hip_norm, "tarih_iso": tarih_iso,
                "kazanan": kazanan, "ekuri": ekuri, "altililar": altililar,
                "n_at": n_at, "kazanan_ad": kazanan_ad, "siralama": siralama,
                "berabere": berabere, "kaynak": "json"}
    return out

def load_all_json(dirpath=None):
    out = {}
    dirpath = dirpath or JSON_SONUC_DIR
    for fp in glob.glob(os.path.join(dirpath, "*.json")):
        out.update(parse_json_sonuc(fp))
    return out

def load_results(prefer="json"):
    """Birleşik sonuç yükleyici. prefer='json' ise JSON taban, eksik (tarih,hip)
    için CSV ile tamamlar; prefer='csv' tersi. -> {(tarih_iso,hip_norm): obj}."""
    j = load_all_json(); c = load_all_csv()
    if prefer == "csv":
        base, ek = c, j
    else:
        base, ek = j, c
    out = dict(ek); out.update(base)   # base öncelikli
    return out

def winning_set(csv_obj, kno):
    """Bir ayağın kazanan kümesi = kazanan ∪ eküri ortakları ∪ berabere (dead-heat) kazananları."""
    w = csv_obj["kazanan"].get(kno)
    if w is None: return set()
    s = {w}
    # berabere (dead-heat) eş-kazananlar (TJK feed): tümü kazanan sayılır
    for co in csv_obj.get("berabere", {}).get(kno, []):
        s.add(co)
    # eküri: kazanan(lar)ın eküri ortakları
    for grp in csv_obj["ekuri"].get(kno, []):
        if s & set(grp):
            s.update(grp)
    return s
