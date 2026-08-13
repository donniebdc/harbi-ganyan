# -*- coding: utf-8 -*-
"""
Sürdirek Politika Backtest: P0 – P4

P0: Mevcut politika (gap * bucket_weight, MIN_GAP>=12, handikap hariç)
P1: P0 + sürpriz_radar koşularını ele
P2: P0 + geniş liste (B sistem) koşularını ağır penalize et (x0.25)
P3: P0 + COK_ZOR koşularını ağır penalize et (x0.3)
P4: P1 + P2 + P3 birleşik

Her politika için her gün+şehir kombinasyonunda en yüksek puanlı uygun koşu seçilir.
O koşunun kazananı ile sürdirek atı (gap'e göre seçilen 1. at) karşılaştırılır.

Rapor:
  - toplam sürdirek sayısı
  - başarı oranı (kazanan = seçilen at)
  - şehir bazlı
  - koşu tipi bazlı
  - Harbi Seçim tipiyle uyum (B sistem tipine göre)
  - sürpriz radar çakışma sayısı
  - fallback (tüm koşular elendi, en iyi kalan seçildi) sayısı
"""
from __future__ import annotations
import sys, json, os, re
from collections import defaultdict

import psycopg2
import psycopg2.extras

sys.path.insert(0, "/opt/harbi_ganyan_v3/src")
sys.path.insert(0, "/opt/harbi_ganyan_backend")

from harbi_v3.harbi_secim import compute as hs_compute
from harbi_v3.confidence  import race_type_bucket
from app.config import settings

# ── DB ───────────────────────────────────────────────────────────────────────
m = re.match(r"postgresql\+psycopg2://([^:]+):([^@]+)@([^/]+)/(.+)", settings.database_url)
db_user, db_pass, db_host, db_name = m.groups() if m else ("postgres","","localhost","harbi_ganyan")
conn = psycopg2.connect(host=db_host, user=db_user, password=db_pass, dbname=db_name)
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Her koşu + surpriz_radar + kazanan
cur.execute("""
SELECT
    g.date,
    g.surpriz_radar,
    gh.hipodrom,
    k.kno,
    k.n_at,
    k.race_type,
    k.race_subtype,
    k.analiz_puanlari,
    k.zorluk,
    ks.kazanan
FROM kosu k
JOIN gun_hipodrom gh ON gh.id = k.gh_id
JOIN gun g           ON g.id  = gh.gun_id
LEFT JOIN kosu_sonuc ks ON ks.kosu_id = k.id
WHERE k.analiz_puanlari IS NOT NULL
  AND ks.kazanan IS NOT NULL
ORDER BY g.date, gh.hipodrom, k.kno
""")
rows = cur.fetchall()
cur.close(); conn.close()

print(f"Toplam koşu: {len(rows)}\n")

# ── Bucket ağırlıkları (surdirek.py ile aynı) ────────────────────────────────
BUCKET_WEIGHTS = {
    "kv_grup": 1.3, "grup": 1.2, "sartli": 0.8, "sartli_arap": 0.65,
    "maiden": 0.6, "satis": 0.5, "other": 0.5, "handikap": 0.2,
}
MIN_GAP  = 12.0
OTHER_MIN_GAP = 20.0

# ── Surpriz radar koşuları ────────────────────────────────────────────────────
def _surpriz_race_set(surpriz_radar_json) -> set[tuple[str, int]]:
    """(hip, kno) çiftleri — bu koşularda sürpriz at var."""
    result = set()
    if not isinstance(surpriz_radar_json, dict):
        return result
    for item in (surpriz_radar_json.get("adaylar") or []):
        hip = item.get("hip","")
        kno = item.get("kno")
        if hip and kno is not None:
            result.add((hip, int(kno)))
    return result

# ── B sistemi tip (backtest amacıyla) ────────────────────────────────────────
def _b_sistem_tip(ap, n_at, zk) -> str:
    if not ap:
        return "bilinmiyor"
    try:
        r = hs_compute(ap, n_at=n_at, zorluk_kodu=zk, is_surdirek=False)
        return (r or {}).get("tip", "bilinmiyor")
    except Exception:
        return "bilinmiyor"

