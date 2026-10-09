# OPCA Crypto Data - plateforme dockerisee

Collecte, stockage et exploitation de donnees de marches crypto (Binance, Coinbase)
dans PostgreSQL, exposees par une API et visualisees dans Streamlit et Grafana.

## Architecture

| Brique | Role | Port |
| --- | --- | --- |
| PostgreSQL `dst_db` | Stockage (existant) | 5432 |
| API FastAPI | Seul point d'acces aux donnees | 8001 |
| Dashboard Streamlit | Exploration, passe par l'API | 8502 |
| Airflow 2.9.3 | Collecte horaire (DAG `opca_collecte_horaire`) | 8081 |
| Grafana 11 | Monitoring : fraicheur de la collecte, volumes, prix | 3000 |

## Demarrage

    cp .env.example .env        # puis renseigner DB_PASSWORD, AIRFLOW_ADMIN_PASSWORD, ...
    openssl rand -hex 32        # a coller dans AIRFLOW_SECRET_KEY
    docker compose up -d --build                                           # API + dashboard
    docker compose -p opca_airflow -f docker-compose.airflow.yaml up -d --build   # Airflow
    docker compose -p opca_grafana -f docker-compose.grafana.yaml up -d    # Grafana

Initialisation d'Airflow (premiere fois) :
`docker compose -p opca_airflow -f docker-compose.airflow.yaml up airflow-init`.

Grafana lit la base avec un utilisateur `grafana_ro` en lecture seule :
`CREATE ROLE grafana_ro LOGIN PASSWORD '...'; ALTER ROLE grafana_ro SET default_transaction_read_only = on;`
puis `GRANT CONNECT`, `GRANT USAGE ON SCHEMA public` et `GRANT SELECT ON ALL TABLES IN SCHEMA public`.

## Structure

- `api/` API FastAPI (12 endpoints) - `Streamlit/` dashboard - `collectors/` collecteurs Binance et Coinbase
- `airflow/dags/` DAG de collecte - `ml/` calcul des indicateurs techniques (incremental, `--dry-run`)
- `grafana/` source de donnees et dashboard provisionnes - `sql/` schema de la base

## Securite

Aucun secret n'est versionne : tout passe par `.env` (ignore par git). Limiter les ports 5432, 8001,
8502, 8081 et 3000 aux IP autorisees (Security Group).
