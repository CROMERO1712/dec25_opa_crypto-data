"""
Modèle Random Forest de régression pour prédire le prix à horizon 24 heures.

Le script reprend le DataFrame construit depuis :
- instrument_marche
- serie_prix
- activite_marche
- indicateur_technique

La variable cible demandée est :
- prediction_modele.prix_predit
avec :
- prediction_modele.horizon_prediction = '24h'

IMPORTANT
---------
La table prediction_modele du schéma fourni ne contient pas instrument_id.
La jointure avec les variables explicatives est donc faite sur date_heure.

Cette structure est acceptable si :
1. la base ne contient qu'un seul instrument ;
ou
2. une seule prédiction existe par date_heure pour l'horizon 24h.

Pour plusieurs instruments, il est fortement recommandé d'ajouter instrument_id
dans prediction_modele puis de joindre sur instrument_id + date_heure.

Installation :
    pip install pandas numpy sqlalchemy psycopg2-binary python-dotenv scikit-learn joblib

Fichier .env attendu :
    DB_HOST=51.44.254.88
    DB_PORT=5432
    DB_NAME=nom_de_la_base
    DB_USER=nom_utilisateur
    DB_PASSWORD=mot_de_passe
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import RandomizedSearchCV, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sqlalchemy import text

from integration_variables_explicatives import (
    charger_variables_explicatives,
    creer_moteur_postgresql,
)


HORIZON_HEURES = 24
HORIZON_BDD = "24h"
DOSSIER_SORTIE = Path(os.getenv("RF_SORTIE", "sorties_random_forest"))
PAS_PAR_HEURE = 12  # donnees 5 minutes : 12 lignes = 1 h ; 24 h = 288 lignes
RF_SYMBOLE = os.getenv("RF_SYMBOLE", "BTC-USD")
RF_PLATEFORME_ID = int(os.getenv("RF_PLATEFORME_ID", "1"))  # 1 = Binance, 2 = Coinbase
DOSSIER_SORTIE.mkdir(exist_ok=True)


def charger_cible_prediction(
    moteur,
    horizon_prediction: str = HORIZON_BDD,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
) -> pd.DataFrame:
    """Charge prix_predit depuis prediction_modele."""

    filtres = [
        "horizon_prediction = :horizon_prediction",
        "prix_predit IS NOT NULL",
    ]
    parametres: dict[str, object] = {
        "horizon_prediction": horizon_prediction,
    }

    if date_debut:
        filtres.append("date_heure >= :date_debut")
        parametres["date_debut"] = pd.Timestamp(date_debut)

    if date_fin:
        filtres.append("date_heure <= :date_fin")
        parametres["date_fin"] = pd.Timestamp(date_fin)

    requete = text(
        f"""
        SELECT
            prediction_id,
            date_heure,
            horizon_prediction,
            prix_predit AS cible_prix_24h
        FROM prediction_modele
        WHERE {" AND ".join(filtres)}
        ORDER BY date_heure
        """
    )

    df_cible = pd.read_sql_query(
        requete,
        moteur,
        params=parametres,
        parse_dates=["date_heure"],
    )

    if df_cible.empty:
        raise ValueError(
            "Aucune cible trouvée dans prediction_modele "
            f"pour horizon_prediction='{horizon_prediction}'."
        )

    doublons = df_cible.duplicated(subset=["date_heure"], keep=False)
    if doublons.any():
        exemple = (
            df_cible.loc[doublons, ["date_heure", "prediction_id"]]
            .head(10)
            .to_string(index=False)
        )
        raise ValueError(
            "Plusieurs prédictions existent pour une même date_heure. "
            "Comme prediction_modele ne contient pas instrument_id, "
            "la jointure serait ambiguë.\n"
            f"Exemples :\n{exemple}"
        )

    df_cible["cible_prix_24h"] = pd.to_numeric(
        df_cible["cible_prix_24h"],
        errors="coerce",
    )

    return df_cible.dropna(subset=["cible_prix_24h"])


def creer_variables_retardees(
    df: pd.DataFrame,
    lags: tuple[int, ...] = (1, 2, 3, 6, 12, 36, 72, 144, 288),
) -> pd.DataFrame:
    """
    Crée les lags et statistiques glissantes instrument par instrument.

    Hypothèse :
    une observation correspond à une heure lorsque pas_temps='1h'.
    """

    df = df.copy()
    df = df.sort_values(
        ["instrument_id", "date_heure", "pas_temps"]
    ).reset_index(drop=True)

    groupe = df.groupby("instrument_id", group_keys=False)

    colonnes_lag = [
        "prix_fermeture",
        "prix_ouverture",
        "prix_haut",
        "prix_bas",
        "volume_prix",
        "variation_prix_pct",
        "volume_total",
        "nombre_trades",
        "ratio_achat_vente",
        "liquidite_score",
        "sma_20",
        "sma_50",
        "rsi_14",
        "macd",
        "volatilite",
    ]

    colonnes_lag = [c for c in colonnes_lag if c in df.columns]

    for colonne in colonnes_lag:
        for lag in lags:
            df[f"{colonne}_lag_{lag}"] = groupe[colonne].shift(lag)

    # Rendements passés
    df["rendement_5m"] = groupe["prix_fermeture"].pct_change(1)
    df["rendement_1h"] = groupe["prix_fermeture"].pct_change(12)
    df["rendement_6h"] = groupe["prix_fermeture"].pct_change(72)
    df["rendement_12h"] = groupe["prix_fermeture"].pct_change(144)
    df["rendement_24h"] = groupe["prix_fermeture"].pct_change(288)

    # Statistiques glissantes calculées uniquement sur le passé
    fermeture_decalee = groupe["prix_fermeture"].shift(1)
    volume_decale = groupe["volume_prix"].shift(1)

    for fenetre in (12, 36, 72, 144, 288):
        df[f"prix_moyenne_mobile_{fenetre}x5m"] = (
            fermeture_decalee
            .groupby(df["instrument_id"])
            .rolling(fenetre, min_periods=max(3, fenetre // 3))
            .mean()
            .reset_index(level=0, drop=True)
        )

        df[f"prix_ecart_type_{fenetre}x5m"] = (
            fermeture_decalee
            .groupby(df["instrument_id"])
            .rolling(fenetre, min_periods=max(3, fenetre // 3))
            .std()
            .reset_index(level=0, drop=True)
        )

        df[f"volume_moyen_{fenetre}x5m"] = (
            volume_decale
            .groupby(df["instrument_id"])
            .rolling(fenetre, min_periods=max(3, fenetre // 3))
            .mean()
            .reset_index(level=0, drop=True)
        )

    # Position du prix dans la bougie
    amplitude = df["prix_haut"] - df["prix_bas"]
    df["amplitude_bougie"] = amplitude
    df["position_cloture_bougie"] = np.where(
        amplitude.abs() > 1e-12,
        (df["prix_fermeture"] - df["prix_bas"]) / amplitude,
        np.nan,
    )

    # Écarts aux moyennes mobiles
    if "sma_20" in df.columns:
        df["ecart_prix_sma20_pct"] = (
            df["prix_fermeture"] / df["sma_20"] - 1
        )

    if "sma_50" in df.columns:
        df["ecart_prix_sma50_pct"] = (
            df["prix_fermeture"] / df["sma_50"] - 1
        )

    # Variables calendaires cycliques
    heure = df["date_heure"].dt.hour
    jour_semaine = df["date_heure"].dt.dayofweek
    mois = df["date_heure"].dt.month

    df["heure_sin"] = np.sin(2 * np.pi * heure / 24)
    df["heure_cos"] = np.cos(2 * np.pi * heure / 24)
    df["jour_semaine_sin"] = np.sin(2 * np.pi * jour_semaine / 7)
    df["jour_semaine_cos"] = np.cos(2 * np.pi * jour_semaine / 7)
    df["mois_sin"] = np.sin(2 * np.pi * mois / 12)
    df["mois_cos"] = np.cos(2 * np.pi * mois / 12)

    return df


def construire_dataset_modelisation(
    moteur,
    symbole: Optional[str] = None,
    date_debut: Optional[str] = None,
    date_fin: Optional[str] = None,
):
    """Variables explicatives (pas 5 min) + cible = prix de cloture reel a t + 24 h.

    Retourne (dataset avec cible pour l'entrainement,
              toutes les lignes avec variables explicatives, dont les plus
              recentes sans cible, pour la prevision).
    """

    df_variables = charger_variables_explicatives(
        moteur=moteur,
        symbole=symbole,
        pas_temps="5m",
        date_debut=date_debut,
        date_fin=date_fin,
        conserver_lignes_incompletes=True,
        plateforme_id=RF_PLATEFORME_ID,
    )

    df_features = creer_variables_retardees(df_variables)

    # Cible : prix de cloture reel a t + 24 h (jointure sur la date exacte,
    # robuste aux trous eventuels dans la serie).
    cible = df_variables[["instrument_id", "date_heure", "prix_fermeture"]].copy()
    cible["date_heure"] = cible["date_heure"] - pd.Timedelta(hours=HORIZON_HEURES)
    cible = cible.rename(columns={"prix_fermeture": "cible_prix_24h"})

    df_dataset = df_features.merge(
        cible,
        on=["instrument_id", "date_heure"],
        how="inner",
        validate="one_to_one",
    )
    df_dataset = (
        df_dataset
        .dropna(subset=["cible_prix_24h"])
        .sort_values(["date_heure", "instrument_id"])
        .reset_index(drop=True)
    )

    if df_dataset.empty:
        raise ValueError("Dataset vide : aucune ligne avec une cible a 24 h.")

    return df_dataset, df_features


def separer_chronologiquement(
    df: pd.DataFrame,
    proportion_test: float = 0.20,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sépare train et test sans mélanger le futur avec le passé."""

    if not 0 < proportion_test < 1:
        raise ValueError("proportion_test doit être comprise entre 0 et 1.")

    dates_uniques = np.sort(df["date_heure"].unique())

    if len(dates_uniques) < 30:
        raise ValueError(
            "Le nombre de dates disponibles est insuffisant. "
            "Il faut idéalement plusieurs centaines d'heures."
        )

    indice_coupure = int(len(dates_uniques) * (1 - proportion_test))
    date_coupure = dates_uniques[indice_coupure]

    # Marge de 24 h : la cible d'une ligne d'entrainement ne doit pas chevaucher le test
    train = df[df["date_heure"] < date_coupure - pd.Timedelta(hours=HORIZON_HEURES)].copy()
    test = df[df["date_heure"] >= date_coupure].copy()

    if train.empty or test.empty:
        raise ValueError("La séparation chronologique produit un jeu vide.")

    return train, test


