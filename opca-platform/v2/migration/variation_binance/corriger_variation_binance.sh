#!/usr/bin/env bash
# Remplit serie_prix.variation_prix_pct pour les séries Binance (plateforme 1), vide depuis le 03/09.
# Même formule que le collecteur Coinbase : (clôture - ouverture) / ouverture * 100, arrondi à 4 décimales.
#   1. sauvegarde : dump de serie_prix + copie du collecteur insert_binance.py ;
#   2. collecteur Binance : écrit désormais variation_prix_pct (insert et mise à jour) ;
#   3. historique : UPDATE des lignes Binance dont la variation est vide.
# Usage, sur la VM : bash ~/projet/script_migration/variation_binance/corriger_variation_binance.sh
# Retour arrière : voir la fin de ce fichier.
set -euo pipefail

P=/home/ubuntu/projet
COLL=$P/plateforme/opca-platform/collectors/insert_binance.py
SAUV=$P/backups/variation_binance_$(date +%Y%m%dT%H%M%S)
PSQL() { docker exec -i opca_pg_v2 sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At'; }
ok() { echo "[OK]   $*"; }
ko() { echo "[ÉCHEC] $*"; exit 1; }

echo "===== Correction variation_prix_pct Binance : $(date '+%F %T') ====="
M=$(date +%M); [ "$M" -ge 8 ] && [ "$M" -le 12 ] && ko "le pipeline horaire tourne à hh:10, relancer après hh:12"

# 1. Sauvegardes
mkdir -p "$SAUV" && chmod 700 "$SAUV"
cp -a "$COLL" "$SAUV/"
docker exec opca_pg_v2 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t serie_prix --no-owner' | gzip > "$SAUV/serie_prix.sql.gz"
[ "$(gzip -cd "$SAUV/serie_prix.sql.gz" | grep -c 'PostgreSQL database dump')" -ge 1 ] || ko "dump vide ou invalide"
(cd "$SAUV" && sha256sum * > SHA256SUMS && chmod 600 *)
ok "sauvegarde dans $SAUV ($(du -h "$SAUV/serie_prix.sql.gz" | cut -f1))"

# 2. Collecteur
if grep -q "variation_prix_pct" "$COLL"; then
  ok "collecteur déjà corrigé"
else
  python3 - "$COLL" <<'PY'
import sys
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
rempl = [
    ("                prix_bas, prix_fermeture, volume, instrument_id, plateforme_id\n"
     "            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
     "                prix_bas, prix_fermeture, volume, variation_prix_pct, instrument_id, plateforme_id\n"
     "            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"),
    ("                volume = EXCLUDED.volume;",
     "                volume = EXCLUDED.volume,\n"
     "                variation_prix_pct = EXCLUDED.variation_prix_pct;"),
    ("        for kline in klines:\n",
     "        for kline in klines:\n"
     "            ouverture, fermeture = float(kline[1]), float(kline[4])\n"
     "            # meme calcul que import_bougie_coinbase.py\n"
     "            variation = (fermeture - ouverture) / ouverture * 100 if ouverture else None\n"),
    ("                float(kline[5]),                        # volume\n",
     "                float(kline[5]),                        # volume\n"
     "                variation,                              # variation_prix_pct\n"),
]
for avant, apres in rempl:
    if s.count(avant) != 1:
        sys.exit(f"motif introuvable ou multiple : {avant[:60]!r}")
    s = s.replace(avant, apres)
open(f, "w", encoding="utf-8").write(s)
PY
  python3 -m py_compile "$COLL" && ok "collecteur insert_binance.py corrigé (syntaxe vérifiée)"
fi

# 3. Historique
AVANT=$(echo "select count(*) from serie_prix where plateforme_id = 1 and variation_prix_pct is null;" | PSQL)
echo "update serie_prix
      set variation_prix_pct = round((prix_fermeture - prix_ouverture) / prix_ouverture * 100, 4)
      where plateforme_id = 1 and variation_prix_pct is null and prix_ouverture <> 0;" | PSQL >/dev/null
APRES=$(echo "select count(*) from serie_prix where plateforme_id = 1 and variation_prix_pct is null;" | PSQL)
ok "historique : $AVANT lignes vides avant, $APRES après"

# Contrôles
echo
echo "select plateforme_id, instrument_id, count(*), count(variation_prix_pct) from serie_prix group by 1, 2 order by 1, 2;" | PSQL \
  | awk -F'|' '{printf "       plateforme %s / instrument %s : %s / %s remplies\n", $1, $2, $4, $3}'
echo "Sauvegarde : $SAUV"
echo "La prochaine collecte (hh:10) écrira la variation pour les nouvelles bougies Binance."

# --- Retour arrière -------------------------------------------------------------------------------
# cp <SAUV>/insert_binance.py ~/projet/plateforme/opca-platform/collectors/insert_binance.py
# echo "update serie_prix set variation_prix_pct = null where plateforme_id = 1;" \
#   | docker exec -i opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
