# -*- coding: utf-8 -*-
"""Canlı sonuç bildirimleri — metin üretimi + idempotent push/in-app gönderimi.

Bildirimler.txt spec madde 3-4:
  - Koşu sonucu: gayriresmi (kazanan belli, ganyan yok) -> resmi (ganyan işlendi).
  - 6'lı sonucu: ayak belli (ikramiye yok) -> tam (ikramiye işlendi).

İDEMPOTENCY: her (gün+hipodrom+tip+no+aşama) için GonderilenBildirim tablosuna
bir anahtar yazılır. run_live her 5 dk'da çağrılsa da aynı bildirim tekrar GİTMEZ.
Bu tablo reimport'tan bağımsızdır (kosu_sonuc/altili_sonuc reimport'ta silinir).
"""
from __future__ import annotations
from datetime import date

from sqlalchemy.orm import Session

from . import fcm
from .models import (Gun, GunHipodrom, Kosu, KosuSonuc, Altili, AltiliSonuc,
                     KosuBahis, Kullanici, Bildirim, GonderilenBildirim)

_TIER_RANK = {"standart": 0, "premium": 1, "vip": 2}

_TIER_SIRA = ["simitci", "harbi", "ortakli"]
_TIER_AD = {"simitci": "Simitçi 6'lısı", "harbi": "Harbi Ganyan 6'lısı",
            "ortakli": "Ortak Bonkör 6'lı"}


