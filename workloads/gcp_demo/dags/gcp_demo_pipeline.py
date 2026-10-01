# spec_hash: a876bb000bc07686e8b51ea889918c9247910b3aa5dcb817d2a457ae2bba337b
# template_id: composer_dag
# template_hash: 6e284a580d12010f8773c9dabc75462823ec7c8f0b17189228ea2c0eedb5c237
# schema_version: v1
# rendered_at: 2026-10-01T23:35:13Z
"""Cloud Composer DAG for `gcp_demo` (GCP medallion + quality gates)."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.google.cloud.operators.dataproc import DataprocSubmitJobOperator
from airflow.operators.python import BranchPythonOperator, DummyOperator

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}

DAG_ID = "gcp_demo_pipeline"
PROJECT_ID = "adop-gcp-project"
REGION = "us-central1"
CLUSTER_NAME = "adop-gcp_demo"

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="gcp_demo medallion pipeline (Dataproc + GCS Iceberg)",
    schedule_interval="0 6 * * MON",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["adop", "gcp_demo", "gcp"],
) as dag:
    ingest = DataprocSubmitJobOperator(
        task_id="ingest_to_bronze",
        project_id=PROJECT_ID,
        region=REGION,
        job={
            "reference": {"project_id": PROJECT_ID},
            "placement": {"cluster_name": CLUSTER_NAME},
            "pyspark_job": {"main_python_file_uri": f"gs://adop-scripts/gcp_demo/ingest_to_bronze.py"},
        },
    )
    bronze_to_silver = DataprocSubmitJobOperator(
        task_id="bronze_to_silver",
        project_id=PROJECT_ID,
        region=REGION,
        job={
            "reference": {"project_id": PROJECT_ID},
            "placement": {"cluster_name": CLUSTER_NAME},
            "pyspark_job": {"main_python_file_uri": f"gs://adop-scripts/gcp_demo/bronze_to_silver.py"},
        },
    )
    quality_silver = DataprocSubmitJobOperator(
        task_id="quality_silver",
        project_id=PROJECT_ID,
        region=REGION,
        job={
            "reference": {"project_id": PROJECT_ID},
            "placement": {"cluster_name": CLUSTER_NAME},
            "pyspark_job": {"main_python_file_uri": f"gs://adop-scripts/gcp_demo/run_quality_checks.py"},
        },
    )

    def _silver_gate(**context):
        # Production: read GCS quality sidecar JSON; demo assumes pass.
        return "silver_to_gold"

    gate_silver = BranchPythonOperator(task_id="gate_silver", python_callable=_silver_gate)
    silver_to_gold = DataprocSubmitJobOperator(
        task_id="silver_to_gold",
        project_id=PROJECT_ID,
        region=REGION,
        job={
            "reference": {"project_id": PROJECT_ID},
            "placement": {"cluster_name": CLUSTER_NAME},
            "pyspark_job": {"main_python_file_uri": f"gs://adop-scripts/gcp_demo/silver_to_gold.py"},
        },
    )
    quality_gold = DataprocSubmitJobOperator(
        task_id="quality_gold",
        project_id=PROJECT_ID,
        region=REGION,
        job={
            "reference": {"project_id": PROJECT_ID},
            "placement": {"cluster_name": CLUSTER_NAME},
            "pyspark_job": {"main_python_file_uri": f"gs://adop-scripts/gcp_demo/run_quality_checks.py"},
        },
    )
    done = DummyOperator(task_id="pipeline_complete", trigger_rule="none_failed_min_one_success")

    ingest >> bronze_to_silver >> quality_silver >> gate_silver >> silver_to_gold >> quality_gold >> done
