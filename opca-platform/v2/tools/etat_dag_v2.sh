#!/usr/bin/env bash
# État des tâches des 2 derniers passages du DAG opca_pipeline_horaire_v2 + dernière bougie d'activité.
# Lecture seule (base d'Airflow et opca_db).
docker exec -i opca_airflow-airflow-postgres-1 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT r.execution_date AS passage, t.task_id, t.state, t.end_date - t.start_date AS duree
FROM task_instance t JOIN dag_run r USING (dag_id, run_id)
WHERE t.dag_id = 'opca_pipeline_horaire_v2'
  AND r.execution_date >= (SELECT max(execution_date) FROM dag_run WHERE dag_id = 'opca_pipeline_horaire_v2') - interval '1 hour'
ORDER BY 1 DESC, 2;
SQL
docker exec -i opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"' <<'SQL'
SELECT instrument_id, count(*) AS lignes, max(date_heure) AS derniere_bougie FROM activite_marche GROUP BY 1 ORDER BY 1;
SQL
