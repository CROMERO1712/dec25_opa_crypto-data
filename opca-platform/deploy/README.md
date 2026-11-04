# Installer la plateforme OPCA sur une nouvelle VM

`installer_opca.py` reconstruit toute la plateforme sur une VM Ubuntu neuve, à l'identique de la production :
- base `opca_db` ;
- API, Streamlit et Adminer ;
- Airflow, avec ses DAG, ses variables et la clé SSH du Random Forest ;
- Prometheus et Grafana ;
- les tâches cron : contrôles, sauvegarde et rapports.

## Prérequis

- **Système** : Ubuntu 22.04 ou 24.04.
- **Ressources** : 2 processeurs, 8 Go de mémoire, 30 Go de disque.
- **Utilisateur** : un compte normal avec `sudo`. De préférence `ubuntu`, comme en production ; sinon le script adapte les chemins.
- **Ports** à ouvrir dans le pare-feu ou le groupe de sécurité : 22, 8003, 8503, 8081 et 3001. Les ports 5432 et 5433 restent fermés.

## Installation

```bash
curl -fsSLO https://raw.githubusercontent.com/CROMERO1712/dec25_opa_crypto-data/vm-production-20261104/opca-platform/deploy/installer_opca.py
python3 installer_opca.py --simulation           # voir ce qui sera fait
python3 installer_opca.py --installer-docker     # installation (environ 20 à 30 min, surtout les images)
```

Si Docker vient d'être installé, il faut se déconnecter, se reconnecter, puis relancer la même commande.

Pour retrouver les données de l'ancienne VM, on peut restaurer une sauvegarde nocturne. Elle se trouve dans `~/projet/backups/opca_v2` sur l'ancienne VM. Le fichier `.sha256` à côté est vérifié automatiquement.

```bash
python3 installer_opca.py --dump opca_db_AAAAMMJJTHHMMSSZ.dump
```

## Les 11 étapes

On peut les relancer seules, par exemple avec `--etapes airflow,cron`.

| Étape | Ce qu'elle fait |
| --- | --- |
| `verifier` | Contrôle le système, Docker, `docker0` (172.17.0.1), la mémoire, le disque, les ports et SSH. |
| `code` | Clone le dépôt dans `~/projet/plateforme` et crée le lien `~/projet/v2`. |
| `secrets` | Crée les fichiers `.env` avec des mots de passe aléatoires (droits 600) et le fichier `~/projet/ACCES_EQUIPE.md`. |
| `images` | Construit les images de l'API, de Streamlit, du ML et d'Airflow. |
| `base` | Lance `opca_pg_v2` et crée les rôles `grafana_ro` et `opca_admin`. Ensuite, soit il crée le schéma et les données de référence, soit il restaure la sauvegarde donnée. |
| `adminer` | Lance Adminer, accessible uniquement sur 127.0.0.1:8085 (par tunnel SSH). |
| `api` | Lance l'API (:8003) et Streamlit (:8503). |
| `airflow` | Lance Airflow (:8081), crée la clé SSH du scheduler vers l'hôte et les variables `opca_v2_*`. Il met le DAG v1 en pause et active les DAG v2 et Random Forest. |
| `supervision` | Lance Prometheus, node-exporter, cAdvisor et Grafana (:3001). |
| `cron` | Ajoute les 4 lignes cron et crée les dossiers des sauvegardes et des rapports. |
| `controle` | Lance `check_opca.sh` et affiche les adresses. |

## Sécurité

- **Rien n'est écrasé** : un fichier, un conteneur, un rôle ou une variable déjà présent est conservé tel quel. On peut relancer le script sans risque.
- **Les mots de passe ne sont jamais affichés** ni passés sur la ligne de commande. Ils sont transmis par l'entrée standard.
- **La base n'est pas exposée** : elle écoute seulement sur 172.17.0.1, l'adresse interne de Docker, jamais sur internet.

Juste après l'installation, certains contrôles de fraîcheur des données restent en échec. C'est normal tant que les premières collectes horaires n'ont pas tourné.

## Ce qui ne se reconstruit pas

- **L'historique d'Airflow** (exécutions passées et journaux) n'est pas repris.
- **Les données** ne sont reprises qu'avec `--dump`. Sans sauvegarde, les prix se recollectent à partir de maintenant, mais l'historique des prévisions (`prediction_oos`) est perdu.
- **La base au moment de l'installation** : les fichiers `schema_opca_db.sql` et `donnees_reference.sql` ont été exportés de la production le 04/11/2026. Il faut les exporter à nouveau si le schéma change.
