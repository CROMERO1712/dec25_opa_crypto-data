from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

# Copie du DAG existant, branchee sur la NOUVELLE base (variables opca_v2_*).
COLLECT_PY = "/home/airflow/collector-venv/bin/python"
ML_PY = "/home/airflow/ml-venv/bin/python"
COLLECTORS = "/opt/airflow/collectors"
ML = "/opt/airflow/ml"

DRY = "{{ '' if var.value.get('opca_v2_write_predictions', '0') == '1' else '--dry-run' }}"

# Surcharge des variables DB_* (append_env : le reste de l'environnement est conserve)
ENV_V2 = {
    "DB_HOST": "{{ var.value.opca_v2_db_host }}",
    "DB_PORT": "{{ var.value.opca_v2_db_port }}",
    "DB_NAME": "{{ var.value.opca_v2_db_name }}",
    "DB_USER": "{{ var.value.opca_v2_db_user }}",
    "DB_PASSWORD": "{{ var.value.opca_v2_db_password }}",
}

default_args = {
    "owner": "opca",
    "retries": 2,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="opca_pipeline_horaire_v2",
    description="V2 (nouvelle base) : collecte 5m -> indicateurs -> regression XGBoost",
    start_date=datetime(2026, 10, 1),
    schedule="10 * * * *",
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["opca", "v2"],
) as dag:
    collecte_binance = BashOperator(
        task_id="collecte_binance",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_binance.py",
        env=ENV_V2, append_env=True,
    )
    collecte_coinbase = BashOperator(
        task_id="collecte_coinbase",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/import_bougie_coinbase.py",
        env=ENV_V2, append_env=True,
    )
    # Activite de marche Binance (volume USDT, nombre de transactions, part des achats) -> activite_marche
    collecte_activite_binance = BashOperator(
        task_id="collecte_activite_binance",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_activite_binance.py",
        env=ENV_V2, append_env=True,
    )
    calcul_indicateurs = BashOperator(
        task_id="calcul_indicateurs",
        bash_command=f"cd {ML} && {ML_PY} compute_indicateurs.py",
        trigger_rule="all_done",
        env=ENV_V2, append_env=True,
    )
    regression_xgboost = BashOperator(
        task_id="regression_xgboost",
        bash_command=f"cd {ML} && {ML_PY} regression_xgboost.py " + DRY,
        env=ENV_V2, append_env=True,
    )

    [collecte_binance, collecte_coinbase, collecte_activite_binance] >> calcul_indicateurs >> regression_xgboost
    log_previsions_oos = BashOperator(
        task_id="log_previsions_oos",
        bash_command=f"cd {ML} && {ML_PY} log_previsions_oos.py",
        env={**ENV_V2, "OPCA_OOS_DRY": "{{ '0' if var.value.get('opca_v2_write_predictions', '0') == '1' else '1' }}"},
        append_env=True,
    )
    regression_xgboost >> log_previsions_oos
    # Signal de trading (simulation, aucun ordre) : derniere prevision + score_confiance -> signal_trading
    generer_signaux = BashOperator(
        task_id="generer_signaux",
        trigger_rule="all_done",  # une source de contexte en panne ne bloque pas le signal
        bash_command=f"cd {ML} && {ML_PY} generer_signaux.py " + DRY,
        env=ENV_V2, append_env=True,
    )
    regression_xgboost >> generer_signaux
    # Contexte des signaux : sentiment de marche (Fear & Greed, 1 valeur/jour) et actualites (RSS)
    collecte_sentiment = BashOperator(
        task_id="collecte_sentiment",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_sentiment_fear_greed.py",
        env=ENV_V2, append_env=True,
    )
    collecte_evenements = BashOperator(
        task_id="collecte_evenements",
        bash_command=f"{COLLECT_PY} {COLLECTORS}/insert_evenements_rss.py",
        env=ENV_V2, append_env=True,
    )
    [collecte_sentiment, collecte_evenements] >> generer_signaux
