# -*- coding: utf-8 -*-
"""Merkezi VIP erişim çözümleyicisi ve manuel VIP işlemleri (Faz 1C).

Erişim kararı İSTEK ANINDA burada verilir; cron yalnız veri temizliği yapar.

Kaynaklar:
  GOOGLE_PLAY : Uyelik(kaynak='google_play', aktif=True, expires_at gelecekte)
  MANUAL      : kullanici.vip_until gelecekte VEYA aktif google_play-dışı Uyelik
                kaydında bitis gelecekte / bitis NULL (admin'in süresiz ataması —
                mevcut admin panel tier dropdown akışıyla geriye uyum)
  NONE        : hiçbiri

Fail-closed: tier=='vip' olduğu hâlde yukarıdaki kaynakların hiçbiri aktif değilse
kullanıcı VIP DEĞİLDİR (eski hatanın kalıntısı sayılır ve düşürülür).

Saat: mevcut sistemle aynı UTC-naive (datetime.utcnow()). Timezone-aware girdiler
_naive_utc ile normalize edilir; karışım engellenir.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from .models import Kullanici, Uyelik

MANUEL_KAYNAK = "admin"  # mevcut _sync_membership'in yazdığı kaynak değeri


def _now() -> datetime:
    return datetime.utcnow()


def _naive_utc(dt: datetime | None) -> datetime | None:
    """tz-aware ise UTC'ye çevirip naive yapar; naive ise aynen döner."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@dataclass
class ErisimDurumu:
    is_vip: bool
    source: str                      # GOOGLE_PLAY | MANUAL | NONE
    effective_until: datetime | None  # None = süresiz manuel (bitis NULL)
    manual_active: bool
    google_play_active: bool
    expired_manual: bool
    tier_for_response: str           # vip | standart


def _google_play_uyelik(db: Session, kullanici_id: int, now: datetime) -> Uyelik | None:
    """Aktif Google Play üyeliği (kanıtlı: aktif=True + expires_at gelecekte)."""
    return (
        db.query(Uyelik)
        .filter(Uyelik.kullanici_id == kullanici_id,
                Uyelik.kaynak == "google_play",
                Uyelik.aktif == True,  # noqa: E712
                Uyelik.expires_at.isnot(None),
                Uyelik.expires_at > now)
        .order_by(Uyelik.expires_at.desc())
        .first()
    )


def _manuel_bitis(db: Session, user: Kullanici, now: datetime):
    """(manuel_aktif, bitis|None, suresiz) — vip_until + aktif admin uyelikleri.

    vip_until yalnız google_play'e ait DEĞİLSE manuel sayılır (GP akışı vip_until'i
    kendi bitişiyle ezdiği için vip_source ayrımı yapılır).
    """
    adaylar: list[datetime] = []
    suresiz = False
    vu = _naive_utc(user.vip_until)
    if vu is not None and (user.vip_source or "") != "google_play":
        adaylar.append(vu)
    rows = (
        db.query(Uyelik)
        .filter(Uyelik.kullanici_id == user.id,
                Uyelik.kaynak != "google_play",
                Uyelik.aktif == True)  # noqa: E712
        .all()
    )
    for r in rows:
        if r.bitis is None:
            suresiz = True  # admin süresiz VIP ataması (dropdown akışı)
        else:
            adaylar.append(_naive_utc(r.bitis))
    en_gec = max(adaylar) if adaylar else None
    aktif = suresiz or (en_gec is not None and en_gec > now)
    return aktif, en_gec, suresiz


def erisim_coz(db: Session, user: Kullanici, now: datetime | None = None) -> ErisimDurumu:
    """Kullanıcının EFEKTİF VIP durumunu istek anında çözer (DB'ye yazmaz)."""
    now = now or _now()
    gp = _google_play_uyelik(db, user.id, now)
    gp_aktif = gp is not None
    man_aktif, man_bitis, man_suresiz = _manuel_bitis(db, user, now)

    is_vip = gp_aktif or man_aktif
    if gp_aktif and man_aktif:
        source = "GOOGLE_PLAY"  # ikisi de aktifse kanıtlı abonelik öncelikli
        effective = None if man_suresiz else max(
            [d for d in (gp.expires_at, man_bitis) if d is not None], default=None)
    elif gp_aktif:
        source, effective = "GOOGLE_PLAY", gp.expires_at
    elif man_aktif:
        source, effective = "MANUAL", (None if man_suresiz else man_bitis)
    else:
        source, effective = "NONE", None

    expired_manual = (not man_aktif) and (
        man_bitis is not None or (user.tier == "vip" and not gp_aktif))
    return ErisimDurumu(
        is_vip=is_vip, source=source, effective_until=effective,
        manual_active=man_aktif, google_play_active=gp_aktif,
        expired_manual=expired_manual,
        tier_for_response="vip" if is_vip else "standart",
    )


