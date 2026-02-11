# Databricks notebook source
# MAGIC %md
# MAGIC # Stack Top-N Microservice
# MAGIC Runs on Databricks Serverless, trains base models via AutoML, creates stacked ensemble

# COMMAND ----------

# Get parameters from orchestrator
dbutils.widgets.text("workflow_id", "")
dbutils.widgets.text("task_id", "")
dbutils.widgets.text("config", "{}")
dbutils.widgets.text("context", "{}")
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "")
dbutils.widgets.text("table", "")
dbutils.widgets.text("target", "")

import json
import mlflow
import pandas as pd
import numpy as np
from databricks import automl
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier

workflow_id = dbutils.widgets.get("workflow_id")
task_id = dbutils.widgets.get("task_id")
config = json.loads(dbutils.widgets.get("config"))
context = json.loads(dbutils.widgets.get("context"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Data

# COMMAND ----------

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
table = dbutils.widgets.get("table")
target = dbutils.widgets.get("target")

# Check if data was already routed/clustered
input_table = f"{catalog}.{schema}.{table}"

# Look for clustered data from previous task
try:
    clustered_table = f"{catalog}.{schema}.{table}_clustered_{workflow_id}_route_cluster"
    df = spark.table(clustered_table).toPandas()
    print(f"Using clustered data: {clustered_table}")
except:
    df = spark.table(input_table).toPandas()
    print(f"Using original data: {input_table}")

X = df.drop(columns=[target])
y = df[target]

print(f"Dataset shape: {X.shape}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train Base Models via AutoML

# COMMAND ----------

mlflow.set_experiment(f"/Experiments/ensemble_{workflow_id}")

stack_config = config.get('stack', {})
top_n = stack_config.get('top_n', 3)

# Determine task type from context
metric_config = context.get('metric', {})
if 'classification' in metric_config:
    task_type = "classification"
    primary_metric = metric_config['classification'][0]  # First metric
else:
    task_type = "regression"
    primary_metric = metric_config['regression'][0]

print(f"Training {top_n} base models via AutoML for {task_type}")

# COMMAND ----------

# Run AutoML to get top N models
automl_run = automl.classify(
    dataset=spark.createDataFrame(df),
    target_col=target,
    primary_metric=primary_metric,
    timeout_minutes=int(context.get('timeout', '10 minutes').split()[0]),
    experiment_dir=f"/Experiments/automl_{workflow_id}_{task_id}"
) if task_type == "classification" else automl.regress(
    dataset=spark.createDataFrame(df),
    target_col=target,
    primary_metric=primary_metric,
    timeout_minutes=int(context.get('timeout', '10 minutes').split()[0]),
    experiment_dir=f"/Experiments/automl_{workflow_id}_{task_id}"
)

print(f"AutoML completed. Experiment: {automl_run.experiment.experiment_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Get Top N Models and Generate OOF Predictions

# COMMAND ----------

# Retrieve top N models from AutoML
runs = mlflow.search_runs(
    experiment_ids=[automl_run.experiment.experiment_id],
    order_by=[f"metrics.{primary_metric} DESC"],
    max_results=top_n
)

print(f"Top {top_n} models by {primary_metric}:")
print(runs[['run_id', f'metrics.{primary_metric}']].head(top_n))

# COMMAND ----------

# Generate Out-of-Fold (OOF) predictions for stacking
fold_type = context.get('fold_type', ['kfold'])[0]

if fold_type == 'stratified':
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    splits = list(kf.split(X, y))
elif fold_type == 'kfold':
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    splits = list(kf.split(X))
else:
    # Default to simple train/test split
    from sklearn.model_selection import train_test_split
    train_idx, val_idx = train_test_split(
        range(len(X)), test_size=0.2, random_state=42
    )
    splits = [(train_idx, val_idx)]

print(f"Generating OOF predictions using {fold_type} with {len(splits)} folds")

# COMMAND ----------

# Load each top model and generate OOF predictions
oof_predictions = np.zeros((len(X), len(runs)))

for model_idx, (run_id, row) in enumerate(runs.head(top_n).iterrows()):
    run_id = row['run_id']
    
    # Load model from MLflow
    model_uri = f"runs:/{run_id}/model"
    model = mlflow.sklearn.load_model(model_uri)
    
    # Generate OOF predictions
    oof_preds = np.zeros(len(X))
    
    for fold_idx, (train_idx, val_idx) in enumerate(splits):
        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
        
        # Clone and retrain model on this fold
        from sklearn.base import clone
        fold_model = clone(model)
        fold_model.fit(X_train, y_train)
        
        # Predict on validation fold
        if task_type == "classification":
            oof_preds[val_idx] = fold_model.predict_proba(X_val)[:, 1]
        else:
            oof_preds[val_idx] = fold_model.predict(X_val)
    
    oof_predictions[:, model_idx] = oof_preds
    print(f"Model {model_idx + 1}/{top_n}: OOF predictions generated")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train Meta-Learner (Stacking)

# COMMAND ----------

with mlflow.start_run(run_name=f"{task_id}_stacking") as run:
    
    # Log parameters
    mlflow.log_param("task_id", task_id)
    mlflow.log_param("workflow_id", workflow_id)
    mlflow.log_param("n_base_models", top_n)
    mlflow.log_param("fold_type", fold_type)
    
    # Train meta-learner on OOF predictions
    if task_type == "classification":
        meta_learner = LogisticRegression(random_state=42)
    else:
        from sklearn.linear_model import Ridge
        meta_learner = Ridge(random_state=42)
    
    meta_learner.fit(oof_predictions, y)
    
    # Evaluate meta-learner
    from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
    
    meta_preds = meta_learner.predict(oof_predictions)
    
    if task_type == "classification":
        accuracy = accuracy_score(y, meta_preds)
        f1 = f1_score(y, meta_preds, average='weighted')
        mlflow.log_metric("stacked_accuracy", accuracy)
        mlflow.log_metric("stacked_f1", f1)
        print(f"Stacked Ensemble Accuracy: {accuracy:.4f}, F1: {f1:.4f}")
    else:
        mse = mean_squared_error(y, meta_preds)
        r2 = r2_score(y, meta_preds)
        mlflow.log_metric("stacked_mse", mse)
        mlflow.log_metric("stacked_r2", r2)
        print(f"Stacked Ensemble MSE: {mse:.4f}, R2: {r2:.4f}")
    
    # Log meta-learner
    mlflow.sklearn.log_model(meta_learner, "meta_learner")
    
    # Log base model run IDs for later retrieval
    mlflow.log_dict({
        "base_model_runs": runs.head(top_n)['run_id'].tolist()
    }, "base_models.json")
    
    # Save OOF predictions to Unity Catalog for potential use by other tasks
    oof_df = pd.DataFrame(oof_predictions, columns=[f"model_{i}" for i in range(top_n)])
    oof_df[target] = y.values
    
    output_table = f"{catalog}.{schema}.oof_predictions_{workflow_id}_{task_id}"
    spark.createDataFrame(oof_df).write.mode("overwrite").saveAsTable(output_table)
    
    mlflow.log_param("oof_table", output_table)
    
    result_metadata = {
        "meta_learner_run_id": run.info.run_id,
        "n_base_models": top_n,
        "oof_table": output_table,
        "primary_metric": primary_metric,
        "task_type": task_type
    }
    
    mlflow.log_dict(result_metadata, "result_metadata.json")
    
    print(f"✅ Stacking complete. Meta-learner saved.")

# COMMAND ----------

dbutils.notebook.exit(json.dumps(result_metadata))
