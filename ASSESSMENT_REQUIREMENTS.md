# Assessment Requirements & Traceability Matrix

## Project: Natural Language Workflow Generator
**Assessment Issuer:** Isaii AI — Gen AI Developer - Practical Assessment  
**Time Allocation:** Documentation & Design (1 hour), Project Development (5 hours) | Total: 6 hours  
**Submission Deadline:** 12 October 2026, 5:00 PM  

### Problem Statement
> *"Business users often know what they want to accomplish but do not know how to translate that requirement into a sequence of software operations.*  
> **Problem:** Build a GenAI system that converts natural-language objectives into executable workflows involving APIs, tools, data transformations, validations, and human approval steps.  
> The system should not simply generate a textual response. It should convert the user's requirement into a workflow that the application can understand, validate, and execute."

---

### Core Requirement Traceability Matrix

| Assessment Requirement | Implementation Approach | Source File(s) | Verification & Tests | Status |
|---|---|---|---|---|
| **1. Natural-Language Input** | Text input with preset demonstration templates in Streamlit UI | [app.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/app.py) | Manual UI testing & interactive verification | Completed |
| **2. GenAI Workflow Generation** | Uses Google Gemini (`google-genai` SDK) with token-optimized system prompt, strict schema enforcement, and offline Demo Mode | [generator.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/generator.py) | [test_generator.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/tests/test_generator.py) (4 tests) | Completed |
| **3. Workflow Schema & Validation** | Pydantic V2 models for `Workflow`, `WorkflowStep`, `ConditionRule`, unique ID checks, and parameter contracts | [schema.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/schema.py), [validator.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/validator.py) | [test_schema.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/tests/test_schema.py), [test_validator.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/tests/test_validator.py) (12 tests) | Completed |
| **4. Tools Integration** | Whitelisted Python function registry: `validate_email`, `uppercase_text`, `calculate_total`, `transform_data`, `create_notification` | [tools.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/tools.py) | [test_executor.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/tests/test_executor.py) | Completed |
| **5. APIs Integration** | Secure `http_get` tool with strict SSRF prevention, DNS rebinding guards, redirects disabled, and response size limits | [tools.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/tools.py) | Code inspection & unit checks | Completed |
| **6. Data Transformations** | Whitelisted text/data transforms (`trim`, `lower`, `capitalize`, `title`, `reverse`, `word_count`, `uppercase_text`) | [tools.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/tools.py) | [test_executor.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/tests/test_executor.py) | Completed |
| **7. Validations** | Email regex syntax validation (`validate_email`), numerical input assertions, schema bounds checks, input length caps | [tools.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/tools.py), [validator.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/validator.py) | [test_validator.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/tests/test_validator.py) | Completed |
| **8. Conditional Logic** | Dynamic comparison evaluation (`==`, `!=`, `>`, `<`, `>=`, `<=`, `is_valid`) with `if_true` / `if_false` branching | [executor.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/executor.py) | `test_conditional_branching_true`, `test_conditional_branching_false` | Completed |
| **9. Human Approval Steps** | Workflow execution halts when `requires_approval=True` or step is `approval`. UI provides Approve/Reject buttons | [executor.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/executor.py), [app.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/app.py) | `test_approval_pauses_and_resumes`, `test_approval_rejection_cancels_workflow` | Completed |
| **10. Error Handling & Safety** | Halts on runtime failures, logs step duration and errors. Strictly blocks `eval`, `exec`, or dynamic shell execution. Loop & visit caps enforced. | [executor.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/workflow/executor.py) | `test_tool_failure_halts_workflow` | Completed |
| **11. Web UI Dashboard** | Interactive Streamlit web application with prompt input, workflow viewer, raw JSON explorer, execution logs, and approval controls | [app.py](file:///c:/Users/ARAVIND%20A/OneDrive/Desktop/isaii%20tech/nlp/app.py) | Browser launch verification | Completed |

---

### Unimplemented / Omitted Features
- **Arbitrary Python code execution (`eval` / `exec`):** Explicitly excluded for security. All operations are strictly mapped to predefined Python functions.
- **Complex Orchestration Frameworks (LangChain / LangGraph):** Omitted in favor of a clean, lightweight, understandable custom architecture meeting all assessment criteria without bloat.
