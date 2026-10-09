FROM python:3.11-slim

# libgomp1 : requis par XGBoost
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app/ml
COPY requirements-ml.txt /tmp/requirements-ml.txt
RUN pip install --no-cache-dir -r /tmp/requirements-ml.txt
COPY ml/ /app/ml/

# Par defaut : regression en simulation (aucune ecriture). Voir README.
CMD ["python", "regression_xgboost.py", "--dry-run"]
