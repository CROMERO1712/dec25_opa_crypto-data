"""
Calcul et insertion des indicateurs techniques dans la table indicateur_technique
Projet collectif — dec25_opca_crypto_data

OBJECTIF
--------
Lit serie_prix pour chaque instrument/pas_temps, calcule :
- sma_20, sma_50   : moyennes mobiles simples (20 et 50 périodes)
- rsi_14           : Relative Strength Index (14 périodes)
- macd             : Moving Average Convergence Divergence (12/26 périodes)
- volatilite       : écart-type glissant des rendements (20 périodes)

Puis insère les résultats dans indicateur_technique, en respectant les
colonnes attendues par le schéma (create_table bdd OPA.sql) :
date_heure, pas_temps, sma_20, sma_50, rsi_14, macd, volatilite, instrument_id
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# 1. CONNEXION — adapter selon local (localhost) ou serveur distant
# ---------------------------------------------------------------------------
DB_URI = "postgresql://daniel:datascientest@51.44.254.88:5432/dst_db"
engine = create_engine(DB_URI)


def load_serie_prix() -> pd.DataFrame:
    """Charge toute la table serie_prix, triée par instrument/pas_temps/date."""
    query = """
        SELECT prix_id, date_heure, pas_temps, prix_fermeture, instrument_id
        FROM serie_prix
        ORDER BY instrument_id, pas_temps, date_heure
    """
    return pd.read_sql(query, engine)


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Calcule le RSI (Relative Strength Index) sur `period` périodes.
    Principe : ratio entre la moyenne des hausses et des baisses récentes,
    normalisé entre 0 et 100.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(close: pd.Series, fast: int = 12, slow: int = 26) -> pd.Series:
    """
    Calcule le MACD : différence entre EMA rapide (12) et EMA lente (26).
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    return ema_fast - ema_slow


def compute_indicators_for_group(group: pd.DataFrame) -> pd.DataFrame:
    """
    Calcule tous les indicateurs pour un groupe (un instrument + un pas_temps),
    déjà trié chronologiquement.
    """
    group = group.copy()
    close = group["prix_fermeture"]

    group["sma_20"] = close.rolling(window=20, min_periods=20).mean()
    group["sma_50"] = close.rolling(window=50, min_periods=50).mean()
    group["rsi_14"] = compute_rsi(close, period=14)
    group["macd"] = compute_macd(close)

    # Volatilité = écart-type glissant des rendements (variation relative)
    returns = close.pct_change()
    group["volatilite"] = returns.rolling(window=20, min_periods=20).std()

    return group


def build_indicators_dataframe(df_prix: pd.DataFrame) -> pd.DataFrame:
    """
    Applique le calcul des indicateurs par groupe (instrument_id, pas_temps),
    puis ne garde que les lignes complètes (sans NaN dû aux fenêtres glissantes).
    """
    results = []
    for (instrument_id, pas_temps), group in df_prix.groupby(["instrument_id", "pas_temps"]):
        computed = compute_indicators_for_group(group)
        results.append(computed)

    df_all = pd.concat(results, ignore_index=True)

    # On ne garde que les lignes où au moins sma_20/rsi_14/macd sont calculés
    df_indicators = df_all.dropna(subset=["sma_20", "rsi_14", "macd"])

    return df_indicators[["date_heure", "pas_temps", "sma_20", "sma_50",
                           "rsi_14", "macd", "volatilite", "instrument_id"]]


def insert_indicators(df_indicators: pd.DataFrame) -> None:
    """
    Insère les indicateurs calculés dans indicateur_technique.
    Utilise 'append' — si le script est relancé plusieurs fois, ça créera
    des doublons. Pour une insertion "propre", on vide d'abord la table
    (voir clear_existing_indicators ci-dessous) avant de réinsérer.
    """
    df_indicators.to_sql("indicateur_technique", engine, if_exists="append", index=False)


def clear_existing_indicators() -> None:
    """
    Vide la table indicateur_technique avant réinsertion, pour éviter les
    doublons si le script est relancé. À utiliser avec précaution si
    d'autres personnes de l'équipe travaillent sur la même table.
    """
    with engine.connect() as conn:
        conn.execute(text("TRUNCATE TABLE indicateur_technique RESTART IDENTITY"))
        conn.commit()


def main():
    print("Chargement de serie_prix...")
    df_prix = load_serie_prix()
    print(f"{len(df_prix)} lignes chargées.")

    print("Calcul des indicateurs techniques (sma_20, sma_50, rsi_14, macd, volatilite)...")
    df_indicators = build_indicators_dataframe(df_prix)
    print(f"{len(df_indicators)} lignes d'indicateurs calculées (après suppression des NaN de warm-up).")

    # Décommenter la ligne suivante si tu veux repartir de zéro à chaque exécution
    # clear_existing_indicators()

    print("Insertion dans indicateur_technique...")
    insert_indicators(df_indicators)
    print("Terminé.")


if __name__ == "__main__":
    main()
