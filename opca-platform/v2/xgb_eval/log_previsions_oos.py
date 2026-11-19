"""Conserve les VRAIES prévisions du XGBoost (hors échantillon) dans prediction_oos, sans jamais les écraser.
Une ligne = une prévision faite à date_reference pour date_cible (= +HORIZON bougies).
On ne prévoit que les lignes SANS cible (la dernière heure) : le modèle ne les a jamais vues.
Réutilise regression_xgboost.py sans le modifier. N'écrit que dans la table prediction_oos (nouvelle base).
OPCA_OOS_DRY=1 : affiche sans rien écrire."""
import os
import pandas as pd
from sqlalchemy import text
import regression_xgboost as rx

F = rx.FEATURES
DDL = [
    """CREATE TABLE IF NOT EXISTS prediction_oos (
         id BIGSERIAL PRIMARY KEY,
         horizon_prediction VARCHAR(50) NOT NULL,
         date_reference TIMESTAMP NOT NULL,
         date_cible TIMESTAMP NOT NULL,
         prix_actuel NUMERIC(18,8),
         prix_predit NUMERIC(18,8) NOT NULL,
         direction_predite VARCHAR(10) NOT NULL,
         genere_le TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
         UNIQUE (horizon_prediction, date_reference))""",
    # Vue d'évaluation : série BTC / Binance = instrument_id 1, plateforme_id 1 (cf. LABEL du script)
    """CREATE OR REPLACE VIEW v_prediction_oos_eval AS
         SELECT o.horizon_prediction, o.date_reference, o.date_cible, o.genere_le,
                o.prix_actuel, o.prix_predit, o.direction_predite,
                s.prix_fermeture AS prix_reel,
                (o.prix_predit - o.prix_actuel) AS variation_predite,
                (s.prix_fermeture - o.prix_actuel) AS variation_reelle
         FROM prediction_oos o
         JOIN serie_prix s ON s.date_heure = o.date_cible
                          AND s.instrument_id = 1 AND s.plateforme_id = 1""",
    """DO $$ BEGIN
         IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'grafana_ro') THEN
           EXECUTE 'GRANT SELECT ON prediction_oos, v_prediction_oos_eval TO grafana_ro';
         END IF;
       END $$""",
]


def main():
    dry = os.getenv("OPCA_OOS_DRY") == "1"
    eng = rx.make_engine()
    with eng.connect() as conn:
        df = pd.read_sql(text(rx.SQL_DATASET), conn,
                         params={"symbole": rx.SYMBOLE, "plateforme": rx.PLATEFORME, "pas_temps": rx.PAS_TEMPS})
    df = df.sort_values("date_heure").reset_index(drop=True)
    df["date_heure"] = pd.to_datetime(df["date_heure"])
    df["prix_fermeture"] = pd.to_numeric(df["prix_fermeture"], errors="coerce").astype(float)
    df[F] = df[F].apply(pd.to_numeric, errors="coerce").astype(float)
    df["cible"] = df["prix_fermeture"].shift(-rx.HORIZON)
    ok = df.dropna(subset=F)
    lab = ok.dropna(subset=["cible"])
    futur = ok[ok["cible"].isna()]
    if len(lab) < rx.MIN_TRAIN or futur.empty:
        print("rien à faire (pas assez de données ou aucune ligne sans cible)")
        return
    model = rx.new_model().fit(lab[F], lab["cible"])
    preds = model.predict(futur[F])
    pas = pd.Timedelta(minutes=int(str(rx.PAS_TEMPS).rstrip("m")))
    rows = [{"h": rx.LABEL, "ref": r.date_heure.to_pydatetime(),
             "cible": (r.date_heure + rx.HORIZON * pas).to_pydatetime(),
             "px": float(r.prix_fermeture), "pred": float(p),
             "dir": "hausse" if p > r.prix_fermeture else "baisse"}
            for r, p in zip(futur.itertuples(), preds)]
    print(f"[{rx.LABEL}] {len(rows)} prévision(s) hors échantillon, de {rows[0]['ref']} à {rows[-1]['ref']}")
    if dry:
        print("DRY : rien n'est écrit.")
        return
    with eng.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
        conn.execute(text(
            """INSERT INTO prediction_oos (horizon_prediction, date_reference, date_cible, prix_actuel, prix_predit, direction_predite)
               VALUES (:h, :ref, :cible, :px, :pred, :dir)
               ON CONFLICT (horizon_prediction, date_reference) DO NOTHING"""), rows)
    print("écriture terminée (les prévisions déjà présentes ne sont jamais modifiées)")


if __name__ == "__main__":
    main()
