import os
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import create_engine, text

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "dst_db")
DB_USER = os.getenv("DB_USER", "daniel")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

app = FastAPI(
    title="OPCA Crypto Data API",
    description="Point d'acces unique a dst_db (PostgreSQL).",
    version="1.1.0",
)


def clean(df):
    """NaN -> None pour que la reponse soit du JSON valide."""
    return df.astype(object).where(pd.notna(df), None)


def run_query(sql: str, params: Optional[dict] = None) -> pd.DataFrame:
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Erreur base de donnees : {exc}") from exc


def serie(table, alias, cols, symbole, plateforme, pas_temps, limit):
    """Lecture d'une table de serie (prix, indicateurs, activite) avec instrument et plateforme."""
    sql = (
        f"SELECT {cols}, im.symbole, p.nom AS plateforme "
        f"FROM {table} {alias} "
        f"JOIN instrument_marche im ON im.instrument_id = {alias}.instrument_id "
        f"JOIN plateforme p ON p.plateforme_id = {alias}.plateforme_id "
        "WHERE 1=1 "
    )
    params = {"limit": limit}
    if symbole:
        sql += "AND im.symbole = :symbole "
        params["symbole"] = symbole
    if plateforme:
        sql += "AND p.nom = :plateforme "
        params["plateforme"] = plateforme
    if pas_temps:
        sql += f"AND {alias}.pas_temps = :pas_temps "
        params["pas_temps"] = pas_temps
    sql += f"ORDER BY {alias}.date_heure DESC LIMIT :limit"
    return run_query(sql, params).pipe(clean).to_dict(orient="records")


@app.get("/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": DB_NAME, "host": DB_HOST}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Base injoignable : {exc}") from exc


@app.get("/snapshot")
def snapshot():
    tables = [
        "plateforme", "instrument_marche", "serie_prix", "activite_marche",
        "indicateur_technique", "sentiment_social", "evenement_marche",
        "prediction_modele", "signal_trading",
    ]
    counts = {}
    for t in tables:
        df = run_query(f"SELECT count(*) AS n FROM {t}")
        counts[t] = int(df["n"].iloc[0])
    last = run_query(
        "SELECT im.symbole, p.nom AS plateforme, sp.date_heure, sp.prix_fermeture "
        "FROM serie_prix sp "
        "JOIN instrument_marche im ON im.instrument_id = sp.instrument_id "
        "JOIN plateforme p ON p.plateforme_id = sp.plateforme_id "
        "ORDER BY sp.date_heure DESC LIMIT 6"
    )
    return {"counts": counts, "derniers_prix": last.pipe(clean).to_dict(orient="records")}


@app.get("/platforms")
def platforms():
    return run_query("SELECT plateforme_id, nom FROM plateforme ORDER BY nom").pipe(clean).to_dict(orient="records")


@app.get("/instruments")
def instruments():
    return run_query(
        "SELECT instrument_id, symbole, actif, devise_cotation FROM instrument_marche ORDER BY symbole, instrument_id"
    ).pipe(clean).to_dict(orient="records")


@app.get("/prices")
def prices(
    symbole: Optional[str] = Query(None),
    plateforme: Optional[str] = Query(None),
    pas_temps: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    cols = (
        "sp.date_heure, sp.pas_temps, sp.prix_ouverture, sp.prix_haut, sp.prix_bas, "
        "sp.prix_fermeture, sp.volume, sp.variation_prix_pct"
    )
    return serie("serie_prix", "sp", cols, symbole, plateforme, pas_temps, limit)


@app.get("/indicators")
def indicators(
    symbole: Optional[str] = Query(None),
    plateforme: Optional[str] = Query(None),
    pas_temps: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    cols = "it.date_heure, it.pas_temps, it.sma_20, it.sma_50, it.rsi_14, it.macd, it.volatilite"
    return serie("indicateur_technique", "it", cols, symbole, plateforme, pas_temps, limit)


@app.get("/activity")
def activity(
    symbole: Optional[str] = Query(None),
    plateforme: Optional[str] = Query(None),
    pas_temps: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=5000),
):
    cols = (
        "am.date_heure, am.pas_temps, am.volume_total, am.nombre_trades, "
        "am.ratio_achat_vente, am.liquidite_score"
    )
    return serie("activite_marche", "am", cols, symbole, plateforme, pas_temps, limit)


@app.get("/sentiment")
def sentiment(limit: int = Query(200, ge=1, le=2000)):
    return run_query(
        "SELECT date_heure, source, score_sentiment, nombre_messages, score_engagement "
        "FROM sentiment_social ORDER BY date_heure DESC LIMIT :limit",
        {"limit": limit},
    ).pipe(clean).to_dict(orient="records")


@app.get("/events")
def events(limit: int = Query(200, ge=1, le=2000)):
    return run_query(
        "SELECT date_heure, categorie, titre, impact_score "
        "FROM evenement_marche ORDER BY date_heure DESC LIMIT :limit",
        {"limit": limit},
    ).pipe(clean).to_dict(orient="records")


@app.get("/predictions")
def predictions(limit: int = Query(200, ge=1, le=2000)):
    return run_query(
        "SELECT prediction_id, date_heure, horizon_prediction, prix_predit, "
        "direction_predite, score_confiance "
        "FROM prediction_modele ORDER BY date_heure DESC LIMIT :limit",
        {"limit": limit},
    ).pipe(clean).to_dict(orient="records")


@app.get("/signals")
def signals(symbole: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=2000)):
    sql = (
        "SELECT st.date_heure, st.signal, st.prix_entree, st.stop_loss, "
        "st.take_profit, st.score_confiance, im.symbole "
        "FROM signal_trading st JOIN instrument_marche im ON im.instrument_id = st.instrument_id "
        "WHERE 1=1 "
    )
    params = {"limit": limit}
    if symbole:
        sql += "AND im.symbole = :symbole "
        params["symbole"] = symbole
    sql += "ORDER BY st.date_heure DESC LIMIT :limit"
    return run_query(sql, params).pipe(clean).to_dict(orient="records")


@app.get("/correlations")
def correlations(pas_temps: str = Query("5m"), limit: int = Query(4000, ge=10, le=40000)):
    df = run_query(
        "SELECT sp.date_heure, im.symbole || ' (' || p.nom || ')' AS serie, sp.prix_fermeture "
        "FROM serie_prix sp "
        "JOIN instrument_marche im ON im.instrument_id = sp.instrument_id "
        "JOIN plateforme p ON p.plateforme_id = sp.plateforme_id "
        "WHERE sp.pas_temps = :pas_temps ORDER BY sp.date_heure DESC LIMIT :limit",
        {"pas_temps": pas_temps, "limit": limit},
    )
    if df.empty:
        raise HTTPException(status_code=404, detail="Pas de donnees pour ce pas de temps.")
    pivot = df.pivot_table(index="date_heure", columns="serie", values="prix_fermeture")
    if pivot.shape[1] < 2:
        raise HTTPException(status_code=404, detail="Moins de 2 series pour ce pas de temps.")
    corr = pivot.pct_change().corr()
    return {"series": list(corr.columns), "matrix": corr.round(4).fillna(0).values.tolist()}
