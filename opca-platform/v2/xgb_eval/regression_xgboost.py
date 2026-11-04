"""
Regression XGBoost OPCA - prevision du prix de cloture a HORIZON pas de temps.

Version multi-plateforme et idempotente de regression_model_projet_collectif.py :
  - la jointure serie_prix / indicateur_technique inclut plateforme_id ;
  - les predictions sont ecrites dans prediction_modele (seule table modifiee) :
    les lignes de la fenetre sont supprimees puis reinserees dans une seule
    transaction, donc relancer le script ne cree aucun doublon ;
  - l'etiquette horizon_prediction identifie le modele, l'actif et la plateforme
    (ex. "BTC-USD/Binance 12x5m"), sans changer le schema ;
  - les dernieres observations (cible inconnue) sont aussi predites : c'est la
    vraie prevision ;
  - date_heure = instant de l'observation ; prix_predit = prix attendu a
    date_heure + HORIZON pas de temps.

Usage : python regression_xgboost.py [--dry-run]
Variables : DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD, SYMBOLE (BTC-USD),
PLATEFORME (Binance), PAS_TEMPS (5m), HORIZON (12), PRED_WINDOW (288),
MODEL_DIR (optionnel : sauvegarde du modele en .joblib).
"""
import os
import sys

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from xgboost import XGBRegressor

DRY_RUN = "--dry-run" in sys.argv
SYMBOLE = os.getenv("SYMBOLE", "BTC-USD")
PLATEFORME = os.getenv("PLATEFORME", "Binance")
PAS_TEMPS = os.getenv("PAS_TEMPS", "5m")
HORIZON = int(os.getenv("HORIZON", "12"))
PRED_WINDOW = int(os.getenv("PRED_WINDOW", "288"))
MODEL_DIR = os.getenv("MODEL_DIR")
LABEL = f"{SYMBOLE}/{PLATEFORME} {HORIZON}x{PAS_TEMPS}"
FEATURES = ["prix_ouverture", "prix_haut", "prix_bas", "prix_fermeture", "volume",
            "sma_20", "sma_50", "rsi_14", "macd", "volatilite"]
MIN_TRAIN = 200

SQL_DATASET = """
SELECT sp.date_heure, sp.prix_ouverture, sp.prix_haut, sp.prix_bas, sp.prix_fermeture,
       sp.volume, it.sma_20, it.sma_50, it.rsi_14, it.macd, it.volatilite
FROM serie_prix sp
JOIN instrument_marche im ON im.instrument_id = sp.instrument_id
JOIN plateforme p ON p.plateforme_id = sp.plateforme_id
JOIN indicateur_technique it
  ON it.instrument_id = sp.instrument_id AND it.plateforme_id = sp.plateforme_id
 AND it.date_heure = sp.date_heure AND it.pas_temps = sp.pas_temps
WHERE im.symbole = :symbole AND p.nom = :plateforme AND sp.pas_temps = :pas_temps
ORDER BY sp.date_heure
"""


def make_engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER", "daniel"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "dst_db"),
    )
    return create_engine(os.getenv("DATABASE_URL", url), pool_pre_ping=True)


def new_model():
    return XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.05,
                        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=2)


def fit_predict(df):
    """df : jeu de donnees joint. Retourne (predictions, metriques, modele)."""
    df = df.sort_values("date_heure").reset_index(drop=True)
    df[FEATURES] = df[FEATURES].apply(pd.to_numeric, errors="coerce").astype(float)
    df["target"] = df["prix_fermeture"].shift(-HORIZON)
    ok = df.dropna(subset=FEATURES)
    labelled = ok.dropna(subset=["target"])
    if len(labelled) < MIN_TRAIN:
        raise ValueError(f"Pas assez de donnees ({len(labelled)} < {MIN_TRAIN}) pour {LABEL}")
    split = int(len(labelled) * 0.8)
    train, test = labelled.iloc[:split], labelled.iloc[split:]
    model = new_model().fit(train[FEATURES], train["target"])
    pred_test = model.predict(test[FEATURES])
    metrics = {"rmse": float(np.sqrt(mean_squared_error(test["target"], pred_test))),
               "mae": float(mean_absolute_error(test["target"], pred_test)),
               "n_train": len(train), "n_test": len(test)}
    model = new_model().fit(labelled[FEATURES], labelled["target"])  # modele final
    window = ok.tail(PRED_WINDOW)
    preds = model.predict(window[FEATURES])
    out = pd.DataFrame({
        "date_heure": window["date_heure"].values,
        "horizon_prediction": LABEL,
        "prix_predit": preds.astype(float),
        "direction_predite": np.where(preds > window["prix_fermeture"].values, "hausse", "baisse"),
        "score_confiance": None,
    })
    return out, metrics, model


def write_predictions(conn, out):
    conn.execute(text("DELETE FROM prediction_modele WHERE horizon_prediction = :h AND date_heure >= :d"),
                 {"h": LABEL, "d": pd.Timestamp(out["date_heure"].min()).to_pydatetime()})
    out.to_sql("prediction_modele", conn, if_exists="append", index=False,
               method="multi", chunksize=500)


def main():
    engine = make_engine()
    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_xact_lock(710002)"))
        df = pd.read_sql(text(SQL_DATASET), conn,
                         params={"symbole": SYMBOLE, "plateforme": PLATEFORME, "pas_temps": PAS_TEMPS})
        print(f"[{LABEL}] {len(df)} lignes jointes (prix + indicateurs).")
        out, m, model = fit_predict(df)
        print(f"[{LABEL}] RMSE={m['rmse']:.4f} MAE={m['mae']:.4f} (train={m['n_train']}, test={m['n_test']})")
        print(f"[{LABEL}] {len(out)} predictions, de {out['date_heure'].min()} a {out['date_heure'].max()}.")
        if MODEL_DIR:
            os.makedirs(MODEL_DIR, exist_ok=True)
            joblib.dump(model, os.path.join(MODEL_DIR, f"xgboost_{SYMBOLE}_{PLATEFORME}_{PAS_TEMPS}.joblib"))
        if DRY_RUN:
            print("DRY-RUN : rien n'est ecrit dans prediction_modele.")
            return
        write_predictions(conn, out)
        print("Predictions ecrites.")


if __name__ == "__main__":
    main()
