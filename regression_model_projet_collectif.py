"""
Modèle de RÉGRESSION — Prédiction du prix de clôture (prix_fermeture)
Projet collectif — adapté au schéma réel (create_table bdd OPA.sql)

TABLES UTILISÉES
-----------------
- instrument_marche(instrument_id, symbole, actif, devise_cotation, plateforme)
- serie_prix(prix_id, date_heure, pas_temps, prix_ouverture, prix_haut,
             prix_bas, prix_fermeture, volume, variation_prix_pct, instrument_id)
- indicateur_technique(indicateur_id, date_heure, pas_temps, sma_20, sma_50,
                        rsi_14, macd, volatilite, instrument_id)
- prediction_modele(prediction_id, date_heure, horizon_prediction,
                     prix_predit, direction_predite, score_confiance)

⚠️ LIMITE DU SCHÉMA ACTUEL
---------------------------
La table `prediction_modele` n'a pas de colonne `instrument_id` ni de colonne
identifiant le modèle utilisé (`model_name`). On ne peut donc pas, avec ce
schéma tel quel, distinguer plus tard "quelle prédiction appartient à quel
actif / à quel modèle". À signaler à l'équipe pour une évolution du schéma
(ajout de instrument_id et model_name dans prediction_modele).
En attendant, le script écrit quand même les prédictions, mais ce point est
une limite connue.
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
from xgboost import XGBRegressor
import joblib

# ---------------------------------------------------------------------------
# 1. CONNEXION À LA BASE DE DONNÉES
# ---------------------------------------------------------------------------
# À adapter avec les vrais identifiants du docker-compose.yaml du projet
DB_URI = "postgresql://daniel:datascientest@51.44.254.88:5432/dst_db"
engine = create_engine(DB_URI)

SYMBOLE = "BTC-USD"        # doit correspondre à instrument_marche.symbole
PAS_TEMPS = "1h"        # doit correspondre à la valeur utilisée dans serie_prix/indicateur_technique
HORIZON = 1              # horizon de prédiction en nombre de pas de temps


def get_instrument_id(symbole: str) -> int:
    """Récupère l'instrument_id correspondant au symbole (ex: BTC)."""
    query = text("SELECT instrument_id FROM instrument_marche WHERE symbole = :symbole")
    with engine.connect() as conn:
        result = conn.execute(query, {"symbole": symbole}).fetchone()
    if result is None:
        raise ValueError(f"Symbole {symbole} introuvable dans instrument_marche")
    return result[0]


def load_dataset(instrument_id: int, pas_temps: str) -> pd.DataFrame:
    """
    Jointure entre serie_prix et indicateur_technique sur
    (instrument_id, date_heure, pas_temps), triée chronologiquement.
    """
    query = f"""
        SELECT sp.date_heure, sp.prix_ouverture, sp.prix_haut, sp.prix_bas,
               sp.prix_fermeture, sp.volume, sp.variation_prix_pct,
               it.sma_20, it.sma_50, it.rsi_14, it.macd, it.volatilite
        FROM serie_prix sp
        JOIN indicateur_technique it
          ON sp.instrument_id = it.instrument_id
         AND sp.date_heure = it.date_heure
         AND sp.pas_temps = it.pas_temps
        WHERE sp.instrument_id = {instrument_id}
          AND sp.pas_temps = '{pas_temps}'
        ORDER BY sp.date_heure ASC
    """
    return pd.read_sql(query, engine)


def build_features_and_target(df: pd.DataFrame, horizon: int) -> tuple:
    """
    Cible = prix_fermeture décalé de `horizon` pas de temps dans le futur.
    """
    df = df.copy()
    df["target"] = df["prix_fermeture"].shift(-horizon)
    df = df.dropna(subset=["target"])

    # variation_prix_pct exclue : quasiment toujours NULL en base actuellement
    feature_cols = ["prix_ouverture", "prix_haut", "prix_bas", "prix_fermeture",
                     "volume",
                     "sma_20", "sma_50", "rsi_14", "macd", "volatilite"]
    # on ne garde que les colonnes réellement non-nulles pour éviter les erreurs
    df = df.dropna(subset=feature_cols)

    X = df[feature_cols]
    y = df["target"]
    return X, y, df["date_heure"]


def train_model(X_train, y_train) -> XGBRegressor:
    model = XGBRegressor(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
    )
    model.fit(X_train, y_train)
    return model


def evaluate_model(model, X_test, y_test) -> dict:
    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    return {"rmse": rmse, "mae": mae}


def save_predictions(model, X, timestamps, horizon):
    """
    Écrit dans prediction_modele. NB : pas de instrument_id/model_name
    disponibles dans ce schéma (voir avertissement en tête de fichier) —
    direction_predite est déduite du sens de variation prédit vs dernier
    prix connu (approximation simple).
    """
    preds = model.predict(X)
    last_known_close = X["prix_fermeture"].values
    directions = np.where(preds > last_known_close, "hausse", "baisse")

    out = pd.DataFrame({
        "date_heure": timestamps,
        "horizon_prediction": f"{horizon} pas de temps",
        "prix_predit": preds,
        "direction_predite": directions,
        "score_confiance": None,  # non calculé pour la régression pure
    })
    out.to_sql("prediction_modele", engine, if_exists="append", index=False)


def main():
    instrument_id = get_instrument_id(SYMBOLE)
    df = load_dataset(instrument_id, PAS_TEMPS)

    if df.empty:
        print(f"Aucune donnée trouvée pour {SYMBOLE} / pas_temps={PAS_TEMPS}. "
              f"Vérifie que serie_prix et indicateur_technique sont bien alimentées.")
        return

    X, y, timestamps = build_features_and_target(df, HORIZON)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    model = train_model(X_train, y_train)
    metrics = evaluate_model(model, X_test, y_test)
    print(f"[{SYMBOLE}] Régression XGBoost — RMSE: {metrics['rmse']:.4f}, "
          f"MAE: {metrics['mae']:.4f}")

    joblib.dump(model, f"models/xgboost_{SYMBOLE}_{PAS_TEMPS}.joblib")
    save_predictions(model, X, timestamps, HORIZON)


if __name__ == "__main__":
    main()
