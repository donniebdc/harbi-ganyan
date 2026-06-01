# -*- coding: utf-8 -*-
"""
SINYAL FİZİBİLİTE TESTİ — kendi CSV arşivimizden üretilen bağımsız sinyaller.
================================================================================
Amaç: AGF/Pegadrom-akışının GÖRMEDİĞİ bağımsız sinyalleri sırayla ölçmek.
Her sinyal at-yarış başına SADECE GEÇMİŞ yarışlardan üretilir (sızıntı yok).

Test edilen adaylar:
  1) MESAFE+PİST UYUMU  — atın bu mesafe bandı + zeminde tarihsel performansı
  2) FORM TRENDİ        — son yarışların yükselen/düşen ivmesi
  3) SINIF GEÇİŞİ       — kategori (maiden/şartlı/handikap) yukarı/aşağı hareketi
  4) DERECE KALİTESİ    — benzer mesafede ham hız (normalize derece) gücü

Her sinyal için raporlanan:
  - Kapsama: kaç at-yarışta geçerli değer üretilebildi (geçmiş gerektirir)
  - Tekil güç: sinyale göre #1 seçilen atın İlk1/İlk3/İlk4 (aynı altküme AGF ile kıyas)
  - Dekorelasyon: AGF #1 ile sinyal #1 ne kadar AYRIŞIYOR
  - "Ayrışma değeri": sinyalde top2 ama AGF'de alt-yarı atların kazanma oranı
    (= üçüncü görüşün gerçekten yeni bir şey görüp görmediği — KRİTİK metrik)
"""
import sys, io, os, re, glob, collections, math

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "D:/Ganyan Gemini"
CSV_DIRS = [os.path.join(BASE, "CSV Sonuçlar/NİSAN"), os.path.join(BASE, "CSV Sonuçlar/MAYIS")]

HIP_NORM = {"İSTANBUL":"ISTANBUL","ISTANBUL":"ISTANBUL","İZMİR":"IZMIR","IZMIR":"IZMIR","BURSA":"BURSA","ADANA":"ADANA","ANTALYA":"ANTALYA","ELAZIĞ":"ELAZIG","ELAZIG":"ELAZIG","ŞANLIURFA":"SANLIURFA","SANLIURFA":"SANLIURFA","ANKARA":"ANKARA","KOCAELİ":"KOCAELI","KOCAELI":"KOCAELI","DİYARBAKIR":"DIYARBAKIR","DIYARBAKIR":"DIYARBAKIR","BALIKESİR":"BALIKESIR","BALIKESIR":"BALIKESIR","MUŞ":"MUS","MUS":"MUS"}
def norm_hip(s): return HIP_NORM.get(s.strip().upper(), s.strip().upper())
def norm_name(s):
    s = s.upper().strip(); s = re.sub(r'\s+(KG|DB|SK|K|G|D|B|S|AP|KD|SG)+$', '', s); return s.strip()
def derece_to_sec(d):
    m = re.match(r"(\d+):(\d+)\.(\d+)", d.strip())
    return int(m.group(1))*60 + int(m.group(2)) + float("0."+m.group(3)) if m else None

# ── kategori sınıf düzeyi (yaklaşık güç sırası) ──────────────────────────────
def class_level(cat):
    c = cat.upper()
    if "MAIDEN" in c or "MAİDEN" in c: return 1
    if "SATIŞ" in c or "SATIS" in c: return 1
    if "ŞARTLI" in c or "SARTLI" in c:
        m = re.search(r"ŞARTLI\s*(\d+)", c) or re.search(r"SARTLI\s*(\d+)", c)
        return 2 + (int(m.group(1)) if m else 0) * 0.1
    if "HANDİKAP" in c or "HANDIKAP" in c:
        m = re.search(r"HANDİKAP\s*(\d+)", c) or re.search(r"HANDIKAP\s*(\d+)", c)
        return 5 + (int(m.group(1)) if m else 0) * 0.1
    if "KV" in c or "GRUP" in c or "ÖNEMLİ" in c: return 8
    return 3  # bilinmeyen orta

def parse_distance(h):
    m = re.search(r"(\d{3,4})\s*m", h); return int(m.group(1)) if m else None
def parse_surface(h):
    hu = h.upper()
    if "KUM" in hu: return "KUM"
    if "ÇİM" in hu or "CIM" in hu or "ÇIM" in hu: return "CIM"
    if "SENTETİK" in hu or "SENTETIK" in hu: return "SEN"
    return "?"
def parse_agf(s):
    m = re.search(r"%?\s*([\d.,]+)\s*\((\d+)\)", s)
    if m:
        try: return float(m.group(1).replace(",", ".")), int(m.group(2))
        except: return None, None
    m2 = re.search(r"%?\s*([\d.,]+)", s)
    if m2:
        try: return float(m2.group(1).replace(",", ".")), None
        except: return None, None
    return None, None
