"""
Derece Normalizasyon Modülü
===========================
Tahminci referans tablolarına dayalı saf fonksiyonlar.
Mevcut sisteme bağımlılık yoktur; import edilebilir veya bağımsız test edilebilir.

Referans noktası: İstanbul Sentetik, Normal zemin (penetrometre 3.3-4.0), standart kilo.
"""

# ---------------------------------------------------------------------------
# 1. Şehirlerarası handikap tablosu (normalizasyon.txt)
# CITY_HANDICAP[breed][surface][city][range] = +saniye (İstanbul'dan uzaklaştıkça artar)
# Normalize ederken ÇIKAR; projeksiyon yaparken EKLE.
# ---------------------------------------------------------------------------
CITY_HANDICAP: dict = {
    "ing": {
        "cim": {
            "istanbul":  {"kisa": 0.00, "uzun": 0.00},
            "bursa":     {"kisa": 0.40, "uzun": 0.60},
            "antalya":   {"kisa": 0.50, "uzun": 0.80},
            "adana":     {"kisa": 0.70, "uzun": 1.10},
            "ankara":    {"kisa": 0.90, "uzun": 1.30},
            "izmir":     {"kisa": 1.20, "uzun": 1.70},
        },
        "sentetik": {
            "istanbul":   {"kisa": 0.00, "uzun": 0.00},
            "antalya":    {"kisa": 0.30, "uzun": 0.50},
            "bursa":      {"kisa": 0.70, "uzun": 1.00},
            "adana":      {"kisa": 0.90, "uzun": 1.30},
            "izmir":      {"kisa": 1.30, "uzun": 1.80},
            "ankara":     {"kisa": 1.80, "uzun": 2.50},
            "kocaeli":    {"kisa": 2.20, "uzun": 3.00},
            "diyarbakir": {"kisa": 2.50, "uzun": 3.50},
            "elazig":     {"kisa": 2.70, "uzun": 3.70},
            "sanliurfa":  {"kisa": 2.90, "uzun": 4.00},
        },
        "kum": {  # Çoğu şehirde kum = sentetik tablosuyla aynı
            "istanbul":   {"kisa": 0.00, "uzun": 0.00},
            "antalya":    {"kisa": 0.30, "uzun": 0.50},
            "bursa":      {"kisa": 0.70, "uzun": 1.00},
            "adana":      {"kisa": 0.90, "uzun": 1.30},
            "izmir":      {"kisa": 1.30, "uzun": 1.80},
            "ankara":     {"kisa": 1.80, "uzun": 2.50},
            "kocaeli":    {"kisa": 2.20, "uzun": 3.00},
            "diyarbakir": {"kisa": 2.50, "uzun": 3.50},
            "elazig":     {"kisa": 2.70, "uzun": 3.70},
            "sanliurfa":  {"kisa": 2.90, "uzun": 4.00},
        },
    },
    "arap": {
        "cim": {
            "istanbul":  {"kisa": 0.00, "uzun": 0.00},
            "bursa":     {"kisa": 0.60, "uzun": 0.90},
            "antalya":   {"kisa": 0.70, "uzun": 1.10},
            "adana":     {"kisa": 1.00, "uzun": 1.40},
            "ankara":    {"kisa": 1.20, "uzun": 1.80},
            "izmir":     {"kisa": 1.60, "uzun": 2.20},
        },
        "sentetik": {
            "istanbul":   {"kisa": 0.00, "uzun": 0.00},
            "antalya":    {"kisa": 0.40, "uzun": 0.60},
            "bursa":      {"kisa": 1.00, "uzun": 1.40},
            "adana":      {"kisa": 1.20, "uzun": 1.70},
            "izmir":      {"kisa": 1.70, "uzun": 2.30},
            "ankara":     {"kisa": 2.30, "uzun": 3.40},
            "kocaeli":    {"kisa": 2.80, "uzun": 3.90},
            "diyarbakir": {"kisa": 3.10, "uzun": 4.30},
            "elazig":     {"kisa": 3.40, "uzun": 4.60},
            "sanliurfa":  {"kisa": 3.60, "uzun": 5.00},
        },
        "kum": {
            "istanbul":   {"kisa": 0.00, "uzun": 0.00},
            "antalya":    {"kisa": 0.40, "uzun": 0.60},
            "bursa":      {"kisa": 1.00, "uzun": 1.40},
            "adana":      {"kisa": 1.20, "uzun": 1.70},
            "izmir":      {"kisa": 1.70, "uzun": 2.30},
            "ankara":     {"kisa": 2.30, "uzun": 3.40},
            "kocaeli":    {"kisa": 2.80, "uzun": 3.90},
            "diyarbakir": {"kisa": 3.10, "uzun": 4.30},
            "elazig":     {"kisa": 3.40, "uzun": 4.60},
            "sanliurfa":  {"kisa": 3.60, "uzun": 5.00},
        },
    },
}

