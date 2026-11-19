# OPCA Crypto Data - plateforme dockerisee

Collecte, stockage et exploitation de donnees de marches crypto (Binance, Coinbase, sentiment,
actualites) dans PostgreSQL, previsions XGBoost et Random Forest, exposition par une API,
visualisation dans Streamlit et supervision dans Grafana.

Etat decrit : celui de la VM de production au 19/11/2026.

## Architecture

| Brique | Role | Acces |
| --- | --- | --- |
| PostgreSQL `opca_pg_v2` (base `opca_db`) | Stockage unique (10 tables + vue `v_prediction_oos_eval`) | 172.17.0.1:5433, jamais expose |
| API FastAPI | Seul point d'acces aux donnees pour le dashboard | :8003 |
| Dashboard Streamlit | 5 onglets : vue d'ensemble, prix, activite, indicateurs, previsions | :8503 |
| Airflow 2.9.3 (LocalExecutor) | Orchestration : DAG horaire et DAG Random Forest | :8081 |
| Prometheus + node-exporter + cAdvisor | Mesures de la VM et des conteneurs (30 s, 15 jours) | interne |
| Grafana 11 | Tableaux donnees et infrastructure, 5 alertes | :3001 |
| Adminer | Administration de la base | 127.0.0.1:8085 (tunnel SSH) |

Chaque conteneur a une limite de memoire (API 256 Mo, dashboard 384 Mo, Grafana 400 Mo,
Prometheus 300 Mo, cAdvisor 200 Mo, node-exporter 64 Mo, Airflow web 1 500 Mo, scheduler 1 200 Mo,
Random Forest 1 300 Mo).

## Pipelines Airflow

**`opca_pipeline_horaire_v2`**, chaque heure a :10 UTC, 9 taches :

    collecte_binance ┐
    collecte_coinbase ├─> calcul_indicateurs ─> regression_xgboost ─┬─> log_previsions_oos
    collecte_activite_binance ┘                                      └─> generer_signaux
    collecte_sentiment ┐                                                    ▲
    collecte_evenements ┴──────────────────────────────────────────────────┘

- `regression_xgboost` : prevision du prix a 1 h et `score_confiance` (classifieur hausse/baisse).
- `log_previsions_oos` : archive les previsions dans `prediction_oos` pour l'evaluation hors echantillon.
- `generer_signaux` : signaux ACHAT / VENTE / ATTENTE simules dans `signal_trading` (aucun ordre reel).
- `collecte_sentiment` : indice Fear & Greed ; `collecte_evenements` : flux RSS CoinDesk et Cointelegraph.

**`opca_random_forest_24h`**, chaque nuit a 02:15 UTC : Airflow lance en SSH sur l'hote
`v2/rf_v2/lancer_rf.sh`, qui execute l'entrainement dans un conteneur ephemere et ecrit la prevision
a 24 h dans `prediction_oos`. Verrou anti-doublon, `catchup=False`.

L'ancien DAG v1 `opca_pipeline_horaire` a ete retire le 04/11/2026 (script
`v2/migration/supprimer_dag_v1.sh`, avec retour arriere).

## Taches planifiees (cron de l'hote)

Voir `v2/checks/crontab.txt` :

- `check_opca.sh` chaque heure a :25 : 31 controles (conteneurs et fraicheur des donnees) ;
- `backup_v2.sh` a 03:17 UTC : `pg_dump` de `opca_db`, 7 jours conserves ;
- `rapport_quotidien.py` a 07:00 et 22:30 (heure de Paris).

## Installation

Sur une VM Ubuntu neuve, tout est automatise par `deploy/installer_opca.py` (voir `deploy/README.md`) :
code, secrets aleatoires, images, base, Airflow, supervision, cron et controle final.
Simulation sans rien modifier : `python3 deploy/installer_opca.py --simulation` ; une etape seule :
`--etapes airflow,cron` ; restauration d'une sauvegarde : `--dump opca_db_....dump`.

## Structure

- `api/` API FastAPI - `Streamlit/` dashboard - `collectors/` collecteurs (Binance, Coinbase, activite, sentiment, RSS)
- `airflow/dags/` DAG horaire v2 et DAG Random Forest - `ml/` indicateurs, XGBoost, archivage OOS, signaux
- `deploy/` installation complete (schema, donnees de reference, installateur)
- `v2/compose`, `v2/monitoring`, `v2/grafana` : compose de production, Prometheus, tableaux et alertes Grafana
- `v2/rf_v2` Random Forest 24 h - `v2/xgb_eval` evaluation XGBoost - `v2/checks` controles, sauvegarde, cron
- `v2/rapport_quotidien` rapport du matin et du soir - `v2/tools` outils d'exploitation
- `v2/migration` scripts de migration de la VM (octobre-novembre 2026), pour l'historique

## Securite

Aucun secret n'est versionne : seuls les modeles `*.env.example` le sont, les vrais `.env` sont ignores
par git et crees avec des droits 600. La base n'ecoute que sur la passerelle Docker ; ouvrir uniquement
les ports 8003, 8503, 8081 et 3001 aux IP autorisees (Security Group).
