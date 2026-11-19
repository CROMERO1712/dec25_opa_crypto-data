#!/usr/bin/env bash
# Alimente prediction_modele.score_confiance et signal_trading (simulation, aucun ordre réel).
#   0. sauvegarde : dump complet de opca_db + copie de regression_xgboost.py et du DAG v2 ;
#   1. regression_xgboost.py : classifieur XGBoost hausse/baisse -> score_confiance = probabilité que
#      la direction prévue par la régression soit la bonne ; écriture en place (prediction_id stable,
#      nécessaire au lien signal_trading.prediction_id, qui serait sinon remis à NULL à chaque heure) ;
#   2. generer_signaux.py : ACHAT / VENTE / ATTENTE sur la dernière prévision, stop-loss et take-profit ;
#   3. DAG opca_pipeline_horaire_v2 : nouvelle tâche generer_signaux après regression_xgboost.
# Usage, sur la VM : bash ~/projet/script_migration/score_signaux/installer_score_signaux.sh
# Retour arrière : voir la fin de ce fichier.
set -euo pipefail

P=/home/ubuntu/projet
SRC=$(cd "$(dirname "$0")" && pwd)
ML=$P/plateforme/opca-platform/ml
DAG=$P/plateforme/opca-platform/airflow/dags/opca_pipeline_horaire_v2.py
SAUV=$P/backups/score_signaux_$(date +%Y%m%dT%H%M%S)
ok() { echo "[OK]   $*"; }
ko() { echo "[ÉCHEC] $*"; exit 1; }

echo "===== score_confiance + signal_trading : $(date '+%F %T') ====="
M=$(date +%M); [ "$M" -ge 8 ] && [ "$M" -le 15 ] && ko "le pipeline horaire tourne à hh:10, relancer après hh:15"

# 0. Sauvegardes
mkdir -p "$SAUV" && chmod 700 "$SAUV"
cp -a "$ML/regression_xgboost.py" "$DAG" "$SAUV/"
docker exec opca_pg_v2 sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$SAUV/opca_db.dump"
docker exec -i opca_pg_v2 sh -c 'pg_restore -l' < "$SAUV/opca_db.dump" | grep -q "TABLE DATA public prediction_modele" \
  || ko "dump invalide"
(cd "$SAUV" && sha256sum * > SHA256SUMS && chmod 600 *)
ok "sauvegarde dans $SAUV ($(du -h "$SAUV/opca_db.dump" | cut -f1))"

# 1. regression_xgboost.py
if grep -q "XGBClassifier" "$ML/regression_xgboost.py"; then
  ok "regression_xgboost.py déjà modifié"
else
  python3 - "$ML/regression_xgboost.py" <<'PY'
import sys
f = sys.argv[1]
s = open(f, encoding="utf-8").read()
rempl = [
    ("from sklearn.metrics import mean_absolute_error, mean_squared_error\n",
     "from sklearn.metrics import mean_absolute_error, mean_squared_error, roc_auc_score\n"),
    ("from xgboost import XGBRegressor\n", "from xgboost import XGBClassifier, XGBRegressor\n"),
    ("def fit_predict(df):\n",
     "def new_classifier():\n"
     "    \"\"\"Direction (1 = hausse) : sa probabilite donne score_confiance.\"\"\"\n"
     "    return XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,\n"
     "                         colsample_bytree=0.8, random_state=42, n_jobs=2, eval_metric=\"logloss\")\n"
     "\n\n"
     "def fit_predict(df):\n"),
    ("    model = new_model().fit(labelled[FEATURES], labelled[\"target\"])  # modele final\n"
     "    window = ok.tail(PRED_WINDOW)\n"
     "    preds = model.predict(window[FEATURES])\n",
     "    up = (labelled[\"target\"] > labelled[\"prix_fermeture\"]).astype(int)\n"
     "    clf = new_classifier().fit(train[FEATURES], up.iloc[:split])\n"
     "    y_te = up.iloc[split:]\n"
     "    metrics[\"auc_direction\"] = (float(roc_auc_score(y_te, clf.predict_proba(test[FEATURES])[:, 1]))\n"
     "                                if y_te.nunique() > 1 else float(\"nan\"))\n"
     "    model = new_model().fit(labelled[FEATURES], labelled[\"target\"])  # modele final\n"
     "    clf = new_classifier().fit(labelled[FEATURES], up)\n"
     "    window = ok.tail(PRED_WINDOW)\n"
     "    preds = model.predict(window[FEATURES])\n"
     "    proba_up = clf.predict_proba(window[FEATURES])[:, 1]\n"),
    ("        \"score_confiance\": None,\n",
     "        # probabilite (classifieur) que la direction prevue par la regression soit la bonne\n"
     "        \"score_confiance\": np.round(np.where(preds > window[\"prix_fermeture\"].values,\n"
     "                                              proba_up, 1 - proba_up), 4),\n"),
    ("def write_predictions(conn, out):\n"
     "    conn.execute(text(\"DELETE FROM prediction_modele WHERE horizon_prediction = :h AND date_heure >= :d\"),\n"
     "                 {\"h\": LABEL, \"d\": pd.Timestamp(out[\"date_heure\"].min()).to_pydatetime()})\n"
     "    out.to_sql(\"prediction_modele\", conn, if_exists=\"append\", index=False,\n"
     "               method=\"multi\", chunksize=500)\n",
     "def write_predictions(conn, out):\n"
     "    \"\"\"Mise a jour en place, insertion sinon : prediction_id reste stable d'une heure a l'autre\n"
     "    (signal_trading.prediction_id y fait reference).\"\"\"\n"
     "    for r in out.to_dict(\"records\"):\n"
     "        params = {\"h\": LABEL, \"d\": pd.Timestamp(r[\"date_heure\"]).to_pydatetime(),\n"
     "                  \"p\": float(r[\"prix_predit\"]), \"dir\": r[\"direction_predite\"],\n"
     "                  \"s\": None if pd.isna(r[\"score_confiance\"]) else float(r[\"score_confiance\"])}\n"
     "        res = conn.execute(text(\"UPDATE prediction_modele SET prix_predit = :p, direction_predite = :dir, \"\n"
     "                                \"score_confiance = :s WHERE horizon_prediction = :h AND date_heure = :d\"), params)\n"
     "        if res.rowcount == 0:\n"
     "            conn.execute(text(\"INSERT INTO prediction_modele (date_heure, horizon_prediction, prix_predit, \"\n"
     "                              \"direction_predite, score_confiance) VALUES (:d, :h, :p, :dir, :s)\"), params)\n"),
    ("        print(f\"[{LABEL}] {len(out)} predictions, de",
     "        print(f\"[{LABEL}] AUC direction (classifieur, test) = {m['auc_direction']:.3f}\")\n"
     "        print(f\"[{LABEL}] {len(out)} predictions, de"),
]
for avant, apres in rempl:
    if s.count(avant) != 1:
        sys.exit(f"motif introuvable ou multiple : {avant[:70]!r}")
    s = s.replace(avant, apres)
