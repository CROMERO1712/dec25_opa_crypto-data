#!/usr/bin/env bash
# Installe la supervision de l'infrastructure de la VM OPCA dans Grafana.
#   - Prometheus + node-exporter (VM) + cAdvisor (conteneurs), projet compose « opca_v2_monitoring »
#   - source de données « Prometheus infra », tableau « Infrastructure VM OPCA », 5 alertes
# Rien n'est exposé sur internet (écoute sur 172.17.0.1). Aucune donnée existante n'est modifiée.
#
# Usage, sur la VM :  bash ~/projet/script_migration/monitoring/installer_monitoring.sh
# Retour arrière   :  voir la fin de ce fichier.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
V2=/home/ubuntu/projet/v2
JOURNAL="$SRC/installation_$(date +%Y%m%dT%H%M%S).log"
exec > >(tee -a "$JOURNAL") 2>&1

ok()   { echo "[OK]   $*"; }
info() { echo "[..]   $*"; }
ko()   { echo "[ÉCHEC] $*"; exit 1; }

echo "===== Supervision de l'infrastructure : $(date '+%F %T') ====="

# 1. Contrôles avant toute action
[ -d "$V2/grafana/provisioning" ] || ko "dossier $V2/grafana/provisioning introuvable"
docker ps --format '{{.Names}}' | grep -qx opca_grafana_v2 || ko "le conteneur opca_grafana_v2 ne tourne pas"
for p in 9090; do
  if ss -ltn | awk '{print $4}' | grep -qE "[:.]$p\$"; then ko "le port $p est déjà utilisé"; fi
done
DISPO=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
[ "$DISPO" -gt 1200 ] || ko "seulement $DISPO Mo de mémoire disponible (il faut au moins 1,2 Go)"
ok "contrôles préalables (mémoire disponible : $DISPO Mo, port 9090 libre)"

# 2. Sauvegarde de la configuration Grafana actuelle
SAUV="$V2/grafana/sauvegarde_avant_monitoring_$(date +%Y%m%dT%H%M%S)"
mkdir -p "$SAUV" && cp -a "$V2/grafana/provisioning" "$V2/grafana/dashboards" "$SAUV/"
ok "configuration Grafana sauvegardée dans $SAUV"

# 3. Copie des fichiers
mkdir -p "$V2/monitoring" "$V2/grafana/provisioning/alerting"
install -m 644 "$SRC/monitoring/docker-compose.monitoring.yaml" "$V2/monitoring/"
install -m 644 "$SRC/monitoring/prometheus.yml" "$V2/monitoring/"
install -m 644 "$SRC/grafana/provisioning/datasources/prometheus.yaml" "$V2/grafana/provisioning/datasources/"
install -m 644 "$SRC/grafana/provisioning/alerting/infra.yaml" "$V2/grafana/provisioning/alerting/"
install -m 644 "$SRC/grafana/dashboards/infra.json" "$V2/grafana/dashboards/"
ok "fichiers copiés (monitoring/, source de données, alertes, tableau)"

# 4. Démarrage de Prometheus, node-exporter et cAdvisor
docker compose -f "$V2/monitoring/docker-compose.monitoring.yaml" up -d
info "attente des premières mesures (45 s)…"
sleep 45
CIBLES=$(curl -fsS http://172.17.0.1:9090/api/v1/targets 2>/dev/null || true)
for job in vm conteneurs prometheus; do
  if echo "$CIBLES" | python3 -c "import sys,json; d=json.load(sys.stdin); s=[t['health'] for t in d['data']['activeTargets'] if t['labels']['job']=='$job']; sys.exit(0 if s and all(h=='up' for h in s) else 1)"; then
    ok "Prometheus reçoit les mesures « $job »"
  else
    echo "[WARN] Prometheus ne reçoit pas encore « $job » (voir : docker logs opca_prometheus)"
  fi
done

# 5. Grafana relit sa configuration (source de données + alertes) : redémarrage de Grafana seul
docker restart opca_grafana_v2 >/dev/null
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:3001/api/health 2>/dev/null | grep -q '"database": *"ok"' && break
  sleep 2
done
curl -fsS http://127.0.0.1:3001/api/health | grep -q ok && ok "Grafana redémarré et en bonne santé" || ko "Grafana ne répond pas"
if docker logs --since 2m opca_grafana_v2 2>&1 | grep -iE "level=error.*(provision|alert|datasource)" | head -5 | grep -q .; then
  echo "[WARN] erreurs de provisioning dans Grafana :"
  docker logs --since 2m opca_grafana_v2 2>&1 | grep -iE "level=error.*(provision|alert|datasource)" | head -5
else
  ok "source de données, tableau et alertes chargés sans erreur"
fi

# 6. Résumé
echo
docker stats --no-stream --format "{{.Name}} {{.MemUsage}}" opca_prometheus opca_node_exporter opca_cadvisor
echo
echo "Tableau : Grafana (port 3001) > Dashboards > OPCA > « Infrastructure VM OPCA »"
echo "Alertes : Grafana > Alerting > Alert rules > dossier OPCA, groupe « infrastructure »"
echo "Journal de cette installation : $JOURNAL"

# --- Retour arrière (à copier-coller si besoin) ---------------------------------------------------
# docker compose -f ~/projet/v2/monitoring/docker-compose.monitoring.yaml down        # garde les mesures
# rm ~/projet/v2/grafana/provisioning/datasources/prometheus.yaml \
#    ~/projet/v2/grafana/provisioning/alerting/infra.yaml ~/projet/v2/grafana/dashboards/infra.json
# docker restart opca_grafana_v2
