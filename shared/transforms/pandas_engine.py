"""Config-driven pandas transforms. Workload local_runners are thin shims.

Reads `transformations.yaml` (dedup, string ops, quarantine_rules, casts,
PII masking, derived columns, gold schema_style). Glue Python Shell can import
this file as a flat `pandas_engine.py` via --extra-py-files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

try:
    from shared.utils.pii import hash_token, mask_email, mask_ip, mask_ssn
except ImportError:  # pragma: no cover - Glue flat extra-py-files
    from pii import hash_token, mask_email, mask_ip, mask_ssn  # type: ignore

_IDENT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\b")
_SAFE_EXPR = re.compile(r"^[A-Za-z0-9_\s\.\+\-\*/\(\)]+$")
_YEAR = re.compile(r"^year\((\w+)\)$", re.I)
_MONTH = re.compile(r"^month\((\w+)\)$", re.I)
_DATE_TRUNC_HOUR = re.compile(r"^date_trunc\s+hour\s+(\w+)$", re.I)
_COUNT_WHERE = re.compile(r"^count\s+where\s+(\w+)\s*=\s*(\w+)$", re.I)
_NUNIQUE = re.compile(r"^nunique\s+(\w+)$", re.I)
_COUNT_COL = re.compile(r"^count\((\w+)\)$", re.I)
_SUM_COL = re.compile(r"^sum\((\w+)\)$", re.I)

_PII_FNS = {
    "mask_ssn": mask_ssn,
    "mask_email": mask_email,
    "mask_ip": mask_ip,
    "hash_token": hash_token,
    "hash": hash_token,
}


def load_config(name: str, config_dir: Path) -> dict:
    for candidate in (config_dir / name, Path(name), Path("/tmp") / name):
        if candidate.is_file():
            with candidate.open(encoding="utf-8") as fh:
                return yaml.safe_load(fh)
    raise FileNotFoundError(f"{name} not found under {config_dir}")


def ingest_bronze(path: str | Path, source_format: str = "csv") -> pd.DataFrame:
    src = Path(path)
    fmt = (source_format or "csv").lower()
    if fmt in {"jsonl", "json"}:
        rows = []
        with src.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return pd.DataFrame(rows)
    return pd.read_csv(src, dtype=str, keep_default_na=False, na_values=[""])


def _blank_mask(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    return series.isna() | text.eq("") | text.str.lower().eq("nan")


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _eval_numeric_expr(df: pd.DataFrame, expr: str) -> pd.Series:
    expr = expr.strip()
    if not _SAFE_EXPR.match(expr):
        raise ValueError(f"Unsafe numeric expression: {expr}")
    env: dict[str, Any] = {}
    for name in _IDENT.findall(expr):
        if name in df.columns:
            env[name] = _numeric(df[name])
    return eval(expr, {"__builtins__": {}}, env)  # noqa: S307 — identifier allowlist


def _eval_derived(df: pd.DataFrame, expr: str) -> pd.Series:
    raw = expr.strip()
    m = _YEAR.match(raw)
    if m:
        return pd.to_datetime(df[m.group(1)], errors="coerce").dt.year
    m = _MONTH.match(raw)
    if m:
        return pd.to_datetime(df[m.group(1)], errors="coerce").dt.month
    m = _DATE_TRUNC_HOUR.match(raw)
    if m:
        return pd.to_datetime(df[m.group(1)], utc=True, errors="coerce").dt.floor("h")
    if raw in df.columns:
        return df[raw]
    series = _eval_numeric_expr(df, raw)
    if "/" in raw:
        # Match product_inventory: null when divisor is 0.
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) == 2 and parts[1] in df.columns:
            denom = _numeric(df[parts[1]])
            series = series.where(denom > 0)
    return series


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


def _apply_quarantine_rule(df: pd.DataFrame, rule: dict) -> pd.Series:
    rtype = rule.get("type") or rule.get("kind")
    col = rule.get("column")
    if rtype == "blank":
        return _blank_mask(df[col])
    if rtype == "lt":
        return _numeric(df[col]) < rule.get("value", 0)
    if rtype == "range":
        num = _numeric(df[col])
        bad = pd.Series(False, index=df.index)
        if rule.get("null_is_invalid", True):
            bad = bad | num.isna()
        min_v = rule.get("min")
        max_v = rule.get("max")
        if min_v is not None:
            if rule.get("min_inclusive", True):
                bad = bad | (num < min_v)
            else:
                bad = bad | (num <= min_v)
        if max_v is not None:
            bad = bad | (num > max_v)
        return bad
    if rtype == "date_parse":
        parsed = pd.to_datetime(df[col], errors="coerce", format="%Y-%m-%d")
        return parsed.isna()
    if rtype == "formula_delta":
        left = _numeric(df[rule["left"]])
        right = _eval_numeric_expr(df, str(rule["right"]))
        delta = (left - right).abs()
        return delta > float(rule.get("max_abs_delta", 0.01))
    if rtype == "not_in":
        values = set(rule.get("values") or [])
        return ~df[col].astype(str).isin(values)
    if rtype == "invalid_ip":
        return ~df[col].astype(str).str.match(r"^\d{1,3}(\.\d{1,3}){3}$", na=False)
    raise ValueError(f"Unknown quarantine rule type: {rtype}")


def bronze_to_silver(
    bronze: pd.DataFrame, cfg: dict
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Return (silver, quarantine, suppressed_no_consent)."""
    b2s = cfg["bronze_to_silver"]
    df = bronze.copy()
    keys = list(b2s["dedup"]["keys"])
    order_by = b2s["dedup"]["order_by"]
    retain_blank = bool(b2s["dedup"].get("retain_blank_keys"))

    if retain_blank and keys:
        blank = _blank_mask(df[keys[0]])
        keyed = df[~blank].sort_values(order_by).drop_duplicates(subset=keys, keep="last")
        df = pd.concat([keyed, df[blank]], ignore_index=True)
    else:
        df = df.sort_values(order_by).drop_duplicates(subset=keys, keep="last").reset_index(drop=True)

    string_ops = b2s.get("string_ops") or {}
    if string_ops.get("trim") == "all":
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
    for col in string_ops.get("uppercase") or []:
        if col in df.columns:
            df[col] = df[col].apply(lambda v: v.upper() if isinstance(v, str) else v)

    suppressed = df.iloc[0:0].copy()
    consent = b2s.get("consent_filter") or {}
    if consent.get("column"):
        col = consent["column"]
        allowed = df[col].astype(str).str.lower().isin(["true", "1"])
        suppressed = df[~allowed].copy()
        df = df[allowed].copy()

    flags = pd.DataFrame(index=df.index)
    for rule in _quarantine_rules(b2s):
        flags[rule["id"]] = _apply_quarantine_rule(df, rule)
    bad = flags.any(axis=1) if not flags.empty else pd.Series(False, index=df.index)
    quarantine = df[bad].copy()
    if not flags.empty and bad.any():
        quarantine = quarantine.join(
            flags[bad]
            .apply(lambda r: ",".join([k for k, v in r.items() if v]), axis=1)
            .rename("quarantine_reason")
        )
    silver = df[~bad].copy().reset_index(drop=True)

    casts = b2s.get("casts") or {}
    for col, dtype in casts.items():
        if col not in silver.columns:
            continue
        kind = str(dtype).lower()
        if kind in {"integer", "int", "bigint"}:
            silver[col] = pd.to_numeric(silver[col], errors="coerce").astype("Int64")
        elif kind in {"decimal", "double", "float", "number"}:
            silver[col] = _numeric(silver[col])
        elif kind in {"date", "timestamp", "datetime"}:
            utc = kind == "timestamp"
            silver[col] = pd.to_datetime(silver[col], utc=utc, errors="coerce")
            if kind == "date":
                silver[col] = silver[col].dt.tz_localize(None) if getattr(silver[col].dt, "tz", None) else silver[col]
                silver[col] = pd.to_datetime(silver[col], errors="coerce")
        elif kind in {"boolean", "bool"}:
            silver[col] = silver[col].astype(str).str.lower().isin(["true", "1"])

    for rule in b2s.get("pii_masking") or []:
        col = rule.get("column")
        strategy = rule.get("strategy") or rule.get("method") or ""
        fn = _PII_FNS.get(strategy)
        if fn and col in silver.columns:
            silver[col] = silver[col].apply(fn)

    for col, expr in (b2s.get("derived") or {}).items():
        silver[col] = _eval_derived(silver, str(expr))

    if consent.get("column") and consent["column"] in silver.columns:
        silver[consent["column"]] = True

    return silver, quarantine, suppressed