# ---------------------------------------------------------------------------
# 2. Mesafe projeksiyon katsayısı (pist normalizasyon.txt)
# Her 100 metre için eklenecek saniye.
# ---------------------------------------------------------------------------
DIST_SEC_PER_100M: dict = {
    "ing":  {"sentetik": 6.0, "cim": 6.0, "kum": 7.0},
    "arap": {"sentetik": 7.0, "cim": 7.0, "kum": 8.0},
}

# ---------------------------------------------------------------------------
# 3. Pist tipi dönüşüm saniyeleri (pist tipi normalizasyon.txt)
# (from_surface → to_surface). Tersi otomatik hesaplanır.
# ---------------------------------------------------------------------------
SURFACE_CONV: dict = {
    "ing": {
        ("sentetik", "cim"):  {"kisa": -0.40, "uzun": -0.40},
        ("cim",      "kum"):  {"kisa": +1.20, "uzun": +2.00},
        ("sentetik", "kum"):  {"kisa": +1.60, "uzun": +2.50},
    },
    "arap": {
        ("sentetik", "cim"):  {"kisa": -0.60, "uzun": -0.60},
        ("cim",      "kum"):  {"kisa": +2.20, "uzun": +3.50},
        ("sentetik", "kum"):  {"kisa": +2.80, "uzun": +4.50},
    },
}

# ---------------------------------------------------------------------------
# 4. Zemin durumu ceza saniyeleri — çim pist için (pist tipi normalizasyon.txt)
# Penetrometre → level: 1.0-2.5→1, 2.6-3.2→2, 3.3-4.0→3(normal), 4.1-4.5→4, 4.6+→5
# ---------------------------------------------------------------------------
GOING_HANDICAP: dict = {
    "ing": {
        1: {"kisa": +1.50, "uzun": +2.50},
        2: {"kisa": +0.80, "uzun": +1.50},
        3: {"kisa":  0.00, "uzun":  0.00},
        4: {"kisa": +1.20, "uzun": +2.20},
        5: {"kisa": +2.50, "uzun": +4.00},
    },
    "arap": {
        1: {"kisa": +2.00, "uzun": +3.50},
        2: {"kisa": +1.20, "uzun": +2.00},
        3: {"kisa":  0.00, "uzun":  0.00},
        4: {"kisa": +1.80, "uzun": +3.00},
        5: {"kisa": +3.50, "uzun": +5.50},
    },
}

# ---------------------------------------------------------------------------
# 5. Kilo katsayısı ve apranti indirimleri (kilo normalizasyon.txt)
# ---------------------------------------------------------------------------
WEIGHT_SEC_PER_KG: dict = {
    "kisa": 0.12,   # 1000m-1300m
    "orta": 0.15,   # 1400m-1600m
    "uzun": 0.18,   # 1700m+
}

APRANTI_DISCOUNT_KG: dict = {
    "AP1": 1, "*1": 1, "1": 1,
    "AP2": 2, "*2": 2, "2": 2,
    "AP3": 3, "*3": 3, "3": 3,
    "AP4": 4, "*4": 4, "4": 4,
}


# ===========================================================================
# Yardımcı fonksiyonlar
# ===========================================================================

def _dist_range(dist_m: int) -> str:
    return "kisa" if dist_m <= 1500 else "uzun"


def _weight_range(dist_m: int) -> str:
    if dist_m <= 1300:
        return "kisa"
    elif dist_m <= 1600:
        return "orta"
    return "uzun"


