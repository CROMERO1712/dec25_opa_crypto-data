#!/usr/bin/env bash
# Entraînement quotidien du Random Forest 24 h (lancé par le DAG Airflow opca_random_forest_24h).
# 1. réentraîne le modèle dans un conteneur isolé (1,3 Go max) à partir de la base opca_db ;
# 2. enregistre la prévision à 24 h dans prediction_oos (étiquette ci-dessous), jamais écrasée ;
#    la vue v_prediction_oos_eval la compare au prix réel une fois les 24 h écoulées.
set -euo pipefail
D=/home/ubuntu/projet/v2/rf_v2
LABEL="BTC-USD/Binance RF 24h"
J=$D/journal
mkdir -p "$J"
LOG=$J/rf_$(date -u +%Y%m%dT%H%M).log

exec 9>"$D/.verrou"
flock -n 9 || { echo "un entraînement est déjà en cours"; exit 1; }

# Garder la sortie précédente tant que la nouvelle n'est pas réussie
[ -d "$D/sorties" ] && { rm -rf "$D/sorties_precedente"; cp -a "$D/sorties" "$D/sorties_precedente"; }
DEBUT=$(date +%s)

docker rm -f opca_rf_v2 >/dev/null 2>&1 || true
if ! docker run --rm --name opca_rf_v2 --memory 1300m --cpus 1.25 --shm-size 256m \
      -u "$(id -u):$(id -g)" -e HOME=/tmp -e PYTHONPATH=/work/.pkgs -e PYTHONWARNINGS=ignore \
      --env-file /home/ubuntu/projet/v2/api_v2.env \
      -e RF_SYMBOLE=BTC-USD -e RF_PLATEFORME_ID=1 -e RF_N_ITER=8 -e RF_SORTIE=/work/sorties \
      -v "$D":/work -w /work --entrypoint sh opca-platform-ml:latest \
      -c "[ -d /work/.pkgs/dotenv ] || pip install -q --no-cache-dir --target /work/.pkgs python-dotenv; python -u modele_random_forest_prix_24h.py" \
      > "$LOG" 2>&1; then
  echo "ÉCHEC de l'entraînement, journal : $LOG"; tail -30 "$LOG"; exit 1
fi
grep -vE "PerformanceWarning|^  df\[|\[CV\] END" "$LOG" | tail -45

CSV=$D/sorties/prediction_prochaines_24h.csv
[ -s "$CSV" ] && [ "$(stat -c %Y "$CSV")" -ge "$DEBUT" ] || { echo "pas de nouvelle prévision produite"; exit 1; }

python3 - "$CSV" "$LABEL" > "$J/derniere_insertion.sql" <<'PYEOF'
import csv, sys
lab = sys.argv[2].replace("'", "''")
for r in csv.DictReader(open(sys.argv[1], encoding="utf-8-sig")):
    pa, pp = float(r["prix_actuel"]), float(r["prix_predit_24h_random_forest"])
    sens = "hausse" if pp > pa else "baisse"
    print(f"INSERT INTO prediction_oos (horizon_prediction, date_reference, date_cible, prix_actuel, prix_predit, direction_predite) "
          f"VALUES ('{lab}', '{r['date_reference']}', '{r['date_prediction']}', {pa}, {pp}, '{sens}') "
          f"ON CONFLICT (horizon_prediction, date_reference) DO NOTHING;")
PYEOF
docker exec -i opca_pg_v2 sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$J/derniere_insertion.sql"
echo "prévision enregistrée dans prediction_oos ($LABEL) :"; cat "$CSV"

find "$J" -name 'rf_*.log' -mtime +30 -delete
echo "durée : $(( ($(date +%s) - DEBUT) / 60 )) min"
