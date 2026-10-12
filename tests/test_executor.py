"""Unit tests for WorkflowExecutor deterministic execution, inputs, branching, and status handling."""

import pytest
from workflow.schema import Workflow
from workflow.executor import WorkflowExecutor


def test_linear_workflow_execution():
    """A linear workflow executes steps in order and passes outputs via variables."""
    payload = {
        "name": "Linear Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "alice"}
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "admin@example.com",
                    "message": "Processed user: {{step_1.output.result}}",
                    "level": "info"
                }
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "completed"
    assert len(result["logs"]) == 2
    assert result["logs"][0]["status"] == "success"
    assert result["logs"][0]["output"]["result"] == "ALICE"
    assert result["logs"][1]["status"] == "success"
    assert result["logs"][1]["inputs"]["message"] == "Processed user: ALICE"


def test_missing_required_inputs():
    """Workflow with input placeholders rejects execution if required input is missing or null."""
    payload = {
        "name": "Input Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {"email": "{{input.email}}"}
            }
        ]
    }
    wf = Workflow(**payload)

    # 1. Missing input entirely
    executor_missing = WorkflowExecutor(wf, inputs={})
    res_missing = executor_missing.execute()
    assert res_missing["status"] == "failed"
    assert "Missing required workflow input: 'email'" in res_missing["error"]

    # 2. Null input
    executor_null = WorkflowExecutor(wf, inputs={"email": None})
    res_null = executor_null.execute()
    assert res_null["status"] == "failed"
    assert "is null" in res_null["error"]


def test_correct_resolution_of_input_placeholders():
    """Input placeholders like {{input.email}} and {{input.customer_name}} resolve correctly."""
    payload = {
        "name": "User Input Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {"email": "{{input.email}}"}
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "{{input.customer_name}}"}
            }
        ]
    }
    wf = Workflow(**payload)
    inputs = {
        "email": "charlie@company.com",
        "customer_name": "charlie brown"
    }
    executor = WorkflowExecutor(wf, inputs=inputs)
    result = executor.execute()

    assert result["status"] == "completed"
    assert result["logs"][0]["output"]["email"] == "charlie@company.com"
    assert result["logs"][0]["output"]["is_valid"] is True
    assert result["logs"][1]["output"]["result"] == "CHARLIE BROWN"


def test_correct_resolution_of_previous_step_outputs():
    """Later steps correctly resolve previous step outputs (e.g. {{step_1.output.result}})."""
    payload = {
        "name": "Pipelined Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "transform_data",
                "args": {"data": "  hello world  ", "action": "trim"}
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "{{step_1.output.result}}"}
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "completed"
    assert result["logs"][1]["output"]["result"] == "HELLO WORLD"


def test_invalid_email_business_result_without_tool_exception():
    """An invalid email address is a valid business outcome, not an unhandled execution exception."""
    payload = {
        "name": "Invalid Email Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {"email": "not-a-valid-email"}
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    # Step execution succeeded (no Python crash)
    assert result["status"] == "completed"
    step_log = result["logs"][0]
    assert step_log["status"] == "success"
    # But business outcome correctly identifies invalid email
    assert step_log["output"]["is_valid"] is False
    assert "Invalid email" in step_log["business_outcome"]


def test_conditional_branching_true():
    """When condition evaluates to true, if_true branch is taken and if_false branch is marked skipped."""
    payload = {
        "name": "Branching True Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {"email": "valid.user@company.com"}
            },
            {
                "id": "step_2",
                "type": "condition",
                "condition": {
                    "operator": "is_valid",
                    "left": "{{step_1.output.is_valid}}"
                },
                "if_true": "step_success",
                "if_false": "step_failure"
            },
            {
                "id": "step_success",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "alerts",
                    "message": "Email is valid!",
                    "level": "success"
                }
            },
            {
                "id": "step_failure",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "alerts",
                    "message": "Invalid email!",
                    "level": "error"
                }
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "completed"
    logs = result["logs"]

    # step_1 and step_2 ran
    assert logs[0]["step_id"] == "step_1" and logs[0]["status"] == "success"
    assert logs[1]["step_id"] == "step_2" and logs[1]["output"]["matched"] is True

    # step_success ran
    assert any(log["step_id"] == "step_success" and log["status"] == "success" for log in logs)

    # step_failure marked skipped
    assert any(log["step_id"] == "step_failure" and log["status"] == "skipped" for log in logs)