def normalize_surface(raw: str) -> str:
    """JSON'daki pist tipini (Çim/Kum/Sentetik) → 'cim'/'kum'/'sentetik' döner."""
    s = raw.strip().lower()
    if s.endswith("im"):   # Çim / çim
        return "cim"
    if s == "kum":
        return "kum"
    if s.startswith("sen"):
        return "sentetik"
    return "kum"  # bilinmeyen → kum varsayılan


def normalize_city(raw: str) -> str:
    """Hipodrom adını (büyük harf) → küçük harf city key'e çevirir."""
    mapping = {
        "ISTANBUL": "istanbul",
        "ANKARA":   "ankara",
        "IZMIR":    "izmir",
        "BURSA":    "bursa",
        "ADANA":    "adana",
        "ANTALYA":  "antalya",
        "KOCAELI":  "kocaeli",
        "DIYARBAKIR": "diyarbakir",
        "ELAZIG":   "elazig",
        "SANLIURFA": "sanliurfa",
        "BALIKESIR": None,
        "MERSIN":    None,
        "KAYSERI":   None,
        "GAZIANTEP": None,
        "SIVAS":     None,
        "BATMAN":    None,
        "MUS":       None,
    }
    return mapping.get(raw.upper().strip(), None)


def parse_race_time(time_str: str) -> float:
    """'M.SS.HH' veya 'M:SS.HH' formatını saniyeye çevirir. Hatalı → 0.0."""
    try:
        t = time_str.strip().replace(":", ".").replace(",", ".")
        parts = t.split(".")
        if len(parts) == 3:
            return int(parts[0]) * 60 + int(parts[1]) + int(parts[2]) / 100.0
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except Exception:
        pass
    return 0.0


def penetrometer_to_level(value: float) -> int:
    if value <= 2.5:  return 1
    elif value <= 3.2: return 2
    elif value <= 4.0: return 3
    elif value <= 4.5: return 4
    else:              return 5


# ===========================================================================
# Temel normalizasyon fonksiyonları
# ===========================================================================

def city_handicap_sec(city: str, surface: str, dist_m: int, breed: str) -> float:
    """Şehir handikabını saniye olarak döner. Bilinmeyen şehir → 0.0."""
    dr = _dist_range(dist_m)
    table = CITY_HANDICAP.get(breed, CITY_HANDICAP["ing"])
    surf_table = table.get(surface, table.get("kum", {}))
    city_row = surf_table.get(city)
    if city_row is None:
        return 0.0
    return city_row[dr]


def surface_conv_sec(from_surface: str, to_surface: str, dist_m: int, breed: str) -> float:
    """Pist tipi değişiminin saniye etkisini döner. Aynı pist → 0.0."""
    if from_surface == to_surface:
        return 0.0
    dr = _dist_range(dist_m)
    conv = SURFACE_CONV.get(breed, SURFACE_CONV["ing"])
    key = (from_surface, to_surface)
    if key in conv:
        return conv[key][dr]
    rev = (to_surface, from_surface)
    if rev in conv:
        return -conv[rev][dr]
    return 0.0


def going_adj_sec(penetrometer: float, dist_m: int, breed: str, surface: str = "cim") -> float:
    """Zemin durumu cezasını saniye olarak döner. Sadece çim pist için; kum/sentetik → 0.0."""
    if surface != "cim":
        return 0.0
    level = penetrometer_to_level(penetrometer)
    dr = _dist_range(dist_m)
    return GOING_HANDICAP.get(breed, GOING_HANDICAP["ing"])[level][dr]


def project_distance_sec(time_sec: float, from_dist: int, to_dist: int,
                          surface: str, breed: str) -> float:
    """Bir mesafedeki süreyi farklı mesafeye projekte eder."""
    if from_dist == to_dist:
        return time_sec
    delta_100m = (to_dist - from_dist) / 100.0
    coeff = DIST_SEC_PER_100M.get(breed, DIST_SEC_PER_100M["ing"]).get(surface, 6.5)
    return time_sec + delta_100m * coeff


