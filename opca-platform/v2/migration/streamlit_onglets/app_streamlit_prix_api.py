"""
Tableau de bord OPCA Crypto Data (Streamlit), alimenté uniquement par l'API (aucun accès direct à PostgreSQL).

Onglets : Vue d'ensemble · Prix · Activité de marché · Indicateurs techniques · Prévisions.
Optimisations par rapport à la version d'une seule page :
  - un appel API par série (symbole + plateforme) au lieu d'un appel pour toutes les séries,
    ce qui donne jusqu'à 5 000 bougies (≈ 17 jours en 5 min) pour CHAQUE série ;
  - résultats mis en cache 5 min (bouton « Actualiser » pour forcer) et connexion HTTP réutilisée ;
  - chaque onglet ne charge que ce qu'il affiche.
Les dates sont en UTC, comme dans la base.
"""
import os
from datetime import timedelta

import altair as alt
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="OPCA Crypto Data", page_icon="📈", layout="wide")

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PAS = "5m"
LIMITE = 5000              # maximum accepté par l'API par appel
CACHE_S = 300
RETARD_MAX_MIN = 75        # la collecte tourne chaque heure (à :10) : au-delà, elle est en retard
PERIODES = {"24 heures": 1, "3 jours": 3, "7 jours": 7, "Tout (≈ 17 jours)": None}
COLONNES_TEXTE = {"date_heure", "pas_temps", "symbole", "plateforme", "horizon_prediction", "direction_predite"}


# --- Accès à l'API ---------------------------------------------------------------------------------
@st.cache_resource
def session_http():
    return requests.Session()


def appel(chemin, **params):
    try:
        r = session_http().get(f"{API_BASE_URL}{chemin}",
                               params={k: v for k, v in params.items() if v is not None}, timeout=20)
        r.raise_for_status()
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(f"API injoignable à {API_BASE_URL}.") from e
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Erreur API sur {chemin} : {e}") from e
    return r.json()


def en_tableau(lignes):
    df = pd.DataFrame(lignes)
    if df.empty:
        return df
    df["date_heure"] = pd.to_datetime(df["date_heure"], errors="coerce")
    for c in df.columns:
        if c not in COLONNES_TEXTE:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date_heure").reset_index(drop=True)


@st.cache_data(ttl=60, show_spinner=False)
def instantane():
    return appel("/snapshot")


@st.cache_data(ttl=CACHE_S, show_spinner="Chargement des données…")
def serie(chemin, symbole, plateforme):
    """/prices, /indicators ou /activity pour une seule série, au pas de 5 min."""
    return en_tableau(appel(chemin, symbole=symbole, plateforme=plateforme, pas_temps=PAS, limit=LIMITE))


@st.cache_data(ttl=CACHE_S, show_spinner="Chargement des prévisions…")
def previsions():
    return en_tableau(appel("/predictions", limit=2000))


@st.cache_data(ttl=3600, show_spinner=False)
def series_disponibles():
    """Couples (symbole, plateforme) qui ont des prix, triés : BTC/ETH/SOL Binance puis Coinbase."""
    couples, symboles = set(), {x["symbole"] for x in appel("/instruments")}
    for p in appel("/platforms"):
        for i in symboles:
            if appel("/prices", symbole=i, plateforme=p["nom"], pas_temps=PAS, limit=1):
                couples.add((i, p["nom"]))
    return sorted(couples, key=lambda c: (c[1] != "Binance", c[1], c[0]))


def nom(couple):
    return f"{couple[0]} ({couple[1]})"


def sur_periode(df, jours):
    if df.empty or jours is None:
        return df
    return df[df["date_heure"] > df["date_heure"].max() - timedelta(days=jours)]


# --- Graphiques ------------------------------------------------------------------------------------
MARGES = {"left": 12, "right": 8, "top": 6, "bottom": 4}  # évite que les étiquettes de l'axe Y soient coupées


