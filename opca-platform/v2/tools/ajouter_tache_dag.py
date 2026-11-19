"""Ajoute la tache collecte_activite_binance au DAG opca_pipeline_horaire_v2 (idempotent)."""
import ast
import sys

p = sys.argv[1]
s = open(p, encoding="utf-8").read()
if "collecte_activite_binance" in s:
    print("tache deja presente, rien a faire")
    sys.exit(0)

ancre = "    calcul_indicateurs = BashOperator("
ajout = '''    # Activite de marche Binance (volume USDT, nombre de transactions, part des achats) -> activite_marche
    collecte_activite_binance = BashOperator(
        task_id="collecte_activite_binance",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_activite_binance.py",
        env=ENV_V2, append_env=True,
    )
'''
old = "    [collecte_binance, collecte_coinbase] >> calcul_indicateurs"
assert s.count(ancre) == 1 and s.count(old) == 1, "DAG different de celui attendu"
s = s.replace(ancre, ajout + ancre)
s = s.replace(old, "    [collecte_binance, collecte_coinbase, collecte_activite_binance] >> calcul_indicateurs")
ast.parse(s)
open(p, "w", encoding="utf-8").write(s)
print("tache ajoutee")
