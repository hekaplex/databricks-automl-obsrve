# Databricks AutoML Ensemble Orchestrator

Streamlit-based in-process orchestrator that spawns microservices on Databricks Serverless compute.

## Architecture

```
┌─────────────────────────────────────────┐
│   Databricks App (Streamlit)           │
│   ┌─────────────────────────────────┐   │
│   │  StreamlitOrchestrator          │   │
│   │  - In-process workflow state    │   │
│   │  - DAG construction             │   │
│   │  - Dependency management        │   │
│   └─────────────────────────────────┘   │
│              │                           │
│              │ spawn jobs via            │
│              │ Databricks SDK            │
│              ▼                           │
└─────────────────────────────────────────┘
              │
              ├─────────────────────────┐
              ▼                         ▼
   ┌──────────────────┐      ┌──────────────────┐
   │ Serverless GPU   │      │ Serverless       │
   │ Compute          │      │ No-GPU Compute   │
   │                  │      │                  │
   │ - route_cluster  │      │ - stack_top_any  │
   │ - boost          │      │ - vote_top_alg   │
   │ - etc.           │      │ - etc.           │
   └──────────────────┘      └──────────────────┘
         │                         │
         └────────┬────────────────┘
                  ▼
         ┌──────────────────┐
         │  Unity Catalog   │
         │  - Training data │
         │  - OOF predictions│
         │  - Final models  │
         └──────────────────┘
```

## Deployment Steps

### 1. Upload Microservice Notebooks to Databricks Workspace

Upload all microservice notebooks to `/Workspace/ml_ensemble_microservices/`:

```
/Workspace/ml_ensemble_microservices/
  ├── route_cluster_service
  ├── route_feature_service
  ├── route_external_service
  ├── stack_top_any_service
  ├── stack_top_alg_service
  ├── stack_blend_service
  ├── stack_classwise_service
  ├── boost_service
  ├── vote_top_alg_service
  ├── vote_mix_service
  └── vote_weight_service
```

### 2. Create Streamlit App in Databricks

1. Go to Databricks workspace
2. Navigate to **Apps** → **Create App**
3. Select **Streamlit**
4. Upload `streamlit_orchestrator.py`
5. Set environment to use Databricks Runtime 14.3 LTS or higher
6. Configure app settings:
   - **Compute**: Serverless (for the Streamlit host)
   - **Permissions**: Grant access to Unity Catalog tables
   - **Environment Variables** (if needed):
     - `MLFLOW_TRACKING_URI`: databricks
     - `DATABRICKS_HOST`: (auto-configured)
     - `DATABRICKS_TOKEN`: (auto-configured)

### 3. Directory Structure

```
streamlit_app/
├── streamlit_orchestrator.py      # Main Streamlit app
├── requirements.txt                # Python dependencies
└── README.md                       # This file

microservices/
├── route_cluster_service.py        # Clustering routing
├── stack_top_any_service.py        # Top-N stacking
├── boost_service.py                # Boosting coordinator
└── ... (other microservices)
```

### 4. Install Dependencies

Create `requirements.txt`:

```txt
streamlit>=1.31.0
databricks-sdk>=0.18.0
pyyaml>=6.0
mlflow>=2.9.0
pandas>=2.0.0
scikit-learn>=1.3.0
```

## How It Works

### Orchestrator (Streamlit App)

The Streamlit app runs **in-process** on Databricks App infrastructure:

1. **Parses YAML** workflow configuration
2. **Builds DAG** from task dependencies
3. **Spawns Databricks Jobs** on Serverless compute for each task
4. **Polls job status** and manages workflow state in `st.session_state`
5. **Displays real-time progress** in the Streamlit UI

**Key Design Choice**: Orchestrator state lives in Streamlit session memory, not in an external database. This makes it lightweight and stateless between user sessions.

### Microservices (Databricks Notebooks)

Each microservice runs as a **separate Databricks Job** on Serverless compute:

1. Receives parameters from orchestrator via `dbutils.widgets`
2. Loads data from Unity Catalog
3. Performs its specific task (routing, stacking, voting, etc.)
4. Logs all results to MLflow
5. Saves outputs back to Unity Catalog
6. Returns metadata to orchestrator via `dbutils.notebook.exit()`

