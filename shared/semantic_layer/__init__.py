"""Minimal ontology staging for Track B (local TTL + manifest, no AWS Semantic Layer publish)."""

from shared.semantic_layer.staging import StagingResult, induce_and_stage

__all__ = ["StagingResult", "induce_and_stage"]
