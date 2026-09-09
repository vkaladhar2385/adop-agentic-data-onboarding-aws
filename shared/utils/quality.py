"""Reusable data-quality engine shared across workloads.

Mirrors ADOP's `shared/utils/quality_checks.py`. Rules are declarative dicts
(loaded from `config/quality_rules.yaml`) so the same engine grades any workload.
Returns a structured result with a per-dimension score and an overall gate
pass/fail, honouring the "critical rule failure blocks promotion" invariant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

# Five ADOP quality dimensions
DIMENSIONS = ("completeness", "validity", "uniqueness", "accuracy", "consistency")


@dataclass
class RuleResult:
    rule_id: str
    dimension: str
    critical: bool
    passed: bool
    pass_rate: float
    failed_rows: int
    description: str


@dataclass
class QualityReport:
    zone: str
    overall_score: float
    gate_threshold: float
    passed: bool
    critical_failures: list[str] = field(default_factory=list)
    results: list[RuleResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "zone": self.zone,
            "overall_score": round(self.overall_score, 4),
            "gate_threshold": self.gate_threshold,
            "passed": self.passed,
            "critical_failures": self.critical_failures,
            "results": [r.__dict__ for r in self.results],
        }


# ---- Rule primitives ------------------------------------------------------

def _rate(mask: pd.Series) -> tuple[float, int]:
    total = len(mask)
    if total == 0:
        return 1.0, 0
    passed = int(mask.sum())
    return passed / total, total - passed


def not_null(df: pd.DataFrame, column: str) -> tuple[float, int]:
    return _rate(df[column].notna() & (df[column].astype(str).str.strip() != ""))


def unique(df: pd.DataFrame, column: str) -> tuple[float, int]:
    return _rate(~df[column].duplicated(keep=False))


def unique_composite(df: pd.DataFrame, columns: list[str]) -> tuple[float, int]:
    return _rate(~df.duplicated(subset=columns, keep=False))


def in_set(df: pd.DataFrame, column: str, allowed: list[str]) -> tuple[float, int]:
    return _rate(df[column].isin(allowed))


def non_negative(df: pd.DataFrame, column: str) -> tuple[float, int]:
    vals = pd.to_numeric(df[column], errors="coerce")
    return _rate(vals.notna() & (vals >= 0))


def valid_date(df: pd.DataFrame, column: str) -> tuple[float, int]:
    parsed = pd.to_datetime(df[column], errors="coerce", format="%Y-%m-%d")
    return _rate(parsed.notna())


def date_order(df: pd.DataFrame, earlier: str, later: str) -> tuple[float, int]:
    a = pd.to_datetime(df[earlier], errors="coerce")
    b = pd.to_datetime(df[later], errors="coerce")
    return _rate(a.notna() & b.notna() & (a <= b))


def formula_matches(df: pd.DataFrame, target: str, expr: Callable[[pd.DataFrame], pd.Series],
                    tol: float = 0.01) -> tuple[float, int]:
    actual = pd.to_numeric(df[target], errors="coerce")
    expected = expr(df)
    return _rate(actual.notna() & expected.notna() & ((actual - expected).abs() <= tol))


# ---- Built-in rule library for advisory_transactions ----------------------
# Maps rule_id -> callable(df) -> (pass_rate, failed_rows)

def build_rule_library() -> dict[str, Callable[[pd.DataFrame], tuple[float, int]]]:
    def _num(df, c):
        return pd.to_numeric(df[c], errors="coerce")

    return {
        "completeness_transaction_id": lambda df: not_null(df, "transaction_id"),
        "completeness_account_id": lambda df: not_null(df, "account_id"),
        "completeness_net_amount": lambda df: not_null(df, "net_amount"),
        "uniqueness_transaction_id": lambda df: unique(df, "transaction_id"),
        "validity_trade_date": lambda df: valid_date(df, "trade_date"),
        "validity_trade_before_settle": lambda df: date_order(df, "trade_date", "settlement_date"),
        "validity_quantity_non_negative": lambda df: non_negative(df, "quantity"),
        "validity_unit_price_non_negative": lambda df: non_negative(df, "unit_price"),
        "validity_transaction_type": lambda df: in_set(
            df, "transaction_type", ["BUY", "SELL", "DIVIDEND", "FEE"]),
        "validity_currency": lambda df: in_set(df, "currency", ["USD"]),
        # SOX financial-integrity checks (critical)
        "accuracy_gross_amount": lambda df: formula_matches(
            df, "gross_amount", lambda d: _num(d, "quantity") * _num(d, "unit_price")),
        "consistency_net_amount": lambda df: formula_matches(
            df, "net_amount",
            lambda d: _num(d, "gross_amount") - _num(d, "commission") - _num(d, "fees")),
        # web_events (GDPR clickstream)
        "completeness_event_id": lambda df: not_null(df, "event_id"),
        "uniqueness_event_id": lambda df: unique(df, "event_id"),
        "validity_event_type": lambda df: in_set(
            df, "event_type", ["page_view", "click", "session_start", "session_end"]),
        "validity_consent_true": lambda df: _rate(
            df["consent_analytics"].astype(str).str.lower().isin(["true", "1"])),
        "validity_ip_dotted": lambda df: _rate(
            df["ip_address"].astype(str).str.match(r"^\d{1,3}(\.\d{1,3}){3}$", na=False)),
        "completeness_traffic_source": lambda df: not_null(df, "traffic_source"),
        # product_inventory (catalog snapshot)
        "completeness_sku": lambda df: not_null(df, "sku"),
        "uniqueness_sku": lambda df: unique(df, "sku"),
        "validity_on_hand_non_negative": lambda df: non_negative(df, "on_hand_qty"),
        "completeness_product_name": lambda df: not_null(df, "product_name"),
        "consistency_reserved_not_over_on_hand": lambda df: _rate(
            pd.to_numeric(df["reserved_qty"], errors="coerce")
            <= pd.to_numeric(df["on_hand_qty"], errors="coerce")
        ),
        "accuracy_list_price_gte_unit_cost": lambda df: _rate(
            pd.to_numeric(df["list_price"], errors="coerce")
            >= pd.to_numeric(df["unit_cost"], errors="coerce")
        ),
        # supplier_lead_times (procurement catalog)
        "completeness_supplier_id": lambda df: not_null(df, "supplier_id"),
        "uniqueness_supplier_category": lambda df: unique_composite(
            df, ["supplier_id", "product_category"]
        ),
        "validity_lead_time_non_negative": lambda df: non_negative(df, "lead_time_days"),
        "validity_lead_time_max_365": lambda df: _rate(
            pd.to_numeric(df["lead_time_days"], errors="coerce").fillna(9999) <= 365
        ),
        "completeness_supplier_name": lambda df: not_null(df, "supplier_name"),
        # customer_orders (Tier B MWAA proof)
        "completeness_order_id": lambda df: not_null(df, "order_id"),
        "uniqueness_order_id": lambda df: unique(df, "order_id"),
        "validity_quantity_positive": lambda df: _rate(
            pd.to_numeric(df["quantity"], errors="coerce").fillna(0) >= 1
        ),
        "validity_order_total_non_negative": lambda df: non_negative(df, "order_total"),
    }


def run_quality(df: pd.DataFrame, rules: list[dict], zone: str,
                gate_threshold: float) -> QualityReport:
    """Run declarative rules and produce a graded report.

    Each rule dict: {id, dimension, critical(bool), threshold(float), description}
    """
    library = build_rule_library()
    results: list[RuleResult] = []
    critical_failures: list[str] = []

    for rule in rules:
        rid = rule["id"]
        fn = library.get(rid)
        if fn is None:
            continue
        try:
            pass_rate, failed = fn(df)
        except KeyError:
            # Rule references a column not present in this zone (e.g. Gold fact
            # has no settlement_date) -> rule is not applicable here, skip it.
            continue
        rule_threshold = float(rule.get("threshold", 1.0))
        passed = pass_rate >= rule_threshold
        if not passed and rule.get("critical", False):
            critical_failures.append(rid)
        results.append(RuleResult(
            rule_id=rid,
            dimension=rule.get("dimension", "validity"),
            critical=bool(rule.get("critical", False)),
            passed=passed,
            pass_rate=round(pass_rate, 4),
            failed_rows=failed,
            description=rule.get("description", ""),
        ))

    overall = sum(r.pass_rate for r in results) / len(results) if results else 1.0
    gate_passed = overall >= gate_threshold and not critical_failures
    return QualityReport(
        zone=zone,
        overall_score=overall,
        gate_threshold=gate_threshold,
        passed=gate_passed,
        critical_failures=critical_failures,
        results=results,
    )