# ── Koşu adayını hazırla ──────────────────────────────────────────────────────
def _build_candidate(row, surpriz_races: set) -> dict | None:
    """Koşudan sürdirek adayı oluştur (1. sıradaki at + gap)."""
    ap = row["analiz_puanlari"] or []
    if not ap:
        return None

    sirali = sorted(ap, key=lambda x: x.get("ana", 0), reverse=True)
    if len(sirali) < 2:
        return None

    scores    = [float(p.get("ana", 0)) for p in sirali]
    gap       = scores[0] - scores[1]
    top_horse = sirali[0]
    bucket    = race_type_bucket(row.get("race_type"), row.get("race_subtype"))
    zk        = (row["zorluk"] or {}).get("zorluk_kodu")
    hip       = row["hipodrom"]
    kno       = int(row["kno"])
    n_at      = row["n_at"] or len(sirali)

    is_surpriz = (hip, kno) in surpriz_races
    b_tip      = _b_sistem_tip(ap, n_at, zk)
    is_genis   = b_tip == "genis_liste"
    is_cokzor  = zk == "COK_ZOR"

    # Weighted score (temel)
    weighted = gap * BUCKET_WEIGHTS.get(bucket, 0.5)

    return {
        "hip":       hip,
        "kno":       kno,
        "horse_no":  top_horse["at_no"],
        "horse_name": top_horse.get("at", ""),
        "gap":       gap,
        "weighted":  weighted,
        "bucket":    bucket,
        "zk":        zk,
        "n_at":      n_at,
        "kazanan":   row["kazanan"],
        "is_surpriz": is_surpriz,
        "is_genis":   is_genis,
        "is_cokzor":  is_cokzor,
        "b_tip":      b_tip,
    }

# ── Politika skoru hesapla ───────────────────────────────────────────────────
GENIS_PENALTY  = 0.25   # P2: genis_liste koşu cezası
COKZOR_PENALTY = 0.30   # P3: COK_ZOR koşu cezası

def policy_score(c: dict, policy: int) -> float | None:
    """None dönerse bu aday elendi (seçilemez)."""
    # Temel filtreler (P0'da da geçerli)
    if c["gap"] < MIN_GAP:
        return None
    if c["bucket"] == "handikap":
        return None
    if c["bucket"] == "other" and c["gap"] < OTHER_MIN_GAP:
        return None

    score = c["weighted"]

    # P1: sürpriz radar koşularını ele
    if policy in (1, 4) and c["is_surpriz"]:
        return None

    # P2: geniş liste koşularına ağır ceza
    if policy in (2, 4) and c["is_genis"]:
        score *= GENIS_PENALTY

    # P3: COK_ZOR koşularına ağır ceza
    if policy in (3, 4) and c["is_cokzor"]:
        score *= COKZOR_PENALTY

    return score

# ── Gün+şehir bazında grupla ─────────────────────────────────────────────────
from collections import defaultdict

day_hip_rows: dict[tuple, list] = defaultdict(list)
for row in rows:
    key = (str(row["date"]), row["hipodrom"])
    day_hip_rows[key].append(row)

print(f"Gün+şehir kombinasyonu: {len(day_hip_rows)}\n")

# ── Backtest ─────────────────────────────────────────────────────────────────
POLICIES = [0, 1, 2, 3, 4]

def make_stats():
    return {"toplam": 0, "isabetli": 0, "fallback": 0,
            "surpriz_cakisan": 0, "elendi": 0}

stats = {p: make_stats() for p in POLICIES}
hip_stats  = {p: defaultdict(lambda: {"toplam":0,"isabetli":0}) for p in POLICIES}
bkt_stats  = {p: defaultdict(lambda: {"toplam":0,"isabetli":0}) for p in POLICIES}
btip_stats = {p: defaultdict(lambda: {"toplam":0,"isabetli":0}) for p in POLICIES}
gun_stats  = {p: defaultdict(lambda: {"toplam":0,"isabetli":0}) for p in POLICIES}

