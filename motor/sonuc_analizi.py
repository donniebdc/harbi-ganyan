# -*- coding: utf-8 -*-
"""
SONUÇ ANALİZİ — Harbi Ganyan
================================================================================
Günlük tahmin dosyalarını (tahminler_GG-AA-YYYY.txt) ve CSV yarış sonuçlarını
okur. Her koşu için verdiğimiz 5 satırlı atların yarışı KAÇINCI bitirdiğini
yazar. 5 satırda yarışı kazanan atı bulduysak o atın yanına ⚡ koyar ve
"Harbî Ganyan analizi başarılı" bilgisini düşer.

Kullanım:
    python sonuc_analizi.py                 -> tüm günlük tahmin dosyaları
    python sonuc_analizi.py 25.05.2026       -> tek gün
    python sonuc_analizi.py 25.05.2026 30.05.2026  -> tarih aralığı

Çıktı hem ekrana yazılır hem de "sonuc_analizi_raporu.txt" dosyasına kaydedilir.
Eşleştirme anahtarı: (tarih, hipodrom, koşu_no) + at ismi köprüsü.
Kazanan = CSV'de en hızlı dereceyi yapan at (varış sırası bu dereceyle kurulur).
"""
import sys, io, os, re, glob
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "D:/Ganyan Gemini"
CSV_DIRS = [os.path.join(BASE, "CSV Sonuçlar/NİSAN"), os.path.join(BASE, "CSV Sonuçlar/MAYIS")]
RAPOR = os.path.join(BASE, "sonuc_analizi_raporu.txt")

HIP_NORM = {
    "İSTANBUL":"ISTANBUL","ISTANBUL":"ISTANBUL","İZMİR":"IZMIR","IZMIR":"IZMIR","BURSA":"BURSA",
    "ADANA":"ADANA","ANTALYA":"ANTALYA","ELAZIĞ":"ELAZIG","ELAZIG":"ELAZIG","ŞANLIURFA":"SANLIURFA",
    "SANLIURFA":"SANLIURFA","ANKARA":"ANKARA","KOCAELİ":"KOCAELI","KOCAELI":"KOCAELI",
    "DİYARBAKIR":"DIYARBAKIR","DIYARBAKIR":"DIYARBAKIR","BALIKESİR":"BALIKESIR","BALIKESIR":"BALIKESIR",
    "MUŞ":"MUS","MUS":"MUS",
}
def norm_hip(s): return HIP_NORM.get(s.strip().upper(), s.strip().upper())

def norm_name(s):
    s = s.upper().strip()
    s = re.sub(r'\s+(KG|DB|SK|K|G|D|B|S|AP|KD|SG)+$', '', s)
    return s.strip()

def names_match(a, b):
    a, b = norm_name(a), norm_name(b)
    if not a or not b: return False
    return a == b or a.startswith(b) or b.startswith(a)

def derece_to_sec(d):
    m = re.match(r"(\d+):(\d+)\.(\d+)", d.strip())
    return int(m.group(1))*60 + int(m.group(2)) + float("0."+m.group(3)) if m else None

# ── CSV SONUÇLARI ────────────────────────────────────────────────────────────
def parse_csv(dirpath):
    """(tarih_iso, hip, kosu_no) -> {'sira': {NORMAD: pozisyon}, 'wname':, 'nat':}"""
    res = {}
    if not os.path.isdir(dirpath): return res
    for fn in os.listdir(dirpath):
        if not fn.endswith(".csv"): continue
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})-(.+?)-", fn)
        if not m: continue
        g, a, y, hip = m.groups(); tarih = f"{y}-{a}-{g}"; hn = norm_hip(hip)
        with open(os.path.join(dirpath, fn), encoding="utf-8-sig", errors="replace") as f:
            c = f.read()
        parts = re.split(r"\n(\d+)\. Kosu\s*:", c); i = 1
        while i < len(parts):
            kno = int(parts[i]); blk = parts[i+1] if i+1 < len(parts) else ""; i += 2
            am = re.search(r"At No;At İsmi;", blk)
            if not am: continue
            lines = blk[am.start():].strip().split("\n"); horses = []
            for ln in lines[1:]:
                p = ln.strip().split(";")
                if len(p) < 14: break
                try: int(p[0])
                except: break
                sec = derece_to_sec(p[12].strip())
                horses.append((p[1].strip(), sec))
            kosanlar = [h for h in horses if h[1] is not None]
            if not kosanlar: continue
            kosanlar.sort(key=lambda h: h[1])
            sira = {norm_name(nm): pos for pos, (nm, _) in enumerate(kosanlar, 1)}
            res[(tarih, hn, kno)] = {"sira": sira, "wname": kosanlar[0][0], "nat": len(horses)}
    return res

# ── GÜNLÜK TAHMİN DOSYALARI ──────────────────────────────────────────────────
SLOT_ETIKET = [
    ("FAV", "Favori",       "🎯 Favori"),
    ("SUR", "Sürpriz",      "🔒 Sürpriz Olmaz"),
    ("YAZ", "Yazılabilir",  "✍️  Yazılabilir"),
    ("BOM", "Bomba",        "💣 Bomba"),
    ("HAR", "Harbi mi",     "❓ Harbi mi?"),
]
def slot_of(line):
    for slot, anahtar, _ in SLOT_ETIKET:
        if anahtar in line: return slot
    return None

