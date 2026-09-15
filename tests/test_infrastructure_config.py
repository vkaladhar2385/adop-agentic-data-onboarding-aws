"""MCP-first infrastructure owner defaults (no AWS)."""

from shared.deploy.infrastructure_config import owners_from_compute, load_infrastructure_owners


def test_omitted_infrastructure_defaults_data_plane_to_mcp():
    owners = owners_from_compute({"workload": "demo"}, "demo")
    assert owners["catalog_owner"] == "mcp"
    assert owners["kms_owner"] == "mcp"
    assert owners["iam_owner"] == "mcp"
    assert owners["lakeformation_owner"] == "mcp"
    assert owners["glue_jobs_owner"] == "terraform"
    assert owners["orchestration_owner"] == "terraform"
    assert owners["database"] == "demo_db"


def test_explicit_terraform_opt_out_is_respected():
    owners = owners_from_compute(
        {
            "infrastructure": {
                "catalog": {"owner": "terraform", "database": "x_db"},
                "kms": {"owner": "terraform"},
            }
        },
        "x",
    )
    assert owners["catalog_owner"] == "terraform"
    assert owners["kms_owner"] == "terraform"
    assert owners["iam_owner"] == "mcp"
    assert owners["database"] == "x_db"


def test_supplier_lead_times_is_mcp_first():
    owners = load_infrastructure_owners("supplier_lead_times")
    assert owners["catalog_owner"] == "mcp"
    assert owners["glue_jobs_owner"] == "terraform"
