"""
Activite de marche Binance (bougies 5m) -> table activite_marche.

Les bougies Binance contiennent plus que les prix stockes dans serie_prix :
  - volume_total      : montant echange en USDT (quote volume) ;
  - nombre_trades     : nombre de transactions de la bougie ;
  - ratio_achat_vente : part des achats dans le volume (achats a l'initiative
                        de l'acheteur / volume total, entre 0 et 1 ; 0,5 = equilibre) ;
  - liquidite_score   : log10(1 + volume en USDT), entre 0 et ~10.

Fonctionnement :
  - par paire, reprend apres la derniere bougie deja en base ; si la table est
    vide, remonte jusqu'a la premiere bougie de serie_prix (meme paire, meme
    plateforme) pour que l'historique soit complet ;
  - n'ecrit que les bougies terminees (la bougie en cours est ignoree) ;
  - n'insere jamais une bougie deja presente (relancer ne cree aucun doublon) ;
  - dates en UTC, comme insert_binance.py (jointure exacte avec serie_prix) ;
  - n'ecrit QUE dans activite_marche, sans toucher au schema.

Connexion : DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (environnement).
Usage     : python insert_activite_binance.py [--dry-run]
"""
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import psycopg2
from binance.client import Client
from psycopg2.extras import execute_values

DRY_RUN = "--dry-run" in sys.argv
PAIRES = {"BTCUSDT": 1, "ETHUSDT": 2, "SOLUSDT": 3}  # meme correspondance que insert_binance.py
PLATEFORME_ID = 1  # Binance
PAS = "5m"
LOT = 1000  # bougies par appel (maximum Binance)

INSERT = """
INSERT INTO activite_marche (date_heure, pas_temps, volume_total, nombre_trades,
                             ratio_achat_vente, liquidite_score, instrument_id, plateforme_id)
SELECT v.date_heure, v.pas_temps, v.volume_total, v.nombre_trades,
       v.ratio_achat_vente, v.liquidite_score, v.instrument_id, v.plateforme_id
FROM (VALUES %s) AS v(date_heure, pas_temps, volume_total, nombre_trades,
                      ratio_achat_vente, liquidite_score, instrument_id, plateforme_id)
WHERE NOT EXISTS (
    SELECT 1 FROM activite_marche a
    WHERE a.instrument_id = v.instrument_id AND a.plateforme_id = v.plateforme_id
      AND a.pas_temps = v.pas_temps AND a.date_heure = v.date_heure)
"""
GABARIT = "(%s::timestamp, %s, %s::numeric, %s::int, %s::numeric, %s::numeric, %s::int, %s::int)"


def log(msg):
    print(f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def connexion():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "dst_db"),
        user=os.getenv("DB_USER", "daniel"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


def utc_naif(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).replace(tzinfo=None)


def en_ms(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def point_de_depart(cur, instrument_id):
    """Bougie suivant la derniere en base, sinon premiere bougie de serie_prix."""
    cur.execute("SELECT max(date_heure) FROM activite_marche "
                "WHERE instrument_id = %s AND plateforme_id = %s AND pas_temps = %s",
                (instrument_id, PLATEFORME_ID, PAS))
    derniere = cur.fetchone()[0]
    if derniere is not None:
        return derniere + timedelta(minutes=5)
    cur.execute("SELECT min(date_heure) FROM serie_prix "
                "WHERE instrument_id = %s AND plateforme_id = %s AND pas_temps = %s",
                (instrument_id, PLATEFORME_ID, PAS))
    premiere = cur.fetchone()[0]
    return premiere or datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)


def ligne(k, instrument_id):
    volume_base, volume_usdt, achats_base = float(k[5]), float(k[7]), float(k[9])
    return (
        utc_naif(k[0]),
        PAS,
        round(volume_usdt, 8),
        int(k[8]),
        round(achats_base / volume_base, 4) if volume_base > 0 else None,
        round(math.log10(1 + volume_usdt), 4),
        instrument_id,
        PLATEFORME_ID,
    )


def collecter(client, cur, symbole, instrument_id):
    depart = point_de_depart(cur, instrument_id)
    maintenant_ms = int(time.time() * 1000)
    debut_ms, lignes = en_ms(depart), []
    while debut_ms < maintenant_ms:
        klines = client.get_klines(symbol=symbole, interval=Client.KLINE_INTERVAL_5MINUTE,
                                   startTime=debut_ms, limit=LOT)
        terminees = [k for k in klines if k[6] < maintenant_ms]  # k[6] = fin de la bougie
        lignes += [ligne(k, instrument_id) for k in terminees]
        if len(klines) < LOT or not terminees:
            break
        debut_ms = klines[-1][0] + 1
    log(f"{symbole} : {len(lignes)} bougie(s) terminée(s) depuis {depart:%Y-%m-%d %H:%M}")
    if lignes and not DRY_RUN:
        execute_values(cur, INSERT, lignes, template=GABARIT, page_size=1000)
        log(f"{symbole} : {len(lignes)} ligne(s) écrite(s) dans activite_marche (doublons ignorés)")
    elif lignes:
        log(f"{symbole} : simulation, exemple {lignes[-1]}")
    return len(lignes)


def main():
    log("Début insert_activite_binance.py" + (" (simulation)" if DRY_RUN else ""))
    client = Client()
    echecs = 0
    conn = connexion()
    try:
        for symbole, instrument_id in PAIRES.items():
            try:
                with conn.cursor() as cur:
                    collecter(client, cur, symbole, instrument_id)
                conn.commit()
            except Exception as e:  # une paire en erreur n'empêche pas les autres
                conn.rollback()
                echecs += 1
                log(f"{symbole} : ERREUR {e}")
    finally:
        conn.close()
    log(f"Fin insert_activite_binance.py ({echecs} échec(s))")
    sys.exit(1 if echecs else 0)


if __name__ == "__main__":
    main()
