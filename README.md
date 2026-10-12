# Natural Language Workflow Generator & Executor

A production-grade GenAI and NLP system that converts plain-English business tasks into validated, structured JSON workflow graphs and executes them deterministically using pre-approved Python functions, conditional branching, and human-in-the-loop approvals.

Powered by **Google Gemini API** (`google-genai` SDK) with strict token efficiency and built-in offline Demo Mode.

---

## 1. Project Objective

In real-world automation systems, allowing an LLM to generate and execute raw code (`eval()` / `exec()`) poses critical remote-code-execution risks. This project demonstrates a **safe, deterministic GenAI agent architecture**:

1. Accepts user task instructions in plain, everyday conversational English.
2. Prompts Google Gemini (Flash series) via the official `google-genai` SDK to convert instructions into a structured workflow specification JSON.
3. Defensively parses and validates the generated workflow against strict Pydantic schemas and tool registry whitelists.
4. Renders the workflow visually in a clean Streamlit interface for user inspection prior to execution.
5. Executes the workflow deterministically using pre-approved Python functions only.
6. Supports **conditional branching**, **data transformations**, and **human-in-the-loop approvals** for sensitive operations.
7. Gracefully operates in an offline **Demo Mode** if an API key is not present.

---

## 2. Architecture & Data Flow

```text
User Natural Language Instruction
           │
           ▼
┌──────────────────────────┐
│   workflow/generator.py  │  Calls Google Gemini Flash via official SDK (or fallback demo mode)
└──────────┬───────────────┘
           │ Structured Workflow JSON
           ▼
┌──────────────────────────┐
│   workflow/schema.py     │  Validates models (StepType, ConditionRule, Workflow) via Pydantic V2
└──────────┬───────────────┘
           │ Pydantic Object
           ▼
┌──────────────────────────┐
│   workflow/validator.py  │  Verifies unique IDs, tool registry membership, argument completeness
└──────────┬───────────────┘
           │ Validated Pipeline
           ▼
┌──────────────────────────┐
│         app.py           │  Visual Review & Schema Warnings displayed in Streamlit UI
└──────────┬───────────────┘
           │ User explicitly clicks [Execute Workflow]
           ▼
┌──────────────────────────┐
│   workflow/executor.py   │  Deterministic execution loop with state & context management
└──────────┬───────────────┘
           │ Dispatches approved functions
           ▼
┌──────────────────────────┐
│   workflow/tools.py      │  Runs safe Python tools (validate_email, calculate_total, etc.)
└──────────┬───────────────┘
           │ Pauses on approval; logs each status (Success, Failed, Skipped, Pending)
           ▼
┌──────────────────────────┐
│    Streamlit UI Logs     │  Step-by-step inputs, outputs, execution duration, and results
└──────────────────────────┘
```

---

## 3. Technology Stack

