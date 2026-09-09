CREATE TABLE IF NOT EXISTS customer_orders_db.bronze_customer_orders (
    order_id       STRING,
    customer_id    STRING,
    product_sku    STRING,
    quantity       STRING,
    order_date     STRING,
    order_status   STRING,
    order_total    STRING,
    updated_at     STRING,
    ingestion_date STRING
)
LOCATION 's3://data-lake-<account>-us-east-1/bronze/customer_orders/'
TBLPROPERTIES ('classification' = 'parquet');
