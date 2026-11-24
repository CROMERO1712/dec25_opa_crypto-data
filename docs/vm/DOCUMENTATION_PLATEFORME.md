# Plateforme OPCA – Données et prévision des cryptomonnaies

Ce document explique chaque élément de la plateforme OPCA : à quoi il sert, comment il fonctionne, où il se trouve et comment vérifier qu'il marche. Il suppose de connaître les bases (ligne de commande, SQL, Python) mais pas le projet.

État décrit : 04/11/2026 (architecture et code inchangés au 24/11/2026 ; résultats des modèles mis à jour au 24/11/2026 ; configuration détaillée dans CONFIGURATION_VM.md).

---

## Sommaire

1. [Vue d'ensemble](#1-vue-densemble)
2. [La machine : VM AWS et Docker](#2-la-machine--vm-aws-et-docker)
3. [La base de données PostgreSQL](#3-la-base-de-données-postgresql)
4. [La collecte des données](#4-la-collecte-des-données)
5. [Les indicateurs techniques](#5-les-indicateurs-techniques)
6. [Les modèles de prévision](#6-les-modèles-de-prévision)
7. [L'évaluation des prévisions](#7-lévaluation-des-prévisions)
8. [Score de confiance et signaux de trading](#8-score-de-confiance-et-signaux-de-trading)
9. [Sentiment et actualités](#9-sentiment-et-actualités)
10. [Airflow : l'orchestration](#10-airflow--lorchestration)
11. [L'API FastAPI](#11-lapi-fastapi)
12. [Le tableau de bord Streamlit](#12-le-tableau-de-bord-streamlit)
13. [La supervision : Prometheus et Grafana](#13-la-supervision--prometheus-et-grafana)
14. [Contrôles, rapports et sauvegardes](#14-contrôles-rapports-et-sauvegardes)
15. [Accès et sécurité](#15-accès-et-sécurité)
16. [Commandes utiles](#16-commandes-utiles)
17. [Limites connues](#17-limites-connues)
18. [Glossaire](#18-glossaire)

---

## 1. Vue d'ensemble

### Le but du projet

Les prix des cryptomonnaies sont publiés par plusieurs plateformes d'échange (Binance, Coinbase…). OPCA les rassemble dans une seule base pour les rendre comparables, calcule des indicateurs, puis teste si des modèles de machine learning peuvent prévoir le prix du Bitcoin à **1 heure** et à **24 heures**.

Le résultat principal, à garder en tête : **aucun des deux modèles ne bat aujourd'hui la prévision naïve** (« le prix dans 1 h sera le prix actuel »). La plateforme sert surtout à le mesurer proprement.

### Le chemin de la donnée

```
 Sources externes (API publiques, sans clé)
 Binance · Coinbase · Fear & Greed · flux RSS
                  │
                  ▼
 ┌─────────────── VM AWS Ubuntu · 11 conteneurs Docker ───────────────┐
 │                                                                    │
 │  Airflow ──déclenche──► Collecte et calculs (Python)               │
 │  (chaque heure à :10,    collecteurs, indicateurs,                 │
 │   chaque nuit à 02:15)   XGBoost 1 h, Random Forest 24 h, signaux  │
 │                                │ écritures SQL                     │
 │                                ▼                                   │
 │                     PostgreSQL · opca_db  ◄── contrôles (cron)     │
 │                       │              │                             │
 │              lecture SQL        lecture seule                      │
 │                       ▼              ▼                             │
 │                 API FastAPI       Grafana ◄── Prometheus           │
 │                       │ JSON                  (node-exporter,      │
 │                       ▼                        cAdvisor)           │
 │                   Streamlit                                        │
 └────────────────────────────────────────────────────────────────────┘
                  │
                  ▼
 Utilisateurs : Streamlit pour explorer, Grafana pour exploiter
```

En une phrase : **les sources entrent par la collecte, tout est stocké dans `opca_db`, puis lu soit par l'API pour l'utilisateur, soit par Grafana pour l'exploitation.**

### Les sept composants

| N° | Composant | Rôle | Section |
| --- | --- | --- | --- |
| C1 | Modèle de données | Structurer actifs, plateformes et séries | [3](#3-la-base-de-données-postgresql) |
| C2 | Collecte | Récupérer les bougies et l'activité | [4](#4-la-collecte-des-données) |
| C3 | Traitements | Calculer les indicateurs techniques | [5](#5-les-indicateurs-techniques) |
| C4 | Machine learning | Prévoir et mesurer l'erreur | [6](#6-les-modèles-de-prévision), [7](#7-lévaluation-des-prévisions) |
| C5 | API | Exposer les données en HTTP | [11](#11-lapi-fastapi) |
| C6 | Streamlit | Montrer les résultats à l'utilisateur | [12](#12-le-tableau-de-bord-streamlit) |
| C7 | Supervision | Surveiller la chaîne et la machine | [13](#13-la-supervision--prometheus-et-grafana), [14](#14-contrôles-rapports-et-sauvegardes) |

Airflow (orchestration) et Docker (hébergement) traversent les sept composants.

---

## 2. La machine : VM AWS et Docker

### À quoi ça sert

Toute la plateforme tourne sur **une seule machine virtuelle** (VM) louée chez AWS. Chaque service y est isolé dans un **conteneur Docker** : un petit environnement qui contient le programme et ses dépendances, sans gêner les autres.

### Détails techniques

| Élément | Valeur |
| --- | --- |
| Adresse | `51.44.254.88` (AWS EC2) |
| Système | Ubuntu, fuseau horaire UTC |
| Ressources | 7,6 Go de RAM, disque de 29 Go (62 % utilisé au 02/11) |
| Utilisateur | `ubuntu`, connexion par clé `project.pem` uniquement |
| Dossier du projet | `~/projet` |

**Les 11 conteneurs permanents** et leur limite de mémoire :

| Conteneur | Service | Limite mémoire |
| --- | --- | --- |
| `opca_pg_v2` | Base de données métier PostgreSQL 16 | 512 Mo |
| `opca_api_v2` | API FastAPI | 256 Mo |
| `opca_dashboard_v2` | Tableau de bord Streamlit | 384 Mo |
| `opca_adminer_v2` | Adminer (interface web pour la base) | 128 Mo |
| `opca_airflow-airflow-webserver-1` | Interface web d'Airflow | 1,5 Go |
| `opca_airflow-airflow-scheduler-1` | Planificateur Airflow (exécute les tâches) | 1,2 Go |
| `opca_airflow-airflow-postgres-1` | Base interne d'Airflow (métadonnées) | 300 Mo |
| `opca_grafana_v2` | Grafana | 400 Mo |
| `opca_prometheus` | Prometheus | 300 Mo |
| `opca_node_exporter` | Mesures de la VM | 64 Mo |
| `opca_cadvisor` | Mesures des conteneurs | 200 Mo |

Un 12e conteneur, `opca_rf_v2`, est **éphémère** : il est créé chaque nuit pour entraîner le Random Forest, puis supprimé (voir [6](#6-les-modèles-de-prévision)).

**Pourquoi des limites de mémoire ?** Si un service consomme trop (fuite mémoire, gros calcul), Docker l'arrête au lieu de laisser toute la VM tomber. C'est aussi pour cela qu'il ne faut **jamais** lancer `airflow tasks test` dans le scheduler : l'entraînement dépasserait sa limite de 1,2 Go.

### Organisation des dossiers sur la VM

```
~/projet/
├── plateforme/opca-platform/   code de la plateforme (dépôt git)
│   ├── collectors/             scripts de collecte (section 4 et 9)
│   ├── ml/                     indicateurs, XGBoost, signaux (sections 5, 6, 8)
│   ├── airflow/dags/           définition des pipelines Airflow (section 10)
│   ├── api/                    API FastAPI (section 11)
│   └── Streamlit/              tableau de bord (section 12)
├── v2/                         exploitation de la version 2
│   ├── checks/                 check_opca.sh, backup_v2.sh (section 14)
│   ├── xgb_eval/               archivage et évaluation des prévisions (section 7)
│   ├── rf_v2/                  Random Forest 24 h (section 6)
│   └── monitoring/             configuration Prometheus (section 13)
├── rapport_quotidien/          rapports du matin et du soir (section 14)
├── backups/                    sauvegardes de la base et des fichiers modifiés
├── script_migration/           paquets d'installation (chacun avec retour arrière)
└── ACCES_EQUIPE.md             identifiants (chmod 600, jamais copié ailleurs)
```

### Comment vérifier

```bash
docker ps --format "{{.Names}} | {{.Status}}"          # les 11 conteneurs doivent être "Up"
docker stats --no-stream --format "{{.Name}} {{.MemUsage}} {{.MemPerc}}"
df -h /  &&  free -h                                     # disque et mémoire
```

---

## 3. La base de données PostgreSQL

### À quoi ça sert

`opca_db` est le cœur de la plateforme : **tout y est écrit, tout y est lu**. Elle garde les prix, leur provenance (quelle plateforme, quel pas de temps) et les résultats des modèles.

### Détails techniques

| Élément | Valeur |
| --- | --- |
| Moteur | PostgreSQL 16, conteneur `opca_pg_v2` |
| Adresse | `172.17.0.1:5433` (interne à la VM, jamais publiée sur internet) |
| Base | `opca_db`, environ 52 Mo |
| Comptes | `opca_app` (API et Airflow), `opca_admin` (humains), `grafana_ro` (lecture seule) |

### Les tables, par famille

**Référentiels** : les listes de base.

| Table | Contenu | Exemple |
| --- | --- | --- |
| `plateforme` | Les plateformes d'échange | 1 = Binance, 2 = Coinbase |
| `instrument_marche` | Les actifs suivis | 1 = BTC-USD, 2 = ETH-USD, 3 = SOL-USD |

**Données brutes** : ce qui est collecté.

| Table | Contenu | Volume au 02/11 |
| --- | --- | --- |
| `serie_prix` | Bougies de 5 min : ouverture, haut, bas, clôture, volume, variation en % | ~77 000 lignes depuis le 09/08 |
| `activite_marche` | Activité de chaque bougie Binance : volume en USDT, nombre de transactions, part des achats | ~52 000 lignes |
| `evenement_marche` | Actualités crypto (titre, catégorie, impact sur le prix) | alimentée depuis le 02/11 |

**Données calculées**

| Table | Contenu | Volume au 02/11 |
| --- | --- | --- |
| `indicateur_technique` | Moyennes mobiles, RSI, MACD, volatilité, pour chaque bougie | ~80 000 lignes |
| `sentiment_social` | Indice Fear & Greed, une valeur par jour | 3 193 jours depuis 2018 |

**Résultats des modèles**

| Table ou vue | Contenu |
| --- | --- |
| `prediction_modele` | Les 288 dernières prévisions XGBoost (24 h), recalculées chaque heure, avec `score_confiance` |
| `prediction_oos` | Archive des vraies prévisions (faites avant de connaître le résultat), jamais écrasées |
| `v_prediction_oos_eval` | Vue qui rapproche chaque prévision archivée du prix réellement observé |
| `signal_trading` | Un signal par heure : ACHAT, VENTE ou ATTENTE (simulation) |

### Les clés et la traçabilité

Une bougie est identifiée de façon unique par **instrument + plateforme + date + pas de temps**. Une contrainte d'unicité (`uq_serie_prix`) l'impose : recharger une bougie existante la met à jour au lieu de créer un doublon.

```sql
-- Exemple : nombre de bougies et dernière date par série
SELECT p.nom AS plateforme, i.symbole, s.pas_temps, count(*), max(s.date_heure)
FROM serie_prix s
JOIN plateforme p USING (plateforme_id)
JOIN instrument_marche i USING (instrument_id)
GROUP BY 1, 2, 3 ORDER BY 1, 2;
```

Toutes les dates sont stockées **en UTC** (heure universelle, 1 h de moins que Paris en hiver).

### Comment y accéder

Depuis ton PC, par tunnel SSH (voir [15](#15-accès-et-sécurité)) :
- **Adminer** (interface web) : tunnel sur 8085, puis http://localhost:8085, serveur `172.17.0.1:5433`, base `opca_db`, compte `opca_admin` ;
- **DBeaver ou psql** : tunnel sur 5433, puis `localhost:5433`.

Depuis la VM :

```bash
docker exec -it opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

---

## 4. La collecte des données

### À quoi ça sert

Les collecteurs sont des scripts Python qui interrogent les **API publiques** des plateformes et écrivent les bougies dans la base. Ils tournent chaque heure, lancés par Airflow.

### Qu'est-ce qu'une bougie ?

Une bougie (ou *candle*, OHLCV) résume le marché sur un intervalle, ici **5 minutes** :

| Champ | Signification |
| --- | --- |
| Open (`prix_ouverture`) | Prix au début des 5 minutes |
| High (`prix_haut`) | Prix le plus haut atteint |
| Low (`prix_bas`) | Prix le plus bas atteint |
| Close (`prix_fermeture`) | Prix à la fin des 5 minutes |
| Volume | Quantité échangée |

Une heure contient donc 12 bougies, une journée 288.

### Les collecteurs

Dossier : `~/projet/plateforme/opca-platform/collectors/`

| Script | Source | Ce qu'il écrit |
| --- | --- | --- |
| `insert_binance.py` | API Binance, paires BTCUSDT, ETHUSDT, SOLUSDT | `serie_prix` (plateforme 1), y compris `variation_prix_pct` |
| `import_bougie_coinbase.py` | API Coinbase, BTC-USD, granularité 300 s | `serie_prix` (plateforme 2) |
| `insert_activite_binance.py` | Même API Binance | `activite_marche` |
| `insert_sentiment_fear_greed.py` | API alternative.me | `sentiment_social` (voir [9](#9-sentiment-et-actualités)) |
| `insert_evenements_rss.py` | Flux RSS CoinDesk et Cointelegraph | `evenement_marche` (voir [9](#9-sentiment-et-actualités)) |

### Détails techniques

- **Incrémental** : chaque collecteur reprend après la dernière bougie déjà en base, au lieu de tout retélécharger.
- **Bougie en cours ignorée** : une bougie n'est écrite que lorsqu'elle est terminée, sinon on stockerait un prix partiel.
- **Pas de doublon** : `INSERT … ON CONFLICT … DO UPDATE` (prix) ou `DO NOTHING` (activité, sentiment, actualités).
- **Variation en %** : `(clôture − ouverture) / ouverture × 100`. Binance la calcule depuis le 28/10 ; l'historique a été rempli à cette date (47 574 lignes).
- **Part des achats** (`ratio_achat_vente`) : volume acheté à l'initiative de l'acheteur / volume total, entre 0 et 1. Au-dessus de 0,5, les acheteurs dominent.
- **Environnement** : les collecteurs tournent dans un environnement Python séparé, `collector-venv`, dans le conteneur scheduler d'Airflow.
- **Connexion** : variables `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, fournies par Airflow.

### Comment vérifier

Le contrôle `check_opca.sh` vérifie que chaque série a environ 288 bougies sur les dernières 24 h et que la dernière date de moins de 75 minutes.

---

## 5. Les indicateurs techniques

### À quoi ça sert

Les indicateurs transforment une suite de prix en informations plus parlantes pour un modèle : la tendance, l'élan, l'agitation du marché.

### Les indicateurs calculés

| Indicateur | Calcul | Ce qu'il indique |
| --- | --- | --- |
| SMA 20 et SMA 50 | Moyenne des 20 (ou 50) derniers prix de clôture | La tendance. Prix au-dessus de la SMA = plutôt haussier |
| RSI 14 | Rapport entre les hausses et les baisses des 14 dernières bougies, de 0 à 100 | L'élan. Au-dessus de 70 = « suracheté », en dessous de 30 = « survendu » |
| MACD | Moyenne exponentielle sur 12 bougies − moyenne exponentielle sur 26 | Le changement de tendance |
| Volatilité | Écart-type des rendements des 20 dernières bougies | L'agitation du marché |

**Attention :** 20 et 50 désignent des **bougies**, pas des jours. Au pas de 5 minutes, SMA 20 = 100 minutes et SMA 50 ≈ 4 heures.

### Détails techniques

- Script : `~/projet/plateforme/opca-platform/ml/compute_indicateurs.py`, tâche Airflow `calcul_indicateurs`.
- Calcul **séparé** pour chaque combinaison instrument × plateforme × pas de temps : on ne mélange jamais le BTC de Binance et celui de Coinbase.
- **Incrémental** : seules les dates postérieures au dernier calcul sont écrites, par lots de 2 000 lignes.
- Les premières bougies d'une série n'ont pas d'indicateur (il faut 50 bougies pour une SMA 50) : c'est normal.
- Limite : si une ancienne bougie est corrigée, ses indicateurs ne sont pas recalculés automatiquement.

---

## 6. Les modèles de prévision

### À quoi ça sert

Deux modèles prévoient le prix du **BTC sur Binance**, à deux horizons différents.

| | XGBoost | Random Forest |
| --- | --- | --- |
| Horizon | 1 heure (12 bougies) | 24 heures |
| Fréquence | Chaque heure, à :10 | Chaque nuit, à 02:15 UTC |
| Durée | Quelques secondes | Environ 1 h (et elle augmente d'environ 1 min par nuit) |
| Où il tourne | Dans le scheduler Airflow | Dans un conteneur éphémère `opca_rf_v2` |
| Écrit dans | `prediction_modele` et `prediction_oos` | `prediction_oos` |

### XGBoost à 1 heure

**Principe :** XGBoost est un ensemble d'arbres de décision construits les uns après les autres, chacun corrigeant les erreurs du précédent (*gradient boosting*). Ici, c'est une **régression** : il prédit un prix.

- Script : `~/projet/plateforme/opca-platform/ml/regression_xgboost.py`, tâche `regression_xgboost`.
- **Entrées (10 variables)** : ouverture, haut, bas, clôture, volume, SMA 20, SMA 50, RSI 14, MACD, volatilité.
- **Cible** : le prix de clôture 12 bougies plus tard (1 h).
- **Réglages** : 300 arbres, profondeur 5, taux d'apprentissage 0,05, sous-échantillonnage 0,8.
- **Validation** : découpage chronologique 80 % / 20 %. On entraîne sur le passé et on teste sur la période la plus récente, jamais l'inverse.
- Le modèle est ensuite réentraîné sur tout l'historique, puis il prédit les 288 dernières bougies, dont la toute dernière, qui est la vraie prévision.
- **Étiquette** : `horizon_prediction = "BTC-USD/Binance 12x5m"`. C'est elle qui identifie le modèle, car la table n'a pas de colonne dédiée.

### Random Forest à 24 heures

**Principe :** une forêt aléatoire est un ensemble d'arbres de décision entraînés chacun sur une partie différente des données ; la prévision est la moyenne de leurs réponses.

- Scripts : `~/projet/v2/rf_v2/modele_random_forest_prix_24h.py`, lancé par `lancer_rf.sh`.
- **Entrées** : prix, activité de marché, indicateurs, **valeurs passées** (il y a 1, 2, 3, 6, 12, 36, 72, 144 et 288 bougies) et variables de calendrier.
- **Cible** : la variation du prix en dollars sur 24 h. Prix prévu = prix actuel + variation prévue.
- **Validation** : 80 / 20 avec une marge de 24 h entre entraînement et test, puis recherche des réglages par `TimeSeriesSplit` (3 découpages, écart de 288 bougies).
- **Pourquoi un conteneur à part ?** L'entraînement a besoin de 1,3 Go de RAM, plus que la limite du scheduler. Le conteneur `opca_rf_v2` est limité à 1,3 Go et 1,25 CPU, et un verrou (`flock`) empêche deux entraînements simultanés.
- **Étiquette** : `"BTC-USD/Binance RF 24h"`.

---

## 7. L'évaluation des prévisions

### À quoi ça sert

C'est la partie la plus importante pour juger les modèles : **comparer chaque prévision au prix réellement observé**, et à une référence simple.

### La prévision naïve

La référence à battre est la **prévision naïve** : « le prix dans 1 h sera le prix actuel ». Elle paraît bête, mais sur un marché très liquide comme le Bitcoin, elle est difficile à battre. Un modèle qui fait moins bien qu'elle n'apporte rien.

### Pourquoi deux tables de prévisions ?

| Table | Contenu | Usage |
| --- | --- | --- |
| `prediction_modele` | 288 prévisions recalculées chaque heure par un modèle qui a **déjà vu** la plupart des résultats | Affichage. Ses scores sont trop optimistes |
| `prediction_oos` | Uniquement les prévisions faites **avant** de connaître le résultat (*out-of-sample*), jamais modifiées | Évaluation honnête |

Le script `~/projet/v2/xgb_eval/log_previsions_oos.py` (tâche `log_previsions_oos`) archive les prévisions XGBoost dont la cible n'est pas encore connue. La vue `v_prediction_oos_eval` les rapproche ensuite de `serie_prix` quand le prix réel arrive.

### Les mesures

| Mesure | Signification |
| --- | --- |
| MAE (erreur absolue moyenne) | En moyenne, de combien de dollars le modèle se trompe |
| MAE naïve | Même chose pour la prévision naïve |
| Bonne direction | % de fois où le modèle a prévu le bon sens (hausse ou baisse) ; 50 % = hasard |

### Résultats au 24/11/2026

| Modèle | Prévisions évaluées | MAE modèle | MAE naïve | Bonne direction |
| --- | --- | --- | --- | --- |
| XGBoost 1 h | 11 400 | 278 $ | 230 $ | 52,7 % |
| Random Forest 24 h | 34 | 1 796 $ | 1 354 $ | 29,4 % |

Pour comparaison, au 02/11/2026 : XGBoost 5 028 prévisions, 200 $ contre 185 $, 50,4 % ; Random Forest 12 prévisions, 1 782 $ contre 1 146 $, 25,0 %.

**Évolution par semaine** (écart = MAE du modèle comparée à la MAE naïve ; positif = moins bon que la naïve) :

| Semaine du | XGBoost : prévisions | XGBoost : écart | XGBoost : direction | Random Forest : prévisions | Random Forest : écart |
| --- | --- | --- | --- | --- | --- |
| 02/11 | 2 016 | +0,5 % | 56,7 % | 7 | −2,9 % |
| 09/11 | 2 016 | +42,2 % | 52,2 % | 7 | +49,8 % |
| 16/11 | 2 016 | +36,1 % | 55,4 % | 7 | +28,4 % |
| 23/11 (en cours) | 387 | +16,9 % | 53,2 % | 2 | −36,5 % |

Dernier entraînement du Random Forest (nuit du 23 au 24/11, période de test) : MAE 1 882 $ contre 1 415 $ pour la naïve, R² 0,82 contre 0,89.

**Conclusion :** aucun modèle ne bat la prévision naïve. XGBoost devine un peu mieux la direction que le hasard (52 à 57 % selon les semaines), mais son erreur en dollars s'est dégradée depuis le 09/11, période de forte volatilité. Le Random Forest a encore trop peu de prévisions (une par jour) pour conclure.

```sql
-- Résumé de l'évaluation
SELECT * FROM v_prediction_oos_eval ORDER BY date_cible DESC LIMIT 20;
```

---

## 8. Score de confiance et signaux de trading

Ajoutés le 02/11/2026. **Simulation uniquement : aucun ordre n'est jamais passé.**

### Le score de confiance

**À quoi ça sert :** XGBoost prédit un prix, mais ne dit pas s'il est sûr de lui. Le score de confiance comble ce manque.

**Comment :** un second modèle, un **classifieur** XGBoost, apprend à répondre « hausse ou baisse dans 1 h ? » et donne une probabilité de hausse `p`.

```
score_confiance = p        si la régression prévoit une hausse
score_confiance = 1 − p    si elle prévoit une baisse
```

Le score est donc la probabilité que la direction prévue soit la bonne. En dessous de 0,5, le classifieur contredit la régression.

**Qualité :** AUC de 0,519 sur la période de test (0,5 = hasard, 1 = parfait). Le score reste donc souvent proche de 0,5.

**Détail important :** les 288 prévisions de `prediction_modele` sont désormais **mises à jour en place** (`UPDATE`, puis `INSERT` si la ligne n'existe pas) au lieu d'être supprimées et recréées. Sinon leurs identifiants changeraient chaque heure, et les signaux perdraient le lien vers leur prévision.

### Les signaux de trading

Script : `~/projet/plateforme/opca-platform/ml/generer_signaux.py`, tâche `generer_signaux`, un signal par heure sur la prévision la plus récente.

| Règle | Signal |
| --- | --- |
| Hausse prévue et confiance ≥ 0,55 | ACHAT |
| Baisse prévue et confiance ≥ 0,55 | VENTE |
| Sinon | ATTENTE |

Pour un ACHAT ou une VENTE, le signal fixe aussi :
- un **stop-loss** (prix auquel on couperait la perte) à 2 fois l'écart attendu ;
- un **take-profit** (prix auquel on prendrait le gain) à 3 fois l'écart attendu.

```
écart attendu = volatilité 5 min × √12 × prix d'entrée
```

Exemple : volatilité 0,0012 et prix 77 000 $ → écart ≈ 320 $, stop-loss à 76 360 $ et take-profit à 77 960 $ pour un ACHAT.

Chaque signal est relié à sa prévision (`prediction_id`), au sentiment du jour (`sentiment_id`) et à la dernière actualité de l'heure (`evenement_id`). Au 24/11/2026, 516 signaux ont été produits : 236 ATTENTE (46 %), 141 ACHAT et 139 VENTE. Le score de confiance dépasse donc souvent le seuil de 0,55. Comme le modèle ne bat pas la référence, ces signaux restent à évaluer frais compris avant toute conclusion.

Réglages (variables d'environnement de la tâche) : `SEUIL=0.55`, `K_SL=2`, `K_TP=3`.

```sql
-- Derniers signaux avec leur contexte
SELECT s.date_heure, s.signal, s.prix_entree, s.score_confiance,
       ss.score_sentiment, e.categorie, e.titre
FROM signal_trading s
LEFT JOIN sentiment_social ss USING (sentiment_id)
LEFT JOIN evenement_marche e USING (evenement_id)
ORDER BY s.date_heure DESC LIMIT 10;
```

---

## 9. Sentiment et actualités

Ajoutés le 02/11/2026, pour donner du contexte aux signaux.

### Sentiment : l'indice Fear & Greed

- **Source :** https://api.alternative.me/fng/, gratuite et sans clé.
- **Valeur :** de 0 (peur extrême) à 100 (avidité extrême), une par jour, pour tout le marché crypto.
- **Script :** `collectors/insert_sentiment_fear_greed.py`, tâche `collecte_sentiment`.
- Au premier passage, tout l'historique a été chargé (3 193 jours depuis le 01/02/2018). Ensuite, le script ne demande que les 10 derniers jours ; un index unique (`source` + `date_heure`) empêche les doublons.
- Les colonnes `nombre_messages` et `score_engagement` restent vides : l'indice ne les fournit pas.

### Actualités : flux RSS

- **Sources :** flux RSS de CoinDesk et Cointelegraph (25 à 30 articles chacun).
- **Script :** `collectors/insert_evenements_rss.py`, tâche `collecte_evenements`, chaque heure.
- **Catégorie :** la première qui correspond à un mot-clé du titre, dans cet ordre : securite (hack, theft…), regulation (SEC, court…), etf, macro (Fed, inflation…), adoption (stablecoin, tokenization…), entreprise (BlackRock, Coinbase…), marche (price, rally…), sinon autre.
- **impact_score :** variation du BTC sur Binance dans l'heure qui suit la publication, en %. Calculé au passage horaire suivant, quand cette heure est connue.
- Un titre déjà présent n'est jamais réinséré (index unique sur `titre`).
- Les flux RSS ne gardent que les derniers articles : il n'y a pas d'historique avant le 31/10.

---

## 10. Airflow : l'orchestration

### À quoi ça sert

Airflow décide **quand** chaque script s'exécute et **dans quel ordre**, relance ce qui échoue et garde l'historique de chaque exécution. Il ne transforme pas les données lui-même.

### Vocabulaire

| Terme | Signification |
| --- | --- |
| DAG | Un pipeline : un ensemble de tâches et l'ordre dans lequel elles s'enchaînent |
| Tâche | Une étape, ici une commande Python lancée par un `BashOperator` |
| Run | Une exécution du DAG |
| Scheduler | Le processus qui lance les runs à l'heure prévue |

### Le pipeline horaire : `opca_pipeline_horaire_v2`

Lancé chaque heure à **:10** (par exemple 14:10 UTC). Il compte 9 tâches :

```
collecte_binance ─────────┐
collecte_coinbase ────────┼──► calcul_indicateurs ──► regression_xgboost ──┬──► log_previsions_oos
collecte_activite_binance ┘                                                 │
                                                                            ▼
collecte_sentiment ─────────────────────────────────────────────────► generer_signaux
collecte_evenements ────────────────────────────────────────────────►
```

- Les collectes tournent en parallèle.
- `calcul_indicateurs` attend la fin des trois collectes de prix (`trigger_rule="all_done"` : il tourne même si l'une a échoué).
- `generer_signaux` attend XGBoost et les deux sources de contexte, et tourne même si une source de contexte échoue.
- La variable Airflow `opca_v2_write_predictions` active l'écriture des prévisions (`1`) ; sinon les scripts tournent en `--dry-run` (sans rien écrire).

### Le pipeline quotidien : `opca_random_forest_24h`

Lancé chaque nuit à **02:15 UTC** :

```
entrainement_random_forest ──SSH──► lancer_rf.sh (sur la VM) ──docker run──► conteneur opca_rf_v2 ──► prediction_oos
```

Une seule exécution à la fois, une nouvelle tentative après 10 minutes, arrêt forcé au bout de 3 heures.

### Détails techniques

- Airflow 2.9.3, `LocalExecutor` (les tâches tournent dans le scheduler).
- Base de métadonnées séparée (`opca_airflow-airflow-postgres-1`) : on peut redémarrer Airflow sans toucher aux données.
- Les dossiers `collectors/`, `ml/` et `airflow/dags/` de la VM sont montés dans le scheduler (`/opt/airflow/...`). Modifier un fichier sur la VM suffit, sans reconstruire d'image.
- Deux environnements Python : `collector-venv` (collecte) et `ml-venv` (calculs et modèles).
- L'ancien DAG `opca_pipeline_horaire` (v1) est en pause.

### Comment vérifier

Interface : http://51.44.254.88:8081 (compte `admin`).

```bash
S=opca_airflow-airflow-scheduler-1
docker exec $S airflow dags list-runs -d opca_pipeline_horaire_v2 -o plain | head
docker exec $S airflow tasks list opca_pipeline_horaire_v2
```

---

## 11. L'API FastAPI

### À quoi ça sert

L'API est la **porte d'accès aux données** pour les applications. Streamlit ne lit jamais la base directement : il passe par l'API, qui renvoie du JSON.

### Détails techniques

| Élément | Valeur |
| --- | --- |
| Conteneur | `opca_api_v2` (Python 3.11, FastAPI 0.115, Uvicorn) |
| Adresse publique | http://51.44.254.88:8003 |
| Documentation interactive | http://51.44.254.88:8003/docs |
| Code | `~/projet/plateforme/opca-platform/api/main.py` |

**Les 12 routes (toutes en lecture, méthode GET)**

| Groupe | Routes |
| --- | --- |
| Exploitation | `/health`, `/snapshot`, `/platforms`, `/instruments` |
| Marché | `/prices`, `/indicators`, `/activity`, `/correlations` |
| Résultats | `/predictions`, `/signals`, `/sentiment`, `/events` |

- Filtres : `symbole`, `plateforme`, `pas_temps`.
- 500 lignes par défaut, 5 000 au maximum (2 000 pour `/predictions`).
- `/health` exécute `SELECT 1` : 200 si la base répond, 503 sinon.
- Requêtes SQL paramétrées (pas d'injection SQL possible), connexion vérifiée avant usage (`pool_pre_ping`).

```bash
curl -s "http://51.44.254.88:8003/health"
curl -s "http://51.44.254.88:8003/prices?symbole=BTC-USD&plateforme=Binance&limit=3"
curl -s "http://51.44.254.88:8003/signals?limit=5"
```

Limites : pas de filtre par date, et pas encore de route pour `prediction_oos` et son évaluation.

---

## 12. Le tableau de bord Streamlit

### À quoi ça sert

C'est l'écran destiné à l'utilisateur métier : explorer les prix, comparer les séries, voir les prévisions.

### Détails techniques

| Élément | Valeur |
| --- | --- |
| Conteneur | `opca_dashboard_v2`, image `projet_test-dashboard` |
| Adresse | http://51.44.254.88:8503 |
| Code | `~/projet/plateforme/opca-platform/Streamlit/app_streamlit_prix_api.py` |
| Source des données | L'API uniquement (`API_BASE_URL=http://api:8000`) |

**Les 5 onglets**

| Onglet | Contenu |
| --- | --- |
| Vue d'ensemble | Volumes, derniers prix, fraîcheur des données, comparaison en base 100 |
| Prix | Courbes OHLCV, plusieurs séries, statistiques, export CSV |
| Activité de marché | Volumes Binance, nombre de transactions, part des achats |
| Indicateurs techniques | Prix et SMA, RSI, MACD, volatilité |
| Prévisions | Prévisions XGBoost face aux prix observés |

- Cache : 5 minutes pour les séries, 60 s pour le résumé, 1 h pour les listes.
- Périodes proposées : 24 h, 3 jours (par défaut), 7 jours, tout l'historique. Dates en UTC.
- Le code est **figé dans l'image Docker** : modifier le fichier ne suffit pas, il faut reconstruire l'image (`installer_streamlit_onglets.sh`).

Limites : les prévisions Random Forest, l'évaluation `prediction_oos` et les signaux ne sont pas encore affichés.

---

## 13. La supervision : Prometheus et Grafana

### À quoi ça sert

Savoir à tout moment si la plateforme fonctionne : les services répondent-ils, les données sont-elles fraîches, la machine a-t-elle assez de ressources ?

### Deux branches

**Branche infrastructure** : mesurer la machine.

```
VM ──────────► node-exporter ──┐
                               ├──► Prometheus ──► Grafana
Conteneurs ──► cAdvisor ───────┘
```

| Outil | Rôle |
| --- | --- |
| node-exporter | Lit l'état de la VM : CPU, mémoire, disque, réseau |
| cAdvisor | Lit l'état de chaque conteneur : mémoire utilisée par rapport à sa limite, CPU |
| Prometheus | Vient chercher ces mesures **toutes les 30 secondes** et les garde **15 jours** (2 Go maximum) |

**Branche données** : Grafana lit directement `opca_db` avec le compte `grafana_ro`, qui ne peut rien modifier.

### Grafana

- Adresse : http://51.44.254.88:3001
- Tableaux : un tableau métier (fraîcheur, volumes, prix, indicateurs) et « Infrastructure VM OPCA » (VM et conteneurs).
- **5 alertes** :

| Alerte | Seuil |
| --- | --- |
| CPU de la VM | > 85 % pendant 10 min |
| Mémoire de la VM | > 90 % pendant 5 min |
| Disque | > 85 % pendant 15 min |
| Mémoire d'un conteneur | > 90 % de sa limite pendant 10 min |
| Source de mesures muette | pendant 5 min |

- Configuration par fichiers (*provisioning*), montés en lecture seule : on ne modifie pas les tableaux depuis l'interface.

### Détails techniques

- Prometheus n'écoute que sur `172.17.0.1:9090` : il n'est pas accessible depuis internet.
- node-exporter et cAdvisor ne publient aucun port.
- Limite : les alertes s'affichent dans Grafana, mais ne sont envoyées ni par e-mail ni sur Slack.

```bash
# Les 3 cibles doivent être "up"
curl -s http://172.17.0.1:9090/api/v1/targets | python3 -c \
  "import sys,json;[print(t['labels']['job'],t['health']) for t in json.load(sys.stdin)['data']['activeTargets']]"
```

---

## 14. Contrôles, rapports et sauvegardes

Ces tâches tournent sur la VM elle-même (planifiées par `cron`), en dehors de Docker et d'Airflow.

### Le contrôle complet : `check_opca.sh`

- Emplacement : `~/projet/v2/checks/check_opca.sh`, lancé **chaque heure à :25**.
- **31 contrôles** : conteneurs actifs, runs Airflow, services HTTP, fraîcheur et volume des bougies, absence de doublons, comptes connectés à la base, mémoire, disque, âge de la sauvegarde.
- Résultat : `OK`, `WARN` (à surveiller) ou `FAIL` (problème).
- Seuils de fraîcheur : WARN à 75 min, FAIL à 130 min. Bougies sur 24 h : WARN sous 270, FAIL sous 240.

```bash
cd ~/projet/v2 && bash checks/check_opca.sh          # attendu : 31 OK, 0 WARN, 0 FAIL
```

### Les rapports quotidiens

- Script : `~/projet/rapport_quotidien/rapport_quotidien.py`, en lecture seule.
- Deux fois par jour, à **07:00** et **22:30 heure de Paris**. La VM est en UTC : chaque ligne cron est doublée et vérifie l'heure de Paris, pour suivre les changements d'heure.
- Contenu : résumé des contrôles, ressources, conteneurs, runs Airflow, fraîcheur des données, résultats des modèles, dernières prévisions Random Forest.
- Fichiers : `rapport_AAAA-MM-JJ_matin.html` et `.txt`, idem pour le soir, plus `dernier_rapport.*`. Conservés 60 jours.

```bash
cat ~/projet/rapport_quotidien/dernier_rapport.txt
```

### Les sauvegardes

- Script : `~/projet/v2/checks/backup_v2.sh`, chaque nuit à **03:17 UTC**.
- `pg_dump` au format custom (`-Fc`), empreinte SHA-256, conservation 7 jours, dans `~/projet/backups/opca_v2`.
- Avant chaque modification de la plateforme, une sauvegarde dédiée est faite dans `~/projet/backups/<nom>_<date>` (dump complet + fichiers modifiés), et le script d'installation contient les commandes de retour arrière.

```bash
# Restaurer en dernier recours (écrase la base actuelle)
docker exec -i opca_pg_v2 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < <fichier.dump>
```

Limite : aucun test de restauration régulier n'est fait.

---

## 15. Accès et sécurité

### Services publics (navigateur, sans tunnel)

| Service | Adresse | Compte |
| --- | --- | --- |
| Streamlit | http://51.44.254.88:8503 | aucun |
| Grafana | http://51.44.254.88:3001 | admin |
| API | http://51.44.254.88:8003/docs | aucun |
| Airflow | http://51.44.254.88:8081 | admin |

Ces services sont en **HTTP non chiffré** : éviter de s'y connecter depuis un Wi-Fi public.

### Services internes (tunnel SSH obligatoire)

La base, Adminer et Prometheus ne sont **jamais** ouverts sur internet. Pour y accéder, on crée un **tunnel SSH** : la connexion SSH transporte un port de la VM jusqu'à ton PC.

```bash
# Adminer, puis http://localhost:8085
ssh -i ~/Downloads/project.pem -L 8085:127.0.0.1:8085 ubuntu@51.44.254.88

# PostgreSQL pour DBeaver ou psql, puis localhost:5433
ssh -i ~/Downloads/project.pem -L 5433:172.17.0.1:5433 ubuntu@51.44.254.88

# Prometheus, puis http://localhost:9090
ssh -i ~/Downloads/project.pem -L 9090:172.17.0.1:9090 ubuntu@51.44.254.88
```

La fenêtre du tunnel doit rester ouverte. Pour un tunnel permanent sous Windows : `installer_tunnel.ps1` (dossier `C:\Users\<toi>\tunnel_opca`), qui l'ouvre à chaque ouverture de session et le relance s'il tombe.

### La clé SSH

Le fichier `project.pem` est la seule façon d'entrer sur la VM. Sous Windows, il faut le protéger une fois, sinon SSH le refuse :

```powershell
icacls "$env:USERPROFILE\Downloads\project.pem" /inheritance:r
icacls "$env:USERPROFILE\Downloads\project.pem" /grant:r "$($env:USERNAME):(R)"
```

### Les identifiants

Tous les mots de passe sont dans `~/projet/ACCES_EQUIPE.md` sur la VM (lisible par `ubuntu` uniquement). **Ils ne doivent jamais être copiés dans un dépôt, un document ou une conversation.**

```bash
cat ~/projet/ACCES_EQUIPE.md
```

| Compte de la base | Usage | Droits |
| --- | --- | --- |
| `opca_admin` | Les humains (Adminer, DBeaver) | Administrateur |
| `opca_app` | L'API et Airflow | Administrateur |
| `grafana_ro` | Grafana | Lecture seule |

### Page d'accès

La page « Accès VM OPCA » regroupe ces liens et commandes, avec des boutons pour les copier : `C:\Users\<toi>\acces_vm_opca\index.html`.

---

## 16. Commandes utiles

Toutes à lancer sur la VM, après `ssh -i ~/Downloads/project.pem ubuntu@51.44.254.88`.

| Je veux… | Commande |
| --- | --- |
| Savoir si tout va bien | `cd ~/projet/v2 && bash checks/check_opca.sh` |
| Lire le dernier rapport | `cat ~/projet/rapport_quotidien/dernier_rapport.txt` |
| Voir les conteneurs | `docker ps --format "{{.Names}} \| {{.Status}}"` |
| Voir la mémoire des conteneurs | `docker stats --no-stream` |
| Voir les derniers runs | `docker exec opca_airflow-airflow-scheduler-1 airflow dags list-runs -d opca_pipeline_horaire_v2 -o plain \| head` |
| Ouvrir la base | `docker exec -it opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'` |
| Lire le journal d'une tâche | `ls ~/projet/plateforme/opca-platform/airflow/logs/dag_id=opca_pipeline_horaire_v2/` |
| Voir les sauvegardes | `ls -lt ~/projet/backups/opca_v2 \| head` |
| Voir les identifiants | `cat ~/projet/ACCES_EQUIPE.md` |

### Règles d'exploitation

- **Ne rien modifier entre hh:08 et hh:15** : le pipeline horaire tourne à hh:10.
- **Ne jamais lancer `airflow tasks test`** dans le scheduler : l'entraînement dépasse sa limite de mémoire et laisse un run bloquant.
- **Sauvegarder avant de modifier** : dump de la base et copie des fichiers touchés, avec les commandes de retour arrière.
- Les connexions SSH longues sont parfois coupées : préférer plusieurs commandes courtes.

---

## 17. Limites connues

| Domaine | Limite |
| --- | --- |
| Modèles | Aucun ne bat la prévision naïve ; le Random Forest a trop peu de prévisions évaluées |
| Données | `prediction_modele` n'a ni `instrument_id` ni nom de modèle : l'étiquette `horizon_prediction` compense |
| Données | `sentiment_social` et `evenement_marche` n'ont pas d'`instrument_id` : le contexte vaut pour tout le marché |
| Données | 999 doublons anciens (juin–août) dans `prediction_modele`, 3 421 indicateurs orphelins de l'ancienne version, un instrument BTC-USD en double (id 4, inutilisé) |
| Données | USD (Coinbase) et USDT (Binance) sont traités comme équivalents, sans conversion |
| API | Pas de filtre par date ; pas de route pour `prediction_oos` |
| Streamlit | Random Forest, évaluation et signaux pas encore affichés |
| Supervision | Alertes non envoyées (ni e-mail ni Slack) ; pas de test de restauration régulier |
| Random Forest | Durée d'entraînement en hausse d'environ 1 min par nuit (65 min le 02/11) |
| Sécurité | Grafana, API, Airflow et Streamlit ouverts sur internet en HTTP |
| Architecture | Une seule VM : si elle tombe, tout tombe |

---

## 18. Glossaire

| Terme | Définition |
| --- | --- |
| AUC | Mesure de la qualité d'un classifieur, de 0,5 (hasard) à 1 (parfait) |
| Bougie (OHLCV) | Résumé du marché sur un intervalle : ouverture, haut, bas, clôture, volume |
| Conteneur | Environnement isolé qui fait tourner un programme et ses dépendances |
| Cron | Planificateur de tâches de Linux |
| DAG | Pipeline Airflow : des tâches et leur ordre d'exécution |
| `--dry-run` | Mode test d'un script : il calcule mais n'écrit rien |
| Idempotent | Relancer le script donne le même résultat, sans doublon |
| Incrémental | Ne traite que les nouvelles données depuis le dernier passage |
| MAE | Erreur absolue moyenne : en moyenne, de combien on se trompe |
| OOS (*out-of-sample*) | Prévision faite sur des données que le modèle n'a jamais vues |
| Prévision naïve | « Le prix futur sera le prix actuel » ; la référence à battre |
| Régression / classification | Prédire un nombre (un prix) / prédire une catégorie (hausse ou baisse) |
| Stop-loss / take-profit | Prix auxquels on couperait la perte / prendrait le gain |
| Tunnel SSH | Connexion SSH qui transporte un port de la VM jusqu'à son PC |
| UTC | Heure universelle ; Paris = UTC + 1 en hiver, UTC + 2 en été |
| Upsert | Insérer une ligne, ou la mettre à jour si elle existe déjà |
