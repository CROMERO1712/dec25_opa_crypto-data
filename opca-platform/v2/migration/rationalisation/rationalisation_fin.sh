#!/usr/bin/env bash
# Rationalisation de la VM du groupe : tout est centralisé dans ~/projet.
# Aucun volume Docker n'est touché (toutes les données des bases et de Grafana y sont).
set -euo pipefail
H=/home/ubuntu
P=$H/projet
SAUV=sauvegarde_complete_2026-10-21
SCHED=opca_airflow-airflow-scheduler-1
step(){ echo; echo "===== $*"; }
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
  --exclude-dir=ssh --exclude-dir=logs --include=*.sh --include='*.py' --include='*.yaml' --include='*.yml' -I 2>/dev/null | grep -v '/logs/' || echo "aucune ancienne référence restante"

step "4. Recréation des conteneurs liés à des dossiers (mêmes noms, mêmes ports, mêmes volumes)"
( cd "$P/v2/compose" && docker compose -f docker-compose.yaml up -d --no-build && docker compose -f docker-compose.grafana.yaml up -d --no-build )
( cd "$P/plateforme/opca-platform" && docker compose -f docker-compose.airflow.yaml up -d --no-build )
( cd "$P/v1" && docker compose up -d --no-build && docker compose --env-file .env.grafana -f docker-compose.grafana.yaml up -d --no-build )
# pg_container / pgadmin4_container tournent déjà depuis ~/projet : on n'y touche pas.
echo "fin de la migration"