def parse_tahmin(path):
    """tahminler_*.txt -> [ {tarih, hip, kosu, picks:[(slot,at_no,name)]} ]"""
    fn = os.path.basename(path)
    dm = re.search(r"(\d{2})-(\d{2})-(\d{4})", fn)
    if not dm: return []
    tarih = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().split("\n")
    kosular = []; hip = None; cur = None
    for ln in lines:
        hm = re.search(r"🏟️\s*(.+?)\s+HİPODROMU", ln)
        if hm:
            hip = norm_hip(hm.group(1)); continue
        km = re.search(r"┌─\s*(\d+)\.\s*KOŞU", ln)
        if km:
            if cur: kosular.append(cur)
            cur = {"tarih": tarih, "hip": hip, "kosu": int(km.group(1)), "picks": []}
            continue
        if cur is not None:
            slot = slot_of(ln)
            if slot:
                pm = re.search(r"No:(\d+)\s+(\S.*?)\s*$", ln)
                if pm:
                    cur["picks"].append((slot, int(pm.group(1)), pm.group(2).strip()))
    if cur: kosular.append(cur)
    return kosular

# ── ANALİZ / RAPOR ───────────────────────────────────────────────────────────
OUT = []
def yaz(s=""): OUT.append(s); print(s)

def pos_str(pos):
    if pos is None: return "—"      # koşmadı / sonuçta yok
    return f"{pos}."

def main():
    args = [a for a in sys.argv[1:]]
    def to_iso(s):
        m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", s)
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None
    bas = to_iso(args[0]) if len(args) >= 1 else None
    bit = to_iso(args[1]) if len(args) >= 2 else bas

    csv_data = {}
    for d in CSV_DIRS: csv_data.update(parse_csv(d))

    dosyalar = sorted(glob.glob(os.path.join(BASE, "tahminler_*.txt")))
    dosyalar = [d for d in dosyalar if "şablon" not in os.path.basename(d).lower()]

    SLOT_AD = {s: ad for s, _, ad in SLOT_ETIKET}
    SLOT_KISA = {"FAV":"Favori","SUR":"Sürpriz Olmaz","YAZ":"Yazılabilir","BOM":"Bomba","HAR":"Harbi mi?"}

    toplam = 0; isabet = 0
    slot_isabet = {s: 0 for s, _, _ in SLOT_ETIKET}
    eslesmeyen = 0
    gun_ozet = {}  # tarih -> (kosu, isabet)

    yaz("═"*78)
    yaz("⚡ HARBÎ GANYAN — SONUÇ ANALİZİ")
    yaz("═"*78)

    for path in dosyalar:
        for k in parse_tahmin(path):
            tarih, hip, kno = k["tarih"], k["hip"], k["kosu"]
            if bas and not (bas <= tarih <= bit): continue
            key = (tarih, hip, kno)
            if key not in csv_data:
                eslesmeyen += 1
                continue
            sonuc = csv_data[key]; sira = sonuc["sira"]; wname = sonuc["wname"]
            toplam += 1
            gtarih = datetime.strptime(tarih, "%Y-%m-%d").strftime("%d.%m.%Y")

            yaz("")
            yaz(f"┌─ {gtarih} | {hip} | {kno}. KOŞU  ({sonuc['nat']} at)")

            kazanan_satir = None
            for slot, at_no, name in k["picks"]:
                pos = None
                for nad, p in sira.items():
                    if names_match(name, nad):
                        pos = p; break
                kazandi = (pos == 1)
                if kazandi and kazanan_satir is None:
                    kazanan_satir = slot
                imza = "  ⚡" if kazandi else ""
                yaz(f"│  {SLOT_AD[slot]:<18}: No:{at_no:<3} {name:<22} → {pos_str(pos):>4}{imza}")

            if kazanan_satir:
                isabet += 1
                slot_isabet[kazanan_satir] += 1
                yaz(f"│  ⚡ HARBÎ GANYAN ANALİZİ BAŞARILI — kazanan ({wname}) "
                    f"5 satırda bulundu! [{SLOT_KISA[kazanan_satir]}]")
            else:
                yaz(f"│  ❌ Kazanan ({wname}) 5 satırda yok.")
            yaz("└─")

            g = gun_ozet.get(tarih, [0, 0]); g[0] += 1; g[1] += 1 if kazanan_satir else 0
            gun_ozet[tarih] = g

    # ── ÖZET ──
    yaz("")
    yaz("═"*78)
    yaz("📊 GENEL ÖZET")
    yaz("═"*78)
    if toplam == 0:
        yaz("Eşleşen koşu bulunamadı. (Tahmin dosyası tarihleri ile CSV sonuçları örtüşmüyor olabilir.)")
        if eslesmeyen:
            yaz(f"CSV sonucu bulunamayan tahmin koşusu: {eslesmeyen}")
    else:
        yaz(f"Analiz edilen koşu        : {toplam}")
        yaz(f"5 satırda kazanan yakalama: {isabet}/{toplam} = %{100*isabet/toplam:.1f}")
        if eslesmeyen:
            yaz(f"CSV'de karşılığı olmayan  : {eslesmeyen} koşu (atlandı)")
        yaz("")
        yaz("Hangi satır kazandırdı:")
        for slot, _, _ in SLOT_ETIKET:
            h = slot_isabet[slot]
            yaz(f"  {SLOT_KISA[slot]:<14}: {h:>3}  (%{100*h/toplam:.1f})")
        if len(gun_ozet) > 1:
            yaz("")
            yaz("Gün bazında:")
            for t in sorted(gun_ozet):
                kk, hh = gun_ozet[t]
                gt = datetime.strptime(t, "%Y-%m-%d").strftime("%d.%m.%Y")
                yaz(f"  {gt}: {hh}/{kk} = %{100*hh/kk:.1f}")
    yaz("═"*78)

    with open(RAPOR, "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    print(f"\n📝 Rapor kaydedildi: {RAPOR}")

if __name__ == "__main__":
    main()
