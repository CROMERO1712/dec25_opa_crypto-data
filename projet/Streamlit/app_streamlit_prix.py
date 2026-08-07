import os
from datetime import date

import pandas as pd
import psycopg2
import streamlit as st


# ---------------------------------------------------------
# Configuration de la page
# ---------------------------------------------------------
st.set_page_config(
    page_title="Explorateur de séries de prix",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Explorateur de séries de prix")
st.caption("Consultation, filtrage, manipulation et export des données PostgreSQL.")


# ---------------------------------------------------------
# Connexion PostgreSQL
# Les valeurs peuvent être remplacées par des variables
# d'environnement.
# ---------------------------------------------------------
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "51.44.254.88"),
    "database": os.getenv("DB_NAME", "dst_db"),
    "user": os.getenv("DB_USER", "daniel"),
    "password": os.getenv("DB_PASSWORD", "datascientest"),
    "port": int(os.getenv("DB_PORT", "5432")),
}


@st.cache_data(ttl=60)
def charger_donnees() -> pd.DataFrame:
    """Charge les séries de prix depuis PostgreSQL."""
    requete = """
        SELECT
            date_heure,
            pas_temps,
            prix_ouverture,
            prix_haut,
            prix_bas,
            prix_fermeture,
            volume,
            variation_prix_pct,
            instrument_id
        FROM serie_prix
        ORDER BY date_heure DESC;
    """

    connexion = psycopg2.connect(**DB_CONFIG)

    try:
        df = pd.read_sql_query(requete, connexion)
    finally:
        connexion.close()

    df["date_heure"] = pd.to_datetime(df["date_heure"], errors="coerce")

    colonnes_numeriques = [
        "prix_ouverture",
        "prix_haut",
        "prix_bas",
        "prix_fermeture",
        "volume",
        "variation_prix_pct",
        "instrument_id",
    ]

    for colonne in colonnes_numeriques:
        if colonne in df.columns:
            df[colonne] = pd.to_numeric(df[colonne], errors="coerce")

    return df


# ---------------------------------------------------------
# Chargement des données
# ---------------------------------------------------------
try:
    df = charger_donnees()
except Exception as erreur:
    st.error("Impossible de charger les données depuis PostgreSQL.")
    st.exception(erreur)
    st.stop()

if df.empty:
    st.warning("La table serie_prix ne contient aucune donnée.")
    st.stop()


# ---------------------------------------------------------
# Filtres
# ---------------------------------------------------------
st.sidebar.header("Filtres")

