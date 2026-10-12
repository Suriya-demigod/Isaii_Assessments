"""Workflow JSON Schema and Pydantic models."""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class StepType(str, Enum):
    """Supported workflow step types."""
    TOOL = "tool"
    CONDITION = "condition"
    APPROVAL = "approval"


class ConditionRule(BaseModel):
    """Structure for conditional branching rules."""
    operator: str = Field(
        ...,
        description="Comparison operator, e.g., '==', '!=', '>', '<', '>=', '<=', 'contains', 'is_valid', 'is_empty'"
    )
    left: Any = Field(..., description="Left-hand value or variable reference like '{{step_1.output}}'")
    right: Optional[Any] = Field(default=None, description="Right-hand value for binary comparisons")

    @field_validator("operator")
    @classmethod
    def validate_operator(cls, v: str) -> str:
        valid_ops = {"==", "!=", ">", "<", ">=", "<=", "contains", "is_valid", "is_empty"}
        cleaned = v.strip().lower()
        if cleaned in valid_ops:
            return cleaned
        if v in valid_ops:
            return v
        raise ValueError(f"Unsupported condition operator '{v}'. Supported: {', '.join(sorted(valid_ops))}")


class WorkflowStep(BaseModel):
    """Definition of a single step in a workflow."""
    id: str = Field(..., description="Unique step identifier, e.g. 'step_1'")
    type: StepType = Field(default=StepType.TOOL, description="Step type: tool, condition, or approval")
    tool: Optional[str] = Field(default=None, description="Name of approved tool to execute")
    args: Dict[str, Any] = Field(default_factory=dict, description="Arguments to pass to the tool")
    condition: Optional[Union[ConditionRule, Dict[str, Any]]] = Field(
        default=None,
        description="Condition rule evaluated when type is condition"
    )
    if_true: Optional[str] = Field(default=None, description="Next step ID if condition is true")
    if_false: Optional[str] = Field(default=None, description="Next step ID if condition is false")
    requires_approval: bool = Field(
        default=False,
        description="Whether this step pauses execution until human approval is given"
    )
    description: Optional[str] = Field(default=None, description="Human-readable description of what this step does")

    @model_validator(mode="after")
    def validate_step_consistency(self) -> WorkflowStep:
        # If type is approval, requires_approval should naturally be True
        if self.type == StepType.APPROVAL:
            self.requires_approval = True

        # If type is tool, tool name is required
        if self.type == StepType.TOOL and not self.tool:
            raise ValueError(f"Step '{self.id}' has type 'tool' but no tool name was specified.")

        # If condition is passed as a dict, convert to ConditionRule
        if isinstance(self.condition, dict):
            self.condition = ConditionRule(**self.condition)

        # If type is condition, condition rule and at least one branch must exist
        if self.type == StepType.CONDITION:
            if not self.condition:
                raise ValueError(f"Step '{self.id}' has type 'condition' but no condition rule was specified.")
            if not self.if_true and not self.if_false:
                raise ValueError(f"Step '{self.id}' is a condition step but specifies neither 'if_true' nor 'if_false'.")

        return self


class Workflow(BaseModel):
    """Top-level structured workflow container."""
    name: str = Field(..., description="Readable workflow name")
    description: str = Field(default="", description="Summary of workflow purpose")
    steps: List[WorkflowStep] = Field(..., min_length=1, description="Ordered list of workflow steps")

    @field_validator("steps")
    @classmethod
    def validate_unique_step_ids(cls, steps: List[WorkflowStep]) -> List[WorkflowStep]:
        step_ids = [step.id for step in steps]
        if len(step_ids) != len(set(step_ids)):
            duplicates = {s for s in step_ids if step_ids.count(s) > 1}
            raise ValueError(f"Duplicate step IDs found in workflow: {', '.join(duplicates)}")
        return steps
