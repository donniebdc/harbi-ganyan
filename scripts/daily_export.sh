#!/bin/bash
# Harbi Ganyan — gunluk v3 export + import
# Her gün 06:00'da calisir (TJK programi acildiktan sonra)

TODAY=$(date +%Y-%m-%d)
V3_DIR="/opt/harbi_ganyan_v3"
BACK_DIR="/opt/harbi_ganyan_backend"
VENV_PY="$BACK_DIR/.venv/bin/python3"
LOG="/var/log/harbi_ganyan_daily.log"

echo "=== $TODAY $(date +%H:%M) ===" >> $LOG

# v3 export
cd "$V3_DIR"
python3 v3_export.py "$TODAY" >> $LOG 2>&1
if [ $? -ne 0 ]; then
    echo "HATA: v3_export.py basarisiz" >> $LOG
    exit 1
fi

# import (backend venv ile)
IMP=$(find "$BACK_DIR/export/" "$BACK_DIR/" -maxdepth 2 -name 'import_to_db*.py' 2>/dev/null | head -1)
if [ -z "$IMP" ]; then
    echo "HATA: import_to_db scripti bulunamadi" >> $LOG
    exit 1
fi

PYTHONPATH="$BACK_DIR" "$VENV_PY" "$IMP" "$TODAY" >> $LOG 2>&1
if [ $? -eq 0 ]; then
    echo "Tamamlandi: $TODAY" >> $LOG
else
    echo "HATA: import basarisiz" >> $LOG
fi
