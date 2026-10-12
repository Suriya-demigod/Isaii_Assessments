"""Deterministic workflow execution engine.

Handles input resolution, conditional branching, human approval gates,
loop detection, and step-by-step state tracking. No eval/exec anywhere."""

import time
import re
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from .schema import Workflow, WorkflowStep, StepType, ConditionRule
from .tools import execute_tool, check_condition

logger = logging.getLogger(__name__)


class StepExecutionResult:
    """Holds the outcome of running one workflow step."""

    __slots__ = (
        "step_id", "step_type", "tool", "status", "inputs",
        "output", "error", "duration_ms", "notes", "business_outcome"
    )

    def __init__(
        self,
        step_id: str,
        step_type: str,
        tool: Optional[str] = None,
        status: str = "pending",
        inputs: Optional[Dict[str, Any]] = None,
        output: Any = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        notes: str = "",
        business_outcome: Optional[str] = None
    ):
        self.step_id = step_id
        self.step_type = step_type
        self.tool = tool
        self.status = status
        self.inputs = inputs or {}
        self.output = output
        self.error = error
        self.duration_ms = duration_ms
        self.notes = notes
        self.business_outcome = business_outcome

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "tool": self.tool,
            "status": self.status,
            "inputs": self.inputs,
            "output": self.output,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "notes": self.notes,
            "business_outcome": self.business_outcome
        }


