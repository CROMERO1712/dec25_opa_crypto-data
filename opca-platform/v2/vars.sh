export BKP=~/projet/backups        # dossier du jour (garder cette date fixe)
export OLD=pg_container                # PostgreSQL existant (NE PAS MODIFIER)
export NEW=opca_pg_v2                  # nouveau PostgreSQL
export SCH=opca_airflow-airflow-scheduler-1   # scheduler Airflow
export GW=$(docker network inspect bridge -f '{{(index .IPAM.Config 0).Gateway}}')
# Fonctions d'aide : une requête / un dump sur l'ANCIENNE base (lecture) ou la NOUVELLE
oldsql()  { docker exec "$OLD" sh -c 'psql -U "$POSTGRES_USER" -d dst_db -At -c "$1"' _ "$1"; }
newsql()  { docker exec "$NEW" sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -c "$1"' _ "$1"; }
olddump() { docker exec "$OLD" sh -c 'pg_dump -U "$POSTGRES_USER" -d dst_db "$@"' _ "$@"; }
newdump() { docker exec "$NEW" sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' _ "$@"; }
newpsql() { docker exec -i "$NEW" sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'; }