for (tarih, hip), group in day_hip_rows.items():
    # Sürpriz radar koşuları — günden al
    # group içindeki ilk row'dan gun.surpriz_radar'ı al (hepsi aynı gün)
    surpriz_json = None
    for row in group:
        sr = row.get("surpriz_radar")
        if sr:
            surpriz_json = sr
            break
    surpriz_races = _surpriz_race_set(surpriz_json)

    # Adayları hazırla
    candidates = []
    for row in group:
        c = _build_candidate(row, surpriz_races)
        if c:
            candidates.append(c)

    if not candidates:
        continue

    for p in POLICIES:
        # Skor hesapla
        scored = []
        for c in candidates:
            s = policy_score(c, p)
            if s is not None:
                scored.append((s, c))

        is_fallback = False
        if not scored:
            # Tüm adaylar elendi → fallback: en yüksek gap'li (surpriz dahil)
            is_fallback = True
            # P1 için bile fallback gerekli: sürdirek garantisi
            fallback_pool = [c for c in candidates
                             if c["gap"] >= MIN_GAP and c["bucket"] != "handikap"]
            if not fallback_pool:
                fallback_pool = candidates
            chosen = max(fallback_pool, key=lambda c: c["weighted"])
        else:
            chosen = max(scored, key=lambda x: x[0])[1]

        hit = (chosen["kazanan"] == chosen["horse_no"])

        st = stats[p]
        st["toplam"]   += 1
        st["isabetli"] += int(hit)
        if is_fallback:
            st["fallback"] += 1
        if chosen["is_surpriz"]:
            st["surpriz_cakisan"] += 1

        hip_stats[p][hip]["toplam"]   += 1
        hip_stats[p][hip]["isabetli"] += int(hit)
        bkt_stats[p][chosen["bucket"]]["toplam"]   += 1
        bkt_stats[p][chosen["bucket"]]["isabetli"] += int(hit)
        btip_stats[p][chosen["b_tip"]]["toplam"]   += 1
        btip_stats[p][chosen["b_tip"]]["isabetli"] += int(hit)
        gun_stats[p][tarih]["toplam"]   += 1
        gun_stats[p][tarih]["isabetli"] += int(hit)

# ── Rapor ─────────────────────────────────────────────────────────────────────
SEP = "=" * 70

def pct(i, t):
    return f"%{i/t*100:.1f}" if t else "  -"

print(f"\n{SEP}")
print("  SÜRDİREK POLİTİKA BACKTEST SONUÇLARI")
print(f"{SEP}")
print()
print("Politikalar:")
print("  P0: Mevcut (gap*bucket, MIN_GAP>=12, handikap hariç)")
print("  P1: P0 + sürpriz radar koşularını ele")
print("  P2: P0 + geniş liste koşularını x0.25 penalize et")
print("  P3: P0 + COK_ZOR koşularını x0.3 penalize et")
print("  P4: P1 + P2 + P3 birleşik")

print(f"\n{'':28} {'P0':>8} {'P1':>8} {'P2':>8} {'P3':>8} {'P4':>8}")
print(f"  {'-'*58}")
rows_g = [
    ("Toplam sürdirek seçimi", "toplam"),
    ("İsabetli", "isabetli"),
    ("Fallback sayısı", "fallback"),
    ("Sürpriz çakışan seçim", "surpriz_cakisan"),
]
for label, key in rows_g:
    vals = [stats[p][key] for p in POLICIES]
    print(f"  {label:<26} " + "  ".join(f"{v:>8}" for v in vals))
print(f"  {'İsabet oranı':<26} " +
      "  ".join(f"{pct(stats[p]['isabetli'],stats[p]['toplam']):>8}" for p in POLICIES))

# Şehir bazlı
print(f"\n{'-'*70}")
print("ŞEHİR BAZLI İSABET:")
print(f"  {'Şehir':<14} {'P0':>8} {'P1':>8} {'P2':>8} {'P3':>8} {'P4':>8}  {'N':>5}")
print(f"  {'-'*62}")
all_hips = sorted(hip_stats[0].keys(), key=lambda h: -hip_stats[0][h]["toplam"])
for h in all_hips:
    n = hip_stats[0][h]["toplam"]
    if n < 5: continue
    vals = [pct(hip_stats[p][h]["isabetli"], hip_stats[p][h]["toplam"]) for p in POLICIES]
    print(f"  {h:<14} " + "  ".join(f"{v:>8}" for v in vals) + f"  {n:>5}")

