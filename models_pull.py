# -*- coding: utf-8 -*-
"""
models_pull.py — VDS'ten eğitilmiş XGBoost modellerini lokale indirir.

Kullanım:
    python models_pull.py          # tüm modelleri çek
    python models_pull.py --dry    # ne inecek göster, indirme

Config:
    config/vds.json — VDS bağlantı bilgileri
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "vds.json"
MODELS_DIR = ROOT / "models"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"HATA: {CONFIG_PATH} bulunamadı.")
        print("config/vds.json oluşturun:")
        print(json.dumps({
            "host": "SUNUCU_IP",
            "port": 22,
            "username": "kullanici",
            "password": "sifre",
            "remote_models_dir": "/opt/harbi_ganyan_v3/models"
        }, indent=2, ensure_ascii=False))
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    dry = "--dry" in sys.argv

    cfg = _load_config()
    host = cfg["host"]
    port = cfg.get("port", 22)
    username = cfg["username"]
    password = cfg["password"]
    remote_dir = cfg.get("remote_models_dir", "/opt/harbi_ganyan_v3/models")

    print(f"VDS: {host}:{port} -> {remote_dir}")
    print(f"Lokal: {MODELS_DIR}")
    print()

    import paramiko

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        c.connect(host, port=port, username=username, password=password, timeout=15)
    except Exception as e:
        print(f"HATA: VDS'e bağlanılamadı: {e}")
        sys.exit(1)

    sftp = c.open_sftp()

    # Uzaktaki model dosyalarını listele
    try:
        remote_files = sftp.listdir(remote_dir)
    except FileNotFoundError:
        print(f"HATA: VDS'te {remote_dir} bulunamadı.")
        c.close()
        sys.exit(1)

    # Sadece _lokalson dosyalarını çek (2 dosya: ranker_lokalson.json, clf_lokalson.json)
    lokalson_files = sorted(f for f in remote_files if "_lokalson" in f and f.endswith(".json"))
    if not lokalson_files:
        print("VDS'te henüz _lokalson modeli yok (once VDS'te egitim yapilmali).")
        c.close()
        return 1

    print(f"VDS'te {len(lokalson_files)} lokalson modeli:")

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # Lokalde olmayanları indir
    downloaded = 0
    skipped = 0
    for fname in lokalson_files:
        print(f"  {fname}")
        local_path = MODELS_DIR / fname
        if local_path.exists() and not dry:
            # Boyut kontrolü yap
            try:
                remote_attr = sftp.stat(f"{remote_dir}/{fname}")
                if local_path.stat().st_size == remote_attr.st_size:
                    skipped += 1
                    continue
            except Exception:
                pass

        if dry:
            print(f"  [DRY] {fname} indirilecek")
        else:
            sftp.get(f"{remote_dir}/{fname}", str(local_path))
            print(f"  OK {fname}")
        downloaded += 1

    sftp.close()
    c.close()

    if dry:
        print(f"\n{downloaded} dosya indirilecek, {skipped} güncel.")
    else:
        print(f"\n{downloaded} dosya indirildi, {skipped} zaten güncel.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
