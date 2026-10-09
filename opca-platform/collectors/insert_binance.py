import os
import sys
from datetime import datetime

import psycopg2
from binance.client import Client

# Copie conteneurisee de ~/projet/insert_binance.py :
# - connexion PostgreSQL via variables d'environnement (memes valeurs par defaut)
# - logs sur la sortie standard (plus de redirection vers un fichier en dur)
# - code de sortie 1 si une insertion echoue (necessaire pour Airflow)

client = Client()

print(f"[{datetime.now()}] Début du script insert_binance.py", flush=True)

# test connexion à Binance
klines_test = client.get_klines(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_5MINUTE, limit=5)
print(f"Test API Binance: {len(klines_test)} bougies récupérées.", flush=True)
if not klines_test:
    print("aucune donnée récupérée depuis Binance", flush=True)
    sys.exit(1)

# connexion PostgreSQL
db_config = {
    "dbname": os.getenv("DB_NAME", "dst_db"),
    "user": os.getenv("DB_USER", "daniel"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}


def fetch_ohlcv(symbol: str, interval: str = Client.KLINE_INTERVAL_5MINUTE, limit: int = 1000):
    print(f"[{datetime.now()}] Récupération des données OHLCV pour {symbol}...", flush=True)
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    print(f"[{datetime.now()}] {len(klines)} bougies récupérées pour {symbol}.", flush=True)
    return klines


def insert_into_postgres(klines: list, symbol: str, instrument_id: int, interval: str, plateforme_id: int) -> bool:
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        print(f"[{datetime.now()}] Connexion à PostgreSQL réussie.", flush=True)

        for kline in klines:
            insert_query = """
            INSERT INTO serie_prix (
                date_heure, pas_temps, prix_ouverture, prix_haut,
                prix_bas, prix_fermeture, volume, instrument_id, plateforme_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id,plateforme_id, date_heure, pas_temps)
            DO UPDATE SET
                prix_ouverture = EXCLUDED.prix_ouverture,
                prix_haut = EXCLUDED.prix_haut,
                prix_bas = EXCLUDED.prix_bas,
                prix_fermeture = EXCLUDED.prix_fermeture,
                volume = EXCLUDED.volume;
            """
            cursor.execute(insert_query, (
                datetime.fromtimestamp(kline[0] / 1000),  # date_heure
                interval,                                # pas_temps
                float(kline[1]),                        # prix_ouverture
                float(kline[2]),                        # prix_haut
                float(kline[3]),                        # prix_bas
                float(kline[4]),                        # prix_fermeture
                float(kline[5]),                        # volume
                instrument_id,                          # instrument_id
                plateforme_id                           # plateforme_id
            ))
        conn.commit()
        print(f"[{datetime.now()}] {len(klines)} ligne insérées ou update dans serie_prix ({symbol}).", flush=True)
        return True

    except Exception as e:
        print(f"[{datetime.now()}] erreur lors de l'insertion des donnée ({symbol}) : {e}", flush=True)
        if conn is not None:
            conn.rollback()
        return False
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    # dico pour associer les paires à des ids
    instrument_ids = {
        "BTCUSDT": 1,
        "ETHUSDT": 2,
        "SOLUSDT": 3
    }
    # plateforme Binance
    plateforme_id = 1

    echecs = 0
    # recup et insert des données pour chaque paire
    for symbol, instrument_id in instrument_ids.items():
        klines = fetch_ohlcv(symbol)
        if not insert_into_postgres(klines, symbol, instrument_id, Client.KLINE_INTERVAL_5MINUTE, plateforme_id):
            echecs += 1

    print(f"[{datetime.now()}] Fin du script insert_binance.py ({echecs} echec(s)).", flush=True)
    sys.exit(1 if echecs else 0)
