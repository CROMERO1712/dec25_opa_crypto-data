from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Les collecteurs tournent dans un venv dedie (dependances isolees d'Airflow).
PYTHON = "/home/airflow/collector-venv/bin/python"
SCRIPTS = "/opt/airflow/collectors"

default_args = {
    "owner": "opca",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="opca_collecte_horaire",
    description="Collecte horaire des bougies 5m (Binance, Coinbase) vers dst_db",
    start_date=datetime(2026, 10, 1),
    schedule="0 * * * *",  # meme cadence que l'ancien cron
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["opca", "collecte"],
) as dag:
    collecte_binance = BashOperator(
        task_id="collecte_binance",
        bash_command=f"{PYTHON} {SCRIPTS}/insert_binance.py",
    )

    collecte_coinbase = BashOperator(
        task_id="collecte_coinbase",
        bash_command=f"{PYTHON} {SCRIPTS}/import_bougie_coinbase.py",
    )
