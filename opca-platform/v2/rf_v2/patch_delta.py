from pathlib import Path

def rep(s, old, new):
    assert s.count(old) == 1, f"motif introuvable ou multiple : {old[:70]!r}"
    return s.replace(old, new)

p = Path("modele_random_forest_prix_24h.py")
s = p.read_text(encoding="utf-8")
s = rep(s, "        recherche.fit(X_train, y_train)\n",
        "        # Cible apprise : variation du prix a 24 h (USD). Un modele a arbres ne sait pas\n"
        "        # extrapoler un niveau de prix hors de la plage vue a l'entrainement.\n"
        "        y_train_delta = (\n"
        "            y_train.to_numpy(dtype=float)\n"
        "            - X_train[\"prix_fermeture\"].to_numpy(dtype=float)\n"
        "        )\n"
        "        recherche.fit(X_train, y_train_delta)\n")
s = rep(s, "        y_predit = meilleur_modele.predict(X_test)\n",
        "        y_predit = (\n"
        "            X_test[\"prix_fermeture\"].to_numpy(dtype=float)\n"
        "            + meilleur_modele.predict(X_test)\n"
        "        )\n")
s = rep(s, "    predictions = meilleur_modele.predict(X_futur)\n",
        "    predictions = (\n"
        "        dernieres_lignes[\"prix_fermeture\"].to_numpy(dtype=float)\n"
        "        + meilleur_modele.predict(X_futur)\n"
        "    )\n")
s = rep(s, '"reference_naive": reference_naive,',
        '"reference_naive": reference_naive,\n'
        '                    "cible_modele": "variation du prix a 24 h (USD) ; prix predit = prix actuel + variation predite",')
p.write_text(s, encoding="utf-8")
print("PATCH DELTA OK")
