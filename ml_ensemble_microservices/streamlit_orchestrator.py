"""
Streamlit Orchestrator for Databricks AutoML Ensemble
Runs orchestrator in Streamlit app memory, spawns tasks on Databricks Serverless
"""

import streamlit as st
import yaml
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd
from dataclasses import dataclass, asdict
from enum import Enum

# Databricks SDK imports
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import Task, TaskDependency, NotebookTask, Source
from databricks.sdk.service.compute import ServerlessComputeType

# In-memory state management
if 'workflow_state' not in st.session_state:
    st.session_state.workflow_state = {}
if 'active_jobs' not in st.session_state:
    st.session_state.active_jobs = {}


class TaskType(Enum):
    ROUTE_CLUSTER = "route_cluster"
    ROUTE_FEATURE = "route_feature"
    ROUTE_EXTERNAL = "route_external"
    STACK_TOP_ANY = "stack_top_any"
    STACK_TOP_ALG = "stack_top_alg"
    STACK_TOP_N_ALG = "stack_top_n_alg"
    STACK_BLEND = "stack_blend"
    STACK_CLASSWISE = "stack_classwise"
    BOOST = "boost"
    VOTE_TOP_ALG = "vote_top_alg"
    VOTE_MIX = "vote_mix"
    VOTE_WEIGHT = "vote_weight"


@dataclass
class WorkflowContext:
    name: str
    compute: Dict[str, Any]
    timeout: str
    metric: Dict[str, List[str]]
    sample: Dict[str, Any]
    fold_type: List[str]
    source: Dict[str, Any]


