"""Stage OWL + R2RML Turtle artifacts from semantic.yaml (local mode only)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class StagingResult:
    state: str
    workload: str
    namespace: str
    version: str
    ontology_ttl_path: str
    mappings_ttl_path: str
    manifest_path: str
    owl_class_count: int
    pii_flagged_count: int
    warnings: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _xsd_type(type_str: str | None) -> str:
    if not type_str:
        return "xsd:string"
    base = type_str.strip().lower().split("(", 1)[0]
    mapping = {
        "string": "xsd:string",
        "integer": "xsd:integer",
        "int": "xsd:integer",
        "decimal": "xsd:decimal",
        "boolean": "xsd:boolean",
        "date": "xsd:date",
        "timestamp": "xsd:dateTime",
    }
    return mapping.get(base, "xsd:string")


def induce_and_stage(
    *,
    dataset_name: str,
    glue_database: str,
    glue_table: str,
    namespace: str,
    version: str = "v1",
    glue_schema: dict[str, Any] | None = None,
    mode: str = "local",
    workload_root: str = "workloads",
) -> StagingResult:
    if mode != "local":
        raise NotImplementedError(
            "AWS Semantic Layer publish is not implemented in Track A; use mode='local'."
        )

    wl_dir = REPO_ROOT / workload_root / dataset_name
    semantic_path = wl_dir / "config" / "semantic.yaml"
    if not semantic_path.is_file():
        raise FileNotFoundError(f"Missing semantic.yaml: {semantic_path}")

    with semantic_path.open(encoding="utf-8") as fh:
        semantic = yaml.safe_load(fh) or {}

    entities = semantic.get("entities") or []
    columns = semantic.get("columns") or {}
    ns_uri = f"https://adop.example/{namespace}/{version}/"
    class_count = len(entities)
    pii_count = sum(1 for meta in columns.values() if isinstance(meta, dict) and meta.get("pii"))

    ontology_lines = [
        f"@prefix ex: <{ns_uri}> .",
        "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
        "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        f"ex:Ontology a owl:Ontology ; rdfs:label \"{dataset_name} ontology\" .",
        "",
    ]

    for entity in entities:
        name = entity.get("name", "Entity")
        class_iri = f"ex:{name}"
        ontology_lines.append(f"{class_iri} a owl:Class ; rdfs:label \"{name}\" .")

    for col_name, meta in sorted(columns.items()):
        if not isinstance(meta, dict):
            continue
        prop_iri = f"ex:{col_name}"
        dtype = _xsd_type(meta.get("type"))
        ontology_lines.append(f"{prop_iri} a owl:DatatypeProperty ; rdfs:range {dtype} .")
        if meta.get("pii"):
            ontology_lines.append(
                f"{prop_iri} ex:piiClassification \"restricted\" ; ex:dataSensitivity \"high\" ."
            )

    mappings_lines = [
        f"@prefix rr: <http://www.w3.org/ns/r2rml#> .",
        f"@prefix ex: <{ns_uri}> .",
        "",
        f"<#{glue_table}Map> a rr:TriplesMap ;",
        f"  rr:logicalTable [ rr:tableName \"{glue_database}.{glue_table}\" ] ;",
        f"  rr:subjectMap [ rr:class ex:{entities[0]['name'] if entities else 'Entity'} ] .",
        "",
    ]

    config_dir = wl_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    ontology_path = config_dir / "ontology.ttl"
    mappings_path = config_dir / "mappings.ttl"
    manifest_path = config_dir / "ontology_manifest.json"

    ontology_path.write_text("\n".join(ontology_lines) + "\n", encoding="utf-8")
    mappings_path.write_text("\n".join(mappings_lines) + "\n", encoding="utf-8")

    manifest = {
        "state": "STAGED_LOCAL",
        "workload": dataset_name,
        "namespace": namespace,
        "version": version,
        "staged_at": datetime.now(timezone.utc).isoformat(),
        "artifacts": {
            "ontology.ttl": {"sha256": _sha256(ontology_path)},
            "mappings.ttl": {"sha256": _sha256(mappings_path)},
        },
        "steward_checklist": [
            "Review OWL classes against business glossary",
            "Confirm PII annotations before AWS Semantic Layer publish",
            "Validate R2RML maps to Gold Glue table",
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    return StagingResult(
        state="STAGED_LOCAL",
        workload=dataset_name,
        namespace=namespace,
        version=version,
        ontology_ttl_path=str(ontology_path.relative_to(REPO_ROOT)),
        mappings_ttl_path=str(mappings_path.relative_to(REPO_ROOT)),
        manifest_path=str(manifest_path.relative_to(REPO_ROOT)),
        owl_class_count=class_count,
        pii_flagged_count=pii_count,
    )
