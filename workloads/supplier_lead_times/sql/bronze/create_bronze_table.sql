CREATE TABLE IF NOT EXISTS supplier_lead_times_db.bronze_supplier_lead_times (
    supplier_id      STRING,
    supplier_name    STRING,
    product_category STRING,
    lead_time_days   STRING,
    min_order_qty    STRING,
    country_code     STRING,
    is_preferred     STRING,
    effective_date   STRING,
    updated_at       STRING,
    ingestion_date   STRING
)
LOCATION 's3://data-lake-<account>-us-east-1/bronze/supplier_lead_times/'
TBLPROPERTIES ('classification' = 'parquet');
