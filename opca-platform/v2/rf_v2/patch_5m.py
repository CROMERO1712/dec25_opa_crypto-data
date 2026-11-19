import re, shutil
from pathlib import Path

def rep(s, old, new):
    assert s.count(old) == 1, f"motif introuvable ou multiple : {old[:70]!r}"
    return s.replace(old, new)

def depart(p):
    """Sauvegarde .orig (une seule fois) et retourne le texte d'origine."""
    o = Path(str(p) + ".orig")
    if not o.exists():
        shutil.copy(p, o)
    return o.read_text(encoding="utf-8")

# ---------- module d'integration ----------
p = Path("integration_variables_explicatives.py")
s = depart(p)
s = rep(s, "    conserver_lignes_incompletes: bool = True,\n) -> pd.DataFrame:\n    \"\"\"\n    Charge les quatre tables",
        "    conserver_lignes_incompletes: bool = True,\n    plateforme_id: Optional[int] = None,\n) -> pd.DataFrame:\n    \"\"\"\n    Charge les quatre tables")
s = rep(s, '        parametres["pas_temps"] = pas_temps\n',
        '        parametres["pas_temps"] = pas_temps\n\n    if plateforme_id:\n        filtres.append("sp.plateforme_id = :plateforme_id")\n        parametres["plateforme_id"] = int(plateforme_id)\n')
s = rep(s, "            im.devise_cotation,\n            im.plateforme\n        FROM serie_prix AS sp\n        INNER JOIN instrument_marche AS im\n            ON im.instrument_id = sp.instrument_id\n",
        "            im.devise_cotation,\n            sp.plateforme_id,\n            pf.nom AS plateforme\n        FROM serie_prix AS sp\n        INNER JOIN instrument_marche AS im\n            ON im.instrument_id = sp.instrument_id\n        INNER JOIN plateforme AS pf\n            ON pf.plateforme_id = sp.plateforme_id\n")
s = rep(s, "            liquidite_score,\n            instrument_id\n        FROM activite_marche",
        "            liquidite_score,\n            instrument_id,\n            plateforme_id\n        FROM activite_marche")
s = rep(s, "            volatilite,\n            instrument_id\n        FROM indicateur_technique",
        "            volatilite,\n            instrument_id,\n            plateforme_id\n        FROM indicateur_technique")
s = rep(s, 'cles_jointure = ["instrument_id", "date_heure", "pas_temps"]',
        'cles_jointure = ["instrument_id", "plateforme_id", "date_heure", "pas_temps"]')
p.write_text(s, encoding="utf-8")

# ---------- script Random Forest ----------
p = Path("modele_random_forest_prix_24h.py")
s = depart(p)
s = rep(s, "import json\nfrom pathlib import Path", "import json\nimport os\nfrom pathlib import Path")
s = rep(s, 'DOSSIER_SORTIE = Path("sorties_random_forest")',
        'DOSSIER_SORTIE = Path(os.getenv("RF_SORTIE", "sorties_random_forest"))\n'
        'PAS_PAR_HEURE = 12  # donnees 5 minutes : 12 lignes = 1 h ; 24 h = 288 lignes\n'
        'RF_SYMBOLE = os.getenv("RF_SYMBOLE", "BTC-USD")\n'
        'RF_PLATEFORME_ID = int(os.getenv("RF_PLATEFORME_ID", "1"))  # 1 = Binance, 2 = Coinbase')
s = rep(s, "    lags: tuple[int, ...] = (1, 2, 3, 6, 12, 24, 48, 72),",
        "    lags: tuple[int, ...] = (1, 2, 3, 6, 12, 36, 72, 144, 288),")
