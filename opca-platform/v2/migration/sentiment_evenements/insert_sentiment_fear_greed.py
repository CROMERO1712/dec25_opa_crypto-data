"""
Indice Fear & Greed (alternative.me) -> table sentiment_social.

  - score_sentiment : 0 (peur extreme) a 100 (avidite extreme), une valeur par jour pour tout le
    marche crypto ; source = 'fear_greed' ; date_heure = jour de la mesure (00:00 UTC) ;
  - nombre_messages et score_engagement restent vides (l'indice ne les fournit pas) ;
  - premier lancement : tout l'historique disponible ; ensuite les 10 derniers jours ;
  - n'insere jamais une valeur deja presente (index unique source + date_heure) ;
  - n'ecrit QUE dans sentiment_social. API gratuite, sans cle.

Connexion : DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (environnement).
Usage     : python insert_sentiment_fear_greed.py [--dry-run]
"""
import os
import sys
from datetime import datetime, timezone

import psycopg2
import requests
from psycopg2.extras import execute_values

DRY_RUN = "--dry-run" in sys.argv
URL = "https://api.alternative.me/fng/"
SOURCE = "fear_greed"

INSERT = """
INSERT INTO sentiment_social (date_heure, source, score_sentiment) VALUES %s
ON CONFLICT (source, date_heure) DO NOTHING
"""


def connect():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "dst_db"),
        user=os.getenv("DB_USER", "daniel"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


def parse(payload):
    """Reponse de l'API -> [(date_heure UTC naive, source, score)], du plus ancien au plus recent."""
    rows = [(datetime.fromtimestamp(int(d["timestamp"]), tz=timezone.utc).replace(tzinfo=None),
             SOURCE, float(d["value"])) for d in payload.get("data", [])]
    return sorted(rows)


def main():
    with connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM sentiment_social WHERE source = %s", (SOURCE,))
        limit = 10 if cur.fetchone()[0] else 0  # 0 = tout l'historique
        r = requests.get(URL, params={"limit": limit}, timeout=20)
        r.raise_for_status()
        rows = parse(r.json())
        if not rows:
            print("Fear & Greed : aucune valeur recue.")
            return
        print(f"Fear & Greed : {len(rows)} valeurs du {rows[0][0]:%d/%m/%Y} au {rows[-1][0]:%d/%m/%Y}, "
              f"derniere = {rows[-1][2]:.0f}/100.")
        if DRY_RUN:
            print("DRY-RUN : rien n'est ecrit dans sentiment_social.")
            return
        execute_values(cur, INSERT, rows, page_size=max(len(rows), 1))  # rowcount = toutes les lignes
        print(f"{cur.rowcount} nouvelle(s) valeur(s) ecrite(s).")


if __name__ == "__main__":
    main()
