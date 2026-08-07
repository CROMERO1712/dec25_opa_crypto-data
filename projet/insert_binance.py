import sys
from binance.client import Client
import psycopg2
from datetime import datetime

# initialisation client Binance
client = Client()  

# rediriger stdout et stderr vers le fichier de log
sys.stdout = open('/home/ubuntu/projet/log_binance.log', 'a')
sys.stderr = open('/home/ubuntu/projet/log_binance.log', 'a')

print(f"[{datetime.now()}] Début du script insert_binance.py")

# test connexion à Binance
klines_test = client.get_klines(symbol="BTCUSDT", interval=Client.KLINE_INTERVAL_1HOUR, limit=5)
print(f"Test API Binance: {len(klines_test)} bougies récupérées.")
if not klines_test:
    print("aucune donnée récupérée depuis Binance")
    sys.exit(1)

# connexion PostgreSQL
db_config = {
    "dbname": "dst_db",
    "user": "daniel",
    "password": "datascientest",
    "host": "51.44.254.88",
    "port": "5432"
}

def fetch_ohlcv(symbol: str, interval: str = Client.KLINE_INTERVAL_1HOUR, limit: int = 1000):
    print(f"[{datetime.now()}] Récupération des données OHLCV pour {symbol}...")
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    print(f"[{datetime.now()}] {len(klines)} bougies récupérées pour {symbol}.")
    return klines

def insert_into_postgres(klines: list, symbol: str, instrument_id: int, interval: str):
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor()
        print(f"[{datetime.now()}] Connexion à PostgreSQL réussie.")

        for kline in klines:
            insert_query = """
            INSERT INTO serie_prix (
                date_heure, pas_temps, prix_ouverture, prix_haut,
                prix_bas, prix_fermeture, volume, instrument_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instrument_id, date_heure, pas_temps)
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
                instrument_id                          # instrument_id
            ))
        conn.commit()
        print(f"[{datetime.now()}] {len(klines)} ligne insérées ou update dans serie_prix.")

    except Exception as e:
        print(f"[{datetime.now()}] erreur lors de l'insertion des donnée : {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    # dico pour associer les paires à des ids
    instrument_ids = {
        "BTCUSDT": 1,
        "ETHUSDT": 2,
        "SOLUSDT": 3
    }

    # recup et insert des données pour chaque paire
    for symbol, instrument_id in instrument_ids.items():
        klines = fetch_ohlcv(symbol)
        insert_into_postgres(klines, symbol, instrument_id, Client.KLINE_INTERVAL_1HOUR)

    print(f"[{datetime.now()}] Fin du script insert_binance.py.")
