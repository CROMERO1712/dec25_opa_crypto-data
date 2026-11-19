"""
Indicateurs techniques OPCA - version multi-plateforme et incrementale.

Reprend les formules de compute_indicateurs_techniques.py (SMA 20/50, RSI 14,
MACD 12/26, volatilite 20) mais :
  - calcule par (instrument_id, plateforme_id, pas_temps) ;
  - n'insere que les lignes plus recentes que la derniere deja en base
    (relancer le script ne cree donc aucun doublon) ;
  - lit la connexion dans l'environnement (DB_HOST, DB_PORT, DB_NAME,
    DB_USER, DB_PASSWORD) ;
  - n'ecrit QUE dans indicateur_technique, sans toucher au schema.

Usage :  python compute_indicateurs.py [--dry-run]
"""
import os
import sys

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

DRY_RUN = "--dry-run" in sys.argv
PAS_TEMPS = os.getenv("PAS_TEMPS")  # vide = tous les pas de temps presents
COLS_OUT = ["date_heure", "pas_temps", "sma_20", "sma_50", "rsi_14",
            "macd", "volatilite", "instrument_id", "plateforme_id"]


def make_engine():
    url = URL.create(
        "postgresql+psycopg2",
        username=os.getenv("DB_USER", "daniel"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "dst_db"),
    )
    return create_engine(url, pool_pre_ping=True)


def compute_rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(close, fast=12, slow=26):
    return close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()


def compute_group(group):
    group = group.sort_values("date_heure").copy()
    close = group["prix_fermeture"].astype(float)
    group["sma_20"] = close.rolling(window=20, min_periods=20).mean()
    group["sma_50"] = close.rolling(window=50, min_periods=50).mean()
    group["rsi_14"] = compute_rsi(close)
    group["macd"] = compute_macd(close)
    group["volatilite"] = close.pct_change().rolling(window=20, min_periods=20).std()
    return group


def build_new_rows(prix, last):
    """prix : serie_prix ; last : dernier date_heure deja indexe par groupe
    (dict {(instrument_id, plateforme_id, pas_temps): Timestamp})."""
    frames = []
    for key, group in prix.groupby(["instrument_id", "plateforme_id", "pas_temps"]):
        computed = compute_group(group)
        computed = computed.dropna(subset=["sma_20", "rsi_14", "macd"])
        deja = last.get(tuple(key))
        if deja is not None:
            computed = computed[computed["date_heure"] > deja]
        frames.append(computed)
    if not frames:
        return pd.DataFrame(columns=COLS_OUT)
    out = pd.concat(frames, ignore_index=True)
    out = out.replace([np.inf, -np.inf], np.nan)
    return out[COLS_OUT]


def main():
    engine = make_engine()
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(710001)"))  # un seul calcul a la fois
        sql = ("SELECT date_heure, pas_temps, prix_fermeture, instrument_id, plateforme_id "
               "FROM serie_prix")
        params = {}
        if PAS_TEMPS:
            sql += " WHERE pas_temps = :pt"
            params["pt"] = PAS_TEMPS
        prix = pd.read_sql(text(sql), conn, params=params)
        deja = pd.read_sql(text(
            "SELECT instrument_id, plateforme_id, pas_temps, max(date_heure) AS derniere "
            "FROM indicateur_technique GROUP BY 1,2,3"), conn)
        last = {(int(r.instrument_id), int(r.plateforme_id), r.pas_temps): r.derniere
                for r in deja.itertuples()}
        print(f"{len(prix)} lignes de prix chargees, {len(last)} groupes deja indexes.")

        out = build_new_rows(prix, last)
        print(f"{len(out)} nouvelles lignes d'indicateurs a inserer.")
        if out.empty or DRY_RUN:
            print("DRY-RUN : rien n'est ecrit." if DRY_RUN else "Rien a inserer.")
            if not out.empty:
                print(out.groupby(["instrument_id", "plateforme_id", "pas_temps"]).size())
            return
        out.to_sql("indicateur_technique", conn, if_exists="append", index=False,
                   method="multi", chunksize=2000)
        print("Insertion terminee.")


if __name__ == "__main__":
    main()
