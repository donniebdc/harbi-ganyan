# -*- coding: utf-8 -*-
"""
models_push.py — Lokal eğitilmiş XGBoost modellerini VDS'e yükler.

Kullanım:
    python models_push.py          # _lokalson modellerini VDS'e yükle
    python models_push.py --dry    # ne yüklenecek göster, yükleme
    python models_push.py --src    # src/ dizinini de VDS'e yükle

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
SRC_DIR = ROOT / "src"


def _load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"HATA: {CONFIG_PATH} bulunamadı.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _push_models(sftp, remote_dir: str, dry: bool) -> int:
    """Lokal _lokalson modellerini VDS'e yükle."""
    local_files = sorted(MODELS_DIR.glob("*_lokalson.json"))
    if not local_files:
        print("HATA: Lokalde _lokalson modeli yok. Önce eğitim yapın.")
        return 1

    print(f"Lokal modeller ({len(local_files)}):")
    uploaded = 0
    for lf in local_files:
        remote_path = f"{remote_dir}/{lf.name}"
        size_kb = lf.stat().st_size / 1024
        print(f"  {lf.name} ({size_kb:.0f} KB)")

        if dry:
            print(f"  [DRY] -> {remote_path}")
        else:
            sftp.put(str(lf), remote_path)
            print(f"  OK -> {remote_path}")
        uploaded += 1

    return uploaded


def _push_src(sftp, remote_dir: str, dry: bool) -> int:
    """src/harbi_v3/ altındaki değişen dosyaları VDS'e yükle."""
    src_files = [
        "harbi_v3/features.py",
        "harbi_v3/horse_cards.py",
        "harbi_v3/records.py",
        "harbi_v3/predictor.py",
        "harbi_v3/confidence.py",
        "harbi_v3/leakage.py",
    ]

    remote_src = f"{remote_dir}/src"
    uploaded = 0
    print(f"\nKaynak dosyalar ({len(src_files)}):")
    for sf in src_files:
        local_path = SRC_DIR / sf
        if not local_path.exists():
            print(f"  [!] {sf} bulunamadı, atlanıyor")
            continue
        remote_path = f"{remote_src}/{sf}"
        size_kb = local_path.stat().st_size / 1024
        print(f"  {sf} ({size_kb:.0f} KB)")

        if dry:
            print(f"  [DRY] -> {remote_path}")
        else:
            # Klasör yapısını oluştur
            remote_parent = str(Path(remote_path).parent).replace("\\", "/")
            try:
                sftp.stat(remote_parent)
            except FileNotFoundError:
                # Klasör yok, oluşturmayı dene
                try:
                    sftp.mkdir(remote_parent)
                except Exception:
                    # Paramiko mkdir recursive desteklemez, SSH ile yap
                    pass
            sftp.put(str(local_path), remote_path)
            print(f"  OK -> {remote_path}")
        uploaded += 1

    return uploaded


def main():
    dry = "--dry" in sys.argv
    push_src_flag = "--src" in sys.argv
    push_all = "--all" in sys.argv

    cfg = _load_config()
    host = cfg["host"]
    port = cfg.get("port", 22)
    username = cfg["username"]
    password = cfg["password"]
    remote_dir = cfg.get("remote_models_dir", "/opt/harbi_ganyan_v3/models")

    print(f"VDS: {host}:{port}")
    print(f"Remote: {remote_dir}")
    if dry:
        print("[DRY MODE — yukleme yapilmaz]")
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

    # Remote dizini kontrol et/oluştur
    try:
        sftp.stat(remote_dir)
    except FileNotFoundError:
        print(f"HATA: VDS'te {remote_dir} bulunamadı.")
        # Backend dizinini dene
        alt_remote = "/opt/harbi_ganyan_backend/models"
        try:
            sftp.stat(alt_remote)
            remote_dir = alt_remote
            print(f"Alternatif dizin bulundu: {remote_dir}")
        except FileNotFoundError:
            c.close()
            sys.exit(1)

    # Modelleri yükle
    n = _push_models(sftp, remote_dir, dry)
    if not dry and n:
        print(f"\n{n} model VDS'e yuklendi.")

    # Kaynak kodları yükle
    if push_src_flag or push_all:
        # remote_dir burada models dizini, src için bir üst dizine çıkalım
        backend_dir = str(Path(remote_dir).parent)
        ns = _push_src(sftp, backend_dir, dry)
        if not dry and ns:
            print(f"\n{ns} kaynak dosya VDS'e yuklendi.")

    sftp.close()
    c.close()

    if dry:
        print("\nKontrol tamamlandı. Yüklemek için --dry kaldırın.")
    else:
        print("\nDeploy tamamlandı.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
