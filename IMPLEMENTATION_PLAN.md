# Implementation Plan: Natural Language Workflow Generator

## 1. Architectural Overview

```text
User Natural Language Instruction
           │
           ▼
┌──────────────────────────┐
│   workflow/generator.py  │  (Calls Gemini Flash via google-genai SDK or fallback demo mode)
└──────────┬───────────────┘
           │ Structured Workflow JSON
           ▼
┌──────────────────────────┐
│   workflow/schema.py     │  (Pydantic V2 Models: Step, Condition, Workflow)
└──────────┬───────────────┘
           │ Validated Pydantic Structure
           ▼
┌──────────────────────────┐
│   workflow/validator.py  │  (Semantic validation: unique IDs, valid tool names, branching targets)
└──────────┬───────────────┘
           │ Approved Executable Workflow
           ▼
┌──────────────────────────┐
│   workflow/executor.py   │  (Deterministic execution loop, state manager, step results)
└──────────┬───────────────┘
           │ Invokes Approved Tools
           ▼
┌──────────────────────────┐
│   workflow/tools.py      │  (Registry: validate_email, uppercase_text, calculate_total, etc.)
└──────────┬───────────────┘
           │ Execution logs & states (Success, Failed, Pending Approval)
           ▼
┌──────────────────────────┐
│         app.py           │  (Streamlit User Interface & Interactive Controls)
└──────────────────────────┘
```

---

## 2. Component Design & Responsibilities

### A. `workflow/schema.py`
- Pydantic models:
  - `StepType`: Enum (`tool`, `condition`, `approval`)
  - `ConditionRule`: Field comparisons (`operator`, `left`, `right`)
  - `WorkflowStep`: `id`, `type`, `tool`, `args`, `condition`, `if_true`, `if_false`, `requires_approval`, `description`
  - `Workflow`: `name`, `description`, `steps`

### B. `workflow/tools.py`
- Pre-approved safe tools with input size limits:
  - `validate_email(email: str)`: Validates email pattern (max 320 chars).
  - `uppercase_text(text: str)`: Transforms string to uppercase (max 50,000 chars).
  - `transform_data(data: dict | list | str, action: str)`: Safe data transformation (e.g. trim, format, count).
  - `calculate_total(numbers: list[float | int])`: Safe numeric addition (max 500 items).
  - `check_condition(val1: Any, operator: str, val2: Any)`: Supported boolean comparisons.
  - `create_notification(recipient: str, message: str, level: str)`: Simulated notification creator (message capped at 2,000 chars).
  - `http_get(url: str, timeout: int)`: Restricted, secure GET request with DNS rebinding protection, no redirects.
- Tool registry dictionary with schema parameter metadata.

### C. `workflow/validator.py`
- Validates:
  - Non-empty steps with unique step IDs.
  - Step tool must exist in `TOOL_REGISTRY`.
  - Condition branch targets (`if_true`, `if_false`) point to valid future step IDs or `END`.
  - Step arguments match required parameter definitions.
  - Workflows must not exceed maximum safe step count (25 steps).

### D. `workflow/executor.py`
- Context State:
  - Maintains `variables` / `step_outputs` mapped by step ID and variable names.
  - Resolves variable references (e.g., `{{step_1.output}}` or direct step ID references).
- Execution State:
  - Tracks current step pointer.
  - Detects if a step requires human approval. If so, pauses and records `status="pending_approval"`.
  - Evaluates branch conditions and advances pointers accordingly.
  - Protects against infinite loops using a visited counter (max 5 visits per step) and max execution limit (50 ops).
  - Memory-efficient `StepExecutionResult` using `__slots__`.
  - Records step outcome: status (`success`, `failed`, `skipped`, `pending_approval`), execution time, output, and errors.

### E. `workflow/generator.py`
- Calls Google Gemini Flash models via `google-genai` SDK using `GEMINI_API_KEY`.
- Concise, token-efficient system instruction.
- Prompt length capped at 1,500 chars to prevent token waste.
- Robust JSON sanitization: handles raw text, markdown blocks (` ```json ... ``` `), and unexpected formatting.
- Predefined fallback templates for offline / demo mode.

### F. `app.py` (Streamlit UI)
- Title & instructions.
- Gemini API key configuration in sidebar.
- Live API status indicator (Active vs Demo Mode).
- Preset example prompts (Email validation & notification, Order calculation & approval, Data formatting).
- Prompt input and "Generate Workflow" button.
- Two-column view: Visual Step-by-Step Flow and Expandable Raw JSON.
- Validation badge / warnings.
- "Execute Workflow" button.
- Execution logs table and step results.
- Human Approval Interactive dialog (Approve / Reject buttons).

---

## 3. Testing Strategy (`tests/`)
- `tests/test_schema.py`: Test Pydantic model validation on valid and invalid payloads.
- `tests/test_validator.py`: Test rejection of invalid step IDs, cycles, unknown tools, and broken branches.
- `tests/test_executor.py`: Test end-to-end execution of linear flows, conditional branching, tool outputs, failure handling, and approval pausing.
- `tests/test_generator.py`: Test demo fallbacks, JSON sanitization, and empty prompt handling. No external API call required for test suite.
