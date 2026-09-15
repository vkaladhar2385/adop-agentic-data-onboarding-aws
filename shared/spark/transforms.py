# stack: pyspark-iceberg
"""Config-driven PySpark helpers shared by every Glue ETL workload.

Uploaded flat as spark_transforms.py via --extra-py-files. Mirrors
shared.transforms.pandas_engine so local pytest and Glue cannot drift.
"""
from __future__ import annotations

from pathlib import Path

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

try:
    from shared.utils.pii import hash_token, mask_email, mask_ip, mask_ssn
except ImportError:  # pragma: no cover - Glue flat extra-py-files
    from pii import hash_token, mask_email, mask_ip, mask_ssn  # type: ignore

_PII_UDF = {
    "mask_ssn": mask_ssn,
    "mask_email": mask_email,
    "mask_ip": mask_ip,
    "hash_token": hash_token,
    "hash": hash_token,
}


def _load_yaml(name: str) -> dict:
    import yaml

    for path in (Path(name), Path("/tmp") / name, Path(__file__).resolve().parent / name):
        if path.is_file():
            with path.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found (Glue: ensure --extra-files includes it)")


def _blank(col: str):
    return F.col(col).isNull() | (F.trim(F.col(col).cast("string")) == "")


def _quarantine_rules(b2s: dict) -> list[dict]:
    explicit = b2s.get("quarantine_rules")
    if isinstance(explicit, list) and explicit:
        return explicit
    rules = []
    for name in b2s.get("quarantine_when") or []:
        if name.startswith("missing_"):
            rules.append({"id": name, "type": "blank", "column": name[len("missing_") :]})
        elif name.startswith("negative_"):
            col = name[len("negative_") :]
            if col == "on_hand":
                col = "on_hand_qty"
            rules.append({"id": name, "type": "lt", "column": col, "value": 0})
        else:
            rules.append({"id": name, "type": "named", "name": name})
    return rules


def _num(col: str):
    return F.col(col).cast("double")


def _spark_numeric_expr(expr: str):
    return F.expr(expr)


def _apply_rule(rule: dict):
    rtype = rule.get("type") or rule.get("kind")
    col = rule.get("column")
    if rtype == "blank":
        return _blank(col)
    if rtype == "lt":
        return _num(col) < F.lit(rule.get("value", 0))
    if rtype == "range":
        num = _num(col)
        bad = F.lit(False)
        if rule.get("null_is_invalid", True):
            bad = bad | num.isNull()
        min_v = rule.get("min")
        max_v = rule.get("max")
        if min_v is not None:
            bad = bad | (num < F.lit(min_v) if rule.get("min_inclusive", True) else num <= F.lit(min_v))
        if max_v is not None:
            bad = bad | (num > F.lit(max_v))
        return bad
    if rtype == "date_parse":
        parsed = F.to_date(F.col(col).cast("string"), "yyyy-MM-dd")
        return parsed.isNull()
    if rtype == "formula_delta":
        left = _num(rule["left"])
        right = _spark_numeric_expr(str(rule["right"]))
        return F.abs(left - right) > F.lit(float(rule.get("max_abs_delta", 0.01)))
    if rtype == "not_in":
        return ~F.col(col).isin(list(rule.get("values") or []))
    if rtype == "invalid_ip":
        return ~F.col(col).cast("string").rlike(r"^\d{1,3}(\.\d{1,3}){3}$")
    raise ValueError(f"Unknown quarantine rule type: {rtype}")


def _derived_col(expr: str):
    raw = expr.strip()
    if raw.lower().startswith("year("):
        inner = raw[5:-1]
        return F.year(F.to_date(F.col(inner)))
    if raw.lower().startswith("month("):
        inner = raw[6:-1]
        return F.month(F.to_date(F.col(inner)))
    if raw.lower().startswith("date_trunc"):
        col = raw.split()[-1]
        return F.date_trunc("hour", F.to_timestamp(F.col(col)))
    return F.expr(raw)


