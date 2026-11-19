#!/usr/bin/env bash
# Alimente sentiment_social (indice Fear & Greed) et evenement_marche (actualités RSS) et relie
# chaque signal_trading au sentiment et à l'actualité du moment.
#   0. sauvegarde : dump complet de opca_db + DAG v2 + generer_signaux.py ;
#   1. index uniques (sentiment : source + date_heure ; événement : titre) : aucun doublon possible ;
#   2. collecteurs insert_sentiment_fear_greed.py et insert_evenements_rss.py ;
#   3. generer_signaux.py : renseigne sentiment_id et evenement_id ;
#   4. DAG opca_pipeline_horaire_v2 : tâches collecte_sentiment et collecte_evenements, avant
#      generer_signaux (qui passe en trigger_rule all_done : une source indisponible ne bloque pas le signal) ;
#   5. premier remplissage : historique Fear & Greed depuis 2018 et articles du moment.
# Usage, sur la VM : bash ~/projet/script_migration/sentiment_evenements/installer_sentiment_evenements.sh
# Retour arrière : voir la fin de ce fichier.
set -euo pipefail

P=/home/ubuntu/projet
SRC=$(cd "$(dirname "$0")" && pwd)
PF=$P/plateforme/opca-platform
DAG=$PF/airflow/dags/opca_pipeline_horaire_v2.py
SAUV=$P/backups/sentiment_evenements_$(date +%Y%m%dT%H%M%S)
S=opca_airflow-airflow-scheduler-1
PSQL() { docker exec -i opca_pg_v2 sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'; }
ok() { echo "[OK]   $*"; }
ko() { echo "[ÉCHEC] $*"; exit 1; }

echo "===== sentiment_social + evenement_marche : $(date '+%F %T') ====="
M=$(date +%M); [ "$M" -ge 8 ] && [ "$M" -le 15 ] && ko "le pipeline horaire tourne à hh:10, relancer après hh:15"
[ -f "$SRC/../score_signaux/generer_signaux.py" ] || ko "generer_signaux.py introuvable dans ../score_signaux"

# 0. Sauvegardes
mkdir -p "$SAUV" && chmod 700 "$SAUV"
cp -a "$DAG" "$PF/ml/generer_signaux.py" "$SAUV/"
docker exec opca_pg_v2 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$SAUV/opca_db.dump"
docker exec -i opca_pg_v2 sh -c 'pg_restore -l' < "$SAUV/opca_db.dump" | grep -q "TABLE DATA public signal_trading" \
  || ko "dump invalide"
(cd "$SAUV" && sha256sum * > SHA256SUMS && chmod 600 *)
ok "sauvegarde dans $SAUV ($(du -h "$SAUV/opca_db.dump" | cut -f1))"

# 1. Index uniques
echo "CREATE UNIQUE INDEX IF NOT EXISTS uq_sentiment_source_date ON sentiment_social (source, date_heure);
      CREATE UNIQUE INDEX IF NOT EXISTS uq_evenement_titre ON evenement_marche (titre);" | PSQL >/dev/null
ok "index uniques en place"

# 2. et 3. Scripts
install -m 644 "$SRC/insert_sentiment_fear_greed.py" "$SRC/insert_evenements_rss.py" "$PF/collectors/"
install -m 644 "$SRC/../score_signaux/generer_signaux.py" "$PF/ml/generer_signaux.py"
ok "collecteurs et generer_signaux.py installés"

# 4. DAG
if grep -q "collecte_sentiment" "$DAG"; then
  ok "DAG déjà modifié"
else
  python3 - "$DAG" <<'PY'
import sys
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
avant = '        task_id="generer_signaux",\n'
if s.count(avant) != 1:
    sys.exit("motif generer_signaux introuvable ou multiple")
s = s.replace(avant, avant + '        trigger_rule="all_done",  # une source de contexte en panne ne bloque pas le signal\n')
s += '''    # Contexte des signaux : sentiment de marche (Fear & Greed, 1 valeur/jour) et actualites (RSS)
    collecte_sentiment = BashOperator(
        task_id="collecte_sentiment",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_sentiment_fear_greed.py",
        env=ENV_V2, append_env=True,
    )
    collecte_evenements = BashOperator(
        task_id="collecte_evenements",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_evenements_rss.py",
        env=ENV_V2, append_env=True,
    )
    [collecte_sentiment, collecte_evenements] >> generer_signaux
'''
open(f, "w", encoding="utf-8").write(s)
PY
  ok "DAG : tâches collecte_sentiment et collecte_evenements ajoutées"
fi
docker exec "$S" /home/airflow/ml-venv/bin/python -c 'import ast, sys
for f in sys.argv[1:]: ast.parse(open(f).read())' /opt/airflow/collectors/insert_sentiment_fear_greed.py \
  /opt/airflow/collectors/insert_evenements_rss.py /opt/airflow/ml/generer_signaux.py \
  /opt/airflow/dags/opca_pipeline_horaire_v2.py || ko "erreur de syntaxe"
ok "syntaxe vérifiée"

# 5. Premier remplissage, avec les variables de connexion du DAG lues DANS le conteneur
#    (le mot de passe n'apparaît ni dans ce script ni dans la liste des processus de la VM)
docker exec "$S" sh -c '
  for v in host port name user password; do
    export "DB_$(echo $v | tr a-z A-Z)=$(airflow variables get opca_v2_db_$v 2>/dev/null)"
  done
  /home/airflow/collector-venv/bin/python /opt/airflow/collectors/insert_sentiment_fear_greed.py &&
  /home/airflow/collector-venv/bin/python /opt/airflow/collectors/insert_evenements_rss.py'
echo "select 'sentiment_social', count(*), min(date_heure)::date, max(date_heure)::date from sentiment_social
      union all select 'evenement_marche', count(*), min(date_heure)::date, max(date_heure)::date from evenement_marche;" \
  | PSQL | sed 's/^/       /'

for i in $(seq 1 12); do
  docker exec "$S" airflow tasks list opca_pipeline_horaire_v2 2>/dev/null | grep -q collecte_evenements && break
  sleep 10
done
docker exec "$S" airflow tasks list opca_pipeline_horaire_v2 2>/dev/null | grep -q collecte_evenements \
  && ok "Airflow voit les nouvelles tâches" || ko "Airflow ne voit pas encore les tâches (onglet Import errors)"
echo "Sauvegarde : $SAUV"

# --- Retour arrière -------------------------------------------------------------------------------
# cp <SAUV>/opca_pipeline_horaire_v2.py ~/projet/plateforme/opca-platform/airflow/dags/
# cp <SAUV>/generer_signaux.py ~/projet/plateforme/opca-platform/ml/
# rm ~/projet/plateforme/opca-platform/collectors/{insert_sentiment_fear_greed,insert_evenements_rss}.py
# echo "update signal_trading set sentiment_id = null, evenement_id = null;
#       delete from sentiment_social; delete from evenement_marche;
#       drop index if exists uq_sentiment_source_date; drop index if exists uq_evenement_titre;" \
#   | docker exec -i opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
# Restauration complète de la base (dernier recours) :
# docker exec -i opca_pg_v2 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < <SAUV>/opca_db.dump
