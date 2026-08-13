#!/bin/bash
# surdirek cache builder — backend venv + HG_DATABASE_URL
HG_DATABASE_URL=$(grep '^HG_DATABASE_URL=' /opt/harbi_ganyan_backend/.env | head -1 | cut -d= -f2-)
export HG_DATABASE_URL
cd /opt/harbi_ganyan_v3
exec /opt/harbi_ganyan_backend/.venv/bin/python3 scripts/surdirek_build_cache.py "$@"
