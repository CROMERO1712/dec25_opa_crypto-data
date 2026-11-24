# Configuration de la VM du projet OPCA

Releve effectue sur la VM de production le 20/11/2026, verifie le 24/11/2026 (code et configuration
identiques au depot, controle `check_opca.sh` : 31 OK, 0 WARN, 0 FAIL ; disque utilise a 67 %). Aucun mot de passe n'apparait ici :
les secrets sont dans des fichiers `.env` (droits 600) sur la VM, jamais dans le depot.

## 1. Machine

| Element | Valeur |
| --- | --- |
| Hebergement | AWS EC2 |
| Systeme | Ubuntu 22.04.5 LTS |
| Processeur / memoire / disque | 2 vCPU · 7,6 Gio · 29 Go |
| Docker / Docker Compose | 27.5.1 / 2.32.4 |
| Acces | SSH par cle uniquement (`PasswordAuthentication no`), utilisateur `ubuntu` |
| Filtrage reseau | Security Group AWS |

## 2. Organisation des fichiers sur la VM

    ~/projet/
    ├── plateforme/opca-platform/   code (= opca-platform/ de ce depot) + .env d'Airflow
    ├── v2/                         configuration de production (= opca-platform/v2/)
    │   ├── compose/                API, Streamlit, Grafana
    │   ├── monitoring/             Prometheus, node-exporter, cAdvisor
    │   ├── grafana/                tableaux et alertes provisionnes
    │   ├── rf_v2/  xgb_eval/       Random Forest 24 h, evaluation XGBoost
    │   ├── checks/                 check_opca.sh, backup_v2.sh
    │   └── *.env                   secrets (non versionnes)
    ├── rapport_quotidien/          rapport_quotidien.py et rapports produits
    ├── backups/                    sauvegardes pg_dump (7 jours)
    └── ACCES_EQUIPE.md             identifiants de l'equipe (droits 600, jamais copie)

## 3. Conteneurs

| Conteneur | Image | Memoire max | Port publie | Fichier de configuration |
| --- | --- | --- | --- | --- |
| opca_pg_v2 | postgres:16-alpine | 512 Mo | 172.17.0.1:5433 | `v2/compose/docker-compose.base.yaml` |
| opca_adminer_v2 | adminer:4.8.1 | 128 Mo | 127.0.0.1:8085 | `v2/compose/docker-compose.base.yaml` |
| opca_api_v2 | projet_test-api (Dockerfile.api) | 256 Mo | 8003 | `v2/compose/docker-compose.yaml` |
| opca_dashboard_v2 | projet_test-dashboard (Dockerfile.dashboard) | 384 Mo | 8503 | `v2/compose/docker-compose.yaml` |
| opca_airflow-airflow-webserver-1 | opca-airflow:2.9.3 (Dockerfile.airflow) | 1 500 Mo | 8081 | `docker-compose.airflow.yaml` |
| opca_airflow-airflow-scheduler-1 | opca-airflow:2.9.3 | 1 200 Mo | - | `docker-compose.airflow.yaml` |
| opca_airflow-airflow-postgres-1 | postgres:16-alpine (metadonnees Airflow) | 300 Mo | - | `docker-compose.airflow.yaml` |
| opca_grafana_v2 | grafana/grafana-oss:11.2.0 | 400 Mo | 3001 | `v2/compose/docker-compose.grafana.yaml` |
| opca_prometheus | prom/prometheus:v2.54.1 | 300 Mo | 172.17.0.1:9090 | `v2/monitoring/docker-compose.monitoring.yaml` |
| opca_node_exporter | prom/node-exporter:v1.8.2 | 64 Mo | - | `v2/monitoring/docker-compose.monitoring.yaml` |
| opca_cadvisor | ghcr.io/google/cadvisor:v0.60.5 | 200 Mo | - | `v2/monitoring/docker-compose.monitoring.yaml` |
| (ephemere) Random Forest | opca-platform-ml (Dockerfile.ml) | 1 300 Mo | - | `v2/rf_v2/lancer_rf.sh` |

