# script_migration : scripts utilisés pour la migration de la VM OPCA (21/10/2026)

Aucun de ces fichiers ne contient de mot de passe : ils lisent les secrets dans les fichiers .env de ~/projet.

## Ordre d'exécution

| # | Dossier / script | Rôle | Résultat |
|---|---|---|---|
| 1 | rationalisation/rationalisation.sh | Déplace tout dans ~/projet ; supprime projet_test, l'ancien clone, les anciennes sauvegardes | arrêté à l'étape 2 (option find), état vérifié |
| 2 | rationalisation/rationalisation_suite.sh | Reprise : fichiers .bak/.orig, puis chemins et redémarrage | arrêté sur le dossier protégé airflow/ssh |
| 3 | rationalisation/rationalisation_fin.sh | Corrige chemins, crontab, DAG ; recrée les conteneurs | OK |
| - | rationalisation/doublons.sh | Derniers doublons (venvs inutilisés, publication/) | OK (22/10), 860 Mo libérés |
| 4 | fusion_bases/fusion_donnees.sh | Sauvegarde des 2 bases ; copie des 1 998 anciennes prédictions dst_db → opca_db ; vérification par empreinte | OK |
| 5 | fusion_bases/arret_v1.sh | Pause du DAG v1 ; arrêt de la v1, pgAdmin et dst_db (rien supprimé) ; contrôle adapté | OK, 31 OK / 0 FAIL |
| 6 | random_forest/installer_rf.sh | Installe le DAG opca_random_forest_24h (02:15 UTC) et lancer_rf.sh | OK |
| - | random_forest/lancer_rf.sh | Copie de ~/projet/v2/rf_v2/lancer_rf.sh (entraînement + prévision dans prediction_oos) | installé |
| - | random_forest/opca_random_forest_24h.py | Copie du DAG installé dans plateforme/opca-platform/airflow/dags | installé (limite 3 h) |
| - | outils/generer_acces.sh | Régénère ~/projet/ACCES_EQUIPE.md (droits 600) | non versionné (reste sur la VM) |

## Sauvegardes associées

- ~/projet/backups/sauvegarde_complete_2026-10-21 : tout, avant la rationalisation.
- ~/projet/backups/avant_fusion_20261021T2143 : dst_db, opca_db et rôles, juste avant la fusion.
- ~/projet/historique/check_opca.sh.avant_fusion : contrôle d'origine (avec v1 et parité).

## Retour arrière de la fusion (tant que le volume de dst_db existe)

    docker update --restart=always pg_container pgadmin4_container
    docker start pg_container pgadmin4_container opca_api_test opca_dashboard_test opca_grafana
    docker exec opca_airflow-airflow-scheduler-1 airflow dags unpause opca_pipeline_horaire
    cp ~/projet/historique/check_opca.sh.avant_fusion ~/projet/v2/checks/check_opca.sh

## Évolutions suivantes (25/10 → 04/11/2026)

| Date | Dossier / script | Rôle |
|---|---|---|
| 25/10 | monitoring/ | Prometheus, node-exporter, cAdvisor, tableau Grafana « Infrastructure » et 5 alertes |
| 25/10 | streamlit_onglets/ | Tableau de bord Streamlit en 5 onglets |
| 25/10 | desactiver_ancienne_bdd.sh | Arrêt de l'ancienne base dst_db et de son compose (fichiers sauvegardés) |
| 26/10 | rapport_quotidien/ | Rapport quotidien à 07:00 et 22:30 (heure de Paris) |
| 28/10 | variation_binance/ | Correction de variation_prix_pct pour Binance |
| 02/11 | score_signaux/ | score_confiance (classifieur XGBoost) et signaux de trading simulés |
| 02/11 | sentiment_evenements/ | Collecte Fear & Greed et actualités RSS ; DAG horaire porté à 9 tâches |
| 04/11 | supprimer_dag_v1.sh | Suppression du DAG v1 (sauvegarde préalable, retour arrière en fin de script) |

Ces scripts ont été exécutés une seule fois sur la VM ; ils sont conservés pour l'historique.
Le code en service est dans opca-platform/ et opca-platform/v2/.