def bronze_to_silver_df(bronze: DataFrame, cfg: dict | None = None) -> tuple[DataFrame, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    b2s = cfg["bronze_to_silver"]
    df = bronze
    keys = list(b2s["dedup"]["keys"])
    order_by = b2s["dedup"]["order_by"]
    window = Window.partitionBy(*keys).orderBy(F.desc(order_by))
    retain_blank = bool(b2s["dedup"].get("retain_blank_keys"))
    if retain_blank and keys:
        blank = _blank(keys[0])
        keyed = (
            df.filter(~blank)
            .withColumn("_rn", F.row_number().over(window))
            .filter(F.col("_rn") == 1)
            .drop("_rn")
        )
        df = keyed.unionByName(df.filter(blank), allowMissingColumns=True)
    else:
        df = df.withColumn("_rn", F.row_number().over(window)).filter(F.col("_rn") == 1).drop("_rn")

    string_ops = b2s.get("string_ops") or {}
    if string_ops.get("trim") == "all":
        for col_name, dtype in df.dtypes:
            if dtype == "string":
                df = df.withColumn(col_name, F.trim(F.col(col_name)))
    for col_name in string_ops.get("uppercase") or []:
        if col_name in df.columns:
            df = df.withColumn(col_name, F.upper(F.col(col_name)))

    consent = b2s.get("consent_filter") or {}
    if consent.get("column"):
        allowed = F.lower(F.col(consent["column"]).cast("string")).isin("true", "1")
        df = df.filter(allowed)

    flag_cols = []
    for rule in _quarantine_rules(b2s):
        df = df.withColumn(rule["id"], _apply_rule(rule))
        flag_cols.append(rule["id"])
    bad = F.lit(False)
    for name in flag_cols:
        bad = bad | F.col(name)
    quarantine = df.filter(bad)
    if flag_cols:
        quarantine = quarantine.withColumn(
            "quarantine_reason",
            F.concat_ws(",", *[F.when(F.col(c), F.lit(c)) for c in flag_cols]),
        )
    silver = df.filter(~bad).drop(*flag_cols)

    casts = b2s.get("casts") or {}
    spark_cast = {
        "integer": "int",
        "int": "int",
        "bigint": "bigint",
        "decimal": "double",
        "double": "double",
        "float": "double",
        "date": "date",
        "timestamp": "timestamp",
        "boolean": "boolean",
        "bool": "boolean",
    }
    for col_name, dtype in casts.items():
        if col_name not in silver.columns:
            continue
        kind = str(dtype).lower()
        if kind in {"boolean", "bool"}:
            silver = silver.withColumn(
                col_name, F.lower(F.col(col_name).cast("string")).isin("true", "1")
            )
        elif kind in spark_cast:
            silver = silver.withColumn(col_name, F.col(col_name).cast(spark_cast[kind]))

    for rule in b2s.get("pii_masking") or []:
        col_name = rule.get("column")
        strategy = rule.get("strategy") or rule.get("method") or ""
        fn = _PII_UDF.get(strategy)
        if fn and col_name in silver.columns:
            silver = silver.withColumn(col_name, F.udf(fn, StringType())(F.col(col_name)))

    for col_name, expr in (b2s.get("derived") or {}).items():
        silver = silver.withColumn(col_name, _derived_col(str(expr)))

    return silver, quarantine


def silver_to_gold_dfs(silver: DataFrame, cfg: dict | None = None) -> dict[str, DataFrame]:
    cfg = cfg or _load_yaml("transformations.yaml")
    s2g = cfg["silver_to_gold"]
    style = (s2g.get("schema_style") or "flat").lower()
    suppress = list((s2g.get("gold_pii_policy") or {}).get("suppress") or [])
    gold: dict[str, DataFrame] = {}

    if style == "star":
        fact = s2g.get("fact") or {}
        fact_cols = []
        if fact.get("grain"):
            fact_cols.append(fact["grain"])
        fact_cols.extend(fact.get("foreign_keys") or [])
        fact_cols.extend(fact.get("measures") or [])
        fact_cols = [c for c in fact_cols if c in silver.columns]
        gold[fact.get("name", "fact")] = silver.select(*fact_cols)
        for dim in s2g.get("dimensions") or []:
            key = dim["key"]
            cols = [key] + [c for c in (dim.get("attributes") or []) if c in silver.columns]
            frame = silver.select(*cols).dropDuplicates([key])
            if dim.get("name") == "dim_date" and "trade_month" in frame.columns:
                frame = frame.withColumn(
                    "trade_quarter",
                    F.when(
                        F.col("trade_month").isNotNull(),
                        ((F.col("trade_month") - 1) / 3 + 1).cast("int"),
                    ),
                )
            gold[dim["name"]] = frame
        view = s2g.get("analytical_view") or {}
        if view:
            gold[view.get("name", "analytical_view")] = _rollup(silver, view)
    elif style == "rollup":
        view = s2g.get("analytical_view") or {}
        gold[view.get("name", "gold_rollup")] = _rollup(silver, view)
        erasure = s2g.get("erasure_index") or {}
        if erasure:
            key = erasure.get("key", "user_id")
            count_col = erasure.get("count_column", "event_id")
            hook_table = erasure.get("hook_table", "silver_table")
            idx = silver.groupBy(key).agg(F.count(count_col).alias("event_count"))
            idx = idx.withColumn(
                "erasure_hook",
                F.lit(f"DELETE FROM {hook_table} WHERE {key} = :token"),
            )
            gold[erasure.get("table", "gold_erasure_index")] = idx
    else:
        table = s2g.get("table") or f"gold_{cfg.get('workload', 'table')}"
        gold[table] = silver

    for name, frame in list(gold.items()):
        drop_cols = [c for c in suppress if c in frame.columns]
        if drop_cols:
            gold[name] = frame.drop(*drop_cols)
    return gold


silver_to_gold_tables = silver_to_gold_dfs


def _rollup(silver: DataFrame, view: dict) -> DataFrame:
    grouped = silver.groupBy(*view["group_by"])
    aggs = []
    for alias, spec in (view.get("aggregations") or {}).items():
        raw = str(spec).strip()
        if raw.lower().startswith("sum("):
            aggs.append(F.sum(raw[4:-1]).alias(alias))
        elif raw.lower().startswith("count("):
            aggs.append(F.count(raw[6:-1]).alias(alias))
        elif raw.lower().startswith("nunique "):
            aggs.append(F.countDistinct(raw.split()[1]).alias(alias))
        elif raw.lower().startswith("count where "):
            _, _, rest = raw.partition("where")
            col, _, value = rest.strip().partition("=")
            aggs.append(F.sum(F.when(F.col(col.strip()) == value.strip(), 1).otherwise(0)).alias(alias))
        else:
            aggs.append(F.expr(raw).alias(alias))
    return grouped.agg(*aggs) if aggs else grouped.count()


def configure_iceberg_catalog(spark, warehouse: str) -> None:
    """Ensure glue_catalog is registered (Glue ETL jobs should set this via --conf)."""
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


def _drop_non_iceberg_glue_table(
    database: str, table: str, *, expected_path_fragment: str | None = None
) -> None:
    import boto3

    glue = boto3.client("glue")
    try:
        existing = glue.get_table(DatabaseName=database, Name=table)["Table"]
        params = existing.get("Parameters") or {}
        meta = params.get("metadata_location", "")
        if params.get("table_type", "").upper() == "ICEBERG":
            if expected_path_fragment and expected_path_fragment not in meta:
                glue.delete_table(DatabaseName=database, Name=table)
                print(f"[iceberg] dropped misplaced iceberg table {database}.{table} ({meta})")
            return
        glue.delete_table(DatabaseName=database, Name=table)
        print(f"[iceberg] dropped non-iceberg catalog entry {database}.{table}")
    except glue.exceptions.EntityNotFoundException:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"[iceberg] could not drop {database}.{table}: {exc}")


def write_iceberg_table(
    df: DataFrame,
    database: str,
    table: str,
    warehouse: str | None = None,
    *,
    expected_path_fragment: str | None = None,
) -> None:
    spark = df.sparkSession
    configure_iceberg_catalog(spark, warehouse or "s3://")
    full_name = f"glue_catalog.{database}.{table}"
    _drop_non_iceberg_glue_table(database, table, expected_path_fragment=expected_path_fragment)
    df.write.format("iceberg").mode("overwrite").saveAsTable(full_name)
    print(f"[iceberg] wrote {full_name} rows={df.count()}")