Tous redemarrent automatiquement (`restart: unless-stopped`).
Chemins relatifs a `opca-platform/` dans ce depot.

Volumes de donnees : `opca_pg_v2_data` (base), `opca_airflow_airflow_pg_data` (Airflow),
`opca_v2_grafana_grafana_data` (Grafana), `opca_v2_monitoring_prometheus_data` (Prometheus).

## 4. PostgreSQL (`opca_pg_v2`, base `opca_db`)

**Reglages modifies par rapport aux valeurs par defaut**

| Parametre | Valeur | Origine |
| --- | --- | --- |
| TimeZone / log_timezone | UTC | postgresql.conf |
| listen_addresses | * (dans le conteneur ; publie seulement sur 172.17.0.1) | postgresql.conf |
| max_connections | 100 | postgresql.conf |
| shared_buffers | 128 Mo | postgresql.conf |
| log_connections / log_disconnections | on | ALTER SYSTEM (postgresql.auto.conf) |

Connexions reseau authentifiees en `scram-sha-256`.

**Roles**

| Role | Usage | Droits |
| --- | --- | --- |
| opca_app | API, collecteurs, pipelines Airflow | compte principal de la base (cree par l'image postgres) |
| opca_admin | maintenance par les humains (Adminer) | administrateur |
| grafana_ro | lecture par Grafana | SELECT uniquement |

Schema : `opca-platform/deploy/schema_opca_db.sql` (10 tables + vue `v_prediction_oos_eval`).

## 5. Airflow 2.9.3

- Executeur : LocalExecutor ; metadonnees dans `opca_airflow-airflow-postgres-1`.
- DAG actifs : `opca_pipeline_horaire_v2` (chaque heure a :10 UTC, 9 taches) et
  `opca_random_forest_24h` (02:15 UTC). L'ancien DAG v1 a ete supprime le 04/11/2026.
- Variables Airflow (valeurs non publiees) : `opca_v2_db_host`, `opca_v2_db_port`, `opca_v2_db_name`,
  `opca_v2_db_user`, `opca_v2_db_password`, `opca_v2_write_predictions`.
- Le scheduler lance l'entrainement Random Forest sur l'hote par SSH (cle dediee, non versionnee).

## 6. Supervision

- Prometheus : collecte toutes les 30 s, conservation 15 jours (`v2/monitoring/prometheus.yml`).
- Grafana : sources de donnees, tableaux « OPCA » et « Infrastructure » et 5 alertes provisionnes
  depuis `v2/grafana/` (CPU > 85 %, RAM VM > 90 %, disque > 85 %, RAM conteneur > 90 %, source indisponible).

## 7. Taches planifiees (crontab de `ubuntu`)

Voir `opca-platform/v2/checks/crontab.txt` :

| Heure | Script | Role |
| --- | --- | --- |
| chaque heure a :25 | `v2/checks/check_opca.sh` | 31 controles de la plateforme |
| 03:17 UTC | `v2/checks/backup_v2.sh` | sauvegarde `pg_dump` de opca_db, 7 jours conserves |
| 07:00 et 22:30 (Paris) | `rapport_quotidien/rapport_quotidien.py` | rapport quotidien |

## 8. Fichiers de secrets (non versionnes)

| Fichier sur la VM | Modele dans le depot | Contenu |
| --- | --- | --- |
| `v2/pg.env` | `v2/pg.env.example` | compte de la base |
| `v2/api_v2.env` | `v2/api_v2.env.example` | connexion de l'API |
| `v2/grafana_v2.env` | `v2/grafana_v2.env.example` | administrateur Grafana, compte grafana_ro |
| `v2/grafana_ro.env` | `v2/grafana_ro.env.example` | mot de passe grafana_ro |
| `plateforme/opca-platform/.env` | `.env.example` | Airflow (admin, cle secrete) |

## 9. Reinstallation

`opca-platform/deploy/installer_opca.py` reconstruit toute la VM sur une machine Ubuntu neuve
(voir `opca-platform/deploy/README.md`), avec restauration possible d'une sauvegarde (`--dump`).
