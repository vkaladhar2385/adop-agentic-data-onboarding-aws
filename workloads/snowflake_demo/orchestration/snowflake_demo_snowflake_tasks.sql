-- ADOP Phase 7.5: Snowflake Tasks root + dependent chain (Mode B platform)
-- workload=snowflake_demo spec_hash=1aff7ef6f87cd5b6357a3d49176070d22899c77253d2b7b631f18a6c33477d54 template_id=snowflake_tasks

USE DATABASE SNOWFLAKE_DEMO_DB;
USE SCHEMA PIPELINE;

CREATE OR REPLACE TASK snowflake_demo_ingest_to_bronze
  WAREHOUSE = ADOP_WH
  SCHEDULE = 'USING CRON 0 6 * * MON UTC'
AS
  CALL SYSTEM$EXECUTE_PYTHON('/adop/snowflake_demo/scripts/extract/ingest_to_bronze.py');

CREATE OR REPLACE TASK snowflake_demo_bronze_to_silver
  WAREHOUSE = ADOP_WH
  AFTER snowflake_demo_ingest_to_bronze
AS
  CALL SYSTEM$EXECUTE_PYTHON('/adop/snowflake_demo/scripts/transform/bronze_to_silver.py');

CREATE OR REPLACE TASK snowflake_demo_quality_silver
  WAREHOUSE = ADOP_WH
  AFTER snowflake_demo_bronze_to_silver
AS
  CALL SYSTEM$EXECUTE_PYTHON('/adop/snowflake_demo/scripts/quality/run_quality_checks.py', '--zone', 'silver');

CREATE OR REPLACE TASK snowflake_demo_silver_to_gold
  WAREHOUSE = ADOP_WH
  AFTER snowflake_demo_quality_silver
AS
  CALL SYSTEM$EXECUTE_PYTHON('/adop/snowflake_demo/scripts/transform/silver_to_gold.py');

CREATE OR REPLACE TASK snowflake_demo_quality_gold
  WAREHOUSE = ADOP_WH
  AFTER snowflake_demo_silver_to_gold
AS
  CALL SYSTEM$EXECUTE_PYTHON('/adop/snowflake_demo/scripts/quality/run_quality_checks.py', '--zone', 'gold');

-- Resume leaf-to-root so dependencies propagate (Gate C live deploy).
ALTER TASK snowflake_demo_quality_gold RESUME;
ALTER TASK snowflake_demo_silver_to_gold RESUME;
ALTER TASK snowflake_demo_quality_silver RESUME;
ALTER TASK snowflake_demo_bronze_to_silver RESUME;
ALTER TASK snowflake_demo_ingest_to_bronze RESUME;