**Serverless Compute Benefits**:
- Auto-scaling based on workload
- No cluster management overhead
- Pay-per-use pricing
- Faster startup times (~30 seconds vs 5+ minutes for clusters)

## Usage

### 1. Submit a Workflow

Paste your YAML configuration in the sidebar and click **🚀 Launch Workflow**:

```yaml
obsrv:
  context:
    name: credit_risk_ensemble
    compute:
      serverless: [GPU]
    timeout: 15 minutes
    metric:
      classification: [accuracy, f1, auc]
    sample:
      size: 50000
      method: [stratified]
    fold_type: [stratified]
    source:
      catalog: main
      schema: credit_risk
      table: training_data
      target: default_label
  job:
    - task: route_cluster
      route:
        cluster:
          kmeans:
            n_clusters: 3
    - task: stack_top_any
      stack:
        top_n: 5
      depends_on:
        - task: route_cluster
    - task: vote_top_alg
      vote:
        top_alg: 3
```

### 2. Monitor Progress

The Streamlit UI shows:
- Real-time task status (pending → running → completed/failed)
- Job Run IDs for each task
- Task dependencies
- Errors (if any)

### 3. Access Results

All results are logged to:
- **MLflow**: Experiments at `/Experiments/ensemble_{workflow_id}`
- **Unity Catalog**: Output tables with naming convention `{table}_clustered_{workflow_id}_{task_id}`

## Inter-Service Communication

While the original design used **gRPC**, the Databricks Serverless approach uses:

1. **Unity Catalog** as the data passing layer (Delta tables)
2. **MLflow** for model artifacts and metadata
3. **Databricks Jobs API** for orchestration

This is more efficient for Databricks-native workflows since:
- No need to manage gRPC servers on ephemeral compute
- Unity Catalog handles large data transfers efficiently
- MLflow provides built-in versioning and lineage

## Task Dependencies

Dependencies are handled in-process by the orchestrator:

```python
def _wait_for_dependencies(self, workflow_id: str, dependencies: List[str]):
    """Poll dependent tasks until complete"""
    for dep_id in dependencies:
        while dep_task.status == "running":
            status = self.get_job_status(dep_task.job_run_id)
            if status['result_state'] == 'SUCCESS':
                dep_task.status = "completed"
                break
            asyncio.sleep(5)  # Poll every 5 seconds
```

## Scaling Considerations

**Current Design** (Single Streamlit Instance):
- Good for: 1-10 concurrent workflows
- Limitation: Single Streamlit process memory
- State: Lost on Streamlit app restart

**Production Enhancements** (Optional):
1. Add **external state store** (Cosmos DB, DynamoDB)
2. Use **Databricks Workflows** instead of in-process orchestration
3. Implement **webhook callbacks** instead of polling
4. Add **workflow persistence** to survive restarts

## Example Microservices

### route_cluster_service
- Uses scikit-learn for clustering (K-means, hierarchical, etc.)
- Outputs clustered data to Unity Catalog
- Runs on No-GPU Serverless

### stack_top_any_service
- Calls Databricks AutoML to train base models
- Generates OOF predictions via K-fold CV
- Trains meta-learner (stacking)
- Runs on GPU Serverless if specified

### boost_service
- Routes to appropriate AutoML boosting method
- Supports GBM, XGBoost, LightGBM, CatBoost
- Runs on GPU Serverless

## Troubleshooting

**Q: Workflow stuck in "running"**
- Check Databricks Jobs UI for actual job status
- Verify MLflow experiment logs
- Check Unity Catalog permissions

**Q: Task failed with import error**
- Ensure all dependencies in notebook `%pip install` cells
- Check Databricks Runtime version compatibility

**Q: Can't see workflow after Streamlit restart**
- Expected behavior - state is in-memory only
- For persistence, add external state store

## Next Steps

1. Implement remaining microservices (route_feature, vote_weight, etc.)
2. Add Unity Catalog deployment service
3. Enhance UI with workflow visualization (DAG diagram)
4. Add workflow export/import functionality
5. Implement webhook-based status updates instead of polling
