# Informations sur la VM du projet OPCA

| Document | Contenu |
| --- | --- |
| [CONFIGURATION_VM.md](CONFIGURATION_VM.md) | Configuration relevée sur la VM : machine, conteneurs, ports, mémoire, PostgreSQL, rôles, Airflow, supervision, cron, fichiers de secrets |
| [DOCUMENTATION_PLATEFORME.md](DOCUMENTATION_PLATEFORME.md) | Explication de chaque élément de la plateforme : rôle, fonctionnement, emplacement, vérification |

## État au 24/11/2026

- Contrôle automatique horaire (`v2/checks/check_opca.sh`) : 31 OK, 0 WARN, 0 FAIL.
- Le code et la configuration de la VM sont identiques à ce dépôt (vérifié fichier par fichier).
- Lignes par table de `opca_db` :

| Table | Lignes |
| --- | --- |
| serie_prix | 101 744 |
| indicateur_technique | 105 086 |
| activite_marche | 70 827 |
| prediction_modele | 13 949 |
| prediction_oos | 11 447 |
| sentiment_social | 3 215 |
| evenement_marche | 837 |
| signal_trading | 516 |

- Résultats des modèles : section 7 de [DOCUMENTATION_PLATEFORME.md](DOCUMENTATION_PLATEFORME.md#7-lévaluation-des-prévisions).

Fichiers de configuration correspondants dans `opca-platform/` :

- Docker Compose : `docker-compose.airflow.yaml`, `v2/compose/` (base, API, Streamlit, Grafana), `v2/monitoring/`
- Images : `Dockerfile.*`
- Supervision : `v2/monitoring/prometheus.yml`, `v2/grafana/` (sources, tableaux, alertes)
- Planification : `airflow/dags/`, `v2/checks/crontab.txt`
- Modèles de secrets : `.env.example`, `v2/*.env.example`
- Installation complète : `deploy/installer_opca.py`
