"""
Signal de trading OPCA (simulation : aucun ordre n'est passe) a partir de la derniere prevision XGBoost.

  - ACHAT  si hausse prevue et score_confiance >= SEUIL ;
  - VENTE  si baisse prevue et score_confiance >= SEUIL ;
  - ATTENTE sinon (stop_loss / take_profit vides).
stop_loss / take_profit : K_SL et K_TP fois la volatilite attendue sur l'horizon
(volatilite 5m de indicateur_technique x racine(HORIZON)), de part et d'autre du prix d'entree.
Un seul signal par (instrument, date_heure) : relancer le script ne cree aucun doublon.
Contexte : sentiment_id = dernier sentiment connu (Fear & Greed), evenement_id = derniere actualite
publiee dans l'heure precedant le signal (vides s'il n'y en a pas).

Usage : python generer_signaux.py [--dry-run]
Variables : DB_* (comme regression_xgboost.py), SYMBOLE (BTC-USD), PLATEFORME (Binance), PAS_TEMPS (5m),
HORIZON (12), SEUIL (0.55), K_SL (2), K_TP (3).
"""
import math
import os
import sys

ACHAT, VENTE, ATTENTE = "ACHAT", "VENTE", "ATTENTE"


def decider(direction, score, prix, volatilite, seuil=0.55, horizon=12, k_sl=2.0, k_tp=3.0):
    """-> dict(signal, prix_entree, stop_loss, take_profit, score_confiance) ; fonction pure (testable)."""
    sens = {"hausse": 1, "baisse": -1}.get(direction, 0)
    signal = ATTENTE
    if score is not None and score >= seuil and sens:
        signal = ACHAT if sens > 0 else VENTE
    sl = tp = None
    if signal != ATTENTE and volatilite:
        ecart = volatilite * math.sqrt(horizon) * prix  # mouvement typique sur l'horizon, en $
        sl, tp = round(prix - sens * k_sl * ecart, 2), round(prix + sens * k_tp * ecart, 2)
    return {"signal": signal, "prix_entree": prix, "stop_loss": sl, "take_profit": tp,
            "score_confiance": score}


SQL_DERNIERE = """
SELECT pm.prediction_id, pm.date_heure, pm.direction_predite, pm.score_confiance,
       sp.prix_fermeture, sp.instrument_id, it.volatilite
FROM prediction_modele pm
JOIN instrument_marche im ON im.symbole = :symbole
JOIN plateforme p ON p.nom = :plateforme
JOIN serie_prix sp ON sp.instrument_id = im.instrument_id AND sp.plateforme_id = p.plateforme_id
 AND sp.pas_temps = :pas_temps AND sp.date_heure = pm.date_heure
LEFT JOIN indicateur_technique it ON it.instrument_id = sp.instrument_id
 AND it.plateforme_id = sp.plateforme_id AND it.pas_temps = sp.pas_temps AND it.date_heure = sp.date_heure
WHERE pm.horizon_prediction = :label
ORDER BY pm.date_heure DESC LIMIT 1
"""


def main():
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
    dry = "--dry-run" in sys.argv
    symbole, plateforme = os.getenv("SYMBOLE", "BTC-USD"), os.getenv("PLATEFORME", "Binance")
    pas, horizon = os.getenv("PAS_TEMPS", "5m"), int(os.getenv("HORIZON", "12"))
    label = f"{symbole}/{plateforme} {horizon}x{pas}"
    url = URL.create("postgresql+psycopg2", username=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                     host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", "5432")),
                     database=os.getenv("DB_NAME"))
    engine = create_engine(os.getenv("DATABASE_URL", url), pool_pre_ping=True)
    with engine.begin() as conn:
        r = conn.execute(text(SQL_DERNIERE), {"symbole": symbole, "plateforme": plateforme,
                                              "pas_temps": pas, "label": label}).mappings().first()
        if r is None:
            print(f"[{label}] aucune prevision exploitable : pas de signal.")
            return
        s = decider(r["direction_predite"],
                    None if r["score_confiance"] is None else float(r["score_confiance"]),
                    float(r["prix_fermeture"]), None if r["volatilite"] is None else float(r["volatilite"]),
                    float(os.getenv("SEUIL", "0.55")), horizon,
                    float(os.getenv("K_SL", "2")), float(os.getenv("K_TP", "3")))
        print(f"[{label}] {r['date_heure']} : {r['direction_predite']} (confiance {s['score_confiance']}) "
              f"-> {s['signal']} a {s['prix_entree']:.2f} (SL {s['stop_loss']}, TP {s['take_profit']})")
        if dry:
            print("DRY-RUN : rien n'est ecrit dans signal_trading.")
            return
        deja = conn.execute(text("SELECT 1 FROM signal_trading WHERE instrument_id = :i AND date_heure = :d"),
                            {"i": r["instrument_id"], "d": r["date_heure"]}).first()
        if deja:
            print("Signal deja enregistre pour cette bougie.")
            return
        # contexte du signal : dernier sentiment connu, derniere actualite de l'heure ecoulee (sinon NULL)
        conn.execute(text("""
            INSERT INTO signal_trading (date_heure, signal, prix_entree, stop_loss, take_profit,
                                        score_confiance, instrument_id, prediction_id, sentiment_id, evenement_id)
            VALUES (:d, :signal, :prix_entree, :stop_loss, :take_profit, :score_confiance, :i, :p,
                    (SELECT sentiment_id FROM sentiment_social WHERE date_heure <= :d
                     ORDER BY date_heure DESC LIMIT 1),
                    (SELECT evenement_id FROM evenement_marche
                     WHERE date_heure > :d - interval '1 hour' AND date_heure <= :d
                     ORDER BY date_heure DESC LIMIT 1))
        """), {"d": r["date_heure"], "i": r["instrument_id"], "p": r["prediction_id"], **s})
        print("Signal ecrit.")


if __name__ == "__main__":
    main()
