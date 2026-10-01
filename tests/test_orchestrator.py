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
