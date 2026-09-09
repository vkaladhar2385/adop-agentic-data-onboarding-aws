CREATE TABLE IF NOT EXISTS customer_orders_db.gold_customer_orders (
    order_id     STRING,
    product_sku  STRING,
    quantity     INT,
    order_date   DATE,
    order_status STRING,
    order_total  DOUBLE,
    updated_at   TIMESTAMP,
    line_value   DOUBLE
)
LOCATION 's3://data-lake-<account>-us-east-1/gold/customer_orders/'
TBLPROPERTIES ('table_type' = 'ICEBERG');