def parse_kilo(s):
    m = re.search(r"([\d]+[.,]?\d*)", s)
    return float(m.group(1).replace(",", ".")) if m else None

# ── ARŞİV: tüm CSV'leri oku ───────────────────────────────────────────────────
def build_archive():
    arch = {}  # (date_iso,hip,kno) -> {meta, horses:[...]}
    for d in CSV_DIRS:
        if not os.path.isdir(d): continue
        for fn in os.listdir(d):
            if not fn.endswith(".csv"): continue
            m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})-(.+?)-", fn)
            if not m: continue
            g, a, y, hip = m.groups(); date = f"{y}-{a}-{g}"; hn = norm_hip(hip)
            c = open(os.path.join(d, fn), encoding="utf-8-sig", errors="replace").read()
            parts = re.split(r"\n(\d+)\. Kosu\s*:", c); i = 1
            while i < len(parts):
                kno = int(parts[i]); blk = parts[i+1] if i+1 < len(parts) else ""; i += 2
                hdr = blk.split("\n", 1)[0]
                dist = parse_distance(hdr); surf = parse_surface(hdr)
                cat = hdr.split(";")[1].strip() if ";" in hdr else ""
                clvl = class_level(cat)
                am = re.search(r"At No;At İsmi;", blk)
                if not am: continue
                lines = blk[am.start():].strip().split("\n"); horses = []
                for ln in lines[1:]:
                    p = ln.strip().split(";")
                    if len(p) < 14: break
                    try: no = int(p[0])
                    except: break
                    nm = p[1].strip()
                    kilo = parse_kilo(p[5]) if len(p) > 5 else None
                    agf, agf_rank = parse_agf(p[10]) if len(p) > 10 else (None, None)
                    sec = derece_to_sec(p[12])
                    horses.append({"no": no, "name": nm, "nn": norm_name(nm),
                                   "kilo": kilo, "agf": agf, "agf_rank": agf_rank,
                                   "sec": sec})
                # bitiş sırası: derece artan (en hızlı=1); derecesiz koşmadı say
                finishers = sorted([h for h in horses if h["sec"] is not None], key=lambda x: x["sec"])
                for pos, h in enumerate(finishers, 1): h["pos"] = pos
                for h in horses:
                    if "pos" not in h: h["pos"] = None
                nat = len(horses)
                for h in horses:
                    h["nat"] = nat
                    h["npos"] = (h["pos"]-1)/(nat-1) if (h["pos"] and nat > 1) else None  # 0=galip
                arch[(date, hn, kno)] = {"date": date, "hip": hn, "kno": kno,
                                         "dist": dist, "surf": surf, "cat": cat,
                                         "clvl": clvl, "horses": horses, "nat": nat}
    return arch

# ── GEÇMİŞ: at başına kronolojik koşu listesi ────────────────────────────────
def build_history(arch):
    hist = collections.defaultdict(list)  # nn -> [race_record,...] (tarih sıralı)
    for key in sorted(arch.keys()):
        r = arch[key]
        for h in r["horses"]:
            hist[h["nn"]].append({"date": r["date"], "dist": r["dist"], "surf": r["surf"],
                                  "clvl": r["clvl"], "npos": h["npos"], "pos": h["pos"],
                                  "sec": h["sec"], "nat": r["nat"], "kilo": h["kilo"]})
    return hist

def prior_races(hist, nn, date):
    return [x for x in hist.get(nn, []) if x["date"] < date]

# ── SİNYALLER (her biri: tek at için, SADECE geçmişten, yüksek=iyi ya da None) ──
def sig_mesafe_pist(r, h, hist):
    """Bu mesafe bandı (±200m) + aynı zemindeki tarihsel bitiş gücü. 1=hep galip."""
    pr = [x for x in prior_races(hist, h["nn"], r["date"])
          if x["npos"] is not None and x["surf"] == r["surf"]
          and r["dist"] and x["dist"] and abs(x["dist"]-r["dist"]) <= 200]
    if not pr: return None
    return sum(1-x["npos"] for x in pr)/len(pr)

def sig_form_trendi(r, h, hist):
    """Son form (üssel ağırlıklı yakın yarış bitiş gücü). 1=son yarışları kazanıyor."""
    pr = [x for x in prior_races(hist, h["nn"], r["date"]) if x["npos"] is not None]
    if not pr: return None
    pr = sorted(pr, key=lambda x: x["date"])[-4:]          # son 4 yarış
    w = 0.0; tot = 0.0
    for i, x in enumerate(pr):                              # sona doğru ağırlık artar
        wt = 2.0**i
        w += wt*(1-x["npos"]); tot += wt
    return w/tot

