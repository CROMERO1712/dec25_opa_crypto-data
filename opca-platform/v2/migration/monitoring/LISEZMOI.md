# Supervision de l'infrastructure (Grafana)

Ajoute à Grafana (port 3001) un tableau **« Infrastructure VM OPCA »** et **5 alertes** sur les ressources de la VM.

## Ce qui est installé

| Composant | Rôle | Mémoire |
|---|---|---|
| Prometheus v2.54.1 | stocke les mesures toutes les 30 s, 15 jours (2 Go maximum) | limite 300 Mo, ~30 Mo en pratique |
| node-exporter v1.8.2 | mesure la VM : CPU, mémoire, disque, charge | limite 64 Mo, ~7 Mo |
| cAdvisor v0.60.5 | mesure chaque conteneur : CPU, mémoire et sa limite, réseau | limite 200 Mo, ~15 Mo |

Rien n'est exposé sur internet. Les trois services se parlent sur un réseau Docker privé. Seul Prometheus est publié, sur `172.17.0.1:9090`, l'adresse de passerelle Docker que la base `opca_db` utilise déjà (`172.17.0.1:5433`).

## Le tableau

- **Vue d'ensemble** : CPU, mémoire, disque, charge par cœur, conteneurs actifs, temps depuis le dernier redémarrage. Chaque indicateur passe au vert, à l'orange ou au rouge selon son seuil.
- **Historique de la VM** : CPU, mémoire, disque et réseau des conteneurs, avec le seuil d'alerte en pointillés.
- **Conteneurs** :
  - un tableau avec la mémoire, la limite, la part de la limite (jauge) et le CPU de chaque conteneur ;
  - les courbes des 8 conteneurs qui consomment le plus.

## Les alertes

Elles sont dans Grafana, menu Alerting, dossier OPCA.

| Alerte | Seuil | Durée |
|---|---|---|
| CPU de la VM | > 85 % | 10 min |
| Mémoire de la VM | > 90 % (critique : la VM n'a pas de swap) | 5 min |
| Disque / | > 85 % | 15 min |
| Conteneur proche de sa limite mémoire | > 90 % de sa limite | 10 min |
| Supervision muette | une source de mesures ne répond plus | 5 min |

Aucun envoi n'est configuré pour l'instant : les alertes s'affichent dans Grafana. Pour recevoir un message Slack ou un e-mail, ajouter un point de contact dans Alerting > Contact points.

## Installation

Sur la VM :

```bash
bash ~/projet/script_migration/monitoring/installer_monitoring.sh
```

Le script :

1. vérifie la mémoire, le port 9090 et Grafana ;
2. sauvegarde la configuration Grafana ;
3. copie les fichiers ;
4. démarre les 3 services ;
5. contrôle que les mesures arrivent ;
6. redémarre **Grafana seul**, ce qui coupe Grafana une vingtaine de secondes.

Il laisse un journal à côté de lui. Les autres services (API, Streamlit, Airflow, base) ne sont pas touchés.

## Retour arrière

Les commandes sont à la fin de `installer_monitoring.sh`. On arrête les 3 services, on retire 3 fichiers et on redémarre Grafana.

## Fichiers

```
monitoring/docker-compose.monitoring.yaml   les 3 services (projet compose « opca_v2_monitoring »)
monitoring/prometheus.yml                   ce que Prometheus relève
grafana/provisioning/datasources/prometheus.yaml   source de données « Prometheus infra »
grafana/provisioning/alerting/infra.yaml    les 5 alertes
grafana/dashboards/infra.json               le tableau (généré par generer_tableau_infra.py)
installer_monitoring.sh                     installation et contrôles
```

Testé le 25/10/2026 sur une VM Docker 29 avant livraison : les mesures arrivent, et le tableau et les 5 alertes se chargent sans erreur.