def courbes(df, y, titre_y, couleur=None, format_y=",.2f", seuils=(), hauteur=300, zero=False, palette=None):
    """Courbe(s) temporelle(s) avec infobulle ; seuils = lignes horizontales en pointillés."""
    enc = dict(x=alt.X("date_heure:T", title=None),
               y=alt.Y(f"{y}:Q", title=titre_y, scale=alt.Scale(zero=zero)),
               tooltip=[alt.Tooltip("date_heure:T", title="date (UTC)", format="%d/%m %H:%M"),
                        alt.Tooltip(f"{y}:Q", title=titre_y, format=format_y)])
    if couleur:
        echelle = alt.Scale(domain=list(palette), range=list(palette.values())) if palette else alt.Undefined
        enc["color"] = alt.Color(f"{couleur}:N", title=None, scale=echelle, legend=alt.Legend(orient="top"))
        enc["tooltip"].insert(0, alt.Tooltip(f"{couleur}:N", title="série"))
    graphe = alt.Chart(df).mark_line(strokeWidth=2).encode(**enc)
    for valeur in seuils:
        graphe += alt.Chart(pd.DataFrame({"s": [valeur]})).mark_rule(
            strokeDash=[4, 4], color="#9a9a9a").encode(y="s:Q")
    st.altair_chart(graphe.properties(height=hauteur, padding=MARGES).interactive(bind_y=False),
                    use_container_width=True)


def barres(df, y, titre_y, format_y=",.0f", hauteur=260):
    graphe = alt.Chart(df).mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2).encode(
        x=alt.X("date_heure:T", title=None), y=alt.Y(f"{y}:Q", title=titre_y, axis=alt.Axis(format="~s")),
        tooltip=[alt.Tooltip("date_heure:T", title="heure (UTC)", format="%d/%m %H:%M"),
                 alt.Tooltip(f"{y}:Q", title=titre_y, format=format_y)])
    st.altair_chart(graphe.properties(height=hauteur, padding=MARGES), use_container_width=True)


def fmt(x, dec=2, suffixe=""):
    return "N/A" if pd.isna(x) else f"{x:,.{dec}f}".replace(",", " ") + suffixe


# --- Barre latérale --------------------------------------------------------------------------------
st.title("📈 OPCA Crypto Data")
try:
    SERIES = series_disponibles()
except Exception as e:
    st.error("Impossible de joindre l'API.")
    st.exception(e)
    st.stop()
if not SERIES:
    st.warning("L'API ne renvoie aucune série de prix.")
    st.stop()

st.sidebar.header("Réglages")
periode = st.sidebar.radio("Période affichée", list(PERIODES), index=1)
JOURS = PERIODES[periode]
SERIE = st.sidebar.selectbox("Série (onglets Prix et Indicateurs)", SERIES, format_func=nom)
if st.sidebar.button("🔄 Actualiser les données", use_container_width=True):
    st.cache_data.clear()
    st.rerun()
st.sidebar.caption(f"Source : API OPCA ({API_BASE_URL}). Dates en UTC. "
                   f"Données mises en cache {CACHE_S // 60} min ; la collecte a lieu chaque heure à :10.")

o1, o2, o3, o4, o5 = st.tabs(["🏠 Vue d'ensemble", "💹 Prix", "📊 Activité de marché",
                              "📐 Indicateurs techniques", "🔮 Prévisions"])

