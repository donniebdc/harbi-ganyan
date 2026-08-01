# -*- coding: utf-8 -*-
"""Publication persistence yardimcilari (Sprint14 Asama3B).

Harbi Secim'i publish-time hesaplayip Kosu.harbi_secim'e saklar; sehir bazli
publication metadata (input_hash/content_hash/revision/phase) yonetir.

Ortak Harbi Secim modulu: app.serialize._compute_harbi_secim (harbi_v3.compute
wrapper) — ikinci kopya YOK.

Hash kurallari:
  input_hash  : tahmin GIRDILERI (analiz_puanlari, bes, zorluk, guven, n_at,
                canonical surdirek). Sonuc/updated_at/generated_at HARIC.
  content_hash: kullaniciya gosterilen tahmin ICERIGI (+ harbi_secim, agf_radar,
                aciklama_kartlari). Sonuc (kazandi/ganyan/winner/result_*),
                updated_at, generated_at HARIC.
"""
from __future__ import annotations
import json
import hashlib
from datetime import datetime

from app.serialize import (
    _compute_harbi_secim, _surdirek_map_from_daily_panel, _surdirek_map_for_date,
    _build_surpriz_map,
)


def _sha(o) -> str:
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def _bes_tuples(k):
    return sorted([
        (b.sira, b.slot, b.at_no, b.at, round(float(b.ana or 0.0), 4),
         getattr(b, "jokey", "") or "", bool(getattr(b, "apranti", False)),
         getattr(b, "eku_partner_nos", None) or [])
        for b in k.bes
    ])


def gh_input_hash(gh, surdirek_map: dict, surpriz_map: dict | None = None) -> str:
    surpriz_map = surpriz_map or {}
    parts = []
    for k in sorted(gh.kosular, key=lambda x: x.kno):
        parts.append({
            "kno": k.kno,
            "n_at": k.n_at,
            "analiz_puanlari": k.analiz_puanlari,
            "bes": _bes_tuples(k),
            "zorluk": k.zorluk,
            "guven": getattr(k, "guven", "") or "",
            "surdirek": surdirek_map.get((gh.hipodrom, k.kno)),
            "surpriz": sorted(surpriz_map.get((gh.hipodrom, k.kno)) or []),
        })
    return _sha(parts)


def _hs_wo_meta(hs):
    if not isinstance(hs, dict):
        return None
    return {kk: vv for kk, vv in hs.items() if kk != "_publish"}


def gh_content_hash(gh, surdirek_map: dict, daily_panel_hip=None) -> str:
    parts = []
    for k in sorted(gh.kosular, key=lambda x: x.kno):
        parts.append({
            "kno": k.kno,
            "analiz_puanlari": k.analiz_puanlari,
            "harbi_secim": _hs_wo_meta(getattr(k, "harbi_secim", None)),
            "bes": _bes_tuples(k),
            "zorluk": k.zorluk,
            "guven": getattr(k, "guven", "") or "",
            "agf_radar": getattr(k, "agf_radar", None),
            "aciklama_kartlari": getattr(k, "aciklama_kartlari", None) or [],
            "surdirek": surdirek_map.get((gh.hipodrom, k.kno)),
        })
    return _sha(parts)


def persist_harbi_secim(gh, surdirek_map: dict, surpriz_map: dict,
                        now_iso: str, revision: int) -> None:
    """Her kosu icin Harbi Secim'i ortak modulle hesaplar ve Kosu.harbi_secim'e
    yazar. serialize._kosu_with_context ile AYNI girdiler: is_surdirek
    (surdirek_map) + force_include_nos (surpriz_map). Deterministik: ayni girdi
    -> ayni cikti (FINAL immutability korunur).
    """
    for k in gh.kosular:
        key = (gh.hipodrom, k.kno)
        is_sd = key in surdirek_map
        sd_hno = surdirek_map.get(key) if is_sd else None
        force_nos = surpriz_map.get(key) or None
        hs = _compute_harbi_secim(
            k.analiz_puanlari or [], k.n_at, getattr(k, "zorluk", None),
            is_sd, sd_hno, force_nos,
        )
        if hs is None:
            k.harbi_secim = None
            continue
        payload = dict(hs)
        payload["_publish"] = {
            "is_surdirek": is_sd,
            "surdirek_horse_no": sd_hno,
            "generated_at": now_iso,
            "source_revision": revision,
        }
        k.harbi_secim = payload


def publish_gh(db, gun, gh, daily_panel: dict, phase: str, now: datetime,
               run_id: str) -> str:
    """Bir (gun,sehir) icin Harbi Secim persist + publication metadata.
    Ayni input_hash -> NO_CHANGE (revision artmaz). Doner: publication_status.

    NOT: import_payload transaction'i icinde cagirilir (atomik). Advisory lock
    ust katmanda (import_payload) zaten alinir.
    """
    # serialize.gun_payload ile AYNI kaynak: once canonical daily_panel;
    # bos ise (eski gunler) legacy cache fallback. Boylece publish-time ==
    # request-time (esdegerlik korunur).
    surdirek_map = _surdirek_map_from_daily_panel(daily_panel or {})
    if not surdirek_map:
        _tarih = gun.date.isoformat() if getattr(gun, "date", None) else ""
        surdirek_map = _surdirek_map_for_date(_tarih)
    surpriz_map = _build_surpriz_map(getattr(gun, "surpriz_radar", None))
    new_input = gh_input_hash(gh, surdirek_map, surpriz_map)
    now_iso = now.isoformat()

    # FINAL immutability: yayinlanmis FINAL tahmin alanlari degismez.
    if getattr(gh, "publication_phase", None) == "FINAL" and phase != "FINAL":
        gh.last_attempt_at = now
        gh.last_attempt_status = "NO_CHANGE"
        gh.pub_updated_at = now
        return "NO_CHANGE"

    # Ayni input -> gereksiz revision/update yok.
    if getattr(gh, "input_hash", None) == new_input and getattr(gh, "revision", None):
        gh.last_attempt_at = now
        gh.last_attempt_status = "NO_CHANGE"
        gh.pub_updated_at = now
        return "NO_CHANGE"

    new_rev = int(getattr(gh, "revision", None) or 0) + 1
    persist_harbi_secim(gh, surdirek_map, surpriz_map, now_iso, new_rev)
    new_content = gh_content_hash(gh, surdirek_map, daily_panel)

    gh.publication_phase = phase
    gh.publication_status = "PUBLISHED"
    gh.revision = new_rev
    gh.input_hash = new_input
    gh.content_hash = new_content
    gh.source_run_id = run_id
    gh.last_attempt_at = now
    gh.last_attempt_status = "PUBLISHED"
    gh.last_success_at = now
    gh.pub_updated_at = now
    if phase == "PRELIMINARY" and gh.preliminary_published_at is None:
        gh.preliminary_published_at = now
    if phase == "FINAL":
        gh.final_published_at = now
        gh.frozen_at = now
    return "PUBLISHED"
