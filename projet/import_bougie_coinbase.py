import requests
import pandas as pd
import psycopg2
from datetime import datetime, timezone, timedelta
# ===============================
# PARAMETRES
# ===============================
pair = "BTC-USD"
instrument_id = 4 #id for btc coinbase

# ===============================
# 1. RECUPERATION DES BOUGIES
# ===============================
url = f"https://api.exchange.coinbase.com/products/{pair}/candles"

params = {
    "granularity": 3600  # 1h,
    "start": start.isoformat(),
    "end": end.isoformat()
}

response = requests.get(url, params=params)
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
    host="51.44.254.88",
    database="dst_db",
    user="daniel",
    password="datascientest",
    port=5432
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
    instrument_id
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
"""

for _, row in df.iterrows():
    cur.execute(insert_query, (
        row["date_heure"].to_pydatetime(),
        "1h",
        float(row["open"]),
        float(row["high"]),
        float(row["low"]),
        float(row["close"]),
        float(row["volume"]),
        None if pd.isna(row["variation_prix_pct"]) else float(row["variation_prix_pct"]),
        instrument_id
    ))

conn.commit()

print(f"{len(df)} bougies insérées dans serie_prix.")

cur.close()
conn.close()