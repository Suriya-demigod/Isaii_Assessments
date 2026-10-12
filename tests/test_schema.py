"""Unit tests for Workflow Pydantic schema validation."""

import pytest
from pydantic import ValidationError
from workflow.schema import Workflow, WorkflowStep, StepType, ConditionRule


def test_valid_workflow_schema():
    """A well-formed workflow dictionary conforms to the schema."""
    data = {
        "name": "Test Workflow",
        "description": "A test workflow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "hello"},
                "description": "Convert to uppercase"
            }
        ]
    }
    workflow = Workflow(**data)
    assert workflow.name == "Test Workflow"
    assert len(workflow.steps) == 1
    assert workflow.steps[0].id == "step_1"
    assert workflow.steps[0].tool == "uppercase_text"


def test_reject_empty_steps():
    """Workflows with empty steps list are rejected."""
    data = {
        "name": "Empty Workflow",
        "description": "No steps",
        "steps": []
    }
    with pytest.raises(ValidationError):
        Workflow(**data)


def test_reject_duplicate_step_ids():
    """Workflows with duplicate step IDs are rejected."""
    data = {
        "name": "Duplicate IDs",
        "steps": [
            {"id": "step_1", "type": "tool", "tool": "uppercase_text", "args": {"text": "a"}},
            {"id": "step_1", "type": "tool", "tool": "uppercase_text", "args": {"text": "b"}}
        ]
    }
    with pytest.raises(ValueError, match="Duplicate step IDs"):
        Workflow(**data)


def test_tool_step_requires_tool_name():
    """Steps of type 'tool' must have a non-empty tool field."""
    step_data = {
        "id": "step_1",
        "type": "tool",
        "args": {}
    }
    with pytest.raises(ValidationError, match="no tool name was specified"):
        WorkflowStep(**step_data)


def test_condition_step_validation():
    """Condition steps require a condition rule and at least one branch target."""
    # Missing condition rule
    with pytest.raises(ValidationError, match="no condition rule was specified"):
        WorkflowStep(id="step_cond", type=StepType.CONDITION, if_true="step_2")

    # Missing branch targets
    with pytest.raises(ValidationError, match="neither 'if_true' nor 'if_false'"):
        WorkflowStep(
            id="step_cond",
            type=StepType.CONDITION,
            condition=ConditionRule(operator="==", left="a", right="b")
        )

    # Valid condition
    valid_step = WorkflowStep(
        id="step_cond",
        type=StepType.CONDITION,
        condition=ConditionRule(operator="==", left="a", right="b"),
        if_true="step_2",
        if_false="step_3"
    )
    assert valid_step.if_true == "step_2"
    assert valid_step.if_false == "step_3"


def test_invalid_condition_operator():
    """Unsupported condition operators are rejected."""
    with pytest.raises(ValidationError, match="Unsupported condition operator"):
        ConditionRule(operator="INVALID_OP", left="a", right="b")