# --- 1. Vue d'ensemble -----------------------------------------------------------------------------
with o1:
    snap = instantane()
    n = snap.get("counts", {})
    c = st.columns(4)
    c[0].metric("Bougies de prix", fmt(n.get("serie_prix", 0), 0))
    c[1].metric("Activité de marché", fmt(n.get("activite_marche", 0), 0))
    c[2].metric("Indicateurs techniques", fmt(n.get("indicateur_technique", 0), 0))
    c[3].metric("Prévisions XGBoost", fmt(n.get("prediction_modele", 0), 0))

    st.subheader("Dernier prix et fraîcheur de la collecte")
    maintenant = pd.Timestamp.now(tz="UTC").tz_localize(None)
    lignes, normalises = [], []
    for couple in SERIES:
        p = serie("/prices", *couple)
        if p.empty:
            continue
        der = p.iloc[-1]
        il_y_a_24h = p[p["date_heure"] <= der["date_heure"] - timedelta(hours=24)]
        ref = il_y_a_24h["prix_fermeture"].iloc[-1] if not il_y_a_24h.empty else float("nan")
        retard = (maintenant - der["date_heure"]).total_seconds() / 60
        lignes.append({"Série": nom(couple), "Dernier prix": der["prix_fermeture"],
                       "Variation 24 h (%)": 100 * (der["prix_fermeture"] / ref - 1),
                       "Dernière bougie (UTC)": der["date_heure"].strftime("%d/%m %H:%M"),
                       "État": "✅ à jour" if retard <= RETARD_MAX_MIN else f"⚠️ en retard ({retard:.0f} min)"})
        q = sur_periode(p, JOURS)[["date_heure", "prix_fermeture"]].copy()
        q["base_100"] = 100 * q["prix_fermeture"] / q["prix_fermeture"].iloc[0]
        q["série"] = nom(couple)
        normalises.append(q)
    st.dataframe(pd.DataFrame(lignes), hide_index=True, use_container_width=True,
                 column_config={"Dernier prix": st.column_config.NumberColumn(format="%.2f"),
                                "Variation 24 h (%)": st.column_config.NumberColumn(format="%+.2f %%")})

    st.subheader(f"Évolution comparée ({periode}, base 100 au début de la période)")
    if normalises:
        courbes(pd.concat(normalises), "base_100", "base 100", couleur="série", format_y=".2f", seuils=(100,))
    vides = [t for t, v in n.items() if v == 0]
    if vides:
        st.info("Tables encore vides (aucune source branchée) : " + ", ".join(f"`{t}`" for t in vides) + ".")

# --- 2. Prix ---------------------------------------------------------------------------------------
with o2:
    choix = st.multiselect("Séries", SERIES, default=[SERIE], format_func=nom)
    variable = st.selectbox("Variable", ["prix_fermeture", "prix_ouverture", "prix_haut", "prix_bas",
                                         "volume", "variation_prix_pct"])
    if not choix:
        st.info("Sélectionne au moins une série.")
    else:
        df = pd.concat([sur_periode(serie("/prices", *s), JOURS).assign(série=nom(s)) for s in choix])
        if len(choix) > 1 and variable.startswith("prix"):
            st.caption("Les prix de séries différentes n'ont pas la même échelle : "
                       "l'onglet « Vue d'ensemble » les compare en base 100.")
        courbes(df, variable, variable.replace("_", " "), couleur="série" if len(choix) > 1 else None)

        a = df[df["série"] == nom(choix[0])]
        c = st.columns(4)
        c[0].metric("Bougies affichées", fmt(len(df), 0))
        c[1].metric(f"Prix moyen {choix[0][0]}", fmt(a["prix_fermeture"].mean()))
        c[2].metric("Plus bas", fmt(a["prix_bas"].min()))
        c[3].metric("Plus haut", fmt(a["prix_haut"].max()))

        with st.expander("Tableau, statistiques et export"):
            t1, t2 = st.columns([3, 1])
            ordre = t2.radio("Ordre", ["Plus récentes d'abord", "Plus anciennes d'abord"])
            nb = t1.slider("Lignes affichées", 50, 5000, 500, step=50)
            st.dataframe(df.sort_values("date_heure", ascending=ordre.startswith("Plus anciennes")).head(nb),
                         hide_index=True, use_container_width=True)
            num = ["prix_ouverture", "prix_haut", "prix_bas", "prix_fermeture", "volume", "variation_prix_pct"]
            st.dataframe(df.groupby("série")[num].describe().transpose(), use_container_width=True)
            st.download_button("⬇️ Télécharger en CSV", df.to_csv(index=False).encode("utf-8-sig"),
                               file_name="serie_prix.csv", mime="text/csv")

