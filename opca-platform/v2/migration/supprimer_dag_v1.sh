#!/usr/bin/env bash
# Retire l'ancien DAG opca_pipeline_horaire (v1, 4 tâches), remplacé par opca_pipeline_horaire_v2.
# Retour arrière : voir la fin du fichier.
set -euo pipefail
DAG=opca_pipeline_horaire
DAGS=~/projet/plateforme/opca-platform/airflow/dags
PG=opca_airflow-airflow-postgres-1
B=~/projet/backups/dag_v1_$(date -u +%Y%m%dT%H%M%S)
mkdir -p "$B"
psqlA() { docker exec -i "$PG" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -q' ; }

# 1. Sauvegarde : fichier du DAG + base Airflow complète
cp -p "$DAGS/$DAG.py" "$B/"
docker exec "$PG" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$B/airflow_db.dump"
(cd "$B" && sha256sum * > SHA256SUMS)
echo "[OK] sauvegarde $B ($(du -sh "$B" | cut -f1))"

# 2. Pause + arrêt du passage en cours (les tâches échouent depuis la réactivation)
psqlA <<SQL
UPDATE dag SET is_paused = true WHERE dag_id = '$DAG';
UPDATE task_instance SET state = 'failed', end_date = now()
 WHERE dag_id = '$DAG' AND state IN ('running','up_for_retry','queued','scheduled','up_for_reschedule');
UPDATE dag_run SET state = 'failed', end_date = now() WHERE dag_id = '$DAG' AND state IN ('running','queued');
SQL
echo "[OK] DAG en pause, passage en cours arrêté"

# 3. Retrait du fichier (le scheduler ne le charge plus)
mv "$DAGS/$DAG.py" "$B/$DAG.py.retire"
rm -f "$B/$DAG.py"
echo "[OK] fichier retiré du dossier dags"

# 4. Suppression de l'historique dans Airflow (le DAG disparaît de l'interface)
docker exec opca_airflow-airflow-webserver-1 airflow dags delete "$DAG" -y
echo "[OK] DAG $DAG supprimé d'Airflow"

# Retour arrière :
#   cp -p $B/$DAG.py.retire $DAGS/$DAG.py
#   (historique) docker exec -i $PG sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --data-only -t dag_run -t task_instance' < $B/airflow_db.dump
