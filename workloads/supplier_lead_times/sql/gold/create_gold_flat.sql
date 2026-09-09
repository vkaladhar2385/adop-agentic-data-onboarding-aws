CREATE TABLE IF NOT EXISTS supplier_lead_times_db.gold_supplier_lead_times (
    supplier_id      STRING,
    supplier_name    STRING,
    product_category STRING,
    lead_time_days   INT,
    min_order_qty    INT,
    country_code     STRING,
    is_preferred     BOOLEAN,
    effective_date   TIMESTAMP,
    updated_at       TIMESTAMP,
    ingestion_date   STRING,
    lead_time_weeks  DOUBLE
)
LOCATION 's3://data-lake-<account>-us-east-1/gold/supplier_lead_times/'
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format' = 'parquet',
    'write_compression' = 'snappy'
);
