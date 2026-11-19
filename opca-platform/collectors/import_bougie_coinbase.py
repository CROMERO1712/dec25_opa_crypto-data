import os
from datetime import datetime, timezone, timedelta

import pandas as pd
import psycopg2
import requests

# Copie conteneurisee de ~/projet/import_bougie_coinbase.py :
# - connexion PostgreSQL via variables d'environnement (memes valeurs par defaut)
# - timeout sur l'appel Coinbase, fermeture propre de la connexion

# ===============================
# PARAMETRES
# ===============================
pair = "BTC-USD"
instrument_id = 1
plateforme_id = 2  # id for btc coinbase
# Aujourd'hui : -12h → +12h
now = datetime.now(timezone.utc)

start = now - timedelta(hours=12)
end = now + timedelta(hours=12)

# ===============================
# 1. RECUPERATION DES BOUGIES
# ===============================
url = f"https://api.exchange.coinbase.com/products/{pair}/candles"

params = {
    "granularity": 300,  # 5min,
    "start": start.isoformat(),
    "end": end.isoformat()
}

response = requests.get(url, params=params, timeout=30)
response.raise_for_status()

data = response.json()

df = pd.DataFrame(data, columns=[
    "time",
    "low",
    "high",
    "open",
    "close",
    "volume"
])

# ordre chronologique
df = df.sort_values("time").reset_index(drop=True)

# conversion timestamp
df["date_heure"] = pd.to_datetime(df["time"], unit="s")

# calcul variation %
df["variation_prix_pct"] = (
    (df["close"] - df["open"]) / df["open"]
) * 100

# ===============================
# 2. CONNEXION POSTGRESQL
# ===============================
conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "dst_db"),
    user=os.getenv("DB_USER", "daniel"),
    password=os.getenv("DB_PASSWORD", ""),
    port=int(os.getenv("DB_PORT", "5432")),
)

cur = conn.cursor()

# ===============================
# 3. INSERTION
# ===============================
insert_query = """
INSERT INTO serie_prix (
    date_heure,
    pas_temps,
    prix_ouverture,
    prix_haut,
    prix_bas,
    prix_fermeture,
    volume,
    variation_prix_pct,
    instrument_id,
    plateforme_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON CONFLICT (instrument_id, plateforme_id, date_heure, pas_temps)
DO UPDATE SET
    prix_ouverture = EXCLUDED.prix_ouverture,
    prix_haut = EXCLUDED.prix_haut,
    prix_bas = EXCLUDED.prix_bas,
    prix_fermeture = EXCLUDED.prix_fermeture,
    volume = EXCLUDED.volume,
    variation_prix_pct = EXCLUDED.variation_prix_pct;
"""

try:
    for _, row in df.iterrows():
        cur.execute(insert_query, (
            row["date_heure"].to_pydatetime(),
            "5m",
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            float(row["volume"]),
            None if pd.isna(row["variation_prix_pct"]) else float(row["variation_prix_pct"]),
            instrument_id,
            plateforme_id
        ))
    conn.commit()
    print(f"{len(df)} bougies insérées dans serie_prix (Coinbase).", flush=True)
finally:
    cur.close()
    conn.close()
