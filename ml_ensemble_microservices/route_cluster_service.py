# Databricks notebook source
# MAGIC %md
# MAGIC # Route Cluster Microservice
# MAGIC Runs on Databricks Serverless compute, invoked by Streamlit orchestrator

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
from sklearn.cluster import KMeans, BisectingKMeans, AgglomerativeClustering
from sklearn.mixture import GaussianMixture
import mlflow
import pandas as pd

workflow_id = dbutils.widgets.get("workflow_id")
task_id = dbutils.widgets.get("task_id")
config = json.loads(dbutils.widgets.get("config"))
context = json.loads(dbutils.widgets.get("context"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Data from Unity Catalog

# COMMAND ----------

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
table = dbutils.widgets.get("table")
target = dbutils.widgets.get("target")

# Load data
table_path = f"{catalog}.{schema}.{table}"
df = spark.table(table_path).toPandas()

# Separate features and target
X = df.drop(columns=[target])
y = df[target]

print(f"Loaded {len(df)} rows from {table_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Perform Clustering Routing

# COMMAND ----------

# Start MLflow run
mlflow.set_experiment(f"/Experiments/ensemble_{workflow_id}")

with mlflow.start_run(run_name=f"{task_id}_clustering"):
    
    # Log parameters
    mlflow.log_param("task_id", task_id)
    mlflow.log_param("workflow_id", workflow_id)
    mlflow.log_params(config.get('route', {}).get('cluster', {}))
    
    # Determine clustering algorithm
    cluster_config = config.get('route', {}).get('cluster', {})
    
    if 'kmeans' in cluster_config or not cluster_config:
        n_clusters = cluster_config.get('kmeans', {}).get('n_clusters', 5)
        clusterer = KMeans(n_clusters=n_clusters, random_state=42)
        method = "kmeans"
        
    elif 'bisect' in cluster_config:
        n_clusters = cluster_config.get('bisect', {}).get('n_clusters', 5)
        clusterer = BisectingKMeans(n_clusters=n_clusters, random_state=42)
        method = "bisecting_kmeans"
        
    elif 'mixture' in cluster_config:
        n_components = cluster_config.get('mixture', {}).get('n_components', 5)
        clusterer = GaussianMixture(n_components=n_components, random_state=42)
        method = "gaussian_mixture"
        
    elif 'agglom' in cluster_config:
        n_clusters = cluster_config.get('agglom', {}).get('n_clusters', 5)
        clusterer = AgglomerativeClustering(n_clusters=n_clusters)
        method = "agglomerative"
    
    else:
        raise ValueError(f"Unknown clustering method: {cluster_config}")
    
    # Fit clustering
    print(f"Fitting {method} clustering...")
    cluster_labels = clusterer.fit_predict(X)
    
    # Add cluster assignments to dataframe
    df['cluster_id'] = cluster_labels
    
    # Log metrics
    n_clusters_actual = len(set(cluster_labels))
    mlflow.log_metric("n_clusters", n_clusters_actual)
    
    for cluster_id in range(n_clusters_actual):
        cluster_size = (cluster_labels == cluster_id).sum()
        mlflow.log_metric(f"cluster_{cluster_id}_size", cluster_size)
    
    # Save partitioned data back to Unity Catalog
    output_table = f"{catalog}.{schema}.{table}_clustered_{workflow_id}_{task_id}"
    
    spark_df = spark.createDataFrame(df)
    spark_df.write.mode("overwrite").saveAsTable(output_table)
    
    # Log output location
    mlflow.log_param("output_table", output_table)
    mlflow.log_param("method", method)
    
    # Save cluster model
    mlflow.sklearn.log_model(clusterer, "cluster_model")
    
    print(f"✅ Clustering complete. Data saved to {output_table}")
    
    # Return metadata for orchestrator
    result_metadata = {
        "output_table": output_table,
        "n_clusters": n_clusters_actual,
        "method": method,
        "cluster_sizes": {
            f"cluster_{i}": int((cluster_labels == i).sum()) 
            for i in range(n_clusters_actual)
        }
    }
    
    mlflow.log_dict(result_metadata, "result_metadata.json")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Task Complete
# MAGIC Result metadata logged to MLflow for downstream tasks

# COMMAND ----------

dbutils.notebook.exit(json.dumps(result_metadata))
