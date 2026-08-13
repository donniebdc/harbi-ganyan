"""Koşu tipi sınıflandırma, güven etiketi ve ML tabanlı sürpriz tespiti."""

from __future__ import annotations

from pathlib import Path

# Kalibrasyon: 2026-06-16, scripts/calibrate_confidence_thresholds.py ile uretilen
# tip-bazli gap yuzdelik dilimlerinden (top%10/%30/%60). Degerler norm_score_gap
# (gun-bazinda 0-100 normalize, ust ust iki at arasi fark) skalasinda.
CONFIDENCE_THRESHOLDS_BY_TYPE: dict[str, tuple[float, float, float]] = {
    "handikap":    (32.7, 20.7, 9.7),
    "sartli":      (35.1, 22.7, 10.8),
    "sartli_arap": (35.1, 22.7, 10.8),  # Arap ŞARTLI — sartli ile ayni, kalibre edilecek
    "maiden":      (34.6, 24.7, 12.6),
    "kv_grup":     (40.1, 26.3, 13.1),
    "grup":        (40.1, 26.3, 13.1),  # G1/G2/G3 — kv_grup ile benzer esikler
    "satis":       (35.9, 22.4, 12.7),  # Satis (claiming) — other ile ayni, kalibre edilecek
    "other":       (35.9, 22.4, 12.7),
}
DEFAULT_CONFIDENCE_THRESHOLDS = CONFIDENCE_THRESHOLDS_BY_TYPE["other"]

# ML sürpriz etiketleri (opsiyonel)
SURPRISE_LABELS = {
    0: "Favori guvenilir",
    1: "2-3 at arasi",
    2: "Surprize acik",
    3: "Her sey olabilir",
}

_MODEL_DIR: Path | None = None


def _get_model_dir() -> Path:
    global _MODEL_DIR
    if _MODEL_DIR is None:
        from .paths import MODELS_DIR
        _MODEL_DIR = MODELS_DIR
    return _MODEL_DIR


def race_type_bucket(race_type: str, race_group: str) -> str:
    text = f"{race_type} {race_group}".lower()
    if "handikap" in text:
        return "handikap"
    if "maiden" in text:
        return "maiden"
    if "şart" in text or "sart" in text:
        # DHÖW / DHÖ / DHT = Arap yarisi (İngiliz ŞARTLI'da hic gelmez)
        if "dhöw" in text or "dhö" in text or "dht" in text:
            return "sartli_arap"
        return "sartli"
    # Satis (claiming) — sahipleri atlarini satmak icin yazdirir, surprize acik
    if "satiş" in text or "satış" in text or "satis" in text:
        return "satis"
    # KV (Kisa Vade) koşulari — kv_grup adini koruyoruz
    if "kv" in text:
        return "kv_grup"
    # Grup koşulari (G1/G2/G3) — kv_grup'tan ayrildi
    if ("grup" in text
            or "g1" in text or "g2" in text or "g3" in text
            or "g 1" in text or "g 2" in text or "g 3" in text):
        return "grup"
    return "other"


def confidence_label(gap: float, bucket: str) -> str:
    """Gap-bazlı güven etiketi (eski sistem, geriye dönük uyumlu)."""
    cok_yuksek, yuksek, orta = CONFIDENCE_THRESHOLDS_BY_TYPE.get(
        bucket, DEFAULT_CONFIDENCE_THRESHOLDS
    )
    if gap >= cok_yuksek:
        return "Cok Yuksek Guven"
    if gap >= yuksek:
        return "Yuksek Guven"
    if gap >= orta:
        return "Orta Guven"
    return "Dusuk Guven"


def predict_surprise_label(gap: float, bucket: str, field_size: int,
                           score_entropy: float = 0.0) -> str:
    """ML tabanlı sürpriz etiketi. Model varsa kullanır, yoksa gap-bazlıya düşer."""
    model_path = _get_model_dir() / "surprise_model.json"
    if model_path.exists():
        try:
            from xgboost import XGBClassifier
            import numpy as np
            clf = XGBClassifier()
            clf.load_model(str(model_path))
            # Basit feature vektörü
            feats = np.array([[float(field_size), score_entropy, gap, 0.0]], dtype=float)
            label = int(clf.predict(feats)[0])
            return SURPRISE_LABELS.get(label, confidence_label(gap, bucket))
        except Exception:
            pass
    return confidence_label(gap, bucket)
