# stack: pyspark-iceberg
# Logic mirrors config/transformations.yaml and local_runner.py (unit-test source of truth).
"""PySpark transform helpers for advisory_transactions Glue ETL jobs."""
from __future__ import annotations

import sys
from pathlib import Path

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

# Repo import or Glue flat pii.py via --extra-py-files
try:
    from shared.utils.pii import hash_token, mask_email, mask_ssn
except ImportError:
    from pii import hash_token, mask_email, mask_ssn  # type: ignore

DECIMAL_COLS = [
    "quantity",
    "unit_price",
    "gross_amount",
    "commission",
    "fees",
    "net_amount",
]
UPPER_COLS = ["currency", "transaction_type", "asset_class", "account_type"]


def _load_yaml(name: str) -> dict:
    import yaml

    candidates = [
        Path(name),
        Path("/tmp") / name,
        Path(__file__).resolve().parent / name,
    ]
    for path in candidates:
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found (Glue: ensure --extra-files includes it)")


def bronze_to_silver_df(bronze: DataFrame, cfg: dict | None = None) -> tuple[DataFrame, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    b2s = cfg["bronze_to_silver"]
    df = bronze

    keys = b2s["dedup"]["keys"]
    order_by = b2s["dedup"]["order_by"]
    window = Window.partitionBy(*keys).orderBy(F.desc(order_by))
    df = df.withColumn("_rn", F.row_number().over(window)).filter(F.col("_rn") == 1).drop("_rn")

    for col_name in df.columns:
        if dict(df.dtypes).get(col_name) == "string":
            df = df.withColumn(col_name, F.trim(F.col(col_name)))
    for col_name in b2s["string_ops"]["uppercase"]:
        df = df.withColumn(col_name, F.upper(F.col(col_name)))

    qty = F.col("quantity").cast("double")
    unit = F.col("unit_price").cast("double")
    gross = F.col("gross_amount").cast("double")
    commission = F.col("commission").cast("double")
    fees = F.col("fees").cast("double")
    net = F.col("net_amount").cast("double")
    trade_dt = F.to_date(F.col("trade_date"), "yyyy-MM-dd")

    df = (
        df.withColumn("invalid_trade_date", trade_dt.isNull())
        .withColumn("negative_quantity", qty < 0)
        .withColumn(
            "missing_net_amount",
            F.col("net_amount").isNull() | (F.trim(F.col("net_amount")) == ""),
        )
        .withColumn("broken_gross_formula", F.abs(gross - (qty * unit)) > 0.01)
        .withColumn("broken_net_formula", F.abs(net - (gross - commission - fees)) > 0.01)
    )

    flag_cols = [
        "invalid_trade_date",
        "negative_quantity",
        "missing_net_amount",
        "broken_gross_formula",
        "broken_net_formula",
    ]
    bad = F.col(flag_cols[0])
    for col_name in flag_cols[1:]:
        bad = bad | F.col(col_name)

    quarantine = df.filter(bad)
    quarantine = quarantine.withColumn(
        "quarantine_reason",
        F.concat_ws(
            ",",
            *[
                F.when(F.col(c), F.lit(c)).otherwise(F.lit(None))
                for c in flag_cols
            ],
        ),
    )

    silver = df.filter(~bad).drop(*flag_cols)

    for col_name in DECIMAL_COLS:
        silver = silver.withColumn(col_name, F.col(col_name).cast("double"))
    silver = (
        silver.withColumn("trade_date", F.to_date(F.col("trade_date")))
        .withColumn("settlement_date", F.to_date(F.col("settlement_date")))
    )

    mask_ssn_udf = F.udf(mask_ssn, StringType())
    mask_email_udf = F.udf(mask_email, StringType())
    hash_token_udf = F.udf(hash_token, StringType())
    silver = (
        silver.withColumn("client_ssn", mask_ssn_udf(F.col("client_ssn")))
        .withColumn("client_email", mask_email_udf(F.col("client_email")))
        .withColumn("client_id", hash_token_udf(F.col("client_id")))
        .withColumn("trade_year", F.year(F.col("trade_date")))
        .withColumn("trade_month", F.month(F.col("trade_date")))
    )

    return silver, quarantine


def silver_to_gold_tables(silver: DataFrame, cfg: dict | None = None) -> dict[str, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    s2g = cfg["silver_to_gold"]
    suppress = s2g["gold_pii_policy"]["suppress"]

    fact_cols = (
        ["transaction_id", "account_id", "advisor_id", "security_id", "trade_date"]
        + s2g["fact"]["measures"]
    )
    fact = silver.select(*fact_cols)

    dim_account = silver.select("account_id", "account_type", "branch_code", "client_id").dropDuplicates(
        ["account_id"]
    )
    dim_advisor = silver.select("advisor_id", "advisor_name", "branch_code").dropDuplicates(["advisor_id"])
    dim_security = silver.select("security_id", "security_name", "asset_class").dropDuplicates(["security_id"])
    dim_date = silver.select("trade_date", "trade_year", "trade_month").dropDuplicates(["trade_date"])
    dim_date = dim_date.withColumn(
        "trade_quarter",
        F.when(F.col("trade_month").isNotNull(), ((F.col("trade_month") - 1) / 3 + 1).cast("int")).otherwise(
            F.lit(None)
        ),
    )

    summary = (
        silver.groupBy("advisor_id", "trade_date")
        .agg(
            F.sum("net_amount").alias("total_net_amount"),
            F.sum("commission").alias("total_commission"),
            F.count("transaction_id").alias("transaction_count"),
        )
    )

    gold = {
        "fact_transactions": fact,
        "dim_account": dim_account,
        "dim_advisor": dim_advisor,
        "dim_security": dim_security,
        "dim_date": dim_date,
        "gold_advisor_daily_summary": summary,
    }

    for name, frame in list(gold.items()):
        drop_cols = [c for c in suppress if c in frame.columns]
        if drop_cols:
            gold[name] = frame.drop(*drop_cols)
    return gold


def configure_iceberg_catalog(spark, warehouse: str) -> None:
    """Ensure glue_catalog is registered (Glue ETL jobs should set this via --conf)."""
    if spark.conf.get("spark.sql.catalog.glue_catalog", None):
        return
    root = warehouse.rstrip("/") + "/"
    # Static Spark configs (extensions, catalog class) must be set via Glue --conf at job start.
    for key, value in (
        ("spark.sql.catalog.glue_catalog", "org.apache.iceberg.spark.SparkCatalog"),
        ("spark.sql.catalog.glue_catalog.warehouse", root),
        ("spark.sql.catalog.glue_catalog.catalog-impl", "org.apache.iceberg.aws.glue.GlueCatalog"),
        ("spark.sql.catalog.glue_catalog.io-impl", "org.apache.iceberg.aws.s3.S3FileIO"),
        ("spark.sql.defaultCatalog", "glue_catalog"),
    ):
        try:
            spark.conf.set(key, value)
        except Exception as exc:  # pragma: no cover - static config already set or locked
            print(f"[iceberg] skip conf {key}: {exc}")


def _warehouse_from_s3_path(path: str) -> str:
    """Derive catalog warehouse root from a zone path (s3://bucket/zone/workload/ -> s3://bucket/)."""
    without_scheme = path.replace("s3://", "", 1)
    bucket = without_scheme.split("/", 1)[0]
    return f"s3://{bucket}/"


def _drop_non_iceberg_glue_table(
    database: str, table: str, *, expected_path_fragment: str | None = None
) -> None:
    """Remove catalog entries that block Iceberg overwrite (Parquet DDL or wrong warehouse path)."""
    import boto3
    glue = boto3.client("glue")
    try:
        existing = glue.get_table(DatabaseName=database, Name=table)["Table"]
        params = existing.get("Parameters") or {}
        meta = params.get("metadata_location", "")
        if params.get("table_type", "").upper() == "ICEBERG":
            if expected_path_fragment and expected_path_fragment in meta:
                return
            if expected_path_fragment and expected_path_fragment not in meta:
                glue.delete_table(DatabaseName=database, Name=table)
                print(f"[iceberg] dropped misplaced iceberg table {database}.{table} ({meta})")
                return
            return
        glue.delete_table(DatabaseName=database, Name=table)
        print(f"[iceberg] dropped non-iceberg catalog entry {database}.{table}")
    except glue.exceptions.EntityNotFoundException:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[iceberg] could not drop {database}.{table}: {exc}")


def write_iceberg_table(
    df: DataFrame, database: str, table: str, warehouse: str | None = None,
    *, expected_path_fragment: str | None = None,
) -> None:
    spark = df.sparkSession
    if warehouse is None:
        warehouse = "s3://"
    configure_iceberg_catalog(spark, warehouse)
    full_name = f"glue_catalog.{database}.{table}"
    _drop_non_iceberg_glue_table(database, table, expected_path_fragment=expected_path_fragment)
    df.write.format("iceberg").mode("overwrite").saveAsTable(full_name)
    print(f"[iceberg] wrote {full_name} rows={df.count()}")
