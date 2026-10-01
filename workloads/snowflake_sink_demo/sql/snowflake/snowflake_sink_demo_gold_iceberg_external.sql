-- ADOP Phase 7.4: Snowflake Mode A Gold sink (external Iceberg over aws lake)
-- workload=snowflake_sink_demo spec_hash=48734718518001ced20e6d9b6c1934c3dbbeb134e7c0723fe3a807d05b214c56 template_id=gold_iceberg_external
-- Gate C: apply after storage integration + external volume exist in Snowflake.

USE DATABASE SNOWFLAKE_SINK_DEMO_DB;
USE SCHEMA GOLD;

CREATE OR REPLACE ICEBERG TABLE GOLD_SNOWFLAKE_SINK_DEMO
  EXTERNAL_VOLUME = 'ADOP_SNOWFLAKE_SINK_DEMO_GOLD_VOL'
  CATALOG = 'SNOWFLAKE'
  METADATA_FILE_PATH = 's3://<bucket>/gold/snowflake_sink_demo/gold_snowflake_sink_demo/metadata/';

-- Optional: grant read to analyst role (uncomment in live deploy)
-- GRANT SELECT ON TABLE GOLD_SNOWFLAKE_SINK_DEMO TO ROLE ANALYST;