def preparer_matrices(
    train: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Sélectionne X et y en excluant identifiants et variables non prédictives."""

    cible = "cible_prix_24h"

    colonnes_a_exclure = [
        cible,
        "prediction_id",
        "horizon_prediction",
        "prix_id",
        "activite_id",
        "indicateur_id",
        "date_heure",
    ]

    X_train = train.drop(
        columns=[c for c in colonnes_a_exclure if c in train.columns]
    ).copy()

    X_test = test.drop(
        columns=[c for c in colonnes_a_exclure if c in test.columns]
    ).copy()

    y_train = train[cible].astype(float).copy()
    y_test = test[cible].astype(float).copy()

    # Retrait des colonnes entièrement vides dans le train
    colonnes_vides = X_train.columns[X_train.isna().all()].tolist()
    X_train = X_train.drop(columns=colonnes_vides)
    X_test = X_test.drop(columns=colonnes_vides, errors="ignore")

    return X_train, y_train, X_test, y_test


def creer_pipeline_et_recherche(
    X_train: pd.DataFrame,
) -> RandomizedSearchCV:
    """
    Crée un pipeline de prétraitement et recherche des hyperparamètres
    adaptés aux séries temporelles.
    """

    colonnes_categorielles = X_train.select_dtypes(
        include=["object", "category", "bool"]
    ).columns.tolist()

    colonnes_numeriques = [
        c for c in X_train.columns if c not in colonnes_categorielles
    ]

    pipeline_numerique = Pipeline(
        steps=[
            ("imputation", SimpleImputer(strategy="median")),
        ]
    )

    pipeline_categoriel = Pipeline(
        steps=[
            ("imputation", SimpleImputer(strategy="most_frequent")),
            (
                "encodage",
                OneHotEncoder(
                    handle_unknown="ignore",
                    sparse_output=False,
                ),
            ),
        ]
    )

    preprocesseur = ColumnTransformer(
        transformers=[
            ("numerique", pipeline_numerique, colonnes_numeriques),
            ("categoriel", pipeline_categoriel, colonnes_categorielles),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )

    modele = RandomForestRegressor(
        random_state=42,
        n_jobs=-1,
        criterion="squared_error",
    )

    pipeline = Pipeline(
        steps=[
            ("preparation", preprocesseur),
            ("modele", modele),
        ]
    )

    espace_hyperparametres = {
        "modele__n_estimators": [200, 300],
        "modele__max_depth": [8, 12, 16, 24],
        "modele__min_samples_split": [2, 5, 10, 20],
        "modele__min_samples_leaf": [1, 2, 4, 8],
        "modele__max_features": ["sqrt", 0.5, 0.75, 1.0],
        "modele__bootstrap": [True],
        "modele__max_samples": [0.65, 0.80, 1.0],
    }

    # Validation croisée temporelle, jamais de mélange aléatoire.
    validation_temporelle = TimeSeriesSplit(n_splits=3, gap=PAS_PAR_HEURE * HORIZON_HEURES)

    recherche = RandomizedSearchCV(
        estimator=pipeline,
        param_distributions=espace_hyperparametres,
        n_iter=int(os.getenv("RF_N_ITER", "10")),
        scoring="neg_mean_absolute_error",
        cv=validation_temporelle,
        random_state=42,
        n_jobs=1,
        verbose=2,
        refit=True,
    )

    return recherche


def calculer_metriques(
    y_reel: pd.Series,
    y_predit: np.ndarray,
) -> dict[str, float]:
    """Calcule les métriques de régression."""

    mae = mean_absolute_error(y_reel, y_predit)
    rmse = mean_squared_error(y_reel, y_predit) ** 0.5
    r2 = r2_score(y_reel, y_predit)

    masque_non_nul = np.abs(y_reel.to_numpy()) > 1e-12
    if masque_non_nul.any():
        mape = np.mean(
            np.abs(
                (
                    y_reel.to_numpy()[masque_non_nul]
                    - y_predit[masque_non_nul]
                )
                / y_reel.to_numpy()[masque_non_nul]
            )
        ) * 100
    else:
        mape = np.nan

    return {
        "MAE": float(mae),
        "RMSE": float(rmse),
        "R2": float(r2),
        "MAPE_pct": float(mape),
    }


def extraire_importance_variables(
    meilleur_pipeline: Pipeline,
) -> pd.DataFrame:
    """Récupère les importances calculées par Random Forest."""

    preprocesseur = meilleur_pipeline.named_steps["preparation"]
    modele = meilleur_pipeline.named_steps["modele"]

    noms_variables = preprocesseur.get_feature_names_out()

    importance = pd.DataFrame(
        {
            "variable": noms_variables,
            "importance": modele.feature_importances_,
        }
    )

    return importance.sort_values(
        "importance",
        ascending=False,
    ).reset_index(drop=True)


def predire_prix_dans_24h(
    meilleur_modele: Pipeline,
    df_dataset: pd.DataFrame,
    colonnes_modele: list[str],
) -> pd.DataFrame:
    """
    Utilise la ligne la plus récente de chaque instrument afin de produire
    une prévision à date_heure + 24 heures.
    """

    dernieres_lignes = (
        df_dataset
        .sort_values("date_heure")
        .groupby("instrument_id", as_index=False)
        .tail(1)
        .copy()
    )

    X_futur = dernieres_lignes.reindex(columns=colonnes_modele)
    predictions = (
        dernieres_lignes["prix_fermeture"].to_numpy(dtype=float)
        + meilleur_modele.predict(X_futur)
    )

    resultat = pd.DataFrame(
        {
            "instrument_id": dernieres_lignes["instrument_id"].to_numpy(),
            "symbole": dernieres_lignes["symbole"].to_numpy(),
            "date_reference": dernieres_lignes["date_heure"].to_numpy(),
            "date_prediction": (
                dernieres_lignes["date_heure"]
                + pd.Timedelta(hours=HORIZON_HEURES)
            ).to_numpy(),
            "prix_actuel": dernieres_lignes["prix_fermeture"].to_numpy(),
            "prix_predit_24h_random_forest": predictions,
        }
    )

    resultat["variation_predite_pct"] = (
        (
            resultat["prix_predit_24h_random_forest"]
            / resultat["prix_actuel"]
        )
        - 1
    ) * 100

    return resultat


def main() -> None:
    moteur = creer_moteur_postgresql()

    try:
        df_dataset, df_features = construire_dataset_modelisation(
            moteur=moteur,
            symbole=RF_SYMBOLE,
            date_debut=None,   # Exemple : "2025-01-01"
            date_fin=None,
        )

        train, test = separer_chronologiquement(
            df_dataset,
            proportion_test=0.20,
        )

        X_train, y_train, X_test, y_test = preparer_matrices(
            train,
            test,
        )

        print("Dimensions du dataset :", df_dataset.shape)
        print("Dimensions train :", X_train.shape)
        print("Dimensions test :", X_test.shape)
        print("Début du test :", test["date_heure"].min())

        recherche = creer_pipeline_et_recherche(X_train)
        # Cible apprise : variation du prix a 24 h (USD). Un modele a arbres ne sait pas
        # extrapoler un niveau de prix hors de la plage vue a l'entrainement.
        y_train_delta = (
            y_train.to_numpy(dtype=float)
            - X_train["prix_fermeture"].to_numpy(dtype=float)
        )
        recherche.fit(X_train, y_train_delta)

        meilleur_modele = recherche.best_estimator_
        y_predit = (
            X_test["prix_fermeture"].to_numpy(dtype=float)
            + meilleur_modele.predict(X_test)
        )

        metriques = calculer_metriques(y_test, y_predit)
        reference_naive = calculer_metriques(
            y_test, X_test["prix_fermeture"].to_numpy(dtype=float)
        )
        print("\nReference naive (prix dans 24 h = prix actuel) :")
        print(json.dumps(reference_naive, indent=2, ensure_ascii=False))

        print("\nMeilleurs hyperparamètres :")
        print(json.dumps(recherche.best_params_, indent=2, ensure_ascii=False))

        print("\nMétriques sur le jeu de test chronologique :")
        print(json.dumps(metriques, indent=2, ensure_ascii=False))

        resultats_test = test[
            [
                "date_heure",
                "instrument_id",
                "symbole",
                "prix_fermeture",
                "cible_prix_24h",
            ]
        ].copy()

        resultats_test["prix_predit_random_forest"] = y_predit
        resultats_test["erreur_absolue"] = np.abs(
            resultats_test["cible_prix_24h"]
            - resultats_test["prix_predit_random_forest"]
        )

        importance = extraire_importance_variables(meilleur_modele)

        prediction_future = predire_prix_dans_24h(
            meilleur_modele=meilleur_modele,
            df_dataset=df_features,
            colonnes_modele=X_train.columns.tolist(),
        )

        # Sauvegardes
        joblib.dump(
            meilleur_modele,
            DOSSIER_SORTIE / "random_forest_prix_24h.joblib",
        )

        df_dataset.to_csv(
            DOSSIER_SORTIE / "dataset_modelisation_24h.csv",
            index=False,
            encoding="utf-8-sig",
        )

        resultats_test.to_csv(
            DOSSIER_SORTIE / "resultats_test_24h.csv",
            index=False,
            encoding="utf-8-sig",
        )

        importance.to_csv(
            DOSSIER_SORTIE / "importance_variables.csv",
            index=False,
            encoding="utf-8-sig",
        )

        prediction_future.to_csv(
            DOSSIER_SORTIE / "prediction_prochaines_24h.csv",
            index=False,
            encoding="utf-8-sig",
        )

        with open(
            DOSSIER_SORTIE / "metriques_et_hyperparametres.json",
            "w",
            encoding="utf-8",
        ) as fichier:
            json.dump(
                {
                    "meilleurs_hyperparametres": recherche.best_params_,
                    "metriques_test": metriques,
                    "reference_naive": reference_naive,
                    "cible_modele": "variation du prix a 24 h (USD) ; prix predit = prix actuel + variation predite",
                },
                fichier,
                indent=2,
                ensure_ascii=False,
            )

        print("\nPrévision à 24 heures :")
        print(prediction_future.to_string(index=False))

        print("\nLes fichiers ont été enregistrés dans :")
        print(DOSSIER_SORTIE.resolve())

    finally:
        moteur.dispose()


if __name__ == "__main__":
    main()