class WorkflowExecutor:
    """Runs a validated workflow step-by-step in a deterministic loop.

    Features:
      - Placeholder resolution for {{input.x}} and {{step_N.output.y}}
      - Conditional branching with automatic skip-marking
      - Human-in-the-loop approval gates (pause / resume / reject)
      - Loop detection: per-step visit counter + global execution cap
      - Null-input rejection before execution starts
    """

    MAX_EXECUTION_STEPS = 50
    MAX_STEP_VISITS = 5
    PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}")

    def __init__(self, workflow: Workflow, inputs: Optional[Dict[str, Any]] = None):
        self.workflow = workflow
        self.step_map: Dict[str, WorkflowStep] = {s.id: s for s in workflow.steps}
        self.step_order: List[str] = [s.id for s in workflow.steps]

        # User-supplied inputs
        self.inputs: Dict[str, Any] = dict(inputs) if inputs else {}

        # Auto-populate common input aliases (email/email_address, name/customer_name)
        if "email" in self.inputs:
            self.inputs.setdefault("email_address", self.inputs["email"])
            self.inputs.setdefault("customer_email", self.inputs["email"])
        elif "email_address" in self.inputs:
            self.inputs.setdefault("email", self.inputs["email_address"])
            self.inputs.setdefault("customer_email", self.inputs["email_address"])

        if "customer_name" in self.inputs:
            self.inputs.setdefault("name", self.inputs["customer_name"])
            self.inputs.setdefault("user_name", self.inputs["customer_name"])
        elif "name" in self.inputs:
            self.inputs.setdefault("customer_name", self.inputs["name"])
            self.inputs.setdefault("user_name", self.inputs["name"])

        # Execution context — stores step outputs and input values
        self.context: Dict[str, Any] = {"input": self.inputs}
        for k, v in self.inputs.items():
            self.context[f"input.{k}"] = v

        self.logs: List[StepExecutionResult] = []
        self.status: str = "not_started"
        self.current_step_idx: int = 0
        self.step_visit_counts: Dict[str, int] = {}
        self.pending_step_id: Optional[str] = None
        self.skipped_step_ids: Set[str] = set()

    # ------------------------------------------------------------------
    # Pre-flight validation
    # ------------------------------------------------------------------

    def validate_inputs_and_references(self) -> Tuple[bool, List[str]]:
        """Make sure every placeholder can actually be resolved at runtime."""
        errors: List[str] = []
        idx_map = {sid: i for i, sid in enumerate(self.step_order)}

        for idx, step in enumerate(self.workflow.steps):
            placeholders = self._extract_placeholders(step)

            for ph in placeholders:
                if ph.startswith("input."):
                    field = ph.split(".", 1)[1].strip()
                    if field not in self.inputs:
                        errors.append(f"Missing required workflow input: '{field}'. Please provide a valid value before execution.")
                    elif self.inputs[field] is None:
                        errors.append(f"Required workflow input '{field}' is null. Null inputs are not allowed.")
                else:
                    ref_id = ph.split(".")[0]
                    if ref_id not in self.step_map:
                        errors.append(f"Step '{step.id}': References unknown step '{ref_id}' in '{{{{{ph}}}}}'.")
                    elif idx_map[ref_id] >= idx:
                        errors.append(f"Step '{step.id}': Forward reference detected. '{{{{{ph}}}}}' references '{ref_id}' which has not executed yet.")

            # Branch target sanity
            if step.type == StepType.CONDITION:
                for label, target in [("if_true", step.if_true), ("if_false", step.if_false)]:
                    if target:
                        t = str(target).strip()
                        if t.upper() != "END" and t not in self.step_map:
                            errors.append(f"Step '{step.id}': Branch '{label}' references non-existent step '{t}'.")

        return (len(errors) == 0), errors

    # ------------------------------------------------------------------
    # Main execution loop
    # ------------------------------------------------------------------

    def execute(self) -> Dict[str, Any]:
        """Run the workflow from the current position until it completes,
        fails, or pauses for approval."""

        # Pre-flight check on first run
        if self.current_step_idx == 0 and self.status == "not_started":
            ok, errs = self.validate_inputs_and_references()
            if not ok:
                self.status = "failed"
                return self._result(error="Pre-execution validation failed: " + "; ".join(errs))

        self.status = "running"
        ops_count = 0

        while self.current_step_idx < len(self.step_order):
            if ops_count >= self.MAX_EXECUTION_STEPS:
                self.status = "failed"
                return self._result(
                    error=f"Execution limit hit ({self.MAX_EXECUTION_STEPS} ops). Possible infinite loop."
                )

            cur_id = self.step_order[self.current_step_idx]
            step = self.step_map[cur_id]

            # Skip steps that were excluded by a branch
            if cur_id in self.skipped_step_ids:
                if not any(l.step_id == cur_id for l in self.logs):
                    self.logs.append(StepExecutionResult(
                        step_id=cur_id,
                        step_type=step.type.value,
                        tool=step.tool,
                        status="skipped",
                        notes="Bypassed by conditional branch.",
                        business_outcome="Step skipped: Not selected by conditional branch."
                    ))
                self.current_step_idx += 1
                continue

            # Per-step loop guard
            visits = self.step_visit_counts.get(cur_id, 0) + 1
            self.step_visit_counts[cur_id] = visits
            if visits > self.MAX_STEP_VISITS:
                self.status = "failed"
                return self._result(
                    error=f"Infinite loop detected: step '{cur_id}' executed {visits} times."
                )

            # Approval gate
            if step.requires_approval or step.type == StepType.APPROVAL:
                approval_flag = f"_approved_{cur_id}"
                if not self.context.get(approval_flag, False):
                    self.status = "paused_approval"
                    self.pending_step_id = cur_id

                    try:
                        preview_args = self._resolve_args(step.args)
                    except Exception:
                        preview_args = step.args

                    self.logs.append(StepExecutionResult(
                        step_id=cur_id,
                        step_type=step.type.value,
                        tool=step.tool,
                        status="pending_approval",
                        inputs=preview_args,
                        notes="Execution paused: Awaiting explicit human approval.",
                        business_outcome="Awaiting human confirmation before executing protected action."
                    ))
                    return self._result()

            # Actually execute
            ops_count += 1
            ok, jump_target = self._run_step(step)

            if not ok:
                self.status = "failed"
                return self._result()

            # Advance pointer
            if jump_target:
                t = jump_target.strip()
                if t.upper() == "END":
                    self._mark_remaining_skipped(self.current_step_idx + 1)
                    self.current_step_idx = len(self.step_order)
                    break
                elif t in self.step_map:
                    target_idx = self.step_order.index(t)
                    self._mark_range_skipped(self.current_step_idx + 1, target_idx)
                    self.current_step_idx = target_idx
                else:
                    self.status = "failed"
                    return self._result(error=f"Branch target '{jump_target}' does not exist.")
            else:
                self.current_step_idx += 1

        self.status = "completed"
        return self._result()

    # ------------------------------------------------------------------
    # Approval handling
    # ------------------------------------------------------------------

    def handle_approval(self, approved: bool) -> Dict[str, Any]:
        """Resume after user approves, or cancel on rejection."""
        if self.status != "paused_approval" or not self.pending_step_id:
            return self._result(error="No step is currently awaiting approval.")

        sid = self.pending_step_id

        if not approved:
            for log in reversed(self.logs):
                if log.step_id == sid and log.status == "pending_approval":
                    log.status = "rejected"
                    log.notes = "Rejected by human operator. Execution stopped."
                    log.business_outcome = "Action rejected by operator; workflow stopped safely."
                    break
            self.status = "cancelled"
            self.pending_step_id = None
            return self._result()

        # Remove placeholder log, mark approved, and keep going
        for log in reversed(self.logs):
            if log.step_id == sid and log.status == "pending_approval":
                self.logs.remove(log)
                break

        self.context[f"_approved_{sid}"] = True
        self.pending_step_id = None
        self.status = "running"
        return self.execute()

    # ------------------------------------------------------------------
    # Single-step execution
    # ------------------------------------------------------------------

    def _run_step(self, step: WorkflowStep) -> Tuple[bool, Optional[str]]:
        """Execute one step and log the result. Returns (success, jump_target)."""
        t0 = time.perf_counter()

        # --- TOOL / APPROVAL steps ---
        if step.type in (StepType.TOOL, StepType.APPROVAL):
            try:
                resolved_args = self._resolve_args(step.args)
            except Exception as e:
                ms = (time.perf_counter() - t0) * 1000
                self.logs.append(StepExecutionResult(
                    step_id=step.id, step_type=step.type.value, tool=step.tool,
                    status="failed", inputs=step.args,
                    error=f"Argument resolution error: {e}",
                    duration_ms=ms,
                    business_outcome="Execution halted: Failed to resolve step arguments."
                ))
                return False, None

            if not step.tool:
                # Pure approval checkpoint with no tool attached
                ms = (time.perf_counter() - t0) * 1000
                self.logs.append(StepExecutionResult(
                    step_id=step.id, step_type=step.type.value,
                    status="success", inputs=resolved_args,
                    output={"message": "Approval granted."},
                    duration_ms=ms,
                    business_outcome="Human approval verified."
                ))
                return True, None

            tool_resp = execute_tool(step.tool, resolved_args)
            ms = (time.perf_counter() - t0) * 1000

            if not tool_resp["success"]:
                self.logs.append(StepExecutionResult(
                    step_id=step.id, step_type=step.type.value, tool=step.tool,
                    status="failed", inputs=resolved_args,
                    error=tool_resp["error"], duration_ms=ms,
                    business_outcome=f"Execution error: {tool_resp['error']}"
                ))
                return False, None

            output = tool_resp["output"]
            self.context[step.id] = output
            self.context[f"{step.id}.output"] = output

            outcome = self._business_outcome(step.tool, output)
            self.logs.append(StepExecutionResult(
                step_id=step.id, step_type=step.type.value, tool=step.tool,
                status="success", inputs=resolved_args, output=output,
                duration_ms=ms, business_outcome=outcome
            ))
            return True, None

        # --- CONDITION steps ---
        if step.type == StepType.CONDITION:
            rule = step.condition
            if isinstance(rule, dict):
                rule = ConditionRule(**rule)

            try:
                left = self._resolve_value(rule.left)
                right = self._resolve_value(rule.right) if rule.right is not None else None
            except Exception as e:
                ms = (time.perf_counter() - t0) * 1000
                self.logs.append(StepExecutionResult(
                    step_id=step.id, step_type=step.type.value,
                    status="failed",
                    inputs={"left": rule.left, "operator": rule.operator, "right": rule.right},
                    error=f"Condition resolution error: {e}",
                    duration_ms=ms,
                    business_outcome="Execution halted: Failed to resolve condition operands."
                ))
                return False, None

            try:
                cond_result = check_condition(val1=left, operator=rule.operator, val2=right)
            except Exception as e:
                ms = (time.perf_counter() - t0) * 1000
                self.logs.append(StepExecutionResult(
                    step_id=step.id, step_type=step.type.value,
                    status="failed",
                    inputs={"left": left, "operator": rule.operator, "right": right},
                    error=f"Condition evaluation error: {e}",
                    duration_ms=ms,
                    business_outcome="Execution halted: Condition comparison failed."
                ))
                return False, None

            matched = cond_result["matched"]
            ms = (time.perf_counter() - t0) * 1000

            if matched:
                jump = step.if_true
                skip_branch = step.if_false
                branch_note = f"Condition TRUE -> taking branch '{step.if_true}'"
                outcome = f"Evaluated to TRUE; selecting branch '{step.if_true}'"
            else:
                jump = step.if_false
                skip_branch = step.if_true
                branch_note = f"Condition FALSE -> taking branch '{step.if_false}'"
                outcome = f"Evaluated to FALSE; selecting branch '{step.if_false}'"

            if skip_branch and str(skip_branch).strip().upper() != "END":
                self.skipped_step_ids.add(str(skip_branch).strip())

            self.context[step.id] = cond_result
            self.context[f"{step.id}.matched"] = matched

            self.logs.append(StepExecutionResult(
                step_id=step.id, step_type=step.type.value,
                status="success",
                inputs={"left": left, "operator": rule.operator, "right": right},
                output={"matched": matched, "branch_selected": jump},
                notes=branch_note, duration_ms=ms,
                business_outcome=outcome
            ))
            return True, jump

        # Unknown step type (shouldn't happen after schema validation)
        logger.error("Unhandled step type '%s' for step '%s'", step.type, step.id)
        return False, None

    # ------------------------------------------------------------------
    # Skip-marking helpers
    # ------------------------------------------------------------------

    def _mark_remaining_skipped(self, from_idx: int):
        for i in range(from_idx, len(self.step_order)):
            sid = self.step_order[i]
            if not any(l.step_id == sid for l in self.logs):
                s = self.step_map[sid]
                self.logs.append(StepExecutionResult(
                    step_id=sid, step_type=s.type.value, tool=s.tool,
                    status="skipped", notes="Bypassed by branch to END.",
                    business_outcome="Step skipped: Workflow terminated at END."
                ))

    def _mark_range_skipped(self, from_idx: int, to_idx: int):
        for i in range(from_idx, to_idx):
            sid = self.step_order[i]
            if not any(l.step_id == sid for l in self.logs):
                s = self.step_map[sid]
                self.logs.append(StepExecutionResult(
                    step_id=sid, step_type=s.type.value, tool=s.tool,
                    status="skipped", notes="Bypassed by conditional branch.",
                    business_outcome="Step skipped: Unselected branch."
                ))

    # ------------------------------------------------------------------
    # Variable resolution
    # ------------------------------------------------------------------

    def _resolve_args(self, args: Dict[str, Any]) -> Dict[str, Any]:
        return {k: self._resolve_value(v) for k, v in args.items()}

    def _resolve_value(self, val: Any) -> Any:
        """Resolve {{placeholder}} references in a value."""
        if not isinstance(val, str):
            if isinstance(val, dict):
                return {k: self._resolve_value(v) for k, v in val.items()}
            if isinstance(val, list):
                return [self._resolve_value(item) for item in val]
            return val

        pat = r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}"

        # Single-placeholder optimization: return the raw value (preserves type)
        full_match = re.fullmatch(pat, val.strip())
        if full_match:
            path = full_match.group(1).strip()
            found, resolved = self._lookup(path)
            if not found:
                raise ValueError(f"Unresolved placeholder reference: '{{{{{path}}}}}'. Required input or step output is not available.")
            if resolved is None:
                raise ValueError(f"Placeholder '{{{{{path}}}}}' resolved to null/None. Null values cannot be passed to tools.")
            return resolved

        # Embedded interpolation: "Hello {{input.name}}!"
        def _sub(m):
            path = m.group(1).strip()
            found, val_ = self._lookup(path)
            if not found:
                raise ValueError(f"Unresolved placeholder reference: '{{{{{path}}}}}'. Required input or step output is not available.")
            if val_ is None:
                raise ValueError(f"Placeholder '{{{{{path}}}}}' resolved to null/None. Null values cannot be interpolated into strings.")
            return str(val_)

        return re.sub(pat, _sub, val)

    def _lookup(self, path: str) -> Tuple[bool, Any]:
        """Walk the context dict to resolve a dotted path like step_1.output.total."""
        path = path.strip()
        if not path:
            return False, None

        # Direct hit
        if path in self.context:
            return True, self.context[path]

        parts = path.split(".")
        root = parts[0]
        if root not in self.context:
            return False, None

        current = self.context[root]
        for i, part in enumerate(parts[1:]):
            if isinstance(current, dict):
                if part in current:
                    current = current[part]
                elif part == "output" and i == 0:
                    continue  # skip redundant .output token
                # Alias fallback for tool output keys
                elif part in ("text", "result", "value") and ("result" in current or "text" in current or "value" in current):
                    current = current.get("result") if "result" in current else (current.get("text") if "text" in current else current.get("value"))
                elif part in ("is_valid", "valid") and ("is_valid" in current or "valid" in current):
                    current = current.get("is_valid", current.get("valid"))
                # Alias fallback for input fields
                elif root == "input" and part in ("email", "email_address", "customer_email"):
                    found_val = next((current[k] for k in ("email", "email_address", "customer_email") if k in current), None)
                    if found_val is not None:
                        current = found_val
                    else:
                        return False, None
                elif root == "input" and part in ("customer_name", "name", "user_name"):
                    found_val = next((current[k] for k in ("customer_name", "name", "user_name") if k in current), None)
                    if found_val is not None:
                        current = found_val
                    else:
                        return False, None
                else:
                    return False, None
            elif hasattr(current, part):
                current = getattr(current, part)
            else:
                return False, None

        return True, current

    # ------------------------------------------------------------------
    # Business outcome labelling
    # ------------------------------------------------------------------

    def _business_outcome(self, tool_name: Optional[str], output: Any) -> str:
        if not tool_name or not isinstance(output, dict):
            return "Operation completed."

        if tool_name == "validate_email":
            valid = output.get("is_valid")
            email = output.get("email", "")
            if valid:
                return f"Validation result: Valid email ('{email}')."
            return f"Validation result: Invalid email ('{email}'). Reason: {output.get('reason', 'Invalid format')}."

        if tool_name == "uppercase_text":
            return f"Transformed text to uppercase: '{output.get('result', '')}'."

        if tool_name == "transform_data":
            return f"Transformed data ({output.get('action', '')}): '{output.get('result', '')}'."

        if tool_name == "calculate_total":
            return f"Calculated sum: {output.get('total')} (across {output.get('count', 0)} values)."

        if tool_name == "create_notification":
            return (
                f"Notification prepared for '{output.get('recipient')}': \"{output.get('message')}\". "
                "[Simulation completed — no external message was sent]."
            )

        if tool_name == "http_get":
            return f"HTTP GET completed with status {output.get('status_code', '?')} ({output.get('bytes_received', 0)} bytes)."

        return "Tool completed successfully."

    # ------------------------------------------------------------------
    # Placeholder extraction (for pre-flight checks)
    # ------------------------------------------------------------------

    def _extract_placeholders(self, step: WorkflowStep) -> Set[str]:
        found: Set[str] = set()

        def scan(val: Any):
            if isinstance(val, str):
                for m in self.PLACEHOLDER_RE.finditer(val):
                    found.add(m.group(1).strip())
            elif isinstance(val, dict):
                for v in val.values():
                    scan(v)
            elif isinstance(val, list):
                for item in val:
                    scan(item)

        scan(step.args)
        if step.condition:
            if isinstance(step.condition, ConditionRule):
                scan(step.condition.left)
                if step.condition.right is not None:
                    scan(step.condition.right)
            elif isinstance(step.condition, dict):
                scan(step.condition.get("left"))
                scan(step.condition.get("right"))

        return found

    # ------------------------------------------------------------------
    # Result packaging
    # ------------------------------------------------------------------

    def _result(self, error: Optional[str] = None) -> Dict[str, Any]:
        return {
            "status": self.status,
            "current_step_id": self.pending_step_id,
            "error": error,
            "logs": [log.to_dict() for log in self.logs],
            "context": {k: v for k, v in self.context.items() if not k.startswith("_")}
        }
