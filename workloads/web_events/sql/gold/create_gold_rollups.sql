-- GDPR Gold: aggregates only. No email, no IP, no raw user identifier.
-- user_id in the erasure index is the hashed token used for right-to-erasure.

CREATE TABLE IF NOT EXISTS web_events_db.gold_hourly_traffic (
    traffic_source  STRING,
    event_hour      TIMESTAMP,
    event_count     BIGINT,
    page_views      BIGINT,
    unique_users    BIGINT
)
LOCATION 's3://data-lake-<account>-us-east-1/gold/web_events/hourly_traffic/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'parquet');

CREATE TABLE IF NOT EXISTS web_events_db.gold_erasure_index (
    user_id      STRING,   -- hashed token
    event_count  BIGINT,
    erasure_hook STRING
)
LOCATION 's3://data-lake-<account>-us-east-1/gold/web_events/erasure_index/'
TBLPROPERTIES ('table_type' = 'ICEBERG', 'format' = 'parquet');
