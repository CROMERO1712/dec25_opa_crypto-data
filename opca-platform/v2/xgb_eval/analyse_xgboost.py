"""Évaluation HONNÊTE du XGBoost de regression_xgboost.py (lecture seule : aucune écriture en base).
Réutilise le module existant (mêmes variables, même SQL, mêmes hyperparamètres) sans le modifier.
Compare à la référence naïve « le prix dans 1 h = le prix actuel »."""
import json
import numpy as np
import pandas as pd
from sqlalchemy import text
from sklearn.metrics import mean_absolute_error, mean_squared_error
import regression_xgboost as rx

F = rx.FEATURES


def charger():
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
    return ok, ok.dropna(subset=["cible"]).copy()


def mesures(nom, test, pred):
    y, c = test["cible"].to_numpy(float), test["prix_fermeture"].to_numpy(float)
    vr, vp = y - c, pred - c
    nz = vr != 0
    dir_modele = float(np.mean(np.sign(vp[nz]) == np.sign(vr[nz])))
    part_hausse = float(np.mean(vr[nz] > 0))
    jours = pd.DataFrame({"jour": test["date_heure"].dt.date.values,
                          "em": np.abs(y - pred), "en": np.abs(y - c)}).groupby("jour")[["em", "en"]].mean()
    return {
        "scenario": nom, "n_test": int(len(test)),
        "debut_test": str(test["date_heure"].min()), "fin_test": str(test["date_heure"].max()),
        "MAE_modele": float(mean_absolute_error(y, pred)),
        "RMSE_modele": float(np.sqrt(mean_squared_error(y, pred))),
        "MAE_naive": float(mean_absolute_error(y, c)),
        "RMSE_naive": float(np.sqrt(mean_squared_error(y, c))),
        "precision_direction": dir_modele,
        "direction_toujours_majoritaire": max(part_hausse, 1 - part_hausse),
        "correlation_variation_predite_reelle": float(np.corrcoef(vp, vr)[0, 1]),
        "jours_ou_le_modele_bat_la_naive": f"{int((jours.em < jours.en).sum())}/{len(jours)}",
    }


def main():
    ok, lab = charger()
    print(f"Lignes avec cible : {len(lab)} ({lab['date_heure'].min()} -> {lab['date_heure'].max()})")
    split = int(len(lab) * 0.8)
    res = []
    # A : découpage du script d'origine (80/20 chronologique, sans écart)
    tr, te = lab.iloc[:split], lab.iloc[split:]
    res.append(mesures("A - test chronologique 80/20 (script d'origine)", te,
                       rx.new_model().fit(tr[F], tr["cible"]).predict(te[F])))
    # B : même chose avec un écart de HORIZON lignes (les cibles de fin d'entraînement chevauchent le test)
    tr = lab.iloc[:split - rx.HORIZON]
    res.append(mesures(f"B - test 80/20 avec écart de {rx.HORIZON} lignes", te,
                       rx.new_model().fit(tr[F], tr["cible"]).predict(te[F])))
    # C : ce que la table prediction_modele contient réellement (modèle entraîné sur tout, évalué sur la fenêtre)
    mod = rx.new_model().fit(lab[F], lab["cible"])
    fen = ok.tail(rx.PRED_WINDOW).dropna(subset=["cible"])
    res.append(mesures("C - fenêtre de prediction_modele (EN ÉCHANTILLON, flatteur)", fen, mod.predict(fen[F])))
    print(json.dumps(res, indent=2, ensure_ascii=False))
    print("\n===== SYNTHÈSE =====")
    for r in res:
        gain = 100 * (1 - r["MAE_modele"] / r["MAE_naive"])
        print(f"{r['scenario']}\n   MAE modèle {r['MAE_modele']:.0f} $ | MAE naïve {r['MAE_naive']:.0f} $ | gain {gain:+.1f} %"
              f" | direction {100*r['precision_direction']:.1f} % (référence {100*r['direction_toujours_majoritaire']:.1f} %)"
              f" | jours gagnés {r['jours_ou_le_modele_bat_la_naive']}")
    b = res[1]
    verdict = ("le modèle bat la référence naïve en MAE" if b["MAE_modele"] < b["MAE_naive"]
               else "le modèle NE bat PAS la référence naïve en MAE")
    print(f"\nVerdict (scénario B, le plus honnête) : {verdict}.")


if __name__ == "__main__":
    main()
