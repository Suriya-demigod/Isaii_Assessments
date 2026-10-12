"""Workflow validator verifying structure, step references, tool contracts, and inputs."""

import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import ValidationError
from .schema import Workflow, WorkflowStep, StepType, ConditionRule
from .tools import TOOL_REGISTRY


class WorkflowValidator:
    """Performs schema and semantic validation of workflow definitions."""

    MAX_STEPS = 25
    PLACEHOLDER_REGEX = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")

    @classmethod
    def validate_raw(cls, raw_data: Any) -> Tuple[bool, List[str], List[str], Optional[Workflow]]:
        """Validate raw dictionary or JSON object into a validated Workflow instance.
        
        Returns:
            (is_valid, errors, warnings, workflow_instance)
        """
        errors: List[str] = []
        warnings: List[str] = []

        if not isinstance(raw_data, dict):
            return False, ["Workflow payload must be a JSON object (dictionary)."], [], None

        # 1. Pydantic schema validation
        try:
            workflow = Workflow(**raw_data)
        except ValidationError as val_err:
            for err in val_err.errors():
                loc = " -> ".join(str(p) for p in err["loc"])
                msg = err["msg"]
                errors.append(f"Schema Error [{loc}]: {msg}")
            return False, errors, warnings, None
        except Exception as exc:
            return False, [f"Unexpected error while parsing workflow structure: {str(exc)}"], [], None

        # 2. Semantic validation
        semantic_valid, sem_errors, sem_warnings = cls.validate_workflow(workflow)
        errors.extend(sem_errors)
        warnings.extend(sem_warnings)

        return (len(errors) == 0), errors, warnings, (workflow if len(errors) == 0 else None)

    @classmethod
    def validate_workflow(cls, workflow: Workflow) -> Tuple[bool, List[str], List[str]]:
        """Validate an already parsed Workflow object for tool existence, branch integrity, and valid references."""
        errors: List[str] = []
        warnings: List[str] = []

        # Check maximum workflow length
        if len(workflow.steps) > cls.MAX_STEPS:
            errors.append(f"Workflow contains {len(workflow.steps)} steps, which exceeds maximum limit of {cls.MAX_STEPS}.")

        step_ids: Set[str] = {s.id for s in workflow.steps}
        step_index_map: Dict[str, int] = {s.id: idx for idx, s in enumerate(workflow.steps)}

        for idx, step in enumerate(workflow.steps):
            # A. Tool Validation
            if step.type == StepType.TOOL:
                if not step.tool:
                    errors.append(f"Step '{step.id}' (index {idx}): Missing tool name.")
                elif step.tool not in TOOL_REGISTRY:
                    errors.append(
                        f"Step '{step.id}' (index {idx}): Tool '{step.tool}' is not in approved registry. "
                        f"Approved tools: {list(TOOL_REGISTRY.keys())}"
                    )
                else:
                    # Check required tool parameters
                    tool_meta = TOOL_REGISTRY[step.tool]
                    req_params = {
                        p_name for p_name, p_info in tool_meta.get("params", {}).items()
                        if p_info.get("required", False)
                    }
                    provided_args = set(step.args.keys())
                    missing_reqs = req_params - provided_args
                    if missing_reqs:
                        errors.append(
                            f"Step '{step.id}': Tool '{step.tool}' missing required argument(s): {', '.join(missing_reqs)}"
                        )

            # B. Condition Branch Targets Validation
            if step.type == StepType.CONDITION:
                for branch_name, target in [("if_true", step.if_true), ("if_false", step.if_false)]:
                    if target:
                        target_clean = str(target).strip()
                        if target_clean.upper() == "END":
                            continue
                        if target_clean not in step_ids:
                            errors.append(
                                f"Step '{step.id}' (index {idx}): '{branch_name}' points to unknown step '{target_clean}'."
                            )
                        elif target_clean == step.id:
                            errors.append(
                                f"Step '{step.id}' (index {idx}): '{branch_name}' creates an immediate self-loop pointing back to itself."
                            )

            # C. Approval Steps
            if step.type == StepType.APPROVAL:
                if not step.requires_approval:
                    warnings.append(f"Step '{step.id}': Marked as 'approval' type; setting requires_approval=True automatically.")

            # D. Placeholder References Validation
            step_placeholders = cls._extract_placeholders_from_step(step)
            for placeholder in step_placeholders:
                if placeholder.startswith("input."):
                    # Valid workflow input placeholder
                    continue
                
                parts = placeholder.split(".")
                ref_step_id = parts[0]
                if ref_step_id not in step_ids:
                    errors.append(
                        f"Step '{step.id}': References unknown step or invalid prefix '{ref_step_id}' in placeholder '{{{{{placeholder}}}}}'."
                    )
                elif step_index_map[ref_step_id] >= idx:
                    errors.append(
                        f"Step '{step.id}': Forward reference detected. Placeholder '{{{{{placeholder}}}}}' refers to '{ref_step_id}', which has not executed yet."
                    )

        return (len(errors) == 0), errors, warnings

    @classmethod
    def extract_input_placeholders(cls, workflow: Workflow) -> List[str]:
        """Scan workflow steps and return sorted list of unique input field names (from {{input.<field>}})."""
        input_fields: Set[str] = set()
        for step in workflow.steps:
            for ph in cls._extract_placeholders_from_step(step):
                if ph.startswith("input."):
                    field_name = ph.split(".", 1)[1].strip()
                    if field_name:
                        input_fields.add(field_name)
        return sorted(list(input_fields))

    @classmethod
    def _extract_placeholders_from_step(cls, step: WorkflowStep) -> Set[str]:
        """Extract all placeholder references from a single step."""
        found: Set[str] = set()

        def scan_val(val: Any):
            if isinstance(val, str):
                for match in cls.PLACEHOLDER_REGEX.finditer(val):
                    found.add(match.group(1).strip())
            elif isinstance(val, dict):
                for v in val.values():
                    scan_val(v)
            elif isinstance(val, list):
                for item in val:
                    scan_val(item)

        # Scan args
        scan_val(step.args)

        # Scan condition
        if step.condition:
            if isinstance(step.condition, ConditionRule):
                scan_val(step.condition.left)
                if step.condition.right is not None:
                    scan_val(step.condition.right)
            elif isinstance(step.condition, dict):
                scan_val(step.condition.get("left"))
                scan_val(step.condition.get("right"))

        return found
