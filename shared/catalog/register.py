"""Shared Glue catalog + Lake Formation registration.

Workloads keep a thin `scripts/load/register_catalog.py` shim so existing
Lambda handler paths and pytest imports stay stable. Schema and PII tags come
from `config/semantic.yaml` + `config/source.yaml` (not hardcoded columns).
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any

_GLUE_TYPES = {
    "string": "string",
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


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _workload_dir(workload: str) -> Path:
    return _repo_root() / "workloads" / workload


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    import yaml

    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def _configs(workload: str) -> dict[str, dict[str, Any]]:
    cfg = _workload_dir(workload) / "config"
    # Glue/Lambda also deploy configs next to this file.
    here = Path(__file__).resolve().parent
    source = _load_yaml(cfg / "source.yaml") or _load_yaml(here / "source.yaml")
    semantic = _load_yaml(cfg / "semantic.yaml") or _load_yaml(here / "semantic.yaml")
    transforms = _load_yaml(cfg / "transformations.yaml") or _load_yaml(here / "transformations.yaml")
    return {"source": source, "semantic": semantic, "transforms": transforms}


def _columns_from_semantic(semantic: dict[str, Any]) -> list[tuple[str, str]]:
    columns = semantic.get("columns") or {}
    out: list[tuple[str, str]] = []
    if isinstance(columns, dict):
        for name, meta in columns.items():
            meta = meta or {}
            glue_type = _GLUE_TYPES.get(str(meta.get("type", "string")).lower(), "string")
            out.append((name, glue_type))
    return out


def _silver_table(workload: str, source: dict[str, Any]) -> str:
    return str((source.get("zones") or {}).get("silver", {}).get("table") or f"silver_{workload}")


def _gold_table(workload: str, source: dict[str, Any], transforms: dict[str, Any]) -> str:
    s2g = transforms.get("silver_to_gold") or {}
    if (s2g.get("schema_style") or "").lower() == "star":
        return str((s2g.get("fact") or {}).get("name") or "fact_transactions")
    if s2g.get("table"):
        return str(s2g["table"])
    return str((source.get("zones") or {}).get("gold", {}).get("table") or f"gold_{workload}")


def _database(workload: str, source: dict[str, Any], override: str | None) -> str:
    if override:
        return override
    zones = source.get("zones") or {}
    for zone in ("silver", "gold", "bronze"):
        db = (zones.get(zone) or {}).get("database")
        if db:
            return str(db)
    return f"{workload}_db"


def plan_lf_tags(workload: str, database: str | None = None) -> list[dict]:
    cfg = _configs(workload)
    source, semantic = cfg["source"], cfg["semantic"]
    db = _database(workload, source, database)
    table = _silver_table(workload, source)
    tags: list[dict] = []
    columns = semantic.get("columns") or {}
    if not isinstance(columns, dict):
        return tags
    for name, meta in columns.items():
        meta = meta or {}
        if not meta.get("pii"):
            continue
        pii_type = str(meta.get("pii_type") or "PII").upper()
        sensitivity = str(meta.get("sensitivity") or "HIGH").upper()
        tags.append(
            {
                "database": db,
                "table": table,
                "column": name,
                "lf_tags": {"PII_Type": pii_type, "Data_Sensitivity": sensitivity},
            }
        )
    return tags


def run_local(workload: str) -> None:
    cfg = _configs(workload)
    tags = plan_lf_tags(workload)
    print("[load] Glue catalog registration plan (Iceberg):")
    for zone in ("silver", "gold"):
        print(f"  - register {zone} tables from sql/{zone}/*.sql")
    if tags:
        print("[load] Lake Formation LF-Tag plan (TBAC on PII columns):")
        for tag in tags:
            print(f"  - {tag['table']}.{tag['column']} -> {tag['lf_tags']}")
    else:
        print("[load] Lake Formation LF-Tag plan: none (no PII columns).")
    suppress = ((cfg["transforms"].get("silver_to_gold") or {}).get("gold_pii_policy") or {}).get(
        "suppress"
    ) or []
    if suppress:
        print(f"[load] NOTE: Gold suppresses {suppress} (no tags needed).")


def _glue_table_input(name: str, s3_location: str, columns: list[tuple[str, str]]) -> dict:
    return {
        "Name": name,
        "StorageDescriptor": {
            "Columns": [{"Name": c, "Type": t} for c, t in columns],
            "Location": s3_location,
            "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
            "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
            "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"},
        },
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {"classification": "parquet", "table_type": "ICEBERG"},
    }


def register_tables(workload: str, database: str, bucket: str) -> list[dict]:  # pragma: no cover
    import boto3

    cfg = _configs(workload)
    columns = _columns_from_semantic(cfg["semantic"])
    silver = _silver_table(workload, cfg["source"])
    gold = _gold_table(workload, cfg["source"], cfg["transforms"])
    glue = boto3.client("glue")
    tables = [
        (silver, f"s3://{bucket}/silver/{workload}/", columns),
        (gold, f"s3://{bucket}/gold/{workload}/{gold}/", columns),
    ]
    results = []
    for name, location, cols in tables:
        table_input = _glue_table_input(name, location, cols)
        try:
            glue.create_table(DatabaseName=database, TableInput=table_input)
            results.append({"table": name, "status": "created"})
        except glue.exceptions.AlreadyExistsException:
            glue.update_table(DatabaseName=database, TableInput=table_input)
            results.append({"table": name, "status": "updated"})
        except Exception as exc:  # noqa: BLE001
            results.append({"table": name, "status": "failed", "error": str(exc)})
    return results


def apply_lf_tags(tags: list[dict]) -> list[dict]:  # pragma: no cover
    import boto3

    lf = boto3.client("lakeformation")
    results = []
    for tag in tags:
        try:
            lf_tags = [{"TagKey": k, "TagValues": [v]} for k, v in tag["lf_tags"].items()]
            lf.add_lf_tags_to_resource(
                Resource={
                    "TableWithColumns": {
                        "DatabaseName": tag["database"],
                        "Name": tag["table"],
                        "ColumnNames": [tag["column"]],
                    }
                },
                LFTags=lf_tags,
            )
            results.append({**tag, "status": "applied"})
        except Exception as exc:  # noqa: BLE001
            results.append({**tag, "status": "failed", "error": str(exc)})
    return results


def lambda_handler_for(workload: str, event: dict | None, context) -> dict:  # pragma: no cover
    event = event or {}
    cfg = _configs(workload)
    database = event.get("database") or os.environ.get("GLUE_DATABASE")
    database = _database(workload, cfg["source"], database)
    bucket = event.get("data_lake_bucket") or os.environ.get("DATA_LAKE_BUCKET")
    tags = plan_lf_tags(workload, database=database)
    try:
        import boto3  # noqa: F401

        table_results = []
        if event.get("register_tables") and bucket:
            table_results = register_tables(workload, database, bucket)
        results = apply_lf_tags(tags) if tags else []
    except ImportError:
        table_results = []
        results = [{**t, "status": "planned (boto3 unavailable, dry-run)"} for t in tags]
    failed = [r for r in results if r.get("status") == "failed"] + [
        r for r in table_results if r.get("status") == "failed"
    ]
    return {
        "workload": workload,
        "tables": table_results,
        "tagged": len(results),
        "failed": len(failed),
        "results": results or tags,
    }


def cli_main(workload: str, argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args(argv)
    if args.local:
        run_local(workload)
        return 0
    raise SystemExit("Catalog registration runs against AWS; use --local for the demo.")
