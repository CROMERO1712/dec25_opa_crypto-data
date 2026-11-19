#!/usr/bin/env bash
# Rationalisation de la VM du groupe : tout est centralisé dans ~/projet.
# Aucun volume Docker n'est touché (toutes les données des bases et de Grafana y sont).
set -euo pipefail
H=/home/ubuntu
P=$H/projet
SAUV=sauvegarde_complete_2026-10-21
SCHED=opca_airflow-airflow-scheduler-1
step(){ echo; echo "===== $*"; }

step "0. Garde-fous"
[ -s "$H/$SAUV/SHA256SUMS" ] || { echo "sauvegarde complète introuvable"; exit 1; }
RUNNING=$(docker exec $SCHED airflow dags list-runs --state running -d opca_pipeline_horaire -o plain 2>/dev/null | grep -c manual\\\|scheduled || true)
RUNNING2=$(docker exec $SCHED airflow dags list-runs --state running -d opca_pipeline_horaire_v2 -o plain 2>/dev/null | grep -c manual\\\|scheduled || true)
[ "$RUNNING$RUNNING2" = "00" ] || { echo "un DAG est en cours, réessayer dans 2 minutes"; exit 1; }
for d in opca_repo opca_v2 projet_test opca_publish backups/opca_v2 dec25_opa_crypto-data; do
  [ -d "$H/$d" ] || { echo "absent : $d"; exit 1; }; done
for d in plateforme v2 v1 publication historique; do
  [ ! -e "$P/$d" ] || { echo "existe déjà : projet/$d"; exit 1; }; done

step "1. Déplacements dans ~/projet"
mv "$H/opca_repo"    "$P/plateforme"
mv "$H/opca_v2"      "$P/v2"
mv "$H/projet_test"  "$P/v1"
mv "$H/opca_publish" "$P/publication"
# Ancien projet/backups : 2 fichiers .bak du 09/10 (présents dans la sauvegarde complète)
rm -f "$P"/backups/*.bak.*
rmdir "$P/backups" 2>/dev/null || true
[ ! -e "$P/backups" ] || { echo "projet/backups non vide"; ls -la "$P/backups"; exit 1; }
mkdir -p "$P/backups" "$P/historique"
mv "$H/$SAUV"            "$P/backups/$SAUV"
mv "$H/backups/opca_v2"  "$P/backups/opca_v2"
mv "$H/dec25_opa_crypto-data/logs"                   "$P/historique/dec25_logs"
mv "$H/dec25_opa_crypto-data/projet/log_binance.log" "$P/historique/dec25_log_binance.log"
mv "$H/opca_watchdog.sh" "$H/opca_watchdog.log"      "$P/historique/"

step "2. Suppressions : doublons, test, anciennes sauvegardes (tout est dans la sauvegarde complète)"
# Copies identiques de ~/projet faites le 09/10 dans projet_test (vérifiées par diff)
( cd "$P/v1" && rm -rf "ML classification" "ML regression" import_bougie_coinbase.py insert_binance.py \
    "create_table bdd OPA.sql" log_binance.log log_coinbase.log venv mon_env mon_venv backups \
    grafana/provisioning.bak_* )
# Anciennes sauvegardes
rm -rf "$H/backups"
rm -f  "$H"/opca_sauvegarde_2026-10-09.tgz "$H"/opca_projet_equipe_2026-10-09.tgz \
       "$H"/dst_db_2026-10-09.sql.gz "$H"/roles_pg_2026-10-09.sql.gz "$H"/crontab_avant_watchdog.bak
[ -d "$P/backups/$SAUV" ] || { echo "SAUVEGARDE PERDUE ?!"; exit 1; }
# Ancien clone git (même dépôt GitHub que plateforme/), copie de publication obsolète déjà déplacée
rm -rf "$H/dec25_opa_crypto-data"
# Fichiers isolés identiques à ceux de plateforme/ (md5 vérifiés)
rm -f "$H/install.sh" "$H/integration_variable_explicatives" "$H/modèle_random_forest_prev24h"
# Fichiers .bak / .orig / .pre_delta (copies de travail)
find "$P/plateforme" "$P/v2" "$P/v1" -path '*/.git' -prune -o \
     \( -name '*.bak' -o -name '*.orig' -o -name '*.pre_delta' \) -type f -print -delete
rm -f "$P/docker-compose.yaml.orig"

step "3. Chemins mis à jour"
sed -i 's#/home/ubuntu/opca_v2#/home/ubuntu/projet/v2#g' "$P"/v2/compose/docker-compose.yaml "$P"/v2/compose/docker-compose.grafana.yaml
sed -i 's#\$HOME/opca_v2#$HOME/projet/v2#g; s#\$HOME/backups/opca_v2#$HOME/projet/backups/opca_v2#g' "$P"/v2/checks/check_opca.sh "$P"/v2/checks/backup_v2.sh
sed -i 's#~/backups/2026-10-14#~/projet/backups#' "$P/v2/vars.sh"
sed -i 's#\$H/opca_repo/opca-platform#$H/projet/plateforme/opca-platform#g; s#\$H/opca_v2#$H/projet/v2#g; s#~/opca_export#~/projet/export#g; s#\$H/opca_export#$H/projet/export#g' "$P/v2/tools/export_bundle.sh"
sed -i 's#/home/ubuntu/opca_repo/opca-platform#/home/ubuntu/projet/plateforme/opca-platform#g' "$P/plateforme/opca-platform/airflow/dags/opca_pipeline_horaire.py"
sed -i 's#\$HOME/projet_test#$HOME/projet/v1#g; s#~/projet_test#~/projet/v1#g; s#\$HOME/opca_publish#$HOME/projet/publication#g; s#~/opca_publish#~/projet/publication#g' "$P/v1/preparer_publication.sh"
# Nom de projet Docker figé : les conteneurs et volumes existants sont retrouvés quel que soit le dossier
pin(){ grep -q '^name:' "$1" || sed -i "1i name: $2" "$1"; }
pin "$P/v2/compose/docker-compose.yaml"                       opca_v2
pin "$P/v2/compose/docker-compose.grafana.yaml"               opca_v2_grafana
pin "$P/plateforme/opca-platform/docker-compose.airflow.yaml" opca_airflow
pin "$P/v1/docker-compose.yaml"                               projet_test
pin "$P/v1/docker-compose.grafana.yaml"                       opca_grafana
pin "$P/docker-compose.yaml"                                  projet
crontab -l | sed 's#\$HOME/opca_v2#$HOME/projet/v2#g' | crontab -
crontab -l
grep -rn "opca_repo\|/opca_v2\|projet_test/\|opca_publish\|backups/2026" "$P/v2" "$P/plateforme/opca-platform" "$P/v1"/*.yaml "$P/v1"/*.sh \
  --include='*.sh' --include='*.py' --include='*.yaml' --include='*.yml' -I 2>/dev/null | grep -v '/logs/' || echo "aucune ancienne référence restante"

step "4. Recréation des conteneurs liés à des dossiers (mêmes noms, mêmes ports, mêmes volumes)"
( cd "$P/v2/compose" && docker compose -f docker-compose.yaml up -d --no-build && docker compose -f docker-compose.grafana.yaml up -d --no-build )
( cd "$P/plateforme/opca-platform" && docker compose -f docker-compose.airflow.yaml up -d --no-build )
( cd "$P/v1" && docker compose up -d --no-build && docker compose --env-file .env.grafana -f docker-compose.grafana.yaml up -d --no-build )
# pg_container / pgadmin4_container tournent déjà depuis ~/projet : on n'y touche pas.
echo "fin de la migration"
