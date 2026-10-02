from shared.utils.orchestrator import (
    resolve_orchestration_artifacts,
    resolve_orchestrator,
)


def test_default_is_step_functions():
    assert resolve_orchestrator(None) == "step_functions"
    assert resolve_orchestrator({}) == "step_functions"


def test_mwaa_emits_dag_only():
    schedule = {"orchestrator": "mwaa"}
    assert resolve_orchestration_artifacts(schedule) == frozenset({"dag"})


def test_step_functions_emits_sfn_and_eventbridge():
    assert resolve_orchestration_artifacts({"orchestrator": "step_functions"}) == frozenset(
        {"state_machine", "eventbridge_schedule"}
    )


def test_both_emits_dag_and_sfn():
    schedule = {"orchestrator": "both"}
    assert resolve_orchestration_artifacts(schedule) == frozenset(
        {"state_machine", "dag", "eventbridge_schedule"}
    )


def test_adf_emits_adf_pipeline_only():
    assert resolve_orchestration_artifacts({"orchestrator": "adf"}) == frozenset({"adf_pipeline"})


def test_composer_emits_composer_dag_only():
    assert resolve_orchestration_artifacts({"orchestrator": "composer"}) == frozenset({"composer_dag"})


def test_workflows_emits_databricks_workflow_only():
    assert resolve_orchestration_artifacts({"orchestrator": "workflows"}) == frozenset(
        {"databricks_workflow"}
    )


def test_snowflake_tasks_emits_tasks_sql_only():
    assert resolve_orchestration_artifacts({"orchestrator": "snowflake_tasks"}) == frozenset(
        {"snowflake_tasks"}
    )
