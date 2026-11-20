# Informations sur la VM du projet OPCA

| Document | Contenu |
| --- | --- |
| [CONFIGURATION_VM.md](CONFIGURATION_VM.md) | Configuration relevée sur la VM : machine, conteneurs, ports, mémoire, PostgreSQL, rôles, Airflow, supervision, cron, fichiers de secrets |
| [DOCUMENTATION_PLATEFORME.md](DOCUMENTATION_PLATEFORME.md) | Explication de chaque élément de la plateforme : rôle, fonctionnement, emplacement, vérification |

Fichiers de configuration correspondants dans `opca-platform/` :

- Docker Compose : `docker-compose.airflow.yaml`, `v2/compose/` (base, API, Streamlit, Grafana), `v2/monitoring/`
- Images : `Dockerfile.*`
- Supervision : `v2/monitoring/prometheus.yml`, `v2/grafana/` (sources, tableaux, alertes)
- Planification : `airflow/dags/`, `v2/checks/crontab.txt`
- Modèles de secrets : `.env.example`, `v2/*.env.example`
- Installation complète : `deploy/installer_opca.py`