- **Python**: 3.11+ (verified compatible with Python 3.14)
- **Web Interface**: [Streamlit](https://streamlit.io/)
- **LLM SDK**: Official [Google Gen AI SDK](https://github.com/googleapis/python-genai) (`google-genai`)
- **Schema Validation**: [Pydantic v2](https://docs.pydantic.dev/)
- **Configuration**: `python-dotenv`
- **Testing**: `pytest`
- **Networking & Standard Tools**: `requests`, `re`, `json`, `logging`

---

## 4. Prerequisites & Installation

### Prerequisites
- Python 3.11, 3.12, 3.13, or 3.14 installed on your system.

### Installation Steps

1. Clone or open the repository folder:
   ```bash
   cd "natural-language-workflow-generator"
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## 5. API Key Setup

1. Copy `.env.example` to create `.env`:
   ```bash
   cp .env.example .env
   ```
2. Open `.env` and configure your Google Gemini API key:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   ```
   *(Get a free API key from [Google AI Studio](https://aistudio.google.com/)).*

> **Note on Demo Mode:** If you do not have an API key or wish to test completely offline, the application works fully in **Demo / Offline Mode** using built-in deterministic templates. You can also toggle Demo Mode anytime via the sidebar checkbox.

---

## 6. How to Start the Application

Launch the Streamlit web server:
```bash
streamlit run app.py
```

Then open your browser to `http://localhost:8501`.

---

## 7. Example Instructions & Usage

### Example 1: Email Validation and Notification
- **Prompt:**
  ```text
  Check whether an email address is valid. Convert the customer's name to uppercase. If the email is invalid, display an error message. If it is valid, create a notification.
  ```
- **What happens:**
  1. Validates `customer@example.com` using `validate_email`.
  2. Converts name `john doe` to `JOHN DOE` using `uppercase_text`.
  3. Evaluates condition: since email is valid, branches to `step_4` and skips `step_5`.
  4. Generates a welcome notification for `JOHN DOE`.

### Example 2: High-Value Order with Human Approval
- **Prompt:**
  ```text
  Calculate total for prices [45.5, 20.0, 35.0]. If total > 80, require human approval to proceed, then create a notification to finance.
  ```
- **What happens:**
  1. Calculates sum using `calculate_total` ($100.50).
  2. Evaluates condition ($100.50 > 80 ➔ True).
  3. Pauses execution on `step_3` with status **PENDING APPROVAL**.
  4. Streamlit displays interactive **Approve** and **Reject** buttons.
  5. Clicking **Approve** completes the step and notifies finance; clicking **Reject** safely cancels the workflow.

### Example 3: Customer Data Normalization
- **Prompt:**
  ```text
  Trim extra whitespace from customer name '   alice in wonderland   '. Convert it to uppercase, and notify CRM system.
  ```

---

## 8. Supported Tools & Security Safeguards

| Tool Name | Purpose | Limitations & Security Constraints |
|---|---|---|
| `validate_email` | Validates email syntax using RFC 5322 regex | Syntactic check only; does not ping remote mail server. Length capped at 320 chars. |
| `uppercase_text` | Transforms text to uppercase | Standard string manipulation. Input capped at 50,000 chars. |
| `transform_data` | Safe text transformations (trim, lower, title, reverse, word_count) | Strictly whitelisted actions; rejects arbitrary code. Input capped at 50,000 chars. |
| `calculate_total`| Sums lists of numbers | Validates all elements are numeric. List capped at 500 items. |
| `check_condition`| Evaluates comparisons (`==`, `!=`, `>`, `<`, `>=`, `<=`, `contains`, `is_valid`, `is_empty`) | Strict operator whitelist; no `eval()`. Type-aware comparison. |
| `create_notification` | Formats and emits notification messages | Simulated in-app notification (`delivered: False`). Message capped at 2,000 chars. |
| `http_get` | Secure HTTP GET requests | Enforces timeout, 10KB response limit, blocks localhost, private IPs (10.x, 192.168.x, 172.16.x), cloud metadata endpoints, DNS rebinding protection, and disables redirects. |

---

## 9. Running Automated Tests

Run the full automated test suite (does not require an internet connection or live API key):

```bash
python -m pytest tests/ -v
```

### Test Coverage Summary (30 Tests Passing):
- `test_executor.py` (12 tests):
  - Linear execution & parameter resolution
  - Missing and null required input rejection
  - Resolution of `{{input.<field>}}` placeholders
  - Resolution of previous step outputs (`{{step_1.output.result}}`)
  - Distinguishing business outcomes from tool execution status
  - True and false conditional branching with correct branch skipping
  - Rejection of unresolved or nonexistent placeholders
  - Simulated notification guarantees (`delivered: False`)
  - Failure propagation and workflow termination on step errors
  - Human approval pausing, resume without re-running prior steps, and rejection cancellation
- `test_validator.py` (8 tests):
  - Semantic validation & unknown tool rejection
  - Missing required tool argument checks
  - Extraction of dynamic input placeholders
  - Prevention of forward references
  - Prevention of self-loops and broken branch targets
- `test_schema.py` (6 tests):
  - Pydantic schema validation, empty step rejection, duplicate ID rejection, operator constraints
- `test_generator.py` (4 tests):
  - Fallback demo modes, defensive markdown codeblock stripping, empty prompt validation

---

## 10. Backend Architecture & Security Hardening

1. **Zero Arbitrary Code Execution**: Never runs `eval()`, `exec()`, or subshells on LLM output. All actions map to pre-vetted Python functions.
2. **DNS Rebinding & SSRF Protection**: `http_get` resolves hostnames to IP addresses before initiating connections, rejecting any destination in loopback, RFC 1918 private subnets, link-local, or cloud metadata ranges.
3. **Memory & Payload Guardrails**: Enforces input size caps across strings, numbers, lists, and notifications to prevent resource exhaustion attacks.
4. **Fast Memory Footprint**: `StepExecutionResult` utilizes `__slots__` for minimal allocation overhead during multi-step runs.
5. **Strict Placeholder Pre-flight**: Null inputs and missing variables are caught prior to execution, preventing halfway failures.
6. **Cycle & Infinite Loop Protection**: Per-step visit limit (max 5 visits) and global execution cap (max 50 operations) prevent runaway workflows.
7. **Human-in-the-Loop State Machine**: Preserves full execution state during approval pauses and resumes cleanly without replaying earlier steps.
