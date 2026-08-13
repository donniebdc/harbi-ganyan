from __future__ import annotations

import unicodedata


TR_CITIES = {
    "ANKARA",
    "ISTANBUL",
    "IZMIR",
    "BURSA",
    "ADANA",
    "ELAZIG",
    "DIYARBAKIR",
    "KOCAELI",
    "SANLIURFA",
    "BALIKESIR",
    "ANTALYA",
    "MERSIN",
    "KAYSERI",
    "GAZIANTEP",
    "SIVAS",
    "BATMAN",
    "MUS",
}


def norm_text(value: object) -> str:
    text = str(value or "").strip()
    tr_map = str.maketrans({
        "ç": "c", "Ç": "C",
        "ğ": "g", "Ğ": "G",
        "ı": "i", "İ": "I",
        "ö": "o", "Ö": "O",
        "ş": "s", "Ş": "S",
        "ü": "u", "Ü": "U",
    })
    text = text.translate(tr_map).upper()
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def is_turkiye_hipodrom(value: object) -> bool:
    return norm_text(value) in TR_CITIES

