#!/usr/bin/env bash
# Fusion des données : copie des anciennes prédictions de dst_db vers opca_db (ajout seulement).
set -euo pipefail
B=/home/ubuntu/projet/backups/avant_fusion_$(date -u +%Y%m%dT%H%M)
OLD=pg_container; NEW=opca_pg_v2
LABEL="1 pas de temps"
COLS="date_heure, horizon_prediction, prix_predit, direction_predite, score_confiance"
oldq(){ docker exec $OLD sh -c 'psql -U "$POSTGRES_USER" -d dst_db -At -c "$1"' _ "$1"; }
newq(){ docker exec $NEW sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"' _ "$1"; }

echo "===== 1. Sauvegarde fraîche des deux bases"
mkdir -p "$B"; chmod 700 "$B"
docker exec $OLD sh -c 'pg_dump -U "$POSTGRES_USER" -d dst_db -Fc' > "$B/dst_db.dump"
docker exec $NEW sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$B/opca_db.dump"
docker exec $OLD sh -c 'pg_dumpall -U "$POSTGRES_USER" --globals-only' > "$B/dst_db_roles.sql"
[ -s "$B/dst_db.dump" ] && [ -s "$B/opca_db.dump" ] || { echo "dump vide"; exit 1; }
( cd "$B" && sha256sum * > SHA256SUMS ); chmod 600 "$B"/*
ls -la "$B"

echo "===== 2. Contrôles avant copie"
COLS_OLD=$(oldq "select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_name='prediction_modele'")
COLS_NEW=$(newq "select string_agg(column_name, ',' order by ordinal_position) from information_schema.columns where table_name='prediction_modele'")
echo "colonnes dst_db  : $COLS_OLD"; echo "colonnes opca_db : $COLS_NEW"
[ "$COLS_OLD" = "$COLS_NEW" ] || { echo "schémas différents, arrêt"; exit 1; }
N_OLD=$(oldq "select count(*) from prediction_modele where horizon_prediction='$LABEL'")
N_DEJA=$(newq "select count(*) from prediction_modele where horizon_prediction='$LABEL'")
N_AVANT=$(newq "select count(*) from prediction_modele")
echo "à copier : $N_OLD ; déjà présentes dans opca_db : $N_DEJA ; total opca_db avant : $N_AVANT"
[ "$N_DEJA" = "0" ] || { echo "déjà copiées, rien à faire"; exit 0; }
[ "$(oldq "select count(*) from prediction_modele where horizon_prediction<>'$LABEL'")" = "0" ] || { echo "autres étiquettes dans dst_db, arrêt"; exit 1; }

echo "===== 3. Copie (une seule instruction COPY : tout ou rien)"
docker exec $OLD sh -c "psql -U \"\$POSTGRES_USER\" -d dst_db -c \"COPY (SELECT $COLS FROM prediction_modele ORDER BY date_heure) TO STDOUT\"" \
 | docker exec -i $NEW sh -c "psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"COPY prediction_modele ($COLS) FROM STDIN\""

echo "===== 4. Vérification"
N_APRES=$(newq "select count(*) from prediction_modele")
N_COPIE=$(newq "select count(*) from prediction_modele where horizon_prediction='$LABEL'")
echo "opca_db : $N_AVANT avant, $N_APRES après ; anciennes prédictions copiées : $N_COPIE / $N_OLD"
SUM_OLD=$(oldq "select md5(string_agg(date_heure||'|'||coalesce(prix_predit::text,'')||'|'||direction_predite||'|'||coalesce(score_confiance::text,''), ',' order by date_heure)) from prediction_modele")
SUM_NEW=$(newq "select md5(string_agg(date_heure||'|'||coalesce(prix_predit::text,'')||'|'||direction_predite||'|'||coalesce(score_confiance::text,''), ',' order by date_heure)) from prediction_modele where horizon_prediction='$LABEL'")
[ "$SUM_OLD" = "$SUM_NEW" ] && echo "empreinte du contenu identique : OK" || { echo "EMPREINTES DIFFÉRENTES"; exit 1; }
[ "$N_COPIE" = "$N_OLD" ] && [ "$N_APRES" -ge $((N_AVANT + N_OLD)) ] && echo "FUSION DES DONNÉES OK"
