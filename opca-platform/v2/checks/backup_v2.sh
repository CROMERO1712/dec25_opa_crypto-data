#!/usr/bin/env bash
# Sauvegarde de la NOUVELLE base uniquement. Garde 7 jours.
set -euo pipefail
D="${OPCA_BACKUP_DIR:-$HOME/projet/backups/opca_v2}"
mkdir -p "$D"; chmod 700 "$D"
F="$D/opca_db_$(date -u +%Y%m%dT%H%M%SZ).dump"
docker exec opca_pg_v2 pg_dump -U opca_app -d opca_db -Fc > "$F.tmp"
[ -s "$F.tmp" ] || { echo "dump vide"; rm -f "$F.tmp"; exit 1; }
mv "$F.tmp" "$F"; sha256sum "$F" > "$F.sha256"; chmod 600 "$F" "$F.sha256"
find "$D" -name 'opca_db_*' -mtime +7 -delete
echo "OK $F ($(du -h "$F" | cut -f1))"
