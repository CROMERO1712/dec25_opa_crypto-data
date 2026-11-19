"""
Actualites crypto (flux RSS CoinDesk et Cointelegraph) -> table evenement_marche.

  - titre, date_heure (publication, UTC) ;
  - categorie par mots-cles dans le titre (premiere qui correspond) : securite, regulation, etf, macro,
    adoption, entreprise, marche, autre ;
  - impact_score : variation du BTC (Binance, bougies 5m de serie_prix) dans l'heure qui suit la
    publication, en % ; calcule seulement quand cette heure est connue, donc au passage suivant ;
  - n'insere jamais un titre deja present (index unique sur titre) ;
  - n'ecrit QUE dans evenement_marche. Flux gratuits, sans cle ; ~25-30 articles par flux,
    pas d'historique : la table se remplit au fil des passages horaires.

Connexion : DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (environnement).
Usage     : python insert_evenements_rss.py [--dry-run]
"""
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime

import psycopg2
import requests
from psycopg2.extras import execute_values

DRY_RUN = "--dry-run" in sys.argv
FLUX = {"coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "cointelegraph": "https://cointelegraph.com/rss"}
# premiere categorie dont un mot-cle apparait dans le titre (ordre = priorite)
CATEGORIES = [
    ("securite", r"\bhack(s|ed|er|ers)?\b|exploit|stolen|theft|scam|breach|attack|drain|phishing|cybersecurity"),
    ("regulation", r"\bsec\b|regulat|\blaw\b|court|lawsuit|congress|senate|mica|cftc|\bban\b|\btax|legal|\bbill\b"
                   r"|launder|crackdown|sentenced|prison|fatf"),
    ("etf", r"\betfs?\b"),
    ("macro", r"\bfed\b|federal reserve|inflation|\bcpi\b|interest rate|powell|treasury|recession|tariff"
              r"|jobs report|midterm|election"),
    ("adoption", r"tokeni[sz]|stablecoin|\bspac\b|go public|goes public|\bipo\b|adoption"),
    ("entreprise", r"strategy|microstrategy|blackrock|coinbase|binance|tesla|acquires|acquisition|partnership"),
    ("marche", r"price|rally|surge|drop|crash|liquidat|record|all-time high|\bbull|\bbear|whale|rebound|slump"
               r"|outflow|inflow|volatility"),
]

INSERT = """
INSERT INTO evenement_marche (date_heure, categorie, titre) VALUES %s
ON CONFLICT (titre) DO NOTHING
"""
# variation du BTC Binance entre la bougie 5m de la publication et celle une heure plus tard
IMPACT = """
UPDATE evenement_marche e SET impact_score = round((apres.prix_fermeture / avant.prix_fermeture - 1) * 100, 4)
FROM serie_prix avant, serie_prix apres
WHERE e.impact_score IS NULL
  AND avant.plateforme_id = 1 AND avant.instrument_id = 1 AND avant.pas_temps = '5m'
  AND avant.date_heure = date_trunc('hour', e.date_heure)
                         + floor(extract(minute FROM e.date_heure) / 5) * interval '5 minutes'
  AND apres.plateforme_id = 1 AND apres.instrument_id = 1 AND apres.pas_temps = '5m'
  AND apres.date_heure = avant.date_heure + interval '1 hour'
"""


def connect():
    return psycopg2.connect(
        dbname=os.getenv("DB_NAME", "dst_db"),
        user=os.getenv("DB_USER", "daniel"),
        password=os.getenv("DB_PASSWORD", ""),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
    )


def categorie(titre):
    t = titre.lower()
    return next((nom for nom, motif in CATEGORIES if re.search(motif, t)), "autre")


def parse_rss(xml_text):
    """Flux RSS -> [(date_heure UTC naive, categorie, titre)]."""
    rows = []
    for item in ET.fromstring(xml_text).iter("item"):
        titre, date = (item.findtext("title") or "").strip(), item.findtext("pubDate")
        if not titre or not date:
            continue
        d = parsedate_to_datetime(date).astimezone(timezone.utc).replace(tzinfo=None)
        rows.append((d, categorie(titre), titre[:255]))
    return rows


def main():
    rows, erreurs = [], []
    for nom, url in FLUX.items():
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (OPCA collecteur)"})
            r.raise_for_status()
            articles = parse_rss(r.content)
            rows += articles
            print(f"{nom} : {len(articles)} articles.")
        except (requests.RequestException, ET.ParseError, ValueError, TypeError) as e:
            erreurs.append(nom)
            print(f"{nom} : ERREUR {e}")
    if not rows and erreurs:
        sys.exit("aucun flux lisible")
    rows = list({t: (d, c, t) for d, c, t in rows}.values())  # un titre repris par deux flux = une ligne
    if DRY_RUN:
        for d, c, t in sorted(rows)[-5:]:
            print(f"  {d:%d/%m %H:%M} [{c}] {t}")
        print("DRY-RUN : rien n'est ecrit dans evenement_marche.")
        return
    with connect() as conn, conn.cursor() as cur:
        execute_values(cur, INSERT, rows, page_size=max(len(rows), 1))  # rowcount = toutes les lignes
        nouveaux = cur.rowcount
        cur.execute(IMPACT)
        print(f"{nouveaux} nouvel(s) evenement(s) ; impact calcule pour {cur.rowcount} evenement(s).")


if __name__ == "__main__":
    main()
