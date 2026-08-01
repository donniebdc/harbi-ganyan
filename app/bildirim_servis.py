# -*- coding: utf-8 -*-
"""Canlı sonuç bildirimleri — metin üretimi + idempotent push/in-app gönderimi.

VDS Sistem.txt bildirim şeması:
  - Koşu sonucu: gayrıresmi (kazanan belli, ganyan yok) → resmi (ganyan işlendi).
  - 6'lı sonucu: tüm ayaklar bittikten sonra tek bildirim (tier_hits + ikramiye).

İDEMPOTENCY: her (gün+hipodrom+tip+no+aşama) için GonderilenBildirim tablosuna
bir anahtar yazılır. run_live her 1 dk'da çağrılsa da aynı bildirim tekrar GİTMEZ.
Bu tablo reimport'tan bağımsızdır (kosu_sonuc/altili_sonuc reimport'ta silinir).
"""
from __future__ import annotations
from datetime import date

from sqlalchemy.orm import Session

from . import fcm
from .models import (Gun, GunHipodrom, Kosu, KosuSonuc, Altili, AltiliSonuc,
                     KosuBahis, Kullanici, Bildirim, GonderilenBildirim)

_TIER_RANK = {"standart": 0, "vip": 1}

# simitci=Mini, harbi=Standart, ortakli=Geniş (VDS Sistem.txt)
_TIER_SIRA = ["simitci", "harbi", "ortakli"]
_TIER_AD = {"simitci": "Mini 6'lı", "harbi": "Standart 6'lı", "ortakli": "Geniş 6'lı"}