# --- 3. Activité de marché -------------------------------------------------------------------------
with o3:
    binance = [s for s in SERIES if s[1] == "Binance"]
    st.caption("Source : bougies Binance (volume en USDT, nombre de transactions, part des achats). "
               "Coinbase ne fournit pas ces informations.")
    paire = st.radio("Paire", binance, format_func=lambda s: s[0], horizontal=True)
    act = sur_periode(serie("/activity", *paire), JOURS)
    if act.empty:
        st.warning("Aucune donnée d'activité pour cette paire.")
    else:
        h = (act.set_index("date_heure")
             .resample("1h").agg({"volume_total": "sum", "nombre_trades": "sum", "ratio_achat_vente": "mean"})
             .reset_index())
        derniere_24h = act[act["date_heure"] > act["date_heure"].max() - timedelta(hours=24)]
        c = st.columns(3)
        c[0].metric("Volume 24 h (USDT)", fmt(derniere_24h["volume_total"].sum() / 1e6, 1, " M"))
        c[1].metric("Transactions 24 h", fmt(derniere_24h["nombre_trades"].sum(), 0))
        part = derniere_24h["ratio_achat_vente"].mean()
        c[2].metric("Part des achats 24 h · " + ("acheteurs majoritaires" if part > 0.5 else "vendeurs majoritaires"),
                    fmt(100 * part, 1, " %"))

        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**Volume échangé par heure (USDT)**")
            barres(h, "volume_total", "USDT")
        with g2:
            st.markdown("**Transactions par heure**")
            barres(h, "nombre_trades", "transactions")
        st.markdown("**Part des achats (moyenne horaire)** - au-dessus de 50 %, les acheteurs dominent")
        courbes(h, "ratio_achat_vente", "part des achats", format_y=".1%", seuils=(0.5,), hauteur=240)

        st.markdown("**Comparaison des paires sur la période**")
        comp = []
        for s in binance:
            x = sur_periode(serie("/activity", *s), JOURS)
            comp.append({"Paire": s[0], "Volume (M USDT)": x["volume_total"].sum() / 1e6,
                         "Transactions": x["nombre_trades"].sum(),
                         "Part des achats (%)": 100 * x["ratio_achat_vente"].mean(),
                         "Score de liquidité moyen": x["liquidite_score"].mean()})
        st.dataframe(pd.DataFrame(comp), hide_index=True, use_container_width=True,
                     column_config={"Volume (M USDT)": st.column_config.NumberColumn(format="%.1f"),
                                    "Transactions": st.column_config.NumberColumn(format="%d"),
                                    "Part des achats (%)": st.column_config.NumberColumn(format="%.1f"),
                                    "Score de liquidité moyen": st.column_config.NumberColumn(format="%.2f")})

# --- 4. Indicateurs techniques ---------------------------------------------------------------------
with o4:
    st.caption(f"Série : **{nom(SERIE)}** (à changer dans la barre latérale).")
    ind = sur_periode(serie("/indicators", *SERIE), JOURS)
    prix = sur_periode(serie("/prices", *SERIE), JOURS)
    if ind.empty:
        st.warning("Aucun indicateur pour cette série.")
    else:
        d = ind.iloc[-1]
        rsi = d["rsi_14"]
        etat = "surachat" if rsi > 70 else "survente" if rsi < 30 else "zone neutre"
        c = st.columns(4)
        c[0].metric(f"RSI 14 · {etat}", fmt(rsi, 1))
        c[1].metric("MACD · " + ("haussier" if d["macd"] > 0 else "baissier"), fmt(d["macd"], 3))
        c[2].metric("Tendance (SMA 20 / SMA 50)", "haussière" if d["sma_20"] > d["sma_50"] else "baissière",
                    help="Moyenne courte au-dessus de la longue = tendance haussière.")
        c[3].metric("Volatilité (20 bougies)", fmt(100 * d["volatilite"], 3, " %"))

        st.markdown("**Prix et moyennes mobiles**")
        m = prix[["date_heure", "prix_fermeture"]].merge(ind[["date_heure", "sma_20", "sma_50"]], on="date_heure")
        m = m.rename(columns={"prix_fermeture": "prix", "sma_20": "SMA 20", "sma_50": "SMA 50"})
        courbes(m.melt("date_heure", var_name="courbe", value_name="valeur"), "valeur", "prix", couleur="courbe",
                palette={"prix": "#3b4252", "SMA 20": "#e8833a", "SMA 50": "#2a7fd4"})
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("**RSI 14** - au-dessus de 70 : surachat, en dessous de 30 : survente")
            courbes(ind, "rsi_14", "RSI", format_y=".1f", seuils=(30, 70), hauteur=240)
        with g2:
            st.markdown("**MACD (12/26)**")
            courbes(ind, "macd", "MACD", format_y=".4f", seuils=(0,), hauteur=240)
        st.markdown("**Volatilité (écart-type des rendements sur 20 bougies)**")
        courbes(ind, "volatilite", "volatilité", format_y=".4%", hauteur=220, zero=True)

