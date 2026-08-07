import pandas as pd
import psycopg2

# ===========================
# Connexion à PostgreSQL
# ===========================
conn = psycopg2.connect(
    host="51.44.254.88",
    database="dst_db",
    user="daniel",
    password="datascientest",
    port=5432
)

# ===========================
# Lecture des données
# ===========================
requete = """
SELECT *
FROM serie_prix
ORDER BY date_heure;
"""

df = pd.read_sql_query(requete, conn)

# Fermeture de la connexion
conn.close()

# ===========================
# Informations
# ===========================
print("Nombre de lignes :", len(df))
print("Nombre de colonnes :", len(df.columns))

# ===========================
# Affichage des 50 premières lignes
# ===========================
pd.set_option('display.max_rows', 100)
pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', None)

print(df.head(50))

df.head(100).to_excel(
    "serie_prix.xlsx",
    index=False,
    engine="openpyxl"
)
