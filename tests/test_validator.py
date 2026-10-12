"""Unit tests for WorkflowValidator semantic and tool validation."""

from workflow.validator import WorkflowValidator


def test_validator_accepts_valid_workflow():
    """A fully valid workflow passes semantic validation."""
    payload = {
        "name": "Valid Notification Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {"email": "user@example.com"}
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "user@example.com",
                    "message": "Hello!",
                    "level": "info"
                }
            }
        ]
    }
    is_valid, errors, warnings, workflow = WorkflowValidator.validate_raw(payload)
    assert is_valid is True
    assert len(errors) == 0
    assert workflow is not None


def test_validator_rejects_malformed_json_types():
    """Non-dict inputs are rejected immediately."""
    is_valid, errors, _, _ = WorkflowValidator.validate_raw("invalid string")
    assert is_valid is False
    assert any("must be a JSON object" in err for err in errors)


def test_validator_rejects_unknown_tool():
    """Referencing a tool not in the whitelist registry is rejected."""
    payload = {
        "name": "Unknown Tool Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "execute_arbitrary_shell_command",
                "args": {"cmd": "whoami"}
            }
        ]
    }
    is_valid, errors, _, _ = WorkflowValidator.validate_raw(payload)
    assert is_valid is False
    assert any("not in approved registry" in err for err in errors)


def test_validator_rejects_missing_required_args():
    """Calling an approved tool without mandatory parameters is rejected."""
    payload = {
        "name": "Missing Args Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {}  # missing required 'email'
            }
        ]
    }
    is_valid, errors, _, _ = WorkflowValidator.validate_raw(payload)
    assert is_valid is False
    assert any("missing required argument" in err for err in errors)


def test_validator_rejects_unknown_branch_target():
    """Branch targets that do not exist in the workflow are rejected."""
    payload = {
        "name": "Broken Branch Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "condition",
                "condition": {"operator": "==", "left": 1, "right": 1},
                "if_true": "non_existent_step_99",
                "if_false": "END"
            }
        ]
    }
    is_valid, errors, _, _ = WorkflowValidator.validate_raw(payload)
    assert is_valid is False
    assert any("points to unknown step" in err for err in errors)


def test_validator_rejects_immediate_self_loop():
    """Branch targets pointing directly to the condition step itself are rejected."""
    payload = {
        "name": "Self Loop Flow",
        "steps": [
            {
                "id": "step_loop",
                "type": "condition",
                "condition": {"operator": "==", "left": 1, "right": 1},
                "if_true": "step_loop",
                "if_false": "END"
            }
        ]
    }
    is_valid, errors, _, _ = WorkflowValidator.validate_raw(payload)
    assert is_valid is False
    assert any("immediate self-loop" in err for err in errors)


def test_validator_extracts_input_placeholders():
    """extract_input_placeholders correctly extracts all {{input.<var>}} keys."""
    from workflow.schema import Workflow
    payload = {
        "name": "Inputs Workflow",
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
                "args": {"text": "Hello {{input.user_name}}"}
            }
        ]
    }
    wf = Workflow(**payload)
    extracted = WorkflowValidator.extract_input_placeholders(wf)
    assert extracted == ["email", "user_name"]


def test_validator_rejects_forward_reference():
    """Referencing a step that has not yet executed is rejected during validation."""
    payload = {
        "name": "Forward Ref Flow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "{{step_2.output.result}}"}
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "hello"}
            }
        ]
    }
    is_valid, errors, _, _ = WorkflowValidator.validate_raw(payload)
    assert is_valid is False
    assert any("Forward reference detected" in err for err in errors)

