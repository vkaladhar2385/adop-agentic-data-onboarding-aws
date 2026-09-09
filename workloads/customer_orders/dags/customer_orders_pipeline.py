# spec_hash: 860e3477d7a627f94fbbf13824eb36e9027ef1a2a16859f4cde8fba0251e72f2
# template_id: airflow_dag
# template_hash: bb35cd4c35617b65f82f484a41d18068110a2ff660f296bc82c4679586dde0b9
# schema_version: v1
# rendered_at: 2026-09-09T05:21:47Z
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models import Variable
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.operators.python import PythonOperator
from airflow.operators.dummy import DummyOperator

GLUE_SCRIPT_S3_PATH = Variable.get("glue_script_s3_path", default_var="s3://glue-scripts/")
GLUE_IAM_ROLE = Variable.get("glue_iam_role", default_var="AWSGlueServiceRole")

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(seconds=300),
    "retry_exponential_backoff": True,
    "email_on_failure": False,
}

DAG_ID = "customer_orders_pipeline"

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="customer_orders data pipeline (Bronze → Silver → Gold)",
    schedule_interval="0 7 * * *",
    start_date=datetime.fromisoformat("2026-01-01"),
    catchup=False,
    max_active_runs=1,
    tags=["customer_orders", "tier-b", "mwaa"],
) as dag:

    ingest_bronze = GlueJobOperator(
        task_id="ingest_bronze",
        job_name="customer_orders_ingest_bronze",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/extract/ingest_to_bronze.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        execution_timeout=timedelta(minutes=30),
    )

    transform_silver = GlueJobOperator(
        task_id="transform_silver",
        job_name="customer_orders_transform_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/transform/bronze_to_silver.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        execution_timeout=timedelta(minutes=45),
    )

    quality_check_silver = GlueJobOperator(
        task_id="quality_check_silver",
        job_name="customer_orders_quality_check_silver",
        script_location=f"{GLUE_SCRIPT_S3_PATH}quality_check.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        script_args={"--TABLE_NAME": "glue_catalog.customer_orders_db.silver_customer_orders", "--ZONE": "silver"},
    )

    aggregate_gold = GlueJobOperator(
        task_id="aggregate_gold",
        job_name="customer_orders_aggregate_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}scripts/transform/silver_to_gold.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        execution_timeout=timedelta(minutes=30),
    )

    quality_check_gold = GlueJobOperator(
        task_id="quality_check_gold",
        job_name="customer_orders_quality_check_gold",
        script_location=f"{GLUE_SCRIPT_S3_PATH}quality_check.py",
        iam_role_name=GLUE_IAM_ROLE,
        region_name=Variable.get("aws_region", default_var="us-east-1"),
        script_args={"--TABLE_NAME": "glue_catalog.customer_orders_db.gold_customer_orders", "--ZONE": "gold"},
    )

    # Task dependencies
    ingest_bronze >> transform_silver
    transform_silver >> quality_check_silver
    quality_check_silver >> aggregate_gold
    aggregate_gold >> quality_check_gold
