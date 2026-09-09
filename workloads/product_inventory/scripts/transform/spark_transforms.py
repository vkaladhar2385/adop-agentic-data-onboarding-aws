# stack: pyspark-iceberg
"""PySpark helpers for product_inventory Glue ETL jobs. Mirrors local_runner."""
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
    df = bronze
    keys = b2s["dedup"]["keys"]
    order_by = b2s["dedup"]["order_by"]
    window = Window.partitionBy(*keys).orderBy(F.desc(order_by))
    sku_blank = F.col("sku").isNull() | (F.trim(F.col("sku")) == "")
    keyed = df.filter(~sku_blank).withColumn("_rn", F.row_number().over(window)).filter(F.col("_rn") == 1).drop("_rn")
    df = keyed.unionByName(df.filter(sku_blank), allowMissingColumns=True)

    for col_name in df.columns:
        if dict(df.dtypes).get(col_name) == "string":
            df = df.withColumn(col_name, F.trim(F.col(col_name)))
    for col_name in b2s["string_ops"]["uppercase"]:
        df = df.withColumn(col_name, F.upper(F.col(col_name)))

    on_hand = F.col("on_hand_qty").cast("double")
    reserved = F.col("reserved_qty").cast("double")
    unit_cost = F.col("unit_cost").cast("double")
    list_price = F.col("list_price").cast("double")
    df = (
        df.withColumn("missing_sku", F.col("sku").isNull() | (F.trim(F.col("sku")) == ""))
        .withColumn("negative_on_hand", on_hand < 0)
    )
    bad = F.col("missing_sku") | F.col("negative_on_hand")
    quarantine = df.filter(bad).withColumn(
        "quarantine_reason",
        F.concat_ws(
            ",",
            F.when(F.col("missing_sku"), F.lit("missing_sku")),
            F.when(F.col("negative_on_hand"), F.lit("negative_on_hand")),
        ),
    )
    silver = (
        df.filter(~bad)
        .drop("missing_sku", "negative_on_hand")
        .withColumn("on_hand_qty", F.col("on_hand_qty").cast("int"))
        .withColumn("reserved_qty", F.col("reserved_qty").cast("int"))
        .withColumn("unit_cost", unit_cost)
        .withColumn("list_price", list_price)
        .withColumn("updated_at", F.to_timestamp(F.col("updated_at")))
        .withColumn("available_qty", F.col("on_hand_qty") - F.col("reserved_qty"))
        .withColumn("inventory_value", F.col("on_hand_qty") * F.col("unit_cost"))
        .withColumn(
            "margin_pct",
            F.when(list_price > 0, (list_price - unit_cost) / list_price),
        )
    )
    return silver, quarantine


def silver_to_gold_dfs(silver: DataFrame, cfg: dict | None = None) -> dict[str, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    s2g = cfg["silver_to_gold"]
    suppress = [c for c in s2g["gold_pii_policy"]["suppress"] if c in silver.columns]
    gold = silver.drop(*suppress) if suppress else silver
    return {s2g.get("table", "gold_product_inventory"): gold}


def configure_iceberg_catalog(spark, warehouse: str) -> None:
    if spark.conf.get("spark.sql.catalog.glue_catalog", None):
        return
    root = warehouse.rstrip("/") + "/"
    for key, value in (
        ("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog"),
        ("spark.sql.catalog.glue_catalog.warehouse", root),
        ("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog"),
        ("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO"),
        ("spark.sql.defaultCatalog", "glue_catalog"),
    ):
        try:
            spark.conf.set(key, value)
        except Exception as exc:  # pragma: no cover
            print(f"[iceberg] skip conf {key}: {exc}")


def _warehouse_from_s3_path(path: str) -> str:
    without_scheme = path.replace("s3://", "", 1)
    bucket = without_scheme.split("/", 1)[0]
    return f"s3://{bucket}/"


def write_iceberg_table(df: DataFrame, database: str, table: str, warehouse: str | None = None) -> None:
    spark = df.sparkSession
    configure_iceberg_catalog(spark, warehouse or "s3://")
    full_name = f"glue_catalog.{database}.{table}"
    df.write.format("iceberg").mode("overwrite").saveAsTable(full_name)
    print(f"[iceberg] wrote {full_name} rows={df.count()}")