# ── Manuel VIP işlemleri (admin) ──────────────────────────────────────────────

def _sync_manuel_uyelik(db: Session, user: Kullanici, bitis: datetime | None) -> None:
    """Manuel VIP için Uyelik(kaynak='admin') kaydını bitis ile senkron tutar
    (panelin uyelik_bitis görünümü ve mevcut kayıt düzeniyle uyum)."""
    rows = (db.query(Uyelik)
            .filter(Uyelik.kullanici_id == user.id, Uyelik.kaynak != "google_play")
            .all())
    aktif_kayit = None
    for r in rows:
        if r.aktif and aktif_kayit is None:
            aktif_kayit = r
        elif r.aktif:
            r.aktif = False  # tek aktif manuel kayıt
    if aktif_kayit is None:
        aktif_kayit = Uyelik(kullanici_id=user.id, tier="vip",
                             kaynak=MANUEL_KAYNAK, aktif=True)
        db.add(aktif_kayit)
    aktif_kayit.tier = "vip"
    aktif_kayit.bitis = bitis
    aktif_kayit.aktif = bitis is None or bitis > _now()


def manuel_vip_gun_ekle(db: Session, user: Kullanici, gun: int,
                        now: datetime | None = None) -> tuple[datetime | None, datetime]:
    """Manuel VIP'e gün ekler. Aktif manuel bitiş gelecekteyse ONA ekler (kalan
    süre korunur); yoksa/geçmişse şimdiden başlatır. Döner: (eski, yeni)."""
    now = now or _now()
    _aktif, en_gec, suresiz = _manuel_bitis(db, user, now)
    eski = user.vip_until if (user.vip_source or "") != "google_play" else en_gec
    if suresiz:
        # Süresiz manuel VIP'e gün eklemek onu tarihli hâle getirir (now+gun'dan
        # değil, admin'in niyetine en yakın: şimdi + gun).
        base = now
    else:
        base = en_gec if (en_gec is not None and en_gec > now) else now
    yeni = base + timedelta(days=gun)
    user.tier = "vip"
    user.vip_until = yeni
    user.vip_source = "manuel"
    _sync_manuel_uyelik(db, user, yeni)
    return eski, yeni


def manuel_vip_tarih_belirle(db: Session, user: Kullanici, vip_until: datetime,
                             now: datetime | None = None) -> tuple[datetime | None, datetime]:
    """Manuel VIP bitişini doğrudan belirler. Geçmiş tarih = süresi dolmuş kabul."""
    now = now or _now()
    yeni = _naive_utc(vip_until)
    eski = user.vip_until
    user.vip_until = yeni
    user.vip_source = "manuel"
    _sync_manuel_uyelik(db, user, yeni)
    erisim = erisim_coz(db, user, now)
    user.tier = "vip" if erisim.is_vip else "standart"
    return eski, yeni


def manuel_vip_bitir(db: Session, user: Kullanici,
                     now: datetime | None = None) -> tuple[datetime | None, datetime]:
    """Manuel VIP'i sonlandırır: vip_until = şimdi (audit için tarih korunur,
    NULL yapılmaz — NULL eski hatada 'süresiz' anlamına geliyordu). Aktif
    Google Play üyeliğine DOKUNMAZ; GP aktifse kullanıcı VIP kalır."""
    now = now or _now()
    eski = user.vip_until
    user.vip_until = now
    if (user.vip_source or "") != "google_play":
        user.vip_source = "manuel"
    _sync_manuel_uyelik(db, user, now)
    erisim = erisim_coz(db, user, now)
    user.tier = "vip" if erisim.is_vip else "standart"
    return eski, now


def suresi_dolan_manuel_temizle(db: Session, now: datetime | None = None) -> int:
    """Veri temizliği (cron): efektif VIP olmayan tier='vip' kullanıcılarını
    standart'a düşürür. İdempotent — yalnız yanlış satırları değiştirir.
    Erişim kararı zaten istek anında verildiği için bu adım gecikse de
    kullanıcı VIP içerik GÖREMEZ."""
    now = now or _now()
    n = 0
    for u in db.query(Kullanici).filter(Kullanici.tier == "vip").all():
        erisim = erisim_coz(db, u, now)
        if not erisim.is_vip:
            u.tier = "standart"
            n += 1
    return n
