"""Unit tests for sandbox tag manifest (no AWS)."""

from shared.deploy.sandbox_tags import (
    glue_parameters,
    iam_tag_list,
    load_sandbox_tags,
    resource_prefix,
    role_name_matches_prefix,
    tag_filter,
    tag_map,
)


def test_load_sandbox_tags_has_managed_by():
    cfg = load_sandbox_tags()
    tags = tag_map(cfg)
    assert tags["ManagedBy"] == "adop-sandbox"
    assert tags["Project"] == "adop"


def test_iam_tag_list_format():
    tags = iam_tag_list()
    assert all("Key" in t and "Value" in t for t in tags)


def test_tag_filter():
    key, values = tag_filter()
    assert key == "ManagedBy"
    assert "adop-sandbox" in values


def test_glue_parameters():
    params = glue_parameters()
    assert params.get("adop:managed") == "true"


def test_role_name_matches_prefix():
    assert role_name_matches_prefix("adop-mcp-glue-athena-role")
    assert role_name_matches_prefix("advisory_transactions-dev-glue-role")
    assert not role_name_matches_prefix("unrelated-role")


def test_resource_prefix():
    assert resource_prefix() == "adop"