def _ddmmyyyy(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _hip_ad(hip: str) -> str:
    """ANKARA -> Ankara (görünüm). Türkçe büyük şehir adları için yeterli."""
    return hip[:1] + hip[1:].lower() if hip else hip


def _tr_para(x: float) -> str:
    """12948.06 -> '12.948,06' (TR binlik nokta, ondalık virgül)."""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# ---------------- Metin üreticileri ----------------

def kosu_metni(tarih: date, hip: str, kno: int, son: KosuSonuc) -> str:
    """Madde 3 koşu sonucu bildirimi (gayriresmi / resmi)."""
    ad = (son.kazanan_ad or "").strip()
    if son.kazanan is not None:
        kazanan_str = f'{son.kazanan} - {ad}' if ad else f'{son.kazanan}'
    else:
        kazanan_str = "?"
    bas = (f'{_ddmmyyyy(tarih)} | {_hip_ad(hip)} | Koşu {kno} | '
           f'Kazanan "{kazanan_str}"')
    if son.ganyan is None:
        # Gayriresmi: ganyan henüz işlenmedi
        return f"{bas} | Gayrı Resmi |"
    # Resmi: ganyan geldi, 5'li tahmin işareti
    tahmin = ""
    if son.bes_hit is True:
        tahmin = " | 5'li Satır Tahmini ✓"
    elif son.bes_hit is False:
        tahmin = " | 5'li Satır Tahmini ✗"
    return f"{bas} | Ganyan {_tr_para(son.ganyan)}{tahmin}"


def altili_metni(tarih: date, hip: str, idx: int, son: AltiliSonuc) -> str:
    """Madde 4 altılı sonucu bildirimi (ayak belli / tam)."""
    hits = son.tier_hits or {}
    parcalar = []
    tutan = 0
    for k in _TIER_SIRA:
        h = hits.get(k)
        if h == 6:
            parcalar.append(f"{_TIER_AD[k]} ✓")
            tutan += 1
        elif h is not None:
            parcalar.append(f"{_TIER_AD[k]} ❌ ({h}/6)")
        else:
            parcalar.append(f"{_TIER_AD[k]} ❌")
    bas = (f"{_ddmmyyyy(tarih)} | {_hip_ad(hip)} | {idx + 1}. 6'lı Ganyan | "
           + " | ".join(parcalar))
    if tutan > 0:
        bas += f" | Analizini verdiğimiz {tutan} Tahmin Başarılı oldu."
    # İkramiye durumu
    if son.ikramiye is None:
        return f"{bas} | İkramiye Tutarı bekleniyor"
    return f"{bas} | İkramiye Tutarı {_tr_para(son.ikramiye)}"


def bahis_metni(tarih: date, hip: str, b: KosuBahis) -> str:
    """Koşu Analizleri bahis sonucu bildirimi (VIP)."""
    if len(b.legs or []) > 1:
        yer = f"Koşu {b.legs[0]}-{b.legs[-1]}"
    else:
        yer = f"Koşu {b.bas_kosu}"
    bas = f"{_ddmmyyyy(tarih)} | {_hip_ad(hip)} | {yer} | {b.ad}"
    if b.tuttu:
        return (f"{bas} | ✓ Analiz Başarılı | İkramiye {_tr_para(b.ganyan or 0)} × "
                f"{b.misli} misli = {_tr_para(b.net or 0)} TL")
    return f"{bas} | ✗ Analiz Başarısız"


# ---------------- Gönderim ----------------

def _push_basligi(mesaj: str) -> str:
    """Push notification başlığı (kısa). Pipe metnin ilk anlamlı parçaları."""
    p = [s.strip() for s in mesaj.split("|")]
    # "DD.MM.YYYY | Hip | Koşu N | ..." -> "Hip - Koşu N" gibi
    if len(p) >= 3:
        return f"{p[1]} · {p[2]}"
    return "Harbi Ganyan"


def _gonderildi_mi(db: Session, anahtar: str) -> bool:
    return db.query(GonderilenBildirim.id).filter_by(anahtar=anahtar).first() is not None


# ---------------- Orkestrasyon markerları (bildirimden bağımsız) ----------------
# Canlı takip "bu işi bir kez yaptım mı?" durumunu (T-3h regen, tarama slotu) izler.
# Bildirim gönderilmese bile (örn. premium kullanıcı yoksa) marker yazılmalı ki
# tetik tekrar tekrar ateşlenip aynı işi yeniden yapmasın.

def marker_var(db: Session, anahtar: str) -> bool:
    return _gonderildi_mi(db, anahtar)


def marker_yaz(db: Session, anahtar: str) -> bool:
    """Marker'ı idempotent yaz. Döner: yeni mi yazıldı (False=zaten vardı)."""
    if _gonderildi_mi(db, anahtar):
        return False
    db.add(GonderilenBildirim(anahtar=anahtar))
    db.commit()
    return True


def gonder(db: Session, anahtar: str, mesaj: str, data: dict,
           baslik: str | None = None, min_tier: str | None = None) -> bool:
    """İdempotent gönderim: anahtar daha önce gönderildiyse atla.
    Aktif kullanıcılara in-app Bildirim + FCM push. min_tier verilirse yalnız o
    kademe ve üstündeki kullanıcılara gider (örn. 'vip'). Döner: gönderildi mi."""
    if _gonderildi_mi(db, anahtar):
        return False
    users = db.query(Kullanici).filter_by(aktif=True).all()
    if min_tier:
        esik = _TIER_RANK.get(min_tier, 0)
        users = [u for u in users if _TIER_RANK.get(u.tier, 0) >= esik]
    if not users:
        return False
    # Push'a tıklayınca uygulama Bildirimler sayfasına gitsin (deep-link).
    data = {"route": "bildirimler", **(data or {})}
    push_baslik = baslik or _push_basligi(mesaj)
    hedef_idler = [u.id for u in users]
    for u in users:
        db.add(Bildirim(kullanici_id=u.id, baslik=push_baslik, mesaj=mesaj))
    db.add(GonderilenBildirim(anahtar=anahtar))
    db.commit()
    try:
        fcm.kullanicilara_push(db, hedef_idler, push_baslik, mesaj, data)
    except Exception as e:
        print(f"[bildirim] push hatası ({anahtar}): {e}")
    return True


def bildir_gun_sonuclari(db: Session, iso: str) -> int:
    """Verilen günün YENİ sonuçlanan koşu/altılılarını tespit edip bildirim atar.
    run_live import'tan SONRA çağrılır. Döner: gönderilen bildirim sayısı."""
    d = date.fromisoformat(iso)
    gun = db.query(Gun).filter(Gun.date == d).one_or_none()
    if gun is None:
        return 0
    n = 0
    for gh in gun.hipodromlar:
        hip = gh.hipodrom
        # --- Koşu sonuçları (madde 3) ---
        for k in gh.kosular:
            son = k.sonuc
            if son is None or son.kazanan is None:
                continue
            if son.ganyan is None:
                # gayriresmi aşaması
                anahtar = f"{iso}|{hip}|kosu|{k.kno}|gayriresmi"
                if gonder(db, anahtar, kosu_metni(d, hip, k.kno, son),
                          {"tip": "kosu", "tarih": iso, "hipodrom": hip, "kno": k.kno}):
                    n += 1
            else:
                # resmi aşaması (ganyan geldi)
                anahtar = f"{iso}|{hip}|kosu|{k.kno}|resmi"
                if gonder(db, anahtar, kosu_metni(d, hip, k.kno, son),
                          {"tip": "kosu", "tarih": iso, "hipodrom": hip, "kno": k.kno}):
                    n += 1
        # --- Altılı sonuçları (madde 4) ---
        for a in gh.altililar:
            son = a.sonuc
            if son is None:
                continue
            asama = "tam" if son.ikramiye is not None else "ayak"
            anahtar = f"{iso}|{hip}|altili|{a.idx}|{asama}"
            if gonder(db, anahtar, altili_metni(d, hip, a.idx, son),
                      {"tip": "altili", "tarih": iso, "hipodrom": hip, "idx": a.idx}):
                n += 1
        # --- Koşu Analizleri bahis sonuçları (VIP) ---
        # Yalnız BAŞARILI (tuttu) analizler bildirilir; başarısızlar VIP'i
        # spam'lemesin. Takip her koşu için yapılır (grading run_live'da olur),
        # ama bildirim sadece tutan alt oyunlar için gider.
        for b in gh.bahisler:
            if not b.tuttu:
                continue  # None (sonuçlanmadı) veya False (başarısız) -> atla
            anahtar = f"{iso}|{hip}|bahis|{b.bas_kosu}|{b.tip}"
            if gonder(db, anahtar, bahis_metni(d, hip, b),
                      {"tip": "bahis", "tarih": iso, "hipodrom": hip,
                       "bas_kosu": b.bas_kosu, "bahis_tip": b.tip},
                      min_tier="vip"):
                n += 1
    return n


def bildir_kosu_analiz_yayin(db: Session, iso: str) -> bool:
    """Gün yayınlanınca VIP'e TEK 'Koşu Analizleri Yayınlandı' bildirimi gönderir
    (alt oyunlar için toplu yayın duyurusu — tek tek bahis değil). İdempotent:
    anahtar '<iso>|kosu_analiz_yayin'. Döner: gönderildi mi."""
    d = date.fromisoformat(iso)
    gun = db.query(Gun).filter(Gun.date == d).one_or_none()
    if gun is None:
        return False
    if not any(gh.bahisler for gh in gun.hipodromlar):
        return False  # o günde koşu analizi (alt oyun) yoksa duyuru gönderme
    baslik = "Koşu Analizleri Yayınlandı"
    mesaj = (f"{_ddmmyyyy(d)} | Koşu Analizleri yayınlandı. İkili, sıralı, tabela, "
             f"çoklu ganyan ve daha fazlası VIP panelinizde. Bol şans!")
    return gonder(db, f"{iso}|kosu_analiz_yayin", mesaj,
                  {"tip": "kosu_analiz_yayin", "tarih": iso}, baslik=baslik,
                  min_tier="vip")


def bildir_revize(db: Session, iso: str, hip: str, sebep: str, *,
                  anahtar_eki: str, min_tier: str = "premium",
                  baslik: str = "Analizler Güncellendi") -> bool:
    """Canlı takip revize bildirimi (yarış öncesi yeniden üretim).
    sebep örnekleri:
      "Koşular öncesi analizler tekrar gözden geçirildi"  (T-3h)
      "Koşular öncesi analizler yenilendi | Sebep: 3. koşuda 4 numara çıkarıldı"
      "Koşu Analizleri yenilendi | Sebep: 4. koşuda 3 numara koşmaz"  (alt-bahis, VIP)
    İdempotent anahtar: '<iso>|<hip>|revize|<anahtar_eki>'. Döner: gönderildi mi."""
    d = date.fromisoformat(iso)
    mesaj = f"{_ddmmyyyy(d)} | {_hip_ad(hip)} | {sebep}"
    return gonder(db, f"{iso}|{hip}|revize|{anahtar_eki}", mesaj,
                  {"tip": "revize", "tarih": iso, "hipodrom": hip},
                  baslik=baslik, min_tier=min_tier)
