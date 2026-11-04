#!/usr/bin/env bash
# Exporte la plateforme OPCA v2 dans UNE archive téléchargeable (sans secrets, sans .git).
# Lecture seule sur la plateforme : n'écrit que dans ~/projet/export.
set -euo pipefail
H="${OPCA_HOME:-$HOME}"
OUT="${OPCA_EXPORT_DIR:-$H/projet/export}"
STAGE="$OUT/opca_bundle"
rm -rf "$OUT"; mkdir -p "$STAGE/opca_v2"; chmod 700 "$OUT"
EXCL=(--exclude=.git --exclude=__pycache__ --exclude='*.pyc' --exclude='*.env' --exclude='.env*' --exclude='*.pem' --exclude='*.key' --exclude='*.joblib' --exclude=logs --exclude='*.log' --exclude='*.bak')

echo "== 1. Code de la plateforme"
if [ -d "$H/projet/plateforme/opca-platform" ]; then
  mkdir -p "$STAGE/opca-platform"
  tar -C "$H/projet/plateforme/opca-platform" "${EXCL[@]}" -cf - . | tar -C "$STAGE/opca-platform" -xf -
else echo "   ABSENT : $H/projet/plateforme/opca-platform"; fi

echo "== 2. Configuration v2 (compose, Grafana, scripts, modèles)"
for d in compose grafana rf_v2 xgb_eval checks; do
  [ -d "$H/projet/v2/$d" ] && tar -C "$H/projet/v2" "${EXCL[@]}" -cf - "$d" | tar -C "$STAGE/opca_v2" -xf - || echo "   absent : $d"
done
[ -f "$H/projet/v2/vars.sh" ] && cp "$H/projet/v2/vars.sh" "$STAGE/opca_v2/"

echo "== 3. Sauvegarde de la nouvelle base"
if docker exec opca_pg_v2 pg_dump -U opca_app -d opca_db -Fc > "$STAGE/opca_db.dump" 2>/dev/null && [ -s "$STAGE/opca_db.dump" ]; then
  echo "   dump : $(du -h "$STAGE/opca_db.dump" | cut -f1)"
else echo "   ÉCHEC du dump"; rm -f "$STAGE/opca_db.dump"; fi

echo "== 4. Images Docker utilisées par la v2 (à reconstruire ou récupérer sur la nouvelle VM)"
docker ps --format '{{.Names}} -> {{.Image}}' 2>/dev/null | grep -E "v2|airflow" | tee "$STAGE/images_utilisees.txt" || true

echo "== 5. Contrôle de secrets en dur (fichier:ligne seulement, valeurs masquées)"
HITS=$(grep -rInE "(password|passwd|pwd|secret|token|api_key)[\"']?\s*[=:]\s*[\"'][^\"'\$\{ ]{6,}[\"']|postgresql(\+psycopg2)?://[^ :/]+:[^ @\$\{]+@|ghp_[A-Za-z0-9]{20,}|BEGIN (RSA|OPENSSH) PRIVATE KEY" "$STAGE" 2>/dev/null | cut -d: -f1,2 | sed "s|$STAGE/||" || true)
if [ -n "$HITS" ]; then echo "$HITS" | sed 's/^/   À VÉRIFIER : /'; else echo "   rien détecté"; fi

cat > "$STAGE/LISEZMOI.txt" <<'T'
Contenu : opca-platform/ (code, DAG, Dockerfiles), opca_v2/ (compose, Grafana, scripts, RF, XGBoost),
opca_db.dump (base, format pg_dump -Fc), images_utilisees.txt.
NON inclus volontairement : mots de passe (*.env), clés (.pem), .git, journaux.
Sur la nouvelle VM : recréer des mots de passe neufs, puis restaurer le dump avec pg_restore --no-owner.
T
( cd "$STAGE" && find . -type f ! -name opca_db.dump | sort > FICHIERS.txt )
tar -C "$OUT" -czf "$OUT/opca_bundle.tgz" opca_bundle
( cd "$OUT" && sha256sum opca_bundle.tgz > opca_bundle.tgz.sha256 )
chmod 600 "$OUT"/opca_bundle.tgz*
echo "== TERMINÉ : $OUT/opca_bundle.tgz ($(du -h "$OUT/opca_bundle.tgz" | cut -f1))"
echo "== Arborescence (à me coller si tu veux que j'adapte l'installation) :"
sed -n '1,60p' "$STAGE/FICHIERS.txt"
