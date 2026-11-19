#!/usr/bin/env bash
# Fin de la fusion : une seule base (opca_db). Arrête la v1 et l'ancienne base dst_db SANS rien supprimer.
# Retour arrière possible tant que le volume existe :
#   docker update --restart=always pg_container pgadmin4_container && docker start pg_container pgadmin4_container
#   docker start opca_api_test opca_dashboard_test opca_grafana
#   docker exec opca_airflow-airflow-scheduler-1 airflow dags unpause opca_pipeline_horaire
set -euo pipefail
P=/home/ubuntu/projet
SCHED=opca_airflow-airflow-scheduler-1
CHK=$P/v2/checks/check_opca.sh
step(){ echo; echo "===== $*"; }

step "0. Garde-fous"
N=$(docker exec opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from prediction_modele where horizon_prediction='"'"'1 pas de temps'"'"'"')
[ "$N" = "1998" ] || { echo "anciennes prédictions absentes de opca_db ($N), arrêt"; exit 1; }
ls "$P"/backups/avant_fusion_*/dst_db.dump >/dev/null || { echo "sauvegarde avant fusion absente"; exit 1; }
RUN=$(docker exec $SCHED airflow dags list-runs -d opca_pipeline_horaire --state running -o plain 2>/dev/null | grep -c scheduled || true)
[ "$RUN" = "0" ] || { echo "le DAG v1 tourne, réessayer dans 2 minutes"; exit 1; }
echo "OK : 1998 anciennes prédictions dans opca_db, sauvegarde présente"

step "1. Pause du DAG v1 (opca_pipeline_horaire)"
docker exec $SCHED airflow dags pause opca_pipeline_horaire 2>/dev/null | tail -2

step "2. Arrêt de la v1 et de l'ancienne base (conteneurs et volumes conservés)"
V1="opca_api_test opca_dashboard_test opca_grafana pgadmin4_container pg_container"
docker update --restart=no $V1 >/dev/null     # sinon « always » les relancerait au prochain reboot
docker stop $V1

step "3. Contrôle automatique adapté à une seule base"
cp "$CHK" "$P/historique/check_opca.sh.avant_fusion"
sed -i 's#OLD_CONT="${OPCA_OLD_CONTAINERS:-[^}]*}"#OLD_CONT="${OPCA_OLD_CONTAINERS:-opca_airflow-airflow-postgres-1}"#' "$CHK"
sed -i 's#^  if type oldsql >/dev/null 2>\&1; then#  if [ "${OPCA_PARITY:-0}" = 1 ] \&\& type oldsql >/dev/null 2>\&1; then#' "$CHK"
# Les 1998 anciennes prédictions contiennent 999 doublons d'origine (déjà dans dst_db) : on contrôle le modèle actif
sed -i "s#count(\*) - count(distinct date_heure) from prediction_modele\")#count(*) - count(distinct date_heure) from prediction_modele where horizon_prediction <> '1 pas de temps'\")#" "$CHK"
grep -n 'OLD_CONT=\|OPCA_PARITY\|1 pas de temps' "$CHK"

step "4. Fichier des accès mis à jour"
bash /home/ubuntu/generer_acces.sh

step "5. Vérification"
docker ps --format '{{.Names}}|{{.Status}}|{{.Ports}}' | sort
bash "$CHK" 2>&1 | grep -E "WARN|FAIL|Résumé"
echo "fin : une seule base, opca_db"