open(f, "w", encoding="utf-8").write(s)
PY
  ok "regression_xgboost.py : score_confiance + écriture en place"
fi

# 2. generer_signaux.py
install -m 644 "$SRC/generer_signaux.py" "$ML/generer_signaux.py"
ok "generer_signaux.py installé"

# 3. DAG
if grep -q "generer_signaux" "$DAG"; then
  ok "DAG déjà modifié"
else
  grep -q "    regression_xgboost >> log_previsions_oos" "$DAG" || ko "DAG : motif introuvable"
  cat >> "$DAG" <<'EOF'
    # Signal de trading (simulation, aucun ordre) : derniere prevision + score_confiance -> signal_trading
    generer_signaux = BashOperator(
        task_id="generer_signaux",
        bash_command=f"cd {ML} && {ML_PY} generer_signaux.py " + DRY,
        env=ENV_V2, append_env=True,
    )
    regression_xgboost >> generer_signaux
EOF
  ok "DAG : tâche generer_signaux ajoutée"
fi

S=opca_airflow-airflow-scheduler-1
# ast.parse et non py_compile : /opt/airflow/ml est monté en lecture seule (pas de __pycache__)
docker exec "$S" /home/airflow/ml-venv/bin/python -c 'import ast, sys
for f in sys.argv[1:]: ast.parse(open(f).read())' /opt/airflow/ml/regression_xgboost.py \
  /opt/airflow/ml/generer_signaux.py /opt/airflow/dags/opca_pipeline_horaire_v2.py || ko "erreur de syntaxe"
ok "syntaxe vérifiée"
for i in $(seq 1 12); do
  docker exec "$S" airflow tasks list opca_pipeline_horaire_v2 2>/dev/null | grep -q generer_signaux && break
  sleep 10
done
docker exec "$S" airflow tasks list opca_pipeline_horaire_v2 2>/dev/null | grep -q generer_signaux \
  && ok "Airflow voit la tâche generer_signaux" || ko "Airflow ne voit pas encore la tâche (voir l'onglet Import errors)"

echo "Sauvegarde : $SAUV"
echo "Effet au prochain run (hh:10) : score_confiance rempli, un signal par heure dans signal_trading."

# --- Retour arrière -------------------------------------------------------------------------------
# cp <SAUV>/regression_xgboost.py ~/projet/plateforme/opca-platform/ml/
# cp <SAUV>/opca_pipeline_horaire_v2.py ~/projet/plateforme/opca-platform/airflow/dags/
# rm ~/projet/plateforme/opca-platform/ml/generer_signaux.py
# echo "delete from signal_trading; update prediction_modele set score_confiance = null;" \
#   | docker exec -i opca_pg_v2 sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
# Restauration complète de la base (dernier recours) :
# docker exec -i opca_pg_v2 sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' < <SAUV>/opca_db.dump
