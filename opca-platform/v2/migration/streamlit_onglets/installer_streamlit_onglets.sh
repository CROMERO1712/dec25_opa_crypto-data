#!/usr/bin/env bash
# Met en ligne la nouvelle application Streamlit à onglets (port 8503, conteneur opca_dashboard_v2).
#   1. sauvegarde l'ancienne application et garde l'ancienne image (étiquette :avant_onglets) ;
#   2. reconstruit l'image projet_test-dashboard avec la nouvelle application ;
#   3. recrée UNIQUEMENT le conteneur opca_dashboard_v2 (coupure d'environ 10 s du Streamlit).
# L'API, la base, Airflow et Grafana ne sont pas touchés.
#
# Usage, sur la VM :  bash ~/projet/script_migration/streamlit_onglets/installer_streamlit_onglets.sh
# Retour arrière   :  voir la fin de ce fichier.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
CTX=/home/ubuntu/projet/plateforme/opca-platform
COMPOSE=/home/ubuntu/projet/v2/compose/docker-compose.yaml
IMAGE=projet_test-dashboard
JOURNAL="$SRC/installation_$(date +%Y%m%dT%H%M%S).log"
exec > >(tee -a "$JOURNAL") 2>&1

ok() { echo "[OK]   $*"; }
ko() { echo "[ÉCHEC] $*"; exit 1; }

echo "===== Streamlit à onglets : $(date '+%F %T') ====="

# 1. Contrôles
[ -f "$CTX/Dockerfile.dashboard" ] || ko "$CTX/Dockerfile.dashboard introuvable"
[ -f "$COMPOSE" ] || ko "$COMPOSE introuvable"
docker ps --format '{{.Names}}' | grep -qx opca_dashboard_v2 || ko "le conteneur opca_dashboard_v2 ne tourne pas"
(cd "$SRC" && sha256sum -c SHA256SUMS --quiet) || ko "fichiers modifiés depuis la livraison (SHA256SUMS)"
python3 -m py_compile "$SRC/app_streamlit_prix_api.py" || ko "erreur de syntaxe dans la nouvelle application"
ok "contrôles préalables"

# 2. Sauvegardes : ancienne application + ancienne image
SAUV=/home/ubuntu/projet/v2/backups/streamlit_avant_onglets_$(date +%Y%m%dT%H%M%S)
mkdir -p "$SAUV"
cp -a "$CTX/Streamlit/app_streamlit_prix_api.py" "$SAUV/"
docker exec opca_dashboard_v2 cat /app/app.py > "$SAUV/app_dans_le_conteneur.py"
docker image inspect "$IMAGE:avant_onglets" >/dev/null 2>&1 || docker tag "$IMAGE:latest" "$IMAGE:avant_onglets"
ok "ancienne application sauvegardée dans $SAUV, ancienne image gardée sous $IMAGE:avant_onglets"

# 3. Construction de la nouvelle image
install -m 644 "$SRC/app_streamlit_prix_api.py" "$CTX/Streamlit/app_streamlit_prix_api.py"
docker build -q -f "$CTX/Dockerfile.dashboard" -t "$IMAGE:latest" "$CTX" >/dev/null || ko "construction de l'image"
ok "image $IMAGE:latest reconstruite"

# 4. Remplacement du seul conteneur Streamlit
docker compose -f "$COMPOSE" up -d --no-deps dashboard
for i in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8503/_stcore/health 2>/dev/null | grep -q ok && break
  sleep 2
done
curl -fsS http://127.0.0.1:8503/_stcore/health | grep -q ok || ko "Streamlit ne répond pas (voir : docker logs opca_dashboard_v2)"
ok "Streamlit répond sur le port 8503"
if docker logs --since 1m opca_dashboard_v2 2>&1 | grep -iE "error|traceback" | head -5 | grep -q .; then
  echo "[WARN] erreurs dans les journaux du Streamlit :"; docker logs --since 1m opca_dashboard_v2 2>&1 | tail -20
fi
docker stats --no-stream --format "{{.Name}} {{.MemUsage}}" opca_dashboard_v2
echo
echo "Application : http://51.44.254.88:8503  (5 onglets : Vue d'ensemble, Prix, Activité, Indicateurs, Prévisions)"
echo "Journal : $JOURNAL"

# --- Retour arrière (à copier-coller si besoin) ---------------------------------------------------
# docker tag projet_test-dashboard:avant_onglets projet_test-dashboard:latest
# docker compose -f ~/projet/v2/compose/docker-compose.yaml up -d --no-deps dashboard
# cp ~/projet/v2/backups/streamlit_avant_onglets_*/app_streamlit_prix_api.py \
#    ~/projet/plateforme/opca-platform/Streamlit/app_streamlit_prix_api.py
