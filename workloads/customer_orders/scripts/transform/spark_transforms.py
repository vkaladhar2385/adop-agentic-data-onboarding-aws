# stack: pyspark-iceberg
"""PySpark helpers for customer_orders Glue ETL jobs."""
from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F


def _load_yaml(name: str) -> dict:
    import yaml

    for path in (Path(name), Path("/tmp") / name, Path(__file__).resolve().parent / name):
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found")


def bronze_to_silver_df(bronze: DataFrame, cfg: dict | None = None) -> tuple[DataFrame, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    b2s = cfg["bronze_to_silver"]
    keys = b2s["dedup"]["keys"]
    order_by = b2s["dedup"]["order_by"]
    window = Window.partitionBy(*keys).orderBy(F.desc(order_by))
    oid_blank = F.col("order_id").isNull() | (F.trim(F.col("order_id")) == "")
    keyed = (
        bronze.filter(~oid_blank)
        .withColumn("_rn", F.row_number().over(window))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )
    df = keyed.unionByName(bronze.filter(oid_blank), allowMissingColumns=True)

    for col_name in df.columns:
        if dict(df.dtypes).get(col_name) == "string":
            df = df.withColumn(col_name, F.trim(F.col(col_name)))
    for col_name in b2s["string_ops"]["uppercase"]:
        df = df.withColumn(col_name, F.upper(F.col(col_name)))

    qty = F.col("quantity").cast("double")
    df = (
        df.withColumn("missing_order_id", oid_blank)
        .withColumn("invalid_quantity", qty.isNull() | (qty < 1))
    )
    bad = F.col("missing_order_id") | F.col("invalid_quantity")
    quarantine = df.filter(bad).withColumn(
        "quarantine_reason",
        F.concat_ws(
            ",",
            F.when(F.col("missing_order_id"), F.lit("missing_order_id")),
            F.when(F.col("invalid_quantity"), F.lit("invalid_quantity")),
        ),
    )
    silver = (
        df.filter(~bad)
        .drop("missing_order_id", "invalid_quantity")
        .withColumn("quantity", F.col("quantity").cast("int"))
        .withColumn("order_total", F.col("order_total").cast("double"))
        .withColumn("updated_at", F.to_timestamp(F.col("updated_at")))
        .withColumn("order_date", F.to_date(F.col("order_date")))
        .withColumn("line_value", F.col("order_total"))
    )
    return silver, quarantine


def silver_to_gold_dfs(silver: DataFrame, cfg: dict | None = None) -> dict[str, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    s2g = cfg["silver_to_gold"]
    suppress = [c for c in s2g["gold_pii_policy"]["suppress"] if c in silver.columns]
    gold = silver.drop(*suppress) if suppress else silver
    return {s2g.get("table", "gold_customer_orders"): gold}