# --- 5. Prévisions ---------------------------------------------------------------------------------
with o5:
    pr = previsions()
    if pr.empty:
        st.warning("Aucune prévision renvoyée par l'API.")
    else:
        etiquette = st.selectbox("Modèle", sorted(pr["horizon_prediction"].unique()))
        p = pr[pr["horizon_prediction"] == etiquette].copy()
        # Étiquette « BTC-USD/Binance 12x5m » : prévision à 12 bougies de 5 min = 1 h
        sym, reste = etiquette.split("/", 1)
        plat, pas = reste.split(" ", 1)
        horizon = timedelta(minutes=int(pas.split("x")[0]) * int(pas.split("x")[1].rstrip("m")))
        reel = serie("/prices", sym, plat)[["date_heure", "prix_fermeture"]]
        p["date_cible"] = p["date_heure"] + horizon
        p = (p.merge(reel.rename(columns={"prix_fermeture": "prix_au_depart"}), on="date_heure", how="left")
              .merge(reel.rename(columns={"date_heure": "date_cible", "prix_fermeture": "prix_reel"}),
                     on="date_cible", how="left"))
        derniere = p.iloc[-1]
        p = sur_periode(p, JOURS)
        ev = p.dropna(subset=["prix_reel", "prix_au_depart"])
        ev = ev[ev["date_cible"] < reel["date_heure"].max()]  # la dernière bougie peut être incomplète

        st.info(f"Dernière prévision ({derniere['date_heure']:%d/%m %H:%M} UTC) : "
                f"**{fmt(derniere['prix_predit'])} USD** attendus à {derniere['date_cible']:%H:%M} UTC "
                f"({derniere['direction_predite']}, prix au départ {fmt(derniere['prix_au_depart'])} USD).")
        st.warning("⚠️ Ces chiffres sont **optimistes** : les prévisions de cette table sont recalculées chaque heure "
                   "sur les dernières 24 h, avec un modèle qui a déjà vu une partie de ces prix. La seule mesure fiable "
                   "est l'évaluation hors échantillon (table prediction_oos, vue v_prediction_oos_eval), où le modèle "
                   "fait jusqu'ici moins bien que la prévision naïve. Cette évaluation n'est pas encore exposée par l'API.")
        if not ev.empty:
            st.markdown(f"**Évaluation sur la période ({periode}, prévisions recalculées)**")
            mae_modele = (ev["prix_predit"] - ev["prix_reel"]).abs().mean()
            mae_naive = (ev["prix_au_depart"] - ev["prix_reel"]).abs().mean()
            sens_ok = ((ev["prix_predit"] > ev["prix_au_depart"]) == (ev["prix_reel"] > ev["prix_au_depart"])).mean()
            c = st.columns(4)
            c[0].metric("Erreur moyenne du modèle", fmt(mae_modele, 0, " $"))
            c[1].metric("Erreur de la prévision naïve", fmt(mae_naive, 0, " $"),
                        help="Prévision naïve : le prix dans 1 h sera le prix actuel.")
            c[2].metric("Bonne direction", fmt(100 * sens_ok, 1, " %"), help="50 % = pile ou face.")
            c[3].metric("Prévisions évaluées", fmt(len(ev), 0))
            if mae_modele > mae_naive:
                st.error("Même sur ces prévisions recalculées, le modèle fait moins bien que la prévision naïve.")

        st.markdown("**Prix réel et prix prévu** (la prévision est placée à l'heure qu'elle vise)")
        g = pd.concat([
            reel[reel["date_heure"] >= p["date_cible"].min()].rename(columns={"prix_fermeture": "prix"})
            .assign(courbe="prix réel"),
            p[["date_cible", "prix_predit"]].rename(columns={"date_cible": "date_heure", "prix_predit": "prix"})
            .assign(courbe="prix prévu"),
        ])
        courbes(g, "prix", "prix (USD)", couleur="courbe",
                palette={"prix réel": "#3b4252", "prix prévu": "#e8833a"})
        with st.expander("Détail des prévisions"):
            st.dataframe(p.sort_values("date_heure", ascending=False), hide_index=True, use_container_width=True)