def weight_time_adj_sec(old_net_kg: float, new_gross_kg: float,
                         apranti_code: str, dist_m: int) -> float:
    """
    Net kilo farkının saniye etkisini döner.
    Pozitif → at daha ağır, daha yavaş.
    """
    discount = APRANTI_DISCOUNT_KG.get(str(apranti_code).strip(), 0)
    new_net = new_gross_kg - discount
    kg_diff = new_net - old_net_kg
    wr = _weight_range(dist_m)
    return kg_diff * WEIGHT_SEC_PER_KG[wr]


# ===========================================================================
# Ana normalizasyon: Ham time → İstanbul-0 baz derecesi
# ===========================================================================

def normalize_to_istanbul(
    time_sec: float,
    city: str,
    surface: str,
    dist_m: int,
    breed: str,
    penetrometer: float = 3.5,
) -> float:
    """
    Ham yarış derecesini İstanbul Sentetik + Normal Zemin referansına çevirir.

    Tablo referansları:
      - CITY_HANDICAP[...][cim]     → "İstanbul Çim" referanslı
      - CITY_HANDICAP[...][kum/sen] → "İstanbul Sentetik" referanslı

    Adımlar:
      1. Şehir handikabını ÇIKAR (tablo referans noktasına normalize et)
      2. Çim ise: İstanbul Çim → İstanbul Sentetik dönüşümünü EKLE
         Kum/Sentetik: tablolar zaten sentetik referanslı → ekstra adım yok
      3. Zemin durumu (going) cezasını ÇIKAR (sadece çim pist)

    Bilinmeyen şehir → ham time döner (0.0 değil).
    """
    if time_sec <= 0:
        return 0.0

    # Adım 1: Şehir handikabı
    city_h = city_handicap_sec(city, surface, dist_m, breed)

    # Adım 2: Çim → Sentetik dönüşümü (sadece çim pist; kum/sen zaten sentetik referanslı)
    if surface == "cim":
        surf_h = surface_conv_sec("cim", "sentetik", dist_m, breed)
    else:
        surf_h = 0.0

    # Adım 3: Zemin durumu cezası (sadece çim)
    going_h = going_adj_sec(penetrometer, dist_m, breed, surface)

    # city_h çıkar, surf_h EKLE (çim referansı sentetiğe göre daha hızlı → sentetike çevirince artar)
    return time_sec - city_h + surf_h - going_h


def project_to_race(
    base_time_sec: float,
    base_dist: int,
    target_city: str,
    target_surface: str,
    target_dist: int,
    breed: str,
    target_penetrometer: float = 3.5,
    old_net_kg: float = 0.0,
    new_gross_kg: float = 0.0,
    apranti_code: str = "",
) -> float:
    """
    İstanbul Sentetik bazındaki dereceni hedef yarış koşullarına projekte eder.

    Adımlar:
      1. Mesafe projeksiyonu (baz_dist → hedef_dist, sentetik üzerinden)
      2. Çim ise: İstanbul Sentetik → İstanbul Çim dönüşümünü EKLE; ardından şehir handikabı EKLE
         Kum/Sentetik: doğrudan şehir handikabı EKLE (tablo zaten sentetik referanslı)
      3. Hedef zemin durumu cezasını EKLE (sadece çim)
      4. Kilo farkını EKLE (opsiyonel)
    """
    if base_time_sec <= 0:
        return 0.0

    # 1. Mesafe projeksiyonu
    t = project_distance_sec(base_time_sec, base_dist, target_dist, "sentetik", breed)

    # 2. Pist + şehir handikabı
    if target_surface == "cim":
        # Sentetik → Çim dönüşümü (sentetik→çim = -0.40 → çim daha hızlı)
        t += surface_conv_sec("sentetik", "cim", target_dist, breed)
        # Çim tablosundan şehir handikabı (İstanbul Çim referanslı)
        t += city_handicap_sec(target_city, "cim", target_dist, breed)
    else:
        # Kum/Sentetik tablosundan şehir handikabı (İstanbul Sentetik referanslı)
        t += city_handicap_sec(target_city, target_surface, target_dist, breed)

    # 3. Zemin durumu cezası (sadece çim)
    t += going_adj_sec(target_penetrometer, target_dist, breed, target_surface)

    # 4. Kilo farkı
    if old_net_kg > 0 and new_gross_kg > 0:
        t += weight_time_adj_sec(old_net_kg, new_gross_kg, apranti_code, target_dist)

    return t