def sig_sinif_gecis(r, h, hist):
    """Sınıf rahatlaması: geçmiş ortalama sınıf - bugünkü sınıf (+ = kolaya iniyor)."""
    pr = [x for x in prior_races(hist, h["nn"], r["date"]) if x["clvl"] is not None]
    if not pr or r["clvl"] is None: return None
    avg = sum(x["clvl"] for x in pr)/len(pr)
    return avg - r["clvl"]                                  # pozitif = avantaj

def sig_derece_kalite(r, h, hist):
    """Benzer mesafe+zeminde en iyi ham hız (m/s). Yüksek=hızlı."""
    pr = [x for x in prior_races(hist, h["nn"], r["date"])
          if x["sec"] and x["dist"] and x["surf"] == r["surf"]
          and r["dist"] and abs(x["dist"]-r["dist"]) <= 200]
    sp = [x["dist"]/x["sec"] for x in pr if x["sec"] > 0]
    return max(sp) if sp else None

SIGNALS = [
    ("MESAFE+PİST UYUMU", sig_mesafe_pist),
    ("FORM TRENDİ",        sig_form_trendi),
    ("SINIF GEÇİŞİ",       sig_sinif_gecis),
    ("DERECE KALİTESİ",    sig_derece_kalite),
]

def evaluate(arch, hist, sigfunc, min_cand=4):
    """Bir sinyali değerlendir. Döner: metrik sözlüğü."""
    M = collections.Counter()
    contr_n = contr_win = contr_top3 = 0; contr_base = 0.0
    agree = 0; agree_den = 0
    for key, r in arch.items():
        horses = r["horses"]; nat = r["nat"]
        winner = next((h for h in horses if h["pos"] == 1), None)
        if not winner or nat < 2: continue
        # sinyal değerleri
        cand = []
        for h in horses:
            v = sigfunc(r, h, hist)
            if v is not None: cand.append((h, v))
        if len(cand) < min_cand: continue
        M["yarış"] += 1
        cand.sort(key=lambda t: -t[1])                       # sinyal sırası
        sig_order = [h for h, _ in cand]
        # tekil güç — sadece kazananın sinyali VARSA (kaliteyi kapsamadan ayır)
        if any(h is winner for h in sig_order):
            M["kosanli_kazanan"] += 1
            if sig_order[0] is winner: M["s_ilk1"] += 1
            if winner in sig_order[:3]: M["s_ilk3"] += 1
            if winner in sig_order[:4]: M["s_ilk4"] += 1
            # AGF aynı aday kümesinde baseline
            agf_order = sorted(cand, key=lambda t: -(t[0]["agf"] or 0))
            agf_order = [h for h, _ in agf_order]
            if agf_order[0] is winner: M["a_ilk1"] += 1
            if winner in agf_order[:3]: M["a_ilk3"] += 1
            if winner in agf_order[:4]: M["a_ilk4"] += 1
        # dekorelasyon + ayrışma değeri (agf'si olan adaylar)
        ca = [(h, v) for h, v in cand if h["agf"] is not None]
        if len(ca) >= min_cand:
            sig_rank = {id(h): i+1 for i, (h, _) in enumerate(sorted(ca, key=lambda t: -t[1]))}
            agf_rank = {id(h): i+1 for i, (h, _) in enumerate(sorted(ca, key=lambda t: -(t[0]["agf"] or 0)))}
            n = len(ca)
            # sig#1 == agf#1 ?
            s1 = min(ca, key=lambda t: sig_rank[id(t[0])])[0]
            a1 = min(ca, key=lambda t: agf_rank[id(t[0])])[0]
            agree_den += 1; agree += (s1 is a1)
            half = math.ceil(n/2)
            for h, _ in ca:
                if sig_rank[id(h)] <= 2 and agf_rank[id(h)] > half:   # contrarian seçim
                    contr_n += 1; contr_base += 1.0/nat
                    if h["pos"] == 1: contr_win += 1
                    if h["pos"] and h["pos"] <= 3: contr_top3 += 1
    return {"M": M, "contr_n": contr_n, "contr_win": contr_win, "contr_top3": contr_top3,
            "contr_base": contr_base, "agree": agree, "agree_den": agree_den}

