"""
Modèle de RÉGRESSION — Prédiction de la valeur du prix (cours) d'une cryptomonnaie
Projet : dec25_opca_crypto_data

OBJECTIF
--------
Prédire une valeur continue : le prix futur (close) d'un actif à un horizon donné
(ex: prix dans 1h). C'est un problème de régression car la cible (le prix) est
un nombre continu, pas une catégorie.

MODÈLE UTILISÉ : XGBoost Regressor
- Bon compromis performance / temps d'entraînement sur données tabulaires
- Gère bien les features numériques type indicateurs techniques (RSI, MACD, SMA...)
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
from xgboost import XGBRegressor
import joblib
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 1. CONNEXION À LA BASE DE DONNÉES
# ---------------------------------------------------------------------------
# On lit les données depuis PostgreSQL (tables `prices` et `indicators`,
# voir doc technique section 3.1). Adapter la chaîne de connexion.
DB_URI = "postgresql://crypto_user:changeme@localhost:5432/crypto_db"
engine = create_engine(DB_URI)

SYMBOL = "BTC"          # actif ciblé (BTC, ETH, BNB, ADA, SOL)
HORIZON_HOURS = 1        # horizon de prédiction : prix dans 1h


def load_dataset(symbol: str) -> pd.DataFrame:
    """
    Récupère les prix et indicateurs joints pour un actif donné,
    triés chronologiquement. On joint `prices` et `indicators` sur
    (symbol, timestamp) pour avoir features + valeur réelle du cours.
    """
    query = f"""
        SELECT p.timestamp, p.close, p.volume,
               i.sma_20, i.ema_20, i.rsi_14, i.macd, i.macd_signal
        FROM prices p
        JOIN indicators i
          ON p.symbol = i.symbol AND p.timestamp = i.timestamp
        WHERE p.symbol = '{symbol}'
        ORDER BY p.timestamp ASC
    """
    df = pd.read_sql(query, engine)
    return df


def build_features_and_target(df: pd.DataFrame, horizon_hours: int) -> tuple:
    """
    Construit la matrice de features X et la cible y.

    La cible (y) = le prix de clôture `horizon_hours` plus tard.
    On décale (shift) la colonne `close` vers le "futur" pour créer
    la cible que le modèle doit apprendre à prédire.
    """
    df = df.copy()
    df["target"] = df["close"].shift(-horizon_hours)

    # On enlève les dernières lignes sans cible (car pas de futur connu)
    df = df.dropna(subset=["target"])

    feature_cols = ["close", "volume", "sma_20", "ema_20",
                     "rsi_14", "macd", "macd_signal"]
    X = df[feature_cols]
    y = df["target"]
    return X, y, df["timestamp"]


def train_model(X_train, y_train) -> XGBRegressor:
    """
    Entraîne un XGBoost Regressor.
    - n_estimators : nombre d'arbres
    - max_depth : profondeur max des arbres (évite le sur-apprentissage)
    - learning_rate : vitesse d'apprentissage
    """
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
    """
    Évalue le modèle avec deux métriques classiques de régression :
    - RMSE (Root Mean Squared Error) : pénalise fort les grosses erreurs
    - MAE (Mean Absolute Error) : erreur moyenne absolue, plus lisible
    """
    y_pred = model.predict(X_test)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    mae = mean_absolute_error(y_test, y_pred)
    return {"rmse": rmse, "mae": mae}


def save_predictions(model, X, timestamps, symbol, horizon_hours):
    """
    Écrit les prédictions dans la table `predictions` (voir doc technique
    section 3.1) pour qu'elles soient exploitables par le dashboard Streamlit.
    """
    preds = model.predict(X)
    out = pd.DataFrame({
        "symbol": symbol,
        "model_name": "xgboost",
        "timestamp": timestamps,
        "predicted_value": preds,
        "horizon": f"{horizon_hours}h",
    })
    out.to_sql("predictions", engine, if_exists="append", index=False)


def main():
    df = load_dataset(SYMBOL)
    X, y, timestamps = build_features_and_target(df, HORIZON_HOURS)

    # Split chronologique : on n'entraîne PAS sur le futur pour tester sur
    # le passé (contrairement à un split aléatoire classique). shuffle=False
    # est essentiel pour des séries temporelles.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, shuffle=False
    )

    model = train_model(X_train, y_train)
    metrics = evaluate_model(model, X_test, y_test)
    print(f"[{SYMBOL}] Régression XGBoost — RMSE: {metrics['rmse']:.4f}, "
          f"MAE: {metrics['mae']:.4f}")

    # Sauvegarde du modèle entraîné pour réutilisation (voir MongoDB
    # `model_metadata` pour tracer hyperparamètres/métriques associés)
    joblib.dump(model, f"models/xgboost_{SYMBOL}_{HORIZON_HOURS}h.joblib")

    # Prédictions sur l'ensemble du dataset (ou uniquement les dernières
    # lignes en production, pour prédire le prix futur réel)
    save_predictions(model, X, timestamps, SYMBOL, HORIZON_HOURS)


if __name__ == "__main__":
    main()