def test_conditional_branching_false():
    """When condition evaluates to false, if_false branch is taken and if_true branch is marked skipped."""
    payload = {
        "name": "Branching False Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "calculate_total",
                "args": {"numbers": [10, 20]}  # sum = 30
            },
            {
                "id": "step_2",
                "type": "condition",
                "condition": {
                    "operator": ">",
                    "left": "{{step_1.output.total}}",
                    "right": 100.0
                },
                "if_true": "step_expensive",
                "if_false": "step_cheap"
            },
            {
                "id": "step_expensive",
                "type": "tool",
                "tool": "create_notification",
                "args": {"recipient": "boss", "message": "High budget", "level": "warning"}
            },
            {
                "id": "step_cheap",
                "type": "tool",
                "tool": "create_notification",
                "args": {"recipient": "boss", "message": "Affordable", "level": "info"}
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "completed"
    logs = result["logs"]
    assert any(log["step_id"] == "step_expensive" and log["status"] == "skipped" for log in logs)
    assert any(log["step_id"] == "step_cheap" and log["status"] == "success" for log in logs)


def test_unsupported_or_unresolved_placeholder_rejected():
    """References to nonexistent steps or unresolvable placeholders are rejected before execution."""
    payload = {
        "name": "Broken Reference Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "{{nonexistent_step.output.result}}"}
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "failed"
    assert "nonexistent_step" in result["error"]


def test_simulated_notification_never_claims_external_delivery():
    """create_notification tool explicitly sets delivered: False and simulated: True."""
    payload = {
        "name": "Notification Test",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "customer@example.com",
                    "message": "Your order has been placed.",
                    "level": "info"
                }
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "completed"
    log = result["logs"][0]
    assert log["status"] == "success"
    # Never claim actual delivery
    assert log["output"]["delivered"] is False
    assert log["output"]["simulated"] is True
    assert "Simulation completed" in log["output"]["note"]
    assert "Simulation completed" in log["business_outcome"]


def test_correct_overall_status_when_step_fails():
    """When a tool raises an execution error, step is marked failed and overall workflow status is failed."""
    payload = {
        "name": "Failing Tool Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "calculate_total",
                "args": {"numbers": ["not_a_number", "invalid"]}
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "create_notification",
                "args": {"recipient": "me", "message": "Never runs", "level": "info"}
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)
    result = executor.execute()

    assert result["status"] == "failed"
    assert len(result["logs"]) == 1
    assert result["logs"][0]["status"] == "failed"
    assert "is not numeric" in result["logs"][0]["error"]


def test_approval_pauses_and_resumes_without_repeating_steps():
    """Workflow pauses on approval requirement, and resumes without repeating completed steps."""
    payload = {
        "name": "Approval Flow",
        "steps": [
            {
                "id": "step_calc",
                "type": "tool",
                "tool": "calculate_total",
                "args": {"numbers": [50, 60]}
            },
            {
                "id": "step_payout",
                "type": "approval",
                "requires_approval": True,
                "tool": "create_notification",
                "args": {
                    "recipient": "finance",
                    "message": "Dispatch payment: ${{step_calc.output.total}}",
                    "level": "warning"
                }
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)

    # 1. Initial execution pauses at step_payout
    first_run = executor.execute()
    assert first_run["status"] == "paused_approval"
    assert first_run["current_step_id"] == "step_payout"
    assert len(first_run["logs"]) == 2
    assert first_run["logs"][0]["step_id"] == "step_calc"
    assert first_run["logs"][0]["status"] == "success"
    assert first_run["logs"][1]["status"] == "pending_approval"

    # Verify step_calc ran exactly once
    assert executor.step_visit_counts["step_calc"] == 1

    # 2. Grant approval and resume
    resumed_run = executor.handle_approval(approved=True)
    assert resumed_run["status"] == "completed"
    # step_calc was NOT re-executed
    assert executor.step_visit_counts["step_calc"] == 1
    # step_payout completed successfully
    assert resumed_run["logs"][1]["status"] == "success"


def test_approval_rejection_cancels_workflow():
    """Workflow cancels and halts if user rejects pending action."""
    payload = {
        "name": "Reject Flow",
        "steps": [
            {
                "id": "step_payout",
                "type": "approval",
                "requires_approval": True,
                "tool": "create_notification",
                "args": {"recipient": "finance", "message": "Risky transfer", "level": "warning"}
            }
        ]
    }
    wf = Workflow(**payload)
    executor = WorkflowExecutor(wf)

    executor.execute()
    assert executor.status == "paused_approval"

    rejected_run = executor.handle_approval(approved=False)
    assert rejected_run["status"] == "cancelled"
    assert rejected_run["logs"][0]["status"] == "rejected"