@dataclass
class JobTask:
    task_id: str
    task_type: TaskType
    config: Dict[str, Any]
    depends_on: List[str]
    status: str = "pending"
    job_run_id: Optional[int] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class StreamlitOrchestrator:
    """
    In-process orchestrator running in Streamlit app memory.
    Spawns each microservice task on Databricks Serverless compute.
    """
    
    def __init__(self):
        self.w = WorkspaceClient()
        self.notebook_base_path = "/Workspace/ml_ensemble_microservices"
        
    def parse_yaml_config(self, yaml_content: str) -> Dict[str, Any]:
        """Parse YAML workflow configuration"""
        config = yaml.safe_load(yaml_content)
        return config['obsrv']
    
    def create_dag(self, workflow_config: Dict[str, Any]) -> List[JobTask]:
        """Build DAG from workflow configuration"""
        tasks = []
        
        for task_def in workflow_config['job']:
            task_name = task_def['task']
            task_type = TaskType(task_name.replace('_', '_').lower())
            
            # Extract task-specific config
            task_config = {k: v for k, v in task_def.items() if k not in ['task', 'depends_on']}
            
            # Get dependencies
            depends_on = []
            if 'depends_on' in task_def:
                for dep in task_def['depends_on']:
                    depends_on.append(dep['task'])
            
            job_task = JobTask(
                task_id=task_name,
                task_type=task_type,
                config=task_config,
                depends_on=depends_on
            )
            tasks.append(job_task)
        
        return tasks
    
    def create_serverless_job(
        self, 
        task: JobTask, 
        context: WorkflowContext,
        workflow_id: str
    ) -> int:
        """
        Create and run a Databricks job on Serverless compute.
        Each microservice runs as a separate serverless job.
        """
        
        # Determine which microservice notebook to use
        notebook_path = f"{self.notebook_base_path}/{task.task_type.value}_service"
        
        # Prepare task parameters (passed to notebook)
        task_params = {
            "workflow_id": workflow_id,
            "task_id": task.task_id,
            "config": json.dumps(task.config),
            "context": json.dumps(asdict(context)),
            "catalog": context.source.get('catalog'),
            "schema": context.source.get('schema'),
            "table": context.source.get('table'),
            "target": context.source.get('target'),
        }
        
        # Create job with Databricks Serverless compute
        job = self.w.jobs.create(
            name=f"ensemble_{workflow_id}_{task.task_id}",
            tasks=[
                Task(
                    task_key=task.task_id,
                    notebook_task=NotebookTask(
                        notebook_path=notebook_path,
                        source=Source.WORKSPACE,
                        base_parameters=task_params
                    ),
                    compute={"serverless_compute": ServerlessComputeType.GPU}
                    if context.compute.get('serverless') == ['GPU']
                    else {"serverless_compute": ServerlessComputeType.NO_GPU},
                    timeout_seconds=self._parse_timeout(context.timeout),
                )
            ],
            timeout_seconds=self._parse_timeout(context.timeout) + 300,  # Add buffer
        )
        
        # Run the job immediately
        run = self.w.jobs.run_now(job_id=job.job_id)
        
        return run.run_id
    
    def _parse_timeout(self, timeout_str: str) -> int:
        """Convert timeout string to seconds"""
        if 'minute' in timeout_str:
            return int(timeout_str.split()[0]) * 60
        elif 'hour' in timeout_str:
            return int(timeout_str.split()[0]) * 3600
        return 600  # Default 10 minutes
    
    def get_job_status(self, run_id: int) -> Dict[str, Any]:
        """Check status of a Databricks job run"""
        run = self.w.jobs.get_run(run_id=run_id)
        
        return {
            "state": run.state.life_cycle_state.value,
            "result_state": run.state.result_state.value if run.state.result_state else None,
            "start_time": run.start_time,
            "end_time": run.end_time,
        }
    
    def execute_workflow(
        self, 
        workflow_config: Dict[str, Any],
        workflow_id: str
    ):
        """
        Execute workflow by spawning serverless jobs for each task.
        Runs in Streamlit app memory, orchestrates remote execution.
        """
        
        # Parse context
        context = WorkflowContext(**workflow_config['context'])
        
        # Build DAG
        tasks = self.create_dag(workflow_config)
        
        # Store in session state
        st.session_state.workflow_state[workflow_id] = {
            "context": context,
            "tasks": tasks,
            "status": "running",
            "created_at": datetime.now()
        }
        
        # Topological sort for execution order
        execution_order = self._topological_sort(tasks)
        
        # Execute tasks respecting dependencies
        for task in execution_order:
            # Wait for dependencies
            if task.depends_on:
                self._wait_for_dependencies(workflow_id, task.depends_on)
            
            # Spawn serverless job
            try:
                run_id = self.create_serverless_job(task, context, workflow_id)
                task.job_run_id = run_id
                task.status = "running"
                
                st.session_state.active_jobs[run_id] = {
                    "workflow_id": workflow_id,
                    "task_id": task.task_id
                }
                
            except Exception as e:
                task.status = "failed"
                task.error = str(e)
                st.error(f"Failed to launch task {task.task_id}: {e}")
    
    def _topological_sort(self, tasks: List[JobTask]) -> List[JobTask]:
        """Sort tasks by dependencies (simple implementation)"""
        sorted_tasks = []
        remaining = tasks.copy()
        
        while remaining:
            # Find tasks with no unmet dependencies
            ready = [
                t for t in remaining 
                if all(dep in [st.task_id for st in sorted_tasks] for dep in t.depends_on)
            ]
            
            if not ready:
                raise ValueError("Circular dependency detected in workflow")
            
            sorted_tasks.extend(ready)
            for t in ready:
                remaining.remove(t)
        
        return sorted_tasks
    
    def _wait_for_dependencies(self, workflow_id: str, dependencies: List[str]):
        """Wait for dependent tasks to complete"""
        workflow = st.session_state.workflow_state[workflow_id]
        tasks = {t.task_id: t for t in workflow['tasks']}
        
        for dep_id in dependencies:
            dep_task = tasks[dep_id]
            
            while dep_task.status == "running":
                if dep_task.job_run_id:
                    status = self.get_job_status(dep_task.job_run_id)
                    
                    if status['result_state'] == 'SUCCESS':
                        dep_task.status = "completed"
                    elif status['result_state'] in ['FAILED', 'CANCELED']:
                        dep_task.status = "failed"
                        raise Exception(f"Dependency {dep_id} failed")
                
                asyncio.sleep(5)  # Poll every 5 seconds
    
    def poll_active_jobs(self):
        """Poll all active jobs for status updates (called by Streamlit auto-rerun)"""
        for run_id, job_info in list(st.session_state.active_jobs.items()):
            status = self.get_job_status(run_id)
            
            workflow_id = job_info['workflow_id']
            task_id = job_info['task_id']
            
            workflow = st.session_state.workflow_state[workflow_id]
            task = next(t for t in workflow['tasks'] if t.task_id == task_id)
            
            if status['result_state'] == 'SUCCESS':
                task.status = "completed"
                del st.session_state.active_jobs[run_id]
            elif status['result_state'] in ['FAILED', 'CANCELED']:
                task.status = "failed"
                del st.session_state.active_jobs[run_id]


