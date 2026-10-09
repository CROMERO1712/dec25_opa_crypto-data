from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Chaque etape tourne dans un venv dedie (dependances isolees d'Airflow).
COLLECT_PY = "/home/airflow/collector-venv/bin/python"
ML_PY = "/home/airflow/ml-venv/bin/python"
COLLECTORS = "/opt/airflow/collectors"
ML = "/opt/airflow/ml"

# Les predictions ne sont ecrites que si la Variable Airflow
# opca_write_predictions vaut 1 ; sinon simulation (--dry-run).
DRY = "{{ '' if var.value.get('opca_write_predictions', '0') == '1' else '--dry-run' }}"

default_args = {
    "owner": "opca",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="opca_pipeline_horaire",
    description="Collecte 5m (Binance, Coinbase) -> indicateurs -> regression XGBoost",
    start_date=datetime(2026, 10, 1),
    schedule="0 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["opca", "collecte", "ml"],
) as dag:
    collecte_binance = BashOperator(
        task_id="collecte_binance",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_binance.py",
    )
    collecte_coinbase = BashOperator(
        task_id="collecte_coinbase",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/import_bougie_coinbase.py",
    )
    calcul_indicateurs = BashOperator(
        task_id="calcul_indicateurs",
        bash_command=f"cd {ML} && {ML_PY} compute_indicateurs.py",
        trigger_rule="all_done",  # calcule meme si une plateforme a echoue
    )
    regression_xgboost = BashOperator(
        task_id="regression_xgboost",
        bash_command=f"cd {ML} && {ML_PY} regression_xgboost.py " + DRY,
    )

    [collecte_binance, collecte_coinbase] >> calcul_indicateurs >> regression_xgboost
