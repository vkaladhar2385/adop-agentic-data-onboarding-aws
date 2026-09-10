"""Load and apply ADOP sandbox tags for create/destroy lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TAGS_YAML = REPO_ROOT / "config" / "sandbox_tags.yaml"


def load_sandbox_tags(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or TAGS_YAML
    with cfg_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


def tag_map(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    m = dict((cfg or load_sandbox_tags()).get("tags") or {})
    return {str(k): str(v) for k, v in m.items()}


def iam_tag_list(cfg: dict[str, Any] | None = None) -> list[dict[str, str]]:
    return [{"Key": k, "Value": v} for k, v in tag_map(cfg).items()]


def glue_parameters(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    params = dict((cfg or load_sandbox_tags()).get("glue_parameters") or {})
    return {str(k): str(v) for k, v in params.items()}


def resource_prefix(cfg: dict[str, Any] | None = None) -> str:
    return str((cfg or load_sandbox_tags()).get("resource_prefix") or "adop")


def tag_filter(cfg: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    c = cfg or load_sandbox_tags()
    filt = c.get("tag_filter") or {}
    key = str(filt.get("key") or "ManagedBy")
    values = [str(v) for v in (filt.get("values") or ["adop-sandbox"])]
    return key, values


def tag_lambda(lam: Any, function_name: str, *, cfg: dict[str, Any] | None = None) -> None:
    tags = tag_map(cfg)
    if not tags:
        return
    try:
        fn = lam.get_function(FunctionName=function_name)
    except lam.exceptions.ResourceNotFoundException:
        return
    resource_arn = fn["Configuration"]["FunctionArn"]
    lam.tag_resource(Resource=resource_arn, Tags=tags)


def tag_iam_role(iam: Any, role_name: str, *, cfg: dict[str, Any] | None = None) -> None:
    tags = iam_tag_list(cfg)
    if not tags:
        return
    try:
        iam.get_role(RoleName=role_name)
    except iam.exceptions.NoSuchEntityException:
        return
    iam.tag_role(RoleName=role_name, Tags=tags)


def tag_kms_key(kms: Any, key_id: str, *, cfg: dict[str, Any] | None = None) -> None:
    tags = tag_map(cfg)
    if not tags:
        return
    kms.tag_resource(KeyId=key_id, Tags=[{"TagKey": k, "TagValue": v} for k, v in tags.items()])


def list_tagged_resource_arns(
    session: Any,
    *,
    resource_types: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[str]:
    """Return ARNs tagged with sandbox tag_filter (Resource Groups Tagging API)."""
    key, values = tag_filter(cfg)
    client = session.client("resourcegroupstaggingapi")
    arns: list[str] = []
    for value in values:
        kwargs: dict[str, Any] = {
            "TagFilters": [{"Key": key, "Values": [value]}],
        }
        if resource_types:
            kwargs["ResourceTypeFilters"] = resource_types
        for page in client.get_paginator("get_resources").paginate(**kwargs):
            for mapping in page.get("ResourceTagMappingList", []):
                arn = mapping.get("ResourceARN")
                if arn:
                    arns.append(arn)
    return sorted(set(arns))


def list_tagged_lambda_names(session: Any, *, cfg: dict[str, Any] | None = None) -> list[str]:
    names: list[str] = []
    for arn in list_tagged_resource_arns(session, resource_types=["lambda:function"], cfg=cfg):
        # arn:aws:lambda:region:account:function:name
        parts = arn.split(":function:")
        if len(parts) == 2:
            names.append(parts[1])
    return names


def role_name_matches_prefix(role_name: str, *, cfg: dict[str, Any] | None = None) -> bool:
    prefix = resource_prefix(cfg)
    if role_name.startswith(f"{prefix}-"):
        return True
    return bool(__import__("re").match(r".+-dev-(glue|lambda|sfn|scheduler)-role$", role_name))