def _ddmmyyyy(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _hip_ad(hip: str) -> str:
    """ANKARA -> Ankara."""
    return hip[:1] + hip[1:].lower() if hip else hip


def _tr_para(x: float) -> str:
    """12948.06 -> '12.948,06' (TR binlik nokta, ondalık virgül)."""
    return f"{x:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# ── Metin üreticileri ─────────────────────────────────────────────────────────

def _tr_title(s: str) -> str:
    """'KIZILGÖZ' -> 'Kızılgöz' (TR harf duyarlı kelime-başı büyütme)."""
    out = []
    for w in (s or "").strip().split():
        low = w.replace("I", "ı").replace("İ", "i").lower()
        first = w[0] if w[0] in ("I", "İ") else low[0].upper()
        if low[0] == "i":
            first = "İ"
        elif low[0] == "ı":
            first = "I"
        out.append(first + low[1:])
    return " ".join(out)


def _bes_isaret(bes_hit) -> str:
    return ""  # Sprint 1.3: 5li satir bildirimi kaldirildi
def kosu_metni_gayriresmi(tarih: date, kno: int, son: KosuSonuc) -> str:
    """VDS Sistem.txt: '16.06.2026 1. Koşu | Kazanan At Adı | Gayrı Resmi | 5'li Satır ✅'"""
    ad = _tr_title(son.kazanan_ad or "")
    return (f"{_ddmmyyyy(tarih)} {kno}. Koşu"
            f" | {ad}"
            f" | Gayrı Resmi"
            f"{_bes_isaret(son.bes_hit)}")


def kosu_metni_resmi(tarih: date, kno: int, son: KosuSonuc) -> str:
    """VDS Sistem.txt: '16.06.2026 1. Koşu | Resmi | Kazanan At Adı | 5,60 TL | 5'li Satır ✅'"""
    ad = _tr_title(son.kazanan_ad or "")
    ganyan_str = _tr_para(son.ganyan) if son.ganyan else "—"
    return (f"{_ddmmyyyy(tarih)} {kno}. Koşu"
            f" | Resmi"
            f" | {ad}"
            f" | {ganyan_str}"
            f"{_bes_isaret(son.bes_hit)}")


def altili_metni(tarih: date, hip: str, idx: int, son: AltiliSonuc) -> str:
    """VDS Sistem.txt: '16.06.2026 1. 6'lı Ganyan | 2/4/5/1/1/13 | Mini ❌ | Standart ❌ | Geniş ✅'"""
    hits = son.tier_hits or {}
    # Kazanan at numaraları (her ayak için)
    winners = son.winners or []
    winners_str = " / ".join(str(w) for w in winners) if winners else "—"
    # Tier durumu
    tier_parcalar = []
    for k in _TIER_SIRA:
        h = hits.get(k)
        ad = _TIER_AD[k]
        if h == 6:
            tier_parcalar.append(f"{ad} ✅")
        elif h is not None:
            tier_parcalar.append(f"{ad} ❌")
        else:
            tier_parcalar.append(f"{ad} ❌")
    altili_no = idx + 1  # 0-tabanlı idx → 1-tabanlı gösterim
    mesaj = (f"{_ddmmyyyy(tarih)} {altili_no}. 6'lı Ganyan"
             f" | {winners_str}"
             f" | {' | '.join(tier_parcalar)}")
    if son.ikramiye is not None:
        mesaj += f" | {_tr_para(son.ikramiye)} TL"
    return mesaj


def bahis_metni(tarih: date, hip: str, b: KosuBahis) -> str:
    """Koşu Analizleri bahis sonucu bildirimi (VIP)."""
    if len(b.legs or []) > 1:
        yer = f"Koşu {b.legs[0]}-{b.legs[-1]}"
    else:
        yer = f"Koşu {b.bas_kosu}"
    bas = f"{_ddmmyyyy(tarih)} | {_hip_ad(hip)} | {yer} | {b.ad}"
    if b.tuttu:
        return (f"{bas} | ✓ Analiz Başarılı | İkramiye {_tr_para(b.ganyan or 0)} × "
                f"{b.misli} misli = {_tr_para(b.net or 0)}")
    return f"{bas} | ✗ Analiz Başarısız"


# ── Gönderim altyapısı ────────────────────────────────────────────────────────

def _push_basligi(mesaj: str) -> str:
    """Push notification başlığı (kısa)."""
    p = [s.strip() for s in mesaj.split("|")]
    if len(p) >= 2:
        return p[0].strip()
    return "Harbi Ganyan"


def _gonderildi_mi(db: Session, anahtar: str) -> bool:
    return db.query(GonderilenBildirim.id).filter_by(anahtar=anahtar).first() is not None


# ── Marker yardımcıları (bildirimden bağımsız orkestrasyon durumu) ────────────

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
    kademe ve üstündeki kullanıcılara gider. Döner: gönderildi mi."""
    if _gonderildi_mi(db, anahtar):
        return False
    users = db.query(Kullanici).filter_by(aktif=True).all()
    if min_tier:
        esik = _TIER_RANK.get(min_tier, 0)
        users = [u for u in users if _TIER_RANK.get(u.tier, 0) >= esik]
    if not users:
        return False
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


# ── Sonuç orkestrasyon ────────────────────────────────────────────────────────

def bildir_gun_sonuclari(db: Session, iso: str) -> int:
    """Verilen günün YENİ sonuçlanan koşu/altılılarını tespit edip bildirim atar.
    run_live import'tan SONRA çağrılır. Döner: gönderilen bildirim sayısı.

    Koşu başına 2 bildirim:
      1) Gayrıresmi: kazanan at belli, ganyan henüz yok
      2) Resmi: ganyan işlendi
    Altılı başına 1 bildirim: tüm ayaklar bittikten ve winners bilgisi işlendikten sonra.
    """
    d = date.fromisoformat(iso)
    gun = db.query(Gun).filter(Gun.date == d).one_or_none()
    if gun is None:
        return 0
    n = 0
    for gh in gun.hipodromlar:
        hip = gh.hipodrom
        hip_goster = _hip_ad(hip)

        # ── Koşu sonuçları (gayrıresmi + resmi) ──────────────────────────────
        for k in gh.kosular:
            son = k.sonuc
            if son is None or son.kazanan is None:
                continue  # sonuç yok, atla

            # 1) Gayrıresmi: kazanan var, ganyan yok
            anahtar_gr = f"{iso}|{hip}|kosu|{k.kno}|gayriresmi"
            if gonder(db, anahtar_gr,
                      kosu_metni_gayriresmi(d, k.kno, son),
                      {"tip": "kosu_gayriresmi", "tarih": iso, "hipodrom": hip, "kno": k.kno},
                      baslik=f"{hip_goster} {k.kno}. Koşu"):
                n += 1

            # 2) Resmi: ganyan işlenmiş
            if son.ganyan is not None:
                anahtar_r = f"{iso}|{hip}|kosu|{k.kno}|resmi"
                if gonder(db, anahtar_r,
                          kosu_metni_resmi(d, k.kno, son),
                          {"tip": "kosu_resmi", "tarih": iso, "hipodrom": hip, "kno": k.kno},
                          baslik=f"{hip_goster} {k.kno}. Koşu | Resmi"):
                    n += 1

        # ── Altılı sonuçları — 6'lı ganyan uygulamadan kaldırıldı, bildirim GÖNDERİLMEZ ──
        pass

    return n


def bildir_kosu_analiz_yayin(db: Session, iso: str) -> bool:
    """Gün yayınlanınca VIP'e TEK 'Koşu Analizleri Yayınlandı' bildirimi."""
    d = date.fromisoformat(iso)
    gun = db.query(Gun).filter(Gun.date == d).one_or_none()
    if gun is None:
        return False
    if not any(gh.bahisler for gh in gun.hipodromlar):
        return False
    baslik = "Koşu Analizleri Yayınlandı"
    mesaj = (f"{_ddmmyyyy(d)} | Koşu Analizleri yayınlandı. İkili, sıralı, tabela, "
             f"çoklu ganyan ve daha fazlası VIP panelinizde. Bol şans!")
    return gonder(db, f"{iso}|kosu_analiz_yayin", mesaj,
                  {"tip": "kosu_analiz_yayin", "tarih": iso}, baslik=baslik,
                  min_tier="vip")


def bildir_revize(db: Session, iso: str, hip: str, sebep: str, *,
                  anahtar_eki: str, min_tier: str = "vip",
                  baslik: str = "Analizler Güncellendi") -> bool:
    """Canlı takip revize bildirimi (yarış öncesi yeniden üretim)."""
    d = date.fromisoformat(iso)
    mesaj = f"{_ddmmyyyy(d)} | {_hip_ad(hip)} | {sebep}"
    return gonder(db, f"{iso}|{hip}|revize|{anahtar_eki}", mesaj,
                  {"tip": "revize", "tarih": iso, "hipodrom": hip},
                  baslik=baslik, min_tier=min_tier)
