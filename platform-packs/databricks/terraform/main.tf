terraform {
  required_version = ">= 1.5"
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.50"
    }
  }
}

provider "databricks" {
  host = var.workspace_url
}

resource "databricks_job" "pipeline" {
  name        = "adop-${var.workload}-pipeline"
  description = "ADOP medallion pipeline (${var.workload}, ${var.lake_format})"

  task {
    task_key = "ingest_to_bronze"
    spark_python_task {
      python_file = "/Workspace/adop/${var.workload}/scripts/extract/ingest_to_bronze.py"
    }
  }

  task {
    task_key = "bronze_to_silver"
    depends_on {
      task_key = "ingest_to_bronze"
    }
    spark_python_task {
      python_file = "/Workspace/adop/${var.workload}/scripts/transform/bronze_to_silver.py"
    }
  }

  task {
    task_key = "quality_silver"
    depends_on {
      task_key = "bronze_to_silver"
    }
    spark_python_task {
      python_file = "/Workspace/adop/${var.workload}/scripts/quality/run_quality_checks.py"
    }
  }

  task {
    task_key = "silver_to_gold"
    depends_on {
      task_key = "quality_silver"
    }
    spark_python_task {
      python_file = "/Workspace/adop/${var.workload}/scripts/transform/silver_to_gold.py"
    }
  }

  task {
    task_key = "quality_gold"
    depends_on {
      task_key = "silver_to_gold"
    }
    spark_python_task {
      python_file = "/Workspace/adop/${var.workload}/scripts/quality/run_quality_checks.py"
    }
  }
}
