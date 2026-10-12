"""Unit tests for WorkflowGenerator parsing and fallback modes."""

from workflow.generator import WorkflowGenerator


def test_generator_fallback_mode_email():
    """Generator produces valid fallback workflow for email requests without API key."""
    gen = WorkflowGenerator(api_key=None)
    res = gen.generate_workflow("Check email address and uppercase customer name", use_demo_fallback=True)

    assert res["success"] is True
    assert res["source"] == "demo"
    assert res["workflow_data"] is not None
    assert "steps" in res["workflow_data"]
    assert len(res["workflow_data"]["steps"]) > 0


def test_generator_fallback_mode_order():
    """Generator matches order template for calculation prompts."""
    gen = WorkflowGenerator(api_key=None)
    res = gen.generate_workflow("Calculate order total and ask for approval if greater than 80", use_demo_fallback=True)

    assert res["success"] is True
    assert res["workflow_data"]["name"] == "High-Value Order Calculation and Approval"


def test_generator_defensive_json_markdown_stripping():
    """Generator cleans markdown code blocks enclosing JSON."""
    markdown_wrapped = """```json
    {
        "name": "Cleaned Workflow",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "hello"}
            }
        ]
    }
    ```"""
    parsed = WorkflowGenerator._clean_and_parse_json(markdown_wrapped)
    assert parsed["name"] == "Cleaned Workflow"
    assert parsed["steps"][0]["tool"] == "uppercase_text"


def test_generator_empty_prompt_rejected():
    """Empty prompts return error status."""
    gen = WorkflowGenerator(api_key=None)
    res = gen.generate_workflow("   ")
    assert res["success"] is False
    assert "cannot be empty" in res["error"]