# Bucket bazlı
print(f"\n{'-'*70}")
print("KOŞU TİPİ (BUCKET) BAZLI:")
print(f"  {'Bucket':<14} {'P0':>8} {'P1':>8} {'P2':>8} {'P3':>8} {'P4':>8}  {'N':>5}")
print(f"  {'-'*62}")
for bkt in sorted(bkt_stats[0].keys(), key=lambda b: -bkt_stats[0][b]["toplam"]):
    n = bkt_stats[0][bkt]["toplam"]
    if n < 3: continue
    vals = [pct(bkt_stats[p][bkt]["isabetli"], bkt_stats[p][bkt]["toplam"]) for p in POLICIES]
    print(f"  {bkt:<14} " + "  ".join(f"{v:>8}" for v in vals) + f"  {n:>5}")

# B sistem tipi uyum
print(f"\n{'-'*70}")
print("SEÇİLEN KOŞUNUN HARBİ SEÇİM TİPİ (B SİSTEM):")
print(f"  {'HS Tipi':<14} {'P0':>8} {'P1':>8} {'P2':>8} {'P3':>8} {'P4':>8}  {'P0:N':>6}")
print(f"  {'-'*64}")
hs_tip_order = ["tek_at","iki_aday","uc_aday","dort_aday","genis_liste","bilinmiyor"]
for tip in hs_tip_order:
    n0 = btip_stats[0][tip]["toplam"]
    if n0 == 0: continue
    vals_n = [btip_stats[p][tip]["toplam"] for p in POLICIES]
    vals_pct = [pct(btip_stats[p][tip]["isabetli"], btip_stats[p][tip]["toplam"]) for p in POLICIES]
    print(f"  {tip:<14} " + "  ".join(f"{v:>8}" for v in vals_pct) + f"  {n0:>6}")

# Son 14 gün
print(f"\n{'-'*70}")
print("SON 14 GÜN (P0 vs P4):")
print(f"  {'Tarih':<12} {'P0:%':>7} {'P4:%':>7}  {'Fark':>6}  {'N':>4}")
print(f"  {'-'*44}")
all_dates = sorted(set(list(gun_stats[0].keys())+list(gun_stats[4].keys())))[-14:]
for t in all_dates:
    g0 = gun_stats[0][t]; g4 = gun_stats[4][t]
    if g0["toplam"] == 0: continue
    p0 = g0["isabetli"]/g0["toplam"]*100
    p4 = g4["isabetli"]/g4["toplam"]*100 if g4["toplam"] else 0
    d  = p4 - p0
    print(f"  {t:<12} {p0:>6.1f}% {p4:>6.1f}%  {('+' if d>=0 else '')}{d:>5.1f}  {g0['toplam']:>4}")

# Özet
print(f"\n{SEP}")
print("ÖZET")
print(SEP)
for p in POLICIES:
    st = stats[p]
    t  = st["toplam"]
    print(f"  P{p}: {pct(st['isabetli'],t):>7} isabet "
          f"({st['isabetli']}/{t})  "
          f"fallback:{st['fallback']}  "
          f"surpriz_cakisan:{st['surpriz_cakisan']}")

best_p = max(POLICIES, key=lambda p: stats[p]["isabetli"]/stats[p]["toplam"] if stats[p]["toplam"] else 0)
print(f"\n  En iyi politika: P{best_p} — {pct(stats[best_p]['isabetli'],stats[best_p]['toplam'])} isabet")

# JSON
result = {
    f"P{p}": {
        "isabet_pct": stats[p]["isabetli"]/stats[p]["toplam"]*100 if stats[p]["toplam"] else 0,
        **stats[p],
        "hip": {h: dict(v) for h, v in hip_stats[p].items()},
        "bucket": {b: dict(v) for b, v in bkt_stats[p].items()},
    }
    for p in POLICIES
}
out = "/opt/harbi_ganyan_v3/reports/surdirek_politika_backtest_2026-07-09.json"
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print(f"\nJSON: {out}")
