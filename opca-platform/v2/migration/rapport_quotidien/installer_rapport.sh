#!/usr/bin/env bash
# Installe le rapport OPCA écrit dans ~/projet/rapport_quotidien, deux fois par jour :
#   07:00 heure de Paris (après le Random Forest et la sauvegarde de la nuit) et 22:30.
# La VM est en UTC : chaque ligne cron est lancée aux deux heures UTC possibles (heure d'hiver
# et d'été) et ne s'exécute que si l'heure de Paris est la bonne.
# Usage : bash ~/projet/script_migration/rapport_quotidien/installer_rapport.sh
# Retour arrière : crontab -l | grep -v rapport_quotidien.py | crontab -
set -euo pipefail
D=$HOME/projet/rapport_quotidien
SRC=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$D" && chmod 750 "$D"
cp "$SRC/rapport_quotidien.py" "$D/" && chmod 750 "$D/rapport_quotidien.py"

CMD='/usr/bin/python3 $HOME/projet/rapport_quotidien/rapport_quotidien.py >> $HOME/projet/rapport_quotidien/rapport.log 2>&1'
MATIN="0 5,6 * * * [ \"\$(TZ=Europe/Paris date +\\%H)\" = 07 ] && $CMD"
SOIR="30 20,21 * * * [ \"\$(TZ=Europe/Paris date +\\%H)\" = 22 ] && $CMD"
(crontab -l 2>/dev/null | grep -v rapport_quotidien.py; echo "$MATIN"; echo "$SOIR") | crontab -
echo "[OK] cron installé :"
crontab -l | grep rapport_quotidien.py
echo "Rapports dans $D"