s = rep(s, '    df["rendement_1h"] = groupe["prix_fermeture"].pct_change(1)\n'
           '    df["rendement_6h"] = groupe["prix_fermeture"].pct_change(6)\n'
           '    df["rendement_12h"] = groupe["prix_fermeture"].pct_change(12)\n'
           '    df["rendement_24h"] = groupe["prix_fermeture"].pct_change(24)',
        '    df["rendement_5m"] = groupe["prix_fermeture"].pct_change(1)\n'
        '    df["rendement_1h"] = groupe["prix_fermeture"].pct_change(12)\n'
        '    df["rendement_6h"] = groupe["prix_fermeture"].pct_change(72)\n'
        '    df["rendement_12h"] = groupe["prix_fermeture"].pct_change(144)\n'
        '    df["rendement_24h"] = groupe["prix_fermeture"].pct_change(288)')
s = rep(s, "    for fenetre in (6, 12, 24, 48, 72):", "    for fenetre in (12, 36, 72, 144, 288):")
s = rep(s, 'df[f"prix_moyenne_mobile_{fenetre}h"]', 'df[f"prix_moyenne_mobile_{fenetre}x5m"]')
s = rep(s, 'df[f"prix_ecart_type_{fenetre}h"]', 'df[f"prix_ecart_type_{fenetre}x5m"]')
s = rep(s, 'df[f"volume_moyen_{fenetre}h"]', 'df[f"volume_moyen_{fenetre}x5m"]')

NOUVELLE = '''def construire_dataset_modelisation(
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
'''
s, n = re.subn(r"def construire_dataset_modelisation\(.*?(?=\n\ndef separer_chronologiquement\()",
               lambda m: NOUVELLE, s, count=1, flags=re.S)
assert n == 1, "fonction construire_dataset_modelisation introuvable"

s = rep(s, '    train = df[df["date_heure"] < date_coupure].copy()',
        '    # Marge de 24 h : la cible d\'une ligne d\'entrainement ne doit pas chevaucher le test\n'
        '    train = df[df["date_heure"] < date_coupure - pd.Timedelta(hours=HORIZON_HEURES)].copy()')
s = rep(s, "    validation_temporelle = TimeSeriesSplit(n_splits=5)",
        "    validation_temporelle = TimeSeriesSplit(n_splits=3, gap=PAS_PAR_HEURE * HORIZON_HEURES)")
s = rep(s, "        n_iter=30,", '        n_iter=int(os.getenv("RF_N_ITER", "10")),')
s = rep(s, '"modele__n_estimators": [300, 500, 700, 1000],', '"modele__n_estimators": [200, 300],')
s = rep(s, '"modele__max_depth": [8, 12, 16, 24, None],', '"modele__max_depth": [8, 12, 16, 24],')
s = rep(s, '        cv=validation_temporelle,\n        random_state=42,\n        n_jobs=-1,',
        '        cv=validation_temporelle,\n        random_state=42,\n        n_jobs=1,')

s = rep(s, "        df_dataset = construire_dataset_modelisation(",
        "        df_dataset, df_features = construire_dataset_modelisation(")
s, n = re.subn(r'symbole=None,\s*# Exemple : "BTCUSDT"', "symbole=RF_SYMBOLE,", s)
assert n == 1, "appel symbole=None introuvable"
s = rep(s, "        metriques = calculer_metriques(y_test, y_predit)\n",
        "        metriques = calculer_metriques(y_test, y_predit)\n"
        "        reference_naive = calculer_metriques(\n"
        "            y_test, X_test[\"prix_fermeture\"].to_numpy(dtype=float)\n"
        "        )\n"
        "        print(\"\\nReference naive (prix dans 24 h = prix actuel) :\")\n"
        "        print(json.dumps(reference_naive, indent=2, ensure_ascii=False))\n")
s = rep(s, '"metriques_test": metriques,', '"metriques_test": metriques,\n                    "reference_naive": reference_naive,')
s = rep(s, "            df_dataset=df_dataset,\n            colonnes_modele=X_train.columns.tolist(),",
        "            df_dataset=df_features,\n            colonnes_modele=X_train.columns.tolist(),")
p.write_text(s, encoding="utf-8")
print("PATCH OK")
