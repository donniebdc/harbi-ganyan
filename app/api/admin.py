# -*- coding: utf-8 -*-
"""Admin API: kullanici, uyelik, gelir ozeti, bildirim ve manuel uretim."""
from __future__ import annotations
from datetime import datetime, timedelta, date as date_t
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_admin
from ..models import Bildirim, GonderilenBildirim, Kullanici, Uyelik
from ..security import hash_sifre
from .. import fcm
from .. import uyelik_servis

router = APIRouter(prefix="/admin/api", tags=["admin"])

# ─── Manuel üretim (tarih/aralık için engine+export+import) ───
_BACKEND_DIR = Path(os.environ.get("HG_BACKEND_DIR") or
                    Path(__file__).resolve().parents[2])
_ENGINE_ROOT = os.environ.get("HG_ENGINE_ROOT") or "/opt/harbi_ganyan_engine"
_LOG_DIR = _BACKEND_DIR / "logs"
_URET_MAX_GUN = 31  # tek seferde en fazla 31 gün

# Tek aktif iş; uvicorn tek worker varsayımıyla modül-global durum.
_uret_lock = threading.Lock()
_uret_job: dict = {"proc": None, "log": None, "aralik": None, "baslangic": None}


class UretReq(BaseModel):
    start: date_t
    end: date_t | None = None

TIER_PRICE_WEEKLY = {"standart": 0, "vip": 250}
VALID_TIERS = set(TIER_PRICE_WEEKLY)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AdminUserCreate(BaseModel):
    email: str
    sifre: str
    tier: str = "standart"
    email_dogrulandi: bool = True
    is_admin: bool = False
    uyelik_bitis: datetime | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("Gecersiz email.")
        return v

    @field_validator("sifre")
    @classmethod
    def _sifre(cls, v: str) -> str:
        if len(v) < 6:
            raise ValueError("Sifre en az 6 karakter olmali.")
        return v

    @field_validator("tier")
    @classmethod
    def _tier(cls, v: str) -> str:
        if v not in VALID_TIERS:
            raise ValueError("tier standart/vip olmali.")
        return v


