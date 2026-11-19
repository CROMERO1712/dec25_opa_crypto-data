#!/usr/bin/env bash
# Désactive l'ancienne base dst_db (pg_container) et pgAdmin, relancés le 23/10 par un
# « docker compose up -d » dans ~/projet. Rien n'est supprimé :
#   1. sauvegarde : fichier compose + dump complet de dst_db (gzip, empreinte SHA-256) ;
#   2. arrêt des deux conteneurs (conservés, volumes intacts, sans redémarrage automatique) ;
#   3. ~/projet/docker-compose.yaml renommé en docker-compose.yaml.desactive.
# Usage, sur la VM : bash ~/projet/script_migration/desactiver_ancienne_bdd.sh
# Retour arrière : voir la fin de ce fichier.
set -euo pipefail

P=/home/ubuntu/projet
SAUV=$P/backups/ancienne_bdd_$(date +%Y%m%dT%H%M%S)
ok() { echo "[OK]   $*"; }
ko() { echo "[ÉCHEC] $*"; exit 1; }

echo "===== Désactivation de l'ancienne base : $(date '+%F %T') ====="
[ -f "$P/docker-compose.yaml" ] || ko "$P/docker-compose.yaml introuvable (déjà désactivé ?)"
grep -q "pg_container" "$P/docker-compose.yaml" || ko "ce compose ne décrit pas pg_container : arrêt par prudence"

# 1. Sauvegardes
mkdir -p "$SAUV" && chmod 700 "$SAUV"
cp -a "$P/docker-compose.yaml" "$SAUV/"
if docker ps --format '{{.Names}}' | grep -qx pg_container; then
  docker exec pg_container sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner' | gzip > "$SAUV/dst_db.sql.gz"
  [ "$(gzip -cd "$SAUV/dst_db.sql.gz" | head -c 100000 | grep -c 'PostgreSQL database dump')" -ge 1 ] || ko "dump vide ou invalide"
  ok "dump de dst_db : $(du -h "$SAUV/dst_db.sql.gz" | cut -f1)"
else
  echo "[INFO] pg_container ne tourne pas : pas de dump (le volume reste intact)"
fi
for c in pg_container pgadmin4_container; do
  docker inspect "$c" --format '{{.Name}} image={{.Config.Image}} volumes={{range .Mounts}}{{.Name}}:{{.Destination}} {{end}}' 2>/dev/null
done > "$SAUV/conteneurs_et_volumes.txt"
(cd "$SAUV" && sha256sum * > SHA256SUMS && chmod 600 *)
ok "sauvegarde dans $SAUV"

# 2. Arrêt des conteneurs (conservés, sans redémarrage automatique)
for c in pg_container pgadmin4_container; do
  if docker inspect "$c" >/dev/null 2>&1; then
    docker update --restart=no "$c" >/dev/null
    docker stop "$c" >/dev/null
    ok "$c arrêté (conteneur et volume conservés)"
  fi
done

# 3. Compose désactivé
mv "$P/docker-compose.yaml" "$P/docker-compose.yaml.desactive"
ok "$P/docker-compose.yaml renommé en docker-compose.yaml.desactive"

# Contrôles
echo
docker ps --format '{{.Names}}' | grep -E '^(pg_container|pgadmin4_container)$' && ko "un conteneur tourne encore" || ok "plus aucun des deux conteneurs ne tourne"
ss -ltn | grep -E ':(5432|5050)\s' && echo "[WARN] un port 5432/5050 écoute encore" || ok "ports 5432 et 5050 fermés"
docker ps --format '{{.Names}}' | grep -qx opca_pg_v2 && ok "la base en service opca_db (opca_pg_v2) tourne toujours"
echo "Sauvegarde : $SAUV"

# --- Retour arrière -------------------------------------------------------------------------------
# mv ~/projet/docker-compose.yaml.desactive ~/projet/docker-compose.yaml
# docker start pg_container pgadmin4_container
