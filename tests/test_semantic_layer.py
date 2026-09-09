from shared.semantic_layer import induce_and_stage


def test_induce_and_stage_customer_orders():
    result = induce_and_stage(
        dataset_name="customer_orders",
        glue_database="customer_orders_db",
        glue_table="gold_customer_orders",
        namespace="commerce",
    )
    assert result.state == "STAGED_LOCAL"
    assert result.owl_class_count >= 1
    assert result.ontology_ttl_path.endswith("ontology.ttl")