def _agg_series(group: pd.DataFrame, spec: str, default_col: str | None = None) -> Any:
    raw = spec.strip()
    m = _COUNT_WHERE.match(raw)
    if m:
        col, value = m.group(1), m.group(2)
        return int((group[col].astype(str) == value).sum())
    m = _NUNIQUE.match(raw)
    if m:
        return group[m.group(1)].nunique()
    m = _COUNT_COL.match(raw)
    if m:
        return group[m.group(1)].count()
    m = _SUM_COL.match(raw)
    if m:
        return _numeric(group[m.group(1)]).sum()
    if raw in group.columns:
        return group[raw].iloc[0]
    raise ValueError(f"Unsupported aggregation: {spec}")


def silver_to_gold(silver: pd.DataFrame, cfg: dict) -> dict[str, pd.DataFrame]:
    s2g = cfg["silver_to_gold"]
    style = (s2g.get("schema_style") or "flat").lower()
    suppress = list((s2g.get("gold_pii_policy") or {}).get("suppress") or [])
    gold: dict[str, pd.DataFrame] = {}

    if style == "star":
        fact = s2g.get("fact") or {}
        fact_cols = []
        grain = fact.get("grain")
        if grain:
            fact_cols.append(grain)
        fact_cols.extend(fact.get("foreign_keys") or [])
        fact_cols.extend(fact.get("measures") or [])
        fact_cols = [c for c in fact_cols if c in silver.columns]
        gold[fact.get("name", "fact")] = silver[fact_cols].copy()
        for dim in s2g.get("dimensions") or []:
            key = dim["key"]
            cols = [key] + [c for c in (dim.get("attributes") or []) if c in silver.columns]
            frame = silver[cols].drop_duplicates([key])
            if dim.get("name") == "dim_date" and "trade_month" in frame.columns:
                frame = frame.copy()
                month = pd.to_numeric(frame["trade_month"], errors="coerce")
                frame["trade_quarter"] = ((month - 1) // 3 + 1).astype("Int64")
            gold[dim["name"]] = frame
        view = s2g.get("analytical_view") or {}
        if view:
            grouped = silver.groupby(view["group_by"], as_index=False)
            aggs = {}
            for alias, spec in (view.get("aggregations") or {}).items():
                spec_s = str(spec)
                m = _SUM_COL.match(spec_s)
                if m:
                    aggs[alias] = (m.group(1), "sum")
                elif _COUNT_COL.match(spec_s):
                    aggs[alias] = (_COUNT_COL.match(spec_s).group(1), "count")
                else:
                    aggs = None
                    break
            if aggs:
                out = grouped.agg(**{alias: col_fn for alias, col_fn in aggs.items()})
            else:
                rows = []
                for keys, part in silver.groupby(view["group_by"]):
                    rec = dict(zip(view["group_by"], keys if isinstance(keys, tuple) else (keys,)))
                    for alias, spec in (view.get("aggregations") or {}).items():
                        rec[alias] = _agg_series(part, str(spec))
                    rows.append(rec)
                out = pd.DataFrame(rows)
            gold[view.get("name", "analytical_view")] = out
    elif style == "rollup":
        view = s2g.get("analytical_view") or {}
        rows = []
        for keys, part in silver.groupby(view["group_by"]):
            rec = dict(zip(view["group_by"], keys if isinstance(keys, tuple) else (keys,)))
            for alias, spec in (view.get("aggregations") or {}).items():
                rec[alias] = _agg_series(part, str(spec))
            rows.append(rec)
        gold[view.get("name", "gold_rollup")] = pd.DataFrame(rows)
        erasure = s2g.get("erasure_index") or {}
        if erasure:
            key = erasure.get("key", "user_id")
            count_col = erasure.get("count_column", "event_id")
            idx = silver.groupby(key, as_index=False).agg(event_count=(count_col, "count"))
            hook_table = erasure.get("hook_table", "silver_table")
            idx["erasure_hook"] = f"DELETE FROM {hook_table} WHERE {key} = :token"
            gold[erasure.get("table", "gold_erasure_index")] = idx
    else:
        table = s2g.get("table") or f"gold_{cfg.get('workload', 'table')}"
        gold[table] = silver.copy()

    for name, frame in list(gold.items()):
        drop = [c for c in suppress if c in frame.columns]
        if drop:
            gold[name] = frame.drop(columns=drop)
        gold[name] = gold[name].reset_index(drop=True)
    return gold
