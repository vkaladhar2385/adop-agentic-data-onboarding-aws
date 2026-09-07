"""Reusable PII helpers shared across workloads.

In the real ADOP framework these mirror `shared/utils/pii_detection_and_tagging.py`.
Here we keep a small, dependency-free subset: deterministic masking used by the
Bronze->Silver transform, plus the LF-Tag classification map that the DevOps /
Lake Formation step consumes.
"""
from __future__ import annotations

import hashlib
import re

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SSN_RE = re.compile(r"^\d{3}-\d{2}-\d{4}$")

# column -> (PII_Type, Data_Sensitivity) used to emit Lake Formation LF-Tags
PII_CLASSIFICATION = {
    "client_ssn": ("SSN", "CRITICAL"),
    "client_email": ("EMAIL", "HIGH"),
    "client_name": ("NAME", "HIGH"),
    "user_email": ("EMAIL", "HIGH"),
    "ip_address": ("IP", "MEDIUM"),
    "user_id": ("USER_ID", "HIGH"),
}


def mask_ip(value: str | None) -> str | None:
    """Drop the last octet: 203.0.113.45 -> 203.0.113.0"""
    if value is None or value == "":
        return value
    parts = str(value).split(".")
    if len(parts) != 4:
        return "0.0.0.0"
    return ".".join(parts[:3] + ["0"])


def mask_ssn(value: str | None) -> str | None:
    """Keep only the last 4 digits: 123-45-6789 -> ***-**-6789."""
    if value is None or value == "":
        return value
    digits = re.sub(r"\D", "", str(value))
    if len(digits) < 4:
        return "***-**-****"
    return f"***-**-{digits[-4:]}"


def mask_email(value: str | None) -> str | None:
    """Keep first char + domain: john.doe@example.com -> j***@example.com."""
    if value is None or value == "":
        return value
    if "@" not in str(value):
        return "***@invalid"
    local, _, domain = str(value).partition("@")
    head = local[0] if local else "*"
    return f"{head}***@{domain}"


def hash_token(value: str | None, salt: str = "adop-demo") -> str | None:
    """Deterministic one-way token for join-safe pseudonymisation (client_id)."""
    if value is None or value == "":
        return value
    return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:16]


def is_valid_email(value: str | None) -> bool:
    return bool(value) and bool(EMAIL_RE.match(str(value)))


def is_valid_ssn(value: str | None) -> bool:
    return bool(value) and bool(SSN_RE.match(str(value))) and str(value) != "000-00-0000"