if st.sidebar.button("🔄 Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

instruments = sorted(df["instrument_id"].dropna().unique().tolist())
instruments_selectionnes = st.sidebar.multiselect(
    "Instrument ID",
    options=instruments,
    default=instruments,
)

pas_temps_disponibles = sorted(
    df["pas_temps"].dropna().astype(str).unique().tolist()
)
pas_temps_selectionnes = st.sidebar.multiselect(
    "Pas de temps",
    options=pas_temps_disponibles,
    default=pas_temps_disponibles,
)

date_min = df["date_heure"].min().date()
date_max = df["date_heure"].max().date()

plage_dates = st.sidebar.date_input(
    "Période",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max,
)

prix_min_global = float(df["prix_fermeture"].min())
prix_max_global = float(df["prix_fermeture"].max())

prix_min, prix_max = st.sidebar.slider(
    "Prix de fermeture",
    min_value=prix_min_global,
    max_value=prix_max_global,
    value=(prix_min_global, prix_max_global),
)

volume_min = st.sidebar.number_input(
    "Volume minimum",
    min_value=0.0,
    value=0.0,
    step=1.0,
)


# ---------------------------------------------------------
# Application des filtres
# ---------------------------------------------------------
df_filtre = df.copy()

if instruments_selectionnes:
    df_filtre = df_filtre[
        df_filtre["instrument_id"].isin(instruments_selectionnes)
    ]
else:
    df_filtre = df_filtre.iloc[0:0]

if pas_temps_selectionnes:
    df_filtre = df_filtre[
        df_filtre["pas_temps"].astype(str).isin(pas_temps_selectionnes)
    ]
else:
    df_filtre = df_filtre.iloc[0:0]

if isinstance(plage_dates, tuple) and len(plage_dates) == 2:
    date_debut, date_fin = plage_dates
else:
    date_debut = plage_dates
    date_fin = plage_dates

df_filtre = df_filtre[
    (df_filtre["date_heure"].dt.date >= date_debut)
    & (df_filtre["date_heure"].dt.date <= date_fin)
]

df_filtre = df_filtre[
    df_filtre["prix_fermeture"].between(prix_min, prix_max, inclusive="both")
]

df_filtre = df_filtre[df_filtre["volume"].fillna(0) >= volume_min]


# ---------------------------------------------------------
# Indicateurs
# ---------------------------------------------------------
col1, col2, col3, col4 = st.columns(4)

col1.metric("Nombre de lignes", f"{len(df_filtre):,}".replace(",", " "))
col2.metric(
    "Prix moyen",
    f"{df_filtre['prix_fermeture'].mean():,.2f}"
    if not df_filtre.empty
    else "N/A",
)
col3.metric(
    "Prix minimum",
    f"{df_filtre['prix_bas'].min():,.2f}" if not df_filtre.empty else "N/A",
)
col4.metric(
    "Prix maximum",
    f"{df_filtre['prix_haut'].max():,.2f}" if not df_filtre.empty else "N/A",
)


# ---------------------------------------------------------
# Manipulation simple
# ---------------------------------------------------------
st.subheader("Manipulation des données")

col_tri, col_ordre, col_nb = st.columns(3)

with col_tri:
    colonne_tri = st.selectbox(
        "Trier par",
        options=df_filtre.columns.tolist(),
        index=df_filtre.columns.tolist().index("date_heure"),
    )

with col_ordre:
    ordre = st.radio(
        "Ordre",
        options=["Décroissant", "Croissant"],
        horizontal=True,
    )

with col_nb:
    nombre_lignes = st.number_input(
        "Nombre maximal de lignes affichées",
        min_value=10,
        max_value=10000,
        value=500,
        step=10,
    )

df_affiche = df_filtre.sort_values(
    by=colonne_tri,
    ascending=(ordre == "Croissant"),
).head(int(nombre_lignes))


# ---------------------------------------------------------
# Onglets d'affichage
# ---------------------------------------------------------
onglet_tableau, onglet_graphique, onglet_stats = st.tabs(
    ["Tableau", "Graphique", "Statistiques"]
)

with onglet_tableau:
    st.dataframe(
        df_affiche,
        use_container_width=True,
        hide_index=True,
    )

with onglet_graphique:
    if df_filtre.empty:
        st.info("Aucune donnée à afficher avec les filtres sélectionnés.")
    else:
        instruments_graphique = sorted(
            df_filtre["instrument_id"].dropna().unique().tolist()
        )

        instrument_graphique = st.selectbox(
            "Instrument à représenter",
            options=instruments_graphique,
        )

        variable_graphique = st.selectbox(
            "Variable",
            options=[
                "prix_fermeture",
                "prix_ouverture",
                "prix_haut",
                "prix_bas",
                "volume",
                "variation_prix_pct",
            ],
        )

        df_graphique = (
            df_filtre[df_filtre["instrument_id"] == instrument_graphique]
            .sort_values("date_heure")
            .set_index("date_heure")
        )

        st.line_chart(df_graphique[variable_graphique])

with onglet_stats:
    colonnes_stats = [
        "prix_ouverture",
        "prix_haut",
        "prix_bas",
        "prix_fermeture",
        "volume",
        "variation_prix_pct",
    ]
    st.dataframe(
        df_filtre[colonnes_stats].describe().transpose(),
        use_container_width=True,
    )


# ---------------------------------------------------------
# Export
# ---------------------------------------------------------
st.subheader("Export")

csv = df_filtre.to_csv(index=False).encode("utf-8-sig")

st.download_button(
    label="⬇️ Télécharger les données filtrées en CSV",
    data=csv,
    file_name="serie_prix_filtree.csv",
    mime="text/csv",
)

st.caption(
    "Conseil : utilise des variables d’environnement pour éviter de conserver "
    "le mot de passe PostgreSQL directement dans le fichier."
)
