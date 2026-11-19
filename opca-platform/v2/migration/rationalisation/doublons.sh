#!/usr/bin/env bash
# Suppression des derniers doublons de ~/projet. Aucun conteneur ni volume n'est touché.
set -uo pipefail
P=/home/ubuntu/projet
G=$P/plateforme/projet          # copie versionnée (git) de l'ancien projet
step(){ echo; echo "===== $*"; }

step "1. Liste des paquets des environnements Python (pour pouvoir les recréer)"
mkdir -p "$P/historique/venvs"
for e in venv mon_venv mon_env; do
  if [ -x "$P/$e/bin/python" ]; then
    "$P/$e/bin/python" -m pip freeze > "$P/historique/venvs/$e-requirements.txt" 2>/dev/null \
      && echo "$e : $(wc -l < "$P/historique/venvs/$e-requirements.txt") paquets"
  fi
done

step "2. Fichiers de la racine identiques à la copie git (vérifiés un par un)"
same(){ [ -f "$1" ] && [ -f "$2" ] && cmp -s "$1" "$2"; }
for f in "Streamlit/app_streamlit_prix.py" "Streamlit/lancer_streamlit.sh" "Streamlit/requirements_streamlit.txt" \
         "create_table bdd OPA.sql"; do
  same "$P/$f" "$G/$f" && rm -v "$P/$f"
done
same "$P/ML classification/integration_prix_df.py" "$G/integration_prix_df.py" && rm -v "$P/ML classification/integration_prix_df.py"
same "$P/ML regression/regression_model_projet_collectif.py" "$P/plateforme/regression_model_projet_collectif.py" \
  && rm -v "$P/ML regression/regression_model_projet_collectif.py"
same "$P/docker-compose.yaml.orig" "$G/docker-compose.yaml" && rm -v "$P/docker-compose.yaml.orig"
rmdir "$P/Streamlit" "$P/ML regression" 2>/dev/null || true

step "3. Copie de publication (régénérable par v1/preparer_publication.sh)"
rm -rf "$P/publication" && echo "publication/ supprimé"

step "4. Environnements Python inutilisés"
rm -rf "$P/venv" "$P/mon_venv" "$P/mon_env" && echo "venv, mon_venv, mon_env supprimés"

step "Résultat"
ls -la "$P"; du -sh "$P" 2>/dev/null; df -h / | tail -1
docker ps --format '{{.Names}}|{{.Status}}' | sort