# ── ANA: arşiv kur, doğrula ──────────────────────────────────────────────────
def main():
    arch = build_archive()
    hist = build_history(arch)
    nrace = len(arch)
    nhorse = sum(r["nat"] for r in arch.values())
    nfin = sum(1 for r in arch.values() for h in r["horses"] if h["pos"])
    n_with_agf = sum(1 for r in arch.values() for h in r["horses"] if h["agf"] is not None)
    # kapsama: kaç at-yarışta >=1 geçmiş yarış var
    n_hist = 0; n_hist_surf = 0
    for key, r in arch.items():
        for h in r["horses"]:
            pr = prior_races(hist, h["nn"], r["date"])
            if pr: n_hist += 1
            if any(x["surf"] == r["surf"] for x in pr): n_hist_surf += 1
    dist_surf = collections.Counter((r["surf"]) for r in arch.values())
    print("="*78)
    print("ARŞİV DOĞRULAMA")
    print("="*78)
    print(f"Koşu (yarış)        : {nrace}")
    print(f"At kaydı            : {nhorse}")
    print(f"Derecesi olan (koşan): {nfin}  (%{100*nfin/nhorse:.0f})")
    print(f"AGF'si olan         : {n_with_agf}  (%{100*n_with_agf/nhorse:.0f})")
    print(f"Zemin dağılımı      : {dict(dist_surf)}")
    print(f"Tarih aralığı       : {min(r['date'] for r in arch.values())} - {max(r['date'] for r in arch.values())}")
    print(f"Tekil at sayısı     : {len(hist)}")
    print("-"*78)
    print(f"GEÇMİŞ KAPSAMASI (sinyal üretilebilirlik):")
    print(f"  >=1 önceki yarışı olan at-kaydı   : {n_hist}  (%{100*n_hist/nhorse:.0f})")
    print(f"  aynı zeminde geçmişi olan at-kaydı: {n_hist_surf}  (%{100*n_hist_surf/nhorse:.0f})")
    print("="*78)

    print()
    print("="*78)
    print("SİNYAL TESTLERİ  (her sinyal SADECE geçmişten; yüksek=iyi)")
    print("="*78)
    print("Okuma kılavuzu:")
    print("  • Tekil güç = sinyale göre #1 atın, kazananı yakalama oranı (kazananın")
    print("    geçmişi VARSA). Yanında aynı koşularda AGF baz alınır → kıyas.")
    print("  • Ayrışma = sinyal #1 ≠ AGF #1 olduğu koşu oranı (yüksek = bağımsız).")
    print("  • AYRIŞMA DEĞERİ = sinyalde top2 ama AGF'de alt-yarıdaki atların kazanma")
    print("    oranı vs şans beklentisi. >1.0 lift = AGF'nin görmediğini görüyor (KRİTİK).")
    print()
    results = []
    for ad, fn in SIGNALS:
        R = evaluate(arch, hist, fn); M = R["M"]
        k = M["yarış"]; kk = M["kosanli_kazanan"]
        print("─"*78)
        print(f"▶ {ad}")
        if not kk:
            print("   yeterli kapsama yok."); print(); continue
        print(f"   Değerlendirilen koşu          : {k}  (sinyalli kazananı olan: {kk})")
        print(f"   Tekil güç  İlk1/İlk3/İlk4      : "
              f"%{100*M['s_ilk1']/kk:.1f} / %{100*M['s_ilk3']/kk:.1f} / %{100*M['s_ilk4']/kk:.1f}")
        print(f"   (aynı koşularda) AGF baz       : "
              f"%{100*M['a_ilk1']/kk:.1f} / %{100*M['a_ilk3']/kk:.1f} / %{100*M['a_ilk4']/kk:.1f}")
        if R["agree_den"]:
            ayr = 100*(1-R["agree"]/R["agree_den"])
            print(f"   AGF'den ayrışma (sig#1≠AGF#1)  : %{ayr:.0f}")
        cn = R["contr_n"]
        if cn:
            lift = (R["contr_win"]/cn)/(R["contr_base"]/cn) if R["contr_base"] else 0
            print(f"   Ayrışma seçimleri (sig top2 & AGF alt-yarı): {cn} at")
            print(f"     kazanma : {R['contr_win']}/{cn} = %{100*R['contr_win']/cn:.1f}  "
                  f"(şans beklentisi %{100*R['contr_base']/cn:.1f})  →  LİFT ×{lift:.2f}")
            print(f"     ilk3    : {R['contr_top3']}/{cn} = %{100*R['contr_top3']/cn:.1f}")
        print()
        results.append((ad, M, R))
    print("="*78)
    print("ÖZET DEĞERLENDİRME")
    print("="*78)
    for ad, M, R in results:
        kk = M["kosanli_kazanan"]; cn = R["contr_n"]
        s4 = 100*M['s_ilk4']/kk if kk else 0
        a4 = 100*M['a_ilk4']/kk if kk else 0
        lift = (R["contr_win"]/R["contr_base"]) if R["contr_base"] else 0
        verdict = "GÜÇLÜ aday" if (lift > 1.15 and s4 >= a4-3) else \
                  "zayıf/AGF'yle örtüşük" if lift < 1.05 else "sınırda"
        print(f"  {ad:<20} ayrışma-lift ×{lift:.2f} | İlk4 sig {s4:.0f}% vs AGF {a4:.0f}% → {verdict}")
    print("="*78)

if __name__ == "__main__":
    main()
