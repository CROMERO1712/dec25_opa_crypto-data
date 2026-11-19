from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Random Forest 24 h : réentraîné chaque nuit dans un conteneur isolé sur la VM (via SSH, comme la
# collecte v1), car il demande plus de mémoire que le scheduler n'en a. La prévision est archivée
# dans prediction_oos (étiquette « BTC-USD/Binance RF 24h ») et évaluée par v_prediction_oos_eval.
SSH = ("ssh -i /home/airflow/.ssh/airflow_collector "
       "-o BatchMode=yes -o StrictHostKeyChecking=yes ubuntu@172.17.0.1 ")

default_args = {
    "owner": "opca",
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

with DAG(
    dag_id="opca_random_forest_24h",
    description="Random Forest : prévision du prix BTC à 24 h, réentraîné chaque nuit",
    start_date=datetime(2026, 10, 1),
    schedule="15 2 * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["opca", "v2", "ml"],
) as dag:
    entrainement = BashOperator(
        task_id="entrainement_random_forest",
        bash_command=SSH + "'bash /home/ubuntu/projet/v2/rf_v2/lancer_rf.sh'",
        execution_timeout=timedelta(minutes=180),
    )
