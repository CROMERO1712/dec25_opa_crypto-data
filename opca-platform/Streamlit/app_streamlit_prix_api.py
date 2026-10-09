import os

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Explorateur de series de prix", page_icon="📈", layout="wide")
st.title("📈 Explorateur de séries de prix")
st.caption("Consultation, filtrage et export des données, via l'API OPCA Crypto Data.")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
LIMITE_API = 5000


@st.cache_data(ttl=60)
def charger_donnees(pas_temps):
    params = {"limit": LIMITE_API}
    if pas_temps:
        params["pas_temps"] = pas_temps
    try:
        r = requests.get(f"{API_BASE_URL}/prices", params=params, timeout=15)
        r.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"API injoignable a {API_BASE_URL}.") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erreur API : {e}") from e
    df = pd.DataFrame(r.json())
    if df.empty:
        return df
    df["date_heure"] = pd.to_datetime(df["date_heure"], errors="coerce")
    for c in ["prix_ouverture", "prix_haut", "prix_bas", "prix_fermeture", "volume", "variation_prix_pct"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["serie"] = df["symbole"] + " (" + df["plateforme"] + ")"
    return df


# Les pas de temps disponibles viennent d'un premier appel sans filtre.
try:
    df_all = charger_donnees(None)
except Exception as e:
    st.error("Impossible de charger les données depuis l'API.")
    st.exception(e)
    st.stop()

if df_all.empty:
    st.warning("Aucune donnée renvoyée par l'API.")
    st.stop()

st.sidebar.header("Filtres")
if st.sidebar.button("🔄 Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

pas_options = sorted(df_all["pas_temps"].dropna().astype(str).unique().tolist())
pas_choisi = st.sidebar.selectbox("Pas de temps", options=pas_options,
                                  index=pas_options.index("5m") if "5m" in pas_options else 0)

df = charger_donnees(pas_choisi)
if df.empty:
    st.warning("Aucune donnée pour ce pas de temps.")
    st.stop()
if len(df) >= LIMITE_API:
    st.info(f"Affichage limité aux {LIMITE_API} lignes les plus récentes renvoyées par l'API.")

plateformes = sorted(df["plateforme"].dropna().unique().tolist())
plateformes_sel = st.sidebar.multiselect("Plateforme", options=plateformes, default=plateformes)
symboles = sorted(df["symbole"].dropna().unique().tolist())
symboles_sel = st.sidebar.multiselect("Instrument", options=symboles, default=symboles)

date_min, date_max = df["date_heure"].min().date(), df["date_heure"].max().date()
plage = st.sidebar.date_input("Période", value=(date_min, date_max), min_value=date_min, max_value=date_max)
debut, fin = (plage if isinstance(plage, tuple) and len(plage) == 2 else (plage, plage))

pmin, pmax = float(df["prix_fermeture"].min()), float(df["prix_fermeture"].max())
prix_min, prix_max = st.sidebar.slider("Prix de fermeture", min_value=pmin, max_value=pmax, value=(pmin, pmax))
volume_min = st.sidebar.number_input("Volume minimum", min_value=0.0, value=0.0, step=1.0)

f = df[df["plateforme"].isin(plateformes_sel) & df["symbole"].isin(symboles_sel)]
f = f[(f["date_heure"].dt.date >= debut) & (f["date_heure"].dt.date <= fin)]
f = f[f["prix_fermeture"].between(prix_min, prix_max)]
f = f[f["volume"].fillna(0) >= volume_min]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Nombre de lignes", f"{len(f):,}".replace(",", " "))
c2.metric("Prix moyen", f"{f['prix_fermeture'].mean():,.2f}" if not f.empty else "N/A")
c3.metric("Prix minimum", f"{f['prix_bas'].min():,.2f}" if not f.empty else "N/A")
c4.metric("Prix maximum", f"{f['prix_haut'].max():,.2f}" if not f.empty else "N/A")

st.subheader("Manipulation des données")
a, b, c = st.columns(3)
with a:
    tri = st.selectbox("Trier par", options=f.columns.tolist(), index=f.columns.tolist().index("date_heure"))
with b:
    ordre = st.radio("Ordre", options=["Décroissant", "Croissant"], horizontal=True)
with c:
    nb = st.number_input("Nombre maximal de lignes affichées", min_value=10, max_value=10000, value=500, step=10)
affiche = f.sort_values(by=tri, ascending=(ordre == "Croissant")).head(int(nb))

t1, t2, t3 = st.tabs(["Tableau", "Graphique", "Statistiques"])
with t1:
    st.dataframe(affiche, use_container_width=True, hide_index=True)
with t2:
    if f.empty:
        st.info("Aucune donnée à afficher avec les filtres sélectionnés.")
    else:
        series_sel = st.multiselect("Séries à représenter", options=sorted(f["serie"].unique().tolist()),
                                    default=sorted(f["serie"].unique().tolist())[:1])
        variable = st.selectbox("Variable", ["prix_fermeture", "prix_ouverture", "prix_haut", "prix_bas",
                                             "volume", "variation_prix_pct"])
        g = f[f["serie"].isin(series_sel)]
        if g.empty:
            st.info("Sélectionne au moins une série.")
        else:
            st.line_chart(g.pivot_table(index="date_heure", columns="serie", values=variable))
with t3:
    cols = ["prix_ouverture", "prix_haut", "prix_bas", "prix_fermeture", "volume", "variation_prix_pct"]
    st.dataframe(f[cols].describe().transpose(), use_container_width=True)

st.subheader("Export")
st.download_button("⬇️ Télécharger les données filtrées en CSV", data=f.to_csv(index=False).encode("utf-8-sig"),
                   file_name="serie_prix_filtree.csv", mime="text/csv")
st.caption(f"Source : API OPCA Crypto Data ({API_BASE_URL}/prices). Aucun accès direct à PostgreSQL.")
