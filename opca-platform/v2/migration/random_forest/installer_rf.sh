#!/usr/bin/env bash
# Installe l'entraînement quotidien du Random Forest et lance un premier entraînement (~30 min).
set -euo pipefail
H=/home/ubuntu
RF=$H/projet/v2/rf_v2
DAGS=$H/projet/plateforme/opca-platform/airflow/dags
S=opca_airflow-airflow-scheduler-1
step(){ echo; echo "===== $*"; }

step "1. Vérifications"
[ -f "$RF/modele_random_forest_prix_24h.py" ] || { echo "code du modèle absent"; exit 1; }
docker image inspect opca-platform-ml:latest >/dev/null || { echo "image opca-platform-ml absente"; exit 1; }
bash -n "$H/lancer_rf.sh"
python3 -m py_compile "$H/opca_random_forest_24h.py" && rm -rf "$H/__pycache__"

step "2. Installation"
install -m 755 "$H/lancer_rf.sh" "$RF/lancer_rf.sh"
install -m 644 "$H/opca_random_forest_24h.py" "$DAGS/opca_random_forest_24h.py"
ls -la "$RF/lancer_rf.sh" "$DAGS/opca_random_forest_24h.py"

step "3. Accès SSH du scheduler vers la VM"
docker exec $S ssh -i /home/airflow/.ssh/airflow_collector -o BatchMode=yes -o StrictHostKeyChecking=yes \
  ubuntu@172.17.0.1 "test -x $RF/lancer_rf.sh && echo 'SSH OK, script exécutable'"

step "4. Prise en compte par Airflow (jusqu'à 2 min)"
for i in $(seq 1 24); do
  docker exec $S airflow dags list 2>/dev/null | grep -q opca_random_forest_24h && break
  sleep 5
done
docker exec $S airflow dags list-import-errors 2>/dev/null
docker exec $S airflow dags list 2>/dev/null | grep opca_random_forest_24h || { echo "DAG non détecté"; exit 1; }
docker exec $S airflow dags unpause opca_random_forest_24h 2>/dev/null | tail -1

step "5. Premier entraînement maintenant (la suite chaque nuit à 02:15 UTC)"
docker exec $S airflow dags trigger opca_random_forest_24h 2>/dev/null | tail -2
echo "Suivi : interface Airflow (port 8081) ou  tail -f $RF/journal/rf_*.log"