class AdminUserUpdate(BaseModel):
    tier: str | None = None
    aktif: bool | None = None
    email_dogrulandi: bool | None = None
    is_admin: bool | None = None
    uyelik_bitis: datetime | None = None
    uzat_gun: int | None = None

    @field_validator("tier")
    @classmethod
    def _tier(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIERS:
            raise ValueError("tier standart/vip olmali.")
        return v

    @field_validator("uzat_gun")
    @classmethod
    def _uzat(cls, v: int | None) -> int | None:
        if v is not None and (v < 0 or v > 3650):
            raise ValueError("uzat_gun 0-3650 arasinda olmali.")
        return v


class BildirimReq(BaseModel):
    baslik: str
    mesaj: str
    kullanici_id: int | None = None
    hedef_tier: str | None = None

    @field_validator("baslik")
    @classmethod
    def _baslik(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("Baslik 1-120 karakter olmali.")
        return v

    @field_validator("mesaj")
    @classmethod
    def _mesaj(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 2000:
            raise ValueError("Mesaj 1-2000 karakter olmali.")
        return v

    @field_validator("hedef_tier")
    @classmethod
    def _hedef_tier(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_TIERS:
            raise ValueError("hedef_tier standart/vip olmali.")
        return v


def _aktif_uyelik(user: Kullanici) -> Uyelik | None:
    now = datetime.utcnow()
    aktifler = [
        u for u in user.uyelikler
        if u.aktif and (u.bitis is None or u.bitis >= now)
    ]
    return max(aktifler, key=lambda u: u.baslangic, default=None)


def _sync_membership(db: Session, user: Kullanici, bitis: datetime | None = None) -> None:
    now = datetime.utcnow()
    for uyelik in user.uyelikler:
        if uyelik.aktif and uyelik.tier != user.tier:
            uyelik.aktif = False
    if user.tier == "standart":
        for uyelik in user.uyelikler:
            uyelik.aktif = False
        return
    current = _aktif_uyelik(user)
    if current is None or current.tier != user.tier:
        current = Uyelik(kullanici_id=user.id, tier=user.tier, kaynak="admin", aktif=True)
        db.add(current)
    if bitis is not None:
        current.bitis = bitis


def _user_payload(user: Kullanici, db: Session | None = None) -> dict:
    uyelik = _aktif_uyelik(user)
    out = {
        "id": user.id,
        "email": user.email,
        "tier": user.tier,
        "aktif": user.aktif,
        "is_admin": user.is_admin,
        "email_dogrulandi": user.email_dogrulandi,
        "created_at": user.created_at,
        "uyelik_bitis": (uyelik.bitis or getattr(uyelik, "expires_at", None)) if uyelik else None,
        "uyelik_kaynak": uyelik.kaynak if uyelik else None,
        "haftalik_tutar": TIER_PRICE_WEEKLY.get(user.tier, 0) if user.aktif else 0,
    }
    # Faz 1C — additive alanlar (mevcut anahtarlar korunur):
    if db is not None:
        erisim = uyelik_servis.erisim_coz(db, user)
        out["is_vip"] = erisim.is_vip
        out["vip_kaynak"] = erisim.source
        out["vip_bitis"] = erisim.effective_until
        out["suresi_doldu"] = erisim.expired_manual and not erisim.is_vip
    return out


@router.get("/ozet")
def ozet(_: Kullanici = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(Kullanici).all()
    aktif = [u for u in users if u.aktif]
    vip_list = [u for u in aktif if u.tier == "vip"]
    vip = [u for u in aktif if u.tier == "vip"]
    haftalik = sum(TIER_PRICE_WEEKLY.get(u.tier, 0) for u in aktif)
    return {
        "toplam_kullanici": len(users),
        "aktif_kullanici": len(aktif),
        "standart": len([u for u in aktif if u.tier == "standart"]),
        "vip": len(vip_list),
        "vip": len(vip),
        "haftalik_gelir_tl": haftalik,
    }


@router.get("/kullanicilar")
def kullanicilar(
    _: Kullanici = Depends(require_admin),
    db: Session = Depends(get_db),
    q: str | None = Query(None),
    tier: str | None = Query(None),
):
    query = db.query(Kullanici)
    if q:
        like = f"%{q.strip().lower()}%"
        query = query.filter(or_(Kullanici.email.ilike(like)))
    if tier:
        if tier not in VALID_TIERS:
            raise HTTPException(status_code=400, detail="Gecersiz tier.")
        query = query.filter(Kullanici.tier == tier)
    return {"kullanicilar": [_user_payload(u, db) for u in query.order_by(Kullanici.id.desc()).all()]}


@router.post("/kullanicilar", status_code=201)
def kullanici_ekle(req: AdminUserCreate, _: Kullanici = Depends(require_admin),
                   db: Session = Depends(get_db)):
    if db.query(Kullanici).filter_by(email=req.email).first():
        raise HTTPException(status_code=409, detail="Bu email zaten kayitli.")
    user = Kullanici(
        email=req.email,
        sifre_hash=hash_sifre(req.sifre),
        email_dogrulandi=req.email_dogrulandi,
        tier=req.tier,
        is_admin=req.is_admin,
        aktif=True,
    )
    db.add(user)
    db.flush()
    if req.tier == "vip":
        # Manuel VIP: vip_until + uyelik.bitis birlikte yazılır (Faz 1C).
        if req.uyelik_bitis is not None:
            uyelik_servis.manuel_vip_tarih_belirle(db, user, req.uyelik_bitis)
        else:
            _sync_membership(db, user, None)  # süresiz admin ataması (mevcut davranış)
    else:
        _sync_membership(db, user, req.uyelik_bitis)
    db.commit()
    db.refresh(user)
    return _user_payload(user, db)


@router.patch("/kullanicilar/{user_id}")
def kullanici_guncelle(user_id: int, req: AdminUserUpdate,
                       admin: Kullanici = Depends(require_admin),
                       db: Session = Depends(get_db)):
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    if user.id == admin.id and req.aktif is False:
        raise HTTPException(status_code=400, detail="Kendi admin hesabinizi pasife alamazsiniz.")
    if req.tier is not None:
        user.tier = req.tier
    if req.aktif is not None:
        user.aktif = req.aktif
    if req.email_dogrulandi is not None:
        user.email_dogrulandi = req.email_dogrulandi
    if req.is_admin is not None:
        user.is_admin = req.is_admin
    if req.uzat_gun is not None:
        # +7g/+14g/+30g/+60g — merkezi servis: aktif manuel bitiş varsa ONA ekler
        # (kalan süre korunur), yoksa/geçmişse şimdiden başlatır (Faz 1C).
        uyelik_servis.manuel_vip_gun_ekle(db, user, req.uzat_gun)
    elif req.uyelik_bitis is not None:
        uyelik_servis.manuel_vip_tarih_belirle(db, user, req.uyelik_bitis)
    else:
        _sync_membership(db, user, None)
    db.commit()
    db.refresh(user)
    return _user_payload(user, db)


class SifreResetReq(BaseModel):
    sifre: str | None = None  # None -> rastgele geçici şifre üretilir

    @field_validator("sifre")
    @classmethod
    def _sifre(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if len(v) < 6:
                raise ValueError("Sifre en az 6 karakter olmali.")
        return v


@router.post("/kullanicilar/{user_id}/sifre")
def kullanici_sifre_reset(user_id: int, req: SifreResetReq,
                          _: Kullanici = Depends(require_admin),
                          db: Session = Depends(get_db)):
    """Kullanıcı şifresini değiştirir/sıfırlar. `sifre` verilmezse rastgele geçici
    şifre üretilir. Yeni şifre yanıtta BİR KEZ düz metin döner (admin kullanıcıya
    iletir). NOT: Şifreler bcrypt ile hash'li saklanır; MEVCUT şifre düz metin
    GÖRÜNTÜLENEMEZ (hash geri çevrilemez) — güvenli karşılığı bu reset akışıdır."""
    import secrets
    import string
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    gecici = req.sifre is None
    if gecici:
        alfabe = string.ascii_letters + string.digits
        yeni = "".join(secrets.choice(alfabe) for _ in range(12))
    else:
        yeni = req.sifre
    user.sifre_hash = hash_sifre(yeni)
    db.commit()
    return {"id": user.id, "email": user.email, "sifre": yeni, "gecici": gecici}


@router.delete("/kullanicilar/{user_id}", status_code=204)
def kullanici_sil(user_id: int, admin: Kullanici = Depends(require_admin),
                  db: Session = Depends(get_db)):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Kendi admin hesabinizi silemezsiniz.")
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    db.delete(user)
    db.commit()


def _uret_calisiyor() -> bool:
    p = _uret_job.get("proc")
    return p is not None and p.poll() is None


def _log_tail(path: str | None, n: int = 60) -> list[str]:
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return [ln.rstrip("\n") for ln in f.readlines()[-n:]]
    except Exception:
        return []


@router.post("/uret", status_code=202)
def uret_baslat(req: UretReq, _: Kullanici = Depends(require_admin)):
    """Bir tarih (veya aralık) için tahmin motorunu yeniden çalıştırır:
    engine + export + import. Geçmiş günlerin alt-bahis analizlerini doldurmak için.
    Arka planda çalışır; durum /admin/api/uret/durum ile izlenir."""
    start = req.start
    end = req.end or start
    if end < start:
        raise HTTPException(status_code=400, detail="Bitiş, başlangıçtan önce olamaz.")
    span = (end - start).days + 1
    if span > _URET_MAX_GUN:
        raise HTTPException(status_code=400,
                            detail=f"En fazla {_URET_MAX_GUN} gün üretilebilir (istek: {span}).")
    with _uret_lock:
        if _uret_calisiyor():
            raise HTTPException(status_code=409, detail={
                "mesaj": "Zaten süren bir üretim var.",
                "aralik": _uret_job.get("aralik")})
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        log_path = str(_LOG_DIR / f"uret_{ts}.log")
        env = dict(os.environ)
        env["HG_ENGINE_ROOT"] = _ENGINE_ROOT
        env["HG_BACKEND_DIR"] = str(_BACKEND_DIR)
        env["PYTHONIOENCODING"] = "utf-8"
        logf = open(log_path, "w", encoding="utf-8")
        # cwd = engine kökü: motorun cwd-bağıl çıktı klasörleri (ör. "Pegadrom AI
        # Analiz TXT") servis kullanıcısının (harbiganyan) yazabildiği yere düşsün.
        # daily_pipeline ve export import'ları __file__'a göre çözülür, cwd'den bağımsız.
        proc = subprocess.Popen(
            [sys.executable, str(_BACKEND_DIR / "cron" / "daily_pipeline.py"),
             "--uret", start.isoformat(), end.isoformat()],
            cwd=_ENGINE_ROOT, env=env, stdout=logf,
            stderr=subprocess.STDOUT, start_new_session=True)
        _uret_job.update({"proc": proc, "log": log_path,
                          "aralik": f"{start.isoformat()} → {end.isoformat()}",
                          "baslangic": datetime.utcnow().isoformat()})
    return {"durum": "baslatildi", "aralik": _uret_job["aralik"], "gun_sayisi": span}


@router.get("/uret/durum")
def uret_durum(_: Kullanici = Depends(require_admin)):
    """Manuel üretim işinin durumu + son log satırları."""
    p = _uret_job.get("proc")
    calisiyor = _uret_calisiyor()
    bitis_kodu = None
    if p is not None and not calisiyor:
        bitis_kodu = p.returncode
    return {
        "calisiyor": calisiyor,
        "aralik": _uret_job.get("aralik"),
        "baslangic": _uret_job.get("baslangic"),
        "bitis_kodu": bitis_kodu,  # None=hiç çalışmadı/sürüyor, 0=başarılı, !=0 hata
        "son_satirlar": _log_tail(_uret_job.get("log")),
    }


@router.post("/bildirimler", status_code=201)
def bildirim_gonder(req: BildirimReq, _: Kullanici = Depends(require_admin),
                    db: Session = Depends(get_db)):
    if req.kullanici_id is not None and db.get(Kullanici, req.kullanici_id) is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    if req.kullanici_id is None and req.hedef_tier is None:
        targets = db.query(Kullanici).filter_by(aktif=True).all()
        hedef_idler = [u.id for u in targets]
        for user in targets:
            db.add(Bildirim(kullanici_id=user.id, baslik=req.baslik, mesaj=req.mesaj))
    elif req.kullanici_id is not None:
        hedef_idler = [req.kullanici_id]
        db.add(Bildirim(kullanici_id=req.kullanici_id, baslik=req.baslik, mesaj=req.mesaj))
    else:
        targets = db.query(Kullanici).filter_by(aktif=True, tier=req.hedef_tier).all()
        hedef_idler = [u.id for u in targets]
        for user in targets:
            db.add(Bildirim(kullanici_id=user.id, baslik=req.baslik, mesaj=req.mesaj,
                            hedef_tier=req.hedef_tier))
    db.commit()
    # Uygulama-içi bildirim oluşturuldu; ayrıca FCM push (yapılandırılmışsa)
    push_adet = fcm.kullanicilara_push(db, hedef_idler, req.baslik, req.mesaj, {"tip": "admin"})
    return {"durum": "gonderildi", "adet": len(hedef_idler), "push": push_adet}


# ─── Faz 1C: Manuel VIP yönetimi ─────────────────────────────────────────────

_VIP_OPERATIONS = {"add_days", "set_until", "expire"}
HEDIYE_VIP_GUN = 7
HEDIYE_VIP_BASLIK = "1 Hafta Hediye Vip"
HEDIYE_VIP_MESAJ = "1 Hafta Hediye Vip hesabınıza tanımlanmıştır."


class VipOperationRequest(BaseModel):
    operation: str
    days: int | None = None
    vip_until: datetime | None = None

    @field_validator("operation")
    @classmethod
    def _op(cls, v: str) -> str:
        if v not in _VIP_OPERATIONS:
            raise ValueError("operation add_days/set_until/expire olmali.")
        return v

    @field_validator("days")
    @classmethod
    def _days(cls, v: int | None) -> int | None:
        if v is not None and (v < 1 or v > 365):
            raise ValueError("days 1-365 arasinda olmali.")
        return v


class HediyeVipRequest(BaseModel):
    idempotency_key: str

    @field_validator("idempotency_key")
    @classmethod
    def _key(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 64:
            raise ValueError("Gecersiz idempotency_key.")
        return v


def _vip_response(db: Session, user: Kullanici, operation: str,
                  eski, yeni) -> dict:
    erisim = uyelik_servis.erisim_coz(db, user)
    return {
        "ok": True,
        "user_id": user.id,
        "email": user.email,
        "operation": operation,
        "old_vip_until": eski.isoformat() if eski else None,
        "new_vip_until": yeni.isoformat() if yeni else None,
        "is_vip": erisim.is_vip,
        "vip_source": erisim.source,
        "effective_until": erisim.effective_until.isoformat() if erisim.effective_until else None,
        "google_play_active": erisim.google_play_active,
    }


@router.patch("/kullanicilar/{user_id}/vip")
def kullanici_vip(user_id: int, req: VipOperationRequest,
                  admin: Kullanici = Depends(require_admin),
                  db: Session = Depends(get_db)):
    """Manuel VIP yönetimi: add_days (1-365), set_until (ISO datetime), expire.
    Aktif Google Play üyeliğine hiçbir işlem dokunmaz."""
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    if req.operation == "add_days":
        if req.days is None:
            raise HTTPException(status_code=422, detail="days zorunlu.")
        eski, yeni = uyelik_servis.manuel_vip_gun_ekle(db, user, req.days)
    elif req.operation == "set_until":
        if req.vip_until is None:
            raise HTTPException(status_code=422, detail="vip_until zorunlu.")
        eski, yeni = uyelik_servis.manuel_vip_tarih_belirle(db, user, req.vip_until)
    else:  # expire
        eski, yeni = uyelik_servis.manuel_vip_bitir(db, user)
    db.commit()
    db.refresh(user)
    print(f"[admin-vip] admin={admin.id} user={user.id} op={req.operation} "
          f"eski={eski} yeni={yeni}", flush=True)
    return _vip_response(db, user, req.operation, eski, yeni)


@router.post("/kullanicilar/{user_id}/hediye-vip", status_code=201)
def kullanici_hediye_vip(user_id: int, req: HediyeVipRequest,
                         admin: Kullanici = Depends(require_admin),
                         db: Session = Depends(get_db)):
    """1 Hafta Hediye VIP: 7 gün manuel VIP + sabit metinli in-app bildirim + push.

    İdempotency: GonderilenBildirim anahtarı (admin_hediye_vip|user|key) VIP süresi
    ve bildirimle AYNI transaction'da yazılır; aynı anahtar ikinci kez gelirse süre
    TEKRAR EKLENMEZ (mevcut durum döner). Push başarısızlığı işlemi geri almaz."""
    user = db.get(Kullanici, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanici bulunamadi.")
    anahtar = f"admin_hediye_vip|{user_id}|{req.idempotency_key}"
    if db.query(GonderilenBildirim.id).filter_by(anahtar=anahtar).first() is not None:
        erisim = uyelik_servis.erisim_coz(db, user)
        return {
            "ok": True, "user_id": user.id, "repeated": True,
            "old_vip_until": None,
            "new_vip_until": user.vip_until.isoformat() if user.vip_until else None,
            "is_vip": erisim.is_vip, "notification_created": False, "push_sent": False,
        }
    eski, yeni = uyelik_servis.manuel_vip_gun_ekle(db, user, HEDIYE_VIP_GUN)
    db.add(GonderilenBildirim(anahtar=anahtar))
    db.add(Bildirim(kullanici_id=user.id, baslik=HEDIYE_VIP_BASLIK,
                    mesaj=HEDIYE_VIP_MESAJ))
    db.commit()
    push_sent = False
    try:
        push_adet = fcm.kullanicilara_push(
            db, [user.id], HEDIYE_VIP_BASLIK, HEDIYE_VIP_MESAJ, {"tip": "hediye_vip"})
        push_sent = bool(push_adet)
    except Exception as exc:
        print(f"[admin-vip] hediye push hatasi user={user.id}: {exc}", flush=True)
    print(f"[admin-vip] admin={admin.id} user={user.id} op=hediye_vip "
          f"eski={eski} yeni={yeni} push={push_sent}", flush=True)
    erisim = uyelik_servis.erisim_coz(db, user)
    return {
        "ok": True,
        "user_id": user.id,
        "old_vip_until": eski.isoformat() if eski else None,
        "new_vip_until": yeni.isoformat() if yeni else None,
        "is_vip": erisim.is_vip,
        "notification_created": True,
        "push_sent": push_sent,
    }