def main():
    st.set_page_config(page_title="ML Ensemble Orchestrator", layout="wide")
    
    st.title("🤖 Databricks AutoML Ensemble Orchestrator")
    st.caption("In-process orchestration with Serverless execution")
    
    orchestrator = StreamlitOrchestrator()
    
    # Sidebar - Workflow Submission
    with st.sidebar:
        st.header("Submit Workflow")
        
        yaml_input = st.text_area(
            "YAML Configuration",
            height=400,
            placeholder="Paste your workflow YAML here..."
        )
        
        if st.button("🚀 Launch Workflow", type="primary"):
            if yaml_input:
                try:
                    config = orchestrator.parse_yaml_config(yaml_input)
                    workflow_id = f"wf_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    orchestrator.execute_workflow(config, workflow_id)
                    st.success(f"Workflow {workflow_id} launched!")
                    
                except Exception as e:
                    st.error(f"Failed to launch workflow: {e}")
            else:
                st.warning("Please provide a YAML configuration")
        
        st.divider()
        
        # Example YAML
        with st.expander("📄 Example YAML"):
            st.code("""
obsrv:
  context:
    name: my_ensemble
    compute:
      serverless: [GPU]
    timeout: 10 minutes
    metric:
      classification: [accuracy, f1]
    sample:
      size: 10000
      method: [random]
    fold_type: [kfold]
    source:
      catalog: main
      schema: ml_data
      table: training_set
      target: label
  job:
    - task: route_cluster
      route:
        cluster: kmeans
    - task: stack_top_any
      stack:
        top_n: 5
      depends_on:
        - task: route_cluster
    - task: vote_top_alg
      vote:
        top_alg: 3
            """, language="yaml")
    
    # Main area - Active Workflows
    st.header("Active Workflows")
    
    if not st.session_state.workflow_state:
        st.info("No active workflows. Submit a workflow from the sidebar.")
    else:
        # Poll active jobs
        orchestrator.poll_active_jobs()
        
        # Display workflows
        for workflow_id, workflow in st.session_state.workflow_state.items():
            with st.expander(f"📊 {workflow_id} - {workflow['status']}", expanded=True):
                
                # Workflow metadata
                col1, col2, col3 = st.columns(3)
                col1.metric("Workflow ID", workflow_id)
                col2.metric("Status", workflow['status'])
                col3.metric("Created", workflow['created_at'].strftime("%Y-%m-%d %H:%M:%S"))
                
                # Task status table
                st.subheader("Task Status")
                
                task_data = []
                for task in workflow['tasks']:
                    task_data.append({
                        "Task": task.task_id,
                        "Type": task.task_type.value,
                        "Status": task.status,
                        "Job Run ID": task.job_run_id or "—",
                        "Dependencies": ", ".join(task.depends_on) if task.depends_on else "None",
                        "Error": task.error or "—"
                    })
                
                df = pd.DataFrame(task_data)
                
                # Color code status
                def color_status(val):
                    if val == "completed":
                        return 'background-color: #d4edda'
                    elif val == "running":
                        return 'background-color: #fff3cd'
                    elif val == "failed":
                        return 'background-color: #f8d7da'
                    return ''
                
                st.dataframe(
                    df.style.applymap(color_status, subset=['Status']),
                    use_container_width=True
                )
                
                # Refresh button
                if st.button(f"🔄 Refresh {workflow_id}"):
                    st.rerun()
    
    # Auto-refresh every 10 seconds if there are active jobs
    if st.session_state.active_jobs:
        import time
        time.sleep(10)
        st.rerun()


if __name__ == "__main__":
    main()
