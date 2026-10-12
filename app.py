"""Natural Language Workflow Generator & Executor — Streamlit Chat UI.

Professional chatbot-themed interface that converts plain-English business
tasks into visual flowcharts, validates inputs, and executes them with full
audit logging and confirmation popups.
"""

import re
import streamlit as st
from dotenv import load_dotenv

from workflow.generator import WorkflowGenerator
from workflow.validator import WorkflowValidator
from workflow.executor import WorkflowExecutor
from workflow.tools import TOOL_REGISTRY, validate_email as _quick_validate_email

# ── Page Config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Workflow Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

load_dotenv(override=True)


# ── State Initialization ─────────────────────────────────────────────────────
def _init_session_state():
    defaults = {
        "theme": "dark",
        "messages": [],
        "workflow_data": None,
        "workflow_obj": None,
        "validation_status": {"valid": False, "errors": [], "warnings": []},
        "workflow_inputs": {"email": "customer@example.com", "customer_name": "John Doe"},
        "executor": None,
        "execution_result": None,
        "phase": "idle",                   # idle | generated | executed
        "_show_dialog": None,              # "valid" | "invalid" | None
        "_exec_inputs": {},
        "_invalid_reason": "",
        "_exec_confirmed": False,
        "_prev_radio": "✅ Valid Customer (Normal Flow)",
        "task_prompt_val": (
            "Check whether an email address is valid. Convert the customer's name to uppercase. "
            "If the email is invalid, display an error message. If it is valid, create a notification."
        ),
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init_session_state()


# ── HTML Helper: Clean leading/trailing spaces on lines ──────────────────────
def _clean_html(raw_html: str) -> str:
    """Strip leading & trailing whitespace on each line.

    Prevents Markdown parsers from ever interpreting indented HTML tags
    as code blocks (<pre><code>).
    """
    lines = [line.strip() for line in raw_html.strip().split("\n")]
    return "".join(lines)


# ── CSS Theming (Dark & Light) ───────────────────────────────────────────────
def _get_css(theme: str) -> str:
    if theme == "light":
        return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg-primary: #f5f6fb;
    --bg-secondary: #ffffff;
    --bg-card: #ffffff;
    --bg-glass: rgba(0, 0, 0, 0.02);
    --border-color: rgba(0, 0, 0, 0.09);
    --accent: #5846e0;
    --accent-glow: rgba(88, 70, 224, 0.16);
    --success: #009975;
    --danger: #dc3545;
    --warning: #d97706;
    --text-primary: #191c28;
    --text-secondary: #4a4f63;
    --text-muted: #7d8296;
    --code-bg: rgba(88, 70, 224, 0.08);
    --radius: 14px;
    --radius-sm: 10px;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    font-family: 'Inter', sans-serif !important;
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border-color) !important;
}

footer { display: none !important; }

/* Animations */
@keyframes fadeSlideUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 0 0 var(--accent-glow); }
    50%      { box-shadow: 0 0 16px 3px var(--accent-glow); }
}

.chat-msg { animation: fadeSlideUp 0.3s ease-out both; }

/* Chat Container */
.chat-wrap {
    max-width: 880px;
    margin: 0 auto;
    padding: 0.5rem 0 1.5rem;
}

/* Chat Bubbles */
.bubble {
    padding: 1.05rem 1.3rem;
    border-radius: var(--radius);
    line-height: 1.6;
    font-size: 0.92rem;
    word-break: break-word;
}
.bubble-ai {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    box-shadow: 0 3px 12px rgba(0, 0, 0, 0.04);
    margin-right: 2rem;
    color: var(--text-primary);
}
.bubble-user {
    background: linear-gradient(135deg, #5846e0 0%, #8e44ad 100%);
    color: #ffffff;
    margin-left: 2rem;
    text-align: right;
    box-shadow: 0 4px 15px rgba(88, 70, 224, 0.25);
}

.sender {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.sender-ai  { color: var(--accent); }
.sender-you { color: var(--text-muted); text-align: right; }

/* Flowchart Nodes */
.flow-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    margin: 1.2rem 0;
}
.flow-node {
    width: 100%;
    max-width: 540px;
    border-radius: var(--radius-sm);
    padding: 0.9rem 1.1rem;
    position: relative;
    border: 1px solid var(--border-color);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}
.flow-tool {
    background: #fbfbfe;
    border-left: 4px solid var(--accent);
}
.flow-condition {
    background: #fffdfa;
    border-left: 4px solid var(--warning);
}
.flow-approval {
    background: #fff9f9;
    border-left: 4px solid var(--danger);
}
.flow-node-title {
    font-weight: 600;
    font-size: 0.86rem;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-primary);
}
.flow-node-desc {
    font-size: 0.82rem;
    color: var(--text-secondary);
}
.flow-node-tag {
    display: inline-block;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 700;
}
.tag-tool       { background: rgba(88, 70, 224, 0.12); color: #5846e0; }
.tag-condition  { background: rgba(217, 119, 6, 0.12); color: #b45309; }
.tag-approval   { background: rgba(220, 53, 69, 0.12); color: #dc3545; }

.flow-connector {
    width: 2px;
    height: 22px;
    background: linear-gradient(180deg, var(--accent), transparent);
    position: relative;
}
.flow-connector::after {
    content: '';
    position: absolute;
    bottom: -3px;
    left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid var(--accent);
}

.branch-row {
    display: flex;
    justify-content: flex-start;
    gap: 1.2rem;
    margin-top: 6px;
    font-size: 0.78rem;
    font-weight: 500;
}
.branch-true  { color: var(--success); }
.branch-false { color: var(--danger); }

/* Execution Result Cards */
.exec-card {
    border-radius: var(--radius-sm);
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
    border: 1px solid var(--border-color);
    background: var(--bg-card);
}
.exec-success { border-left: 4px solid var(--success); background: #f6fcf9; }
.exec-failed  { border-left: 4px solid var(--danger);  background: #fdf6f6; }
.exec-skipped { border-left: 4px solid var(--text-muted); background: #fbfbfd; }

.exec-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
}
.exec-step-name { font-weight: 600; font-size: 0.84rem; color: var(--text-primary); }
.exec-badge {
    font-size: 0.65rem;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 700;
    text-transform: uppercase;
}
.badge-success { background: rgba(0, 153, 117, 0.15); color: #008764; }
.badge-failed  { background: rgba(220, 53, 69, 0.15); color: #c82333; }
.badge-skipped { background: rgba(125, 130, 150, 0.15); color: #61667b; }
.badge-pending { background: rgba(217, 119, 6, 0.15); color: #b45309; }

.exec-outcome { font-size: 0.81rem; color: var(--text-secondary); margin-top: 2px; }
.exec-time    { font-size: 0.7rem; color: var(--text-muted); }

/* Summary card */
.summary-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 1.1rem 1.4rem;
    margin: 0.8rem 0;
    box-shadow: 0 2px 10px rgba(0,0,0,0.03);
}
.summary-title { font-weight: 700; font-size: 1.05rem; color: var(--text-primary); margin-bottom: 0.2rem; }
.summary-desc  { font-size: 0.84rem; color: var(--text-secondary); }

/* Status dot */
.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
}
.dot-green { background: var(--success); }
.dot-red   { background: var(--danger); }

/* Input Label */
.input-label {
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-primary);
    margin-bottom: 6px;
}

/* Streamlit Widget Overrides */
.stTextArea textarea, .stTextInput input {
    background: #ffffff !important;
    border: 1px solid rgba(0, 0, 0, 0.15) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px var(--accent-glow) !important;
}

div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #5846e0, #8e44ad) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.4rem !important;
    box-shadow: 0 4px 12px rgba(88, 70, 224, 0.25) !important;
}
div.stButton > button:not([kind="primary"]) {
    background: #ffffff !important;
    color: var(--text-primary) !important;
    border: 1px solid rgba(0, 0, 0, 0.14) !important;
    border-radius: var(--radius-sm) !important;
}

code {
    background: var(--code-bg) !important;
    color: var(--accent) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}

/* Modal styling */
div[data-testid="stModal"] > div {
    background: #ffffff !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.12) !important;
}
</style>
"""
    else:  # Dark theme
        return """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg-primary: #0f0f13;
    --bg-secondary: #16161d;
    --bg-card: rgba(26, 26, 35, 0.88);
    --bg-glass: rgba(255, 255, 255, 0.04);
    --border-color: rgba(255, 255, 255, 0.08);
    --accent: #6c5ce7;
    --accent-glow: rgba(108, 92, 231, 0.25);
    --success: #00b894;
    --danger: #ff6b6b;
    --warning: #fdcb6e;
    --text-primary: #e8e8ed;
    --text-secondary: #9a9aaf;
    --text-muted: #6b6b80;
    --code-bg: rgba(108, 92, 231, 0.15);
    --radius: 14px;
    --radius-sm: 10px;
}

html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    font-family: 'Inter', sans-serif !important;
    background: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}

[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] {
    background: var(--bg-secondary) !important;
    border-right: 1px solid var(--border-color) !important;
}

footer { display: none !important; }

/* Animations */
@keyframes fadeSlideUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
@keyframes pulseGlow {
    0%, 100% { box-shadow: 0 0 0 0 var(--accent-glow); }
    50%      { box-shadow: 0 0 16px 4px var(--accent-glow); }
}

.chat-msg { animation: fadeSlideUp 0.3s ease-out both; }

/* Chat Container */
.chat-wrap {
    max-width: 880px;
    margin: 0 auto;
    padding: 0.5rem 0 1.5rem;
}

/* Chat Bubbles */
.bubble {
    padding: 1.05rem 1.3rem;
    border-radius: var(--radius);
    line-height: 1.6;
    font-size: 0.92rem;
    word-break: break-word;
}
.bubble-ai {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    backdrop-filter: blur(12px);
    margin-right: 2rem;
    color: var(--text-primary);
}
.bubble-user {
    background: linear-gradient(135deg, #6c5ce7 0%, #a363d9 100%);
    color: #ffffff;
    margin-left: 2rem;
    text-align: right;
    box-shadow: 0 4px 15px rgba(108, 92, 231, 0.3);
}

.sender {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin-bottom: 4px;
}
.sender-ai  { color: var(--accent); }
.sender-you { color: rgba(255, 255, 255, 0.7); text-align: right; }

/* Flowchart Nodes */
.flow-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0;
    margin: 1.2rem 0;
}
.flow-node {
    width: 100%;
    max-width: 540px;
    border-radius: var(--radius-sm);
    padding: 0.9rem 1.1rem;
    position: relative;
    border: 1px solid var(--border-color);
}
.flow-tool {
    background: linear-gradient(135deg, rgba(108, 92, 231, 0.12), rgba(108, 92, 231, 0.03));
    border-left: 4px solid var(--accent);
}
.flow-condition {
    background: linear-gradient(135deg, rgba(253, 203, 110, 0.12), rgba(253, 203, 110, 0.03));
    border-left: 4px solid var(--warning);
}
.flow-approval {
    background: linear-gradient(135deg, rgba(255, 107, 107, 0.12), rgba(255, 107, 107, 0.03));
    border-left: 4px solid var(--danger);
}
.flow-node-title {
    font-weight: 600;
    font-size: 0.86rem;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--text-primary);
}
.flow-node-desc {
    font-size: 0.82rem;
    color: var(--text-secondary);
}
.flow-node-tag {
    display: inline-block;
    font-size: 0.62rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding: 2px 7px;
    border-radius: 4px;
    font-weight: 700;
}
.tag-tool       { background: rgba(108, 92, 231, 0.2); color: #a29bfe; }
.tag-condition  { background: rgba(253, 203, 110, 0.2); color: #ffeaa7; }
.tag-approval   { background: rgba(255, 107, 107, 0.2); color: #fab1a0; }

.flow-connector {
    width: 2px;
    height: 22px;
    background: linear-gradient(180deg, var(--accent), transparent);
    position: relative;
}
.flow-connector::after {
    content: '';
    position: absolute;
    bottom: -3px;
    left: 50%;
    transform: translateX(-50%);
    width: 0; height: 0;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid var(--accent);
}

.branch-row {
    display: flex;
    justify-content: flex-start;
    gap: 1.2rem;
    margin-top: 6px;
    font-size: 0.78rem;
    font-weight: 500;
}
.branch-true  { color: var(--success); }
.branch-false { color: var(--danger); }

/* Execution Result Cards */
.exec-card {
    border-radius: var(--radius-sm);
    padding: 0.8rem 1rem;
    margin-bottom: 0.6rem;
    border: 1px solid var(--border-color);
}
.exec-success { background: rgba(0, 184, 148, 0.08); border-left: 4px solid var(--success); }
.exec-failed  { background: rgba(255, 107, 107, 0.08); border-left: 4px solid var(--danger); }
.exec-skipped { background: var(--bg-glass); border-left: 4px solid var(--text-muted); }

.exec-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
}
.exec-step-name { font-weight: 600; font-size: 0.84rem; color: var(--text-primary); }
.exec-badge {
    font-size: 0.65rem;
    padding: 2px 8px;
    border-radius: 4px;
    font-weight: 700;
    text-transform: uppercase;
}
.badge-success { background: rgba(0, 184, 148, 0.22); color: #55efc4; }
.badge-failed  { background: rgba(255, 107, 107, 0.22); color: #ff6b6b; }
.badge-skipped { background: rgba(107, 107, 128, 0.22); color: #9a9aaf; }
.badge-pending { background: rgba(253, 203, 110, 0.22); color: #fdcb6e; }

.exec-outcome { font-size: 0.81rem; color: var(--text-secondary); margin-top: 2px; }
.exec-time    { font-size: 0.7rem; color: var(--text-muted); }

/* Summary card */
.summary-card {
    background: var(--bg-card);
    border: 1px solid var(--border-color);
    border-radius: var(--radius);
    padding: 1.1rem 1.4rem;
    margin: 0.8rem 0;
    backdrop-filter: blur(12px);
}
.summary-title { font-weight: 700; font-size: 1.05rem; color: var(--text-primary); margin-bottom: 0.2rem; }
.summary-desc  { font-size: 0.84rem; color: var(--text-secondary); }

/* Status dot */
.status-dot {
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-right: 6px;
    animation: pulseGlow 2s ease-in-out infinite;
}
.dot-green { background: var(--success); --accent-glow: rgba(0, 184, 148, 0.3); }
.dot-red   { background: var(--danger);  --accent-glow: rgba(255, 107, 107, 0.3); }

/* Input label */
.input-label {
    font-size: 0.82rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--text-primary);
    margin-bottom: 6px;
}

/* Streamlit widget overrides */
.stTextArea textarea, .stTextInput input {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
    color: var(--text-primary) !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 2px var(--accent-glow) !important;
}

div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #6c5ce7, #a363d9) !important;
    color: #ffffff !important;
    border: none !important;
    border-radius: var(--radius-sm) !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.4rem !important;
}
div.stButton > button:not([kind="primary"]) {
    background: var(--bg-glass) !important;
    color: var(--text-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius-sm) !important;
}

code {
    background: var(--code-bg) !important;
    color: #a29bfe !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
}

/* Modal styling */
div[data-testid="stModal"] > div {
    background: var(--bg-secondary) !important;
    border: 1px solid var(--border-color) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
}
</style>
"""

st.html(_get_css(st.session_state.theme))


# ── State Reset Helper ───────────────────────────────────────────────────────
def _reset_all(new_prompt: str = None):
    for k in ("workflow_data", "workflow_obj", "executor", "execution_result"):
        st.session_state[k] = None
    st.session_state.messages = []
    st.session_state.validation_status = {"valid": False, "errors": [], "warnings": []}
    st.session_state.workflow_inputs = {"email": "customer@example.com", "customer_name": "John Doe"}
    st.session_state.phase = "idle"
    st.session_state._show_dialog = None
    st.session_state._exec_inputs = {}
    st.session_state._exec_confirmed = False
    st.session_state._prev_radio = "✅ Valid Customer (Normal Flow)"
    for wk in ("input_email", "input_name"):
        st.session_state.pop(wk, None)
    if new_prompt:
        st.session_state.task_prompt_val = new_prompt


# ── Dialogs: Executable Confirmation & Invalid Warning ───────────────────────
@st.dialog("⚡ Confirm Workflow Execution")
def _show_valid_popup():
    inputs = st.session_state.get("_exec_inputs", {})
    email = inputs.get("email", "")
    name = inputs.get("customer_name", "")

    st.markdown("""
    <div style="text-align:center; padding: 0.5rem 0 1rem;">
        <div style="font-size:2.8rem; line-height:1;">✅</div>
        <div style="font-size:1.15rem; font-weight:700; margin-top:0.4rem;">
            Test Data Validated
        </div>
        <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">
            Input parameters satisfy all syntax and schema prerequisites
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"**Customer Email:** `{email}`")
    st.markdown(f"**Customer Name:** `{name}`")
    st.info("The workflow will now execute deterministically across all steps.")

    col_go, col_close = st.columns(2)
    with col_go:
        if st.button("▶️ Execute Now", type="primary", use_container_width=True, key="dlg_confirm_go"):
            st.session_state._exec_confirmed = True
            st.session_state._show_dialog = None
            st.rerun()
    with col_close:
        if st.button("Cancel", use_container_width=True, key="dlg_confirm_cancel"):
            st.session_state._show_dialog = None
            st.rerun()


@st.dialog("⚠️ Invalid Test Data Detected")
def _show_invalid_popup():
    reason = st.session_state.get("_invalid_reason", "Invalid data format.")
    inputs = st.session_state.get("_exec_inputs", {})
    email = inputs.get("email", "")

    st.markdown("""
    <div style="text-align:center; padding: 0.5rem 0 1rem;">
        <div style="font-size:2.8rem; line-height:1;">❌</div>
        <div style="font-size:1.15rem; font-weight:700; margin-top:0.4rem;">
            Validation Failed
        </div>
        <div style="font-size:0.82rem; color:var(--text-secondary); margin-top:2px;">
            The provided test data contains syntax errors
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.error(f"**Email Input:** `{email}`")
    st.warning(f"**Diagnosis:** {reason}")
    st.caption("You can either correct the test data or execute anyway to test how the workflow handles errors.")

    col_fix, col_force = st.columns(2)
    with col_fix:
        if st.button("✏️ Fix Test Data", type="primary", use_container_width=True, key="dlg_invalid_fix"):
            st.session_state._show_dialog = None
            st.rerun()
    with col_force:
        if st.button("▶️ Test Error Flow Anyway", use_container_width=True, key="dlg_invalid_force"):
            st.session_state._exec_confirmed = True
            st.session_state._show_dialog = None
            st.rerun()


# ── Flowchart Generator ──────────────────────────────────────────────────────
def _build_flowchart(steps: list) -> str:
    nodes = []
    for idx, step in enumerate(steps):
        s_type = step.get("type", "tool").lower()
        s_desc = step.get("description", "")
        s_tool = step.get("tool", "")

        node_cls = {"tool": "flow-tool", "condition": "flow-condition",
                     "approval": "flow-approval"}.get(s_type, "flow-tool")
        tag_cls  = {"tool": "tag-tool", "condition": "tag-condition",
                     "approval": "tag-approval"}.get(s_type, "tag-tool")
        icon     = {"tool": "⚙️", "condition": "🔀", "approval": "🛡️"}.get(s_type, "⚙️")

        title_extra = f" — <code>{s_tool}</code>" if s_tool and s_type == "tool" else ""

        branch_html = ""
        if s_type == "condition":
            if_true = step.get("if_true", "—")
            if_false = step.get("if_false", "—")
            branch_html = (
                f'<div class="branch-row">'
                f'<span class="branch-true">✓ True → {if_true}</span>'
                f'<span class="branch-false">✗ False → {if_false}</span>'
                f'</div>'
            )

        node_html = (
            f'<div class="flow-node {node_cls}" style="animation-delay:{idx*0.06}s;">'
            f'<div class="flow-node-title">'
            f'{icon} Step {idx+1}{title_extra}'
            f'<span class="flow-node-tag {tag_cls}">{s_type.upper()}</span>'
            f'</div>'
            f'<div class="flow-node-desc">{s_desc}</div>'
            f'{branch_html}'
            f'</div>'
        )
        nodes.append(node_html)

    connector = '<div class="flow-connector"></div>'
    return '<div class="flow-container">' + connector.join(nodes) + '</div>'


# ── Execution Result Cards Generator ─────────────────────────────────────────
def _build_exec_results(logs: list) -> str:
    cards = []
    for log in logs:
        status = log.get("status", "")
        step_id = log.get("step_id", "")
        step_type = log.get("step_type", "").upper()
        tool = log.get("tool", "")
        outcome = log.get("business_outcome", "")
        duration = log.get("duration_ms", 0)

        if status == "success":
            card_cls, badge_cls, badge_txt = "exec-success", "badge-success", "✓ Success"
        elif status == "failed":
            card_cls, badge_cls, badge_txt = "exec-failed", "badge-failed", "✗ Failed"
        elif status == "skipped":
            card_cls, badge_cls, badge_txt = "exec-skipped", "badge-skipped", "— Skipped"
        elif status == "pending_approval":
            card_cls, badge_cls, badge_txt = "exec-skipped", "badge-pending", "⏸ Pending"
        else:
            card_cls, badge_cls, badge_txt = "exec-skipped", "badge-skipped", status

        tool_label = f"<code>{tool}</code> · " if tool else ""
        card = (
            f'<div class="exec-card {card_cls}">'
            f'<div class="exec-header">'
            f'<span class="exec-step-name">{step_id} <span style="color:var(--text-muted);">({step_type})</span></span>'
            f'<span class="exec-badge {badge_cls}">{badge_txt}</span>'
            f'</div>'
            f'<div class="exec-outcome">{tool_label}{outcome}</div>'
            f'<div class="exec-time">{duration:.1f} ms</div>'
            f'</div>'
        )
        cards.append(card)
    return "".join(cards)


# ═════════════════════════════════════════════════════════════════════════════
#                              LEFT PANEL
# ═════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="padding: 0.4rem 0 0.8rem;">
        <div style="font-size:1.25rem; font-weight:700; letter-spacing:-0.01em;">
            ⚡ Workflow Capabilities
        </div>
        <div style="font-size:0.78rem; color:var(--text-secondary); margin-top:2px;">
            Supported automated business tasks
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Status pill
    st.markdown("""
    <div style="display:inline-flex; align-items:center; background:rgba(0,184,148,0.12); padding:3px 10px; border-radius:20px; margin-bottom:1rem;">
        <span class="status-dot dot-green" style="margin-right:6px;"></span>
        <span style="font-size:0.74rem; font-weight:600; color:var(--success);">Engine Ready · Deterministic Safe</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("#### 📋 Active Automation Workflow")

    # Dedicated Task: Email Verification & Onboarding
    st.markdown("""
    <div style="background:var(--bg-card); border:1px solid var(--border-color); border-radius:var(--radius-sm); padding:1rem; margin-bottom:1rem;">
        <div style="font-weight:700; font-size:0.92rem; color:var(--accent); margin-bottom:6px;">
            📧 Email Verification & Onboarding
        </div>
        <div style="font-size:0.8rem; color:var(--text-secondary); line-height:1.5;">
            Automated customer registration pipeline that performs:
            <ul style="padding-left:1.15rem; margin-top:6px; margin-bottom:6px;">
                <li><strong>RFC 5322 Syntax Validation:</strong> Regex verification of email format.</li>
                <li><strong>Name Normalization:</strong> Uppercase customer name transformation.</li>
                <li><strong>Conditional Branching:</strong> Dual routes based on validation outcome.</li>
                <li><strong>Success Notification:</strong> Personalized welcome message for verified users.</li>
                <li><strong>Error Notification:</strong> Administrative alert when invalid email is detected.</li>
            </ul>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("⚡ Reload Workflow Template", key="btn_task_email", use_container_width=True):
        _reset_all(
            "Check whether an email address is valid. Convert the customer's name to uppercase. "
            "If the email is invalid, display an error message. If it is valid, create a notification."
        )
        st.rerun()

    st.markdown("---")
    st.markdown("#### 🛠️ Workflow Tools Registry")

    tool_info = {
        "validate_email": ("📧", "RFC 5322 regex syntax validator"),
        "uppercase_text": ("🔠", "Customer name uppercase transformer"),
        "check_condition": ("🔀", "Branching condition engine (is_valid)"),
        "create_notification": ("🔔", "Simulated welcome & error alert dispatcher"),
    }
    for name, (icon, desc) in tool_info.items():
        st.markdown(f"""
        <div style="padding:5px 0; border-bottom:1px solid var(--border-color);">
            <span style="font-size:0.82rem; font-weight:600;">{icon} <code>{name}</code></span><br>
            <span style="font-size:0.72rem; color:var(--text-muted);">{desc}</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("""
    <div style="font-size:0.7rem; color:var(--text-muted); line-height:1.5;">
        🔒 <strong>Security Guarantee:</strong> Arbitrary code execution (eval/exec) is strictly forbidden.
        All workflows map to audited, safe Python functions.
    </div>
    """, unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
#                              MAIN VIEW
# ═════════════════════════════════════════════════════════════════════════════

# ── Top Bar: Title on Left, Dark/Light Theme on Top Right ────────────────────
col_title, col_theme_btn = st.columns([7.5, 2.5])

with col_title:
    st.markdown("""
    <div style="display:flex; align-items:center; gap:12px; padding: 0.5rem 0;">
        <span style="font-size:2.2rem; line-height:1;">⚡</span>
        <div>
            <div style="font-size:1.75rem; font-weight:700; letter-spacing:-0.02em; line-height:1.2;">
                AI Workflow Assistant
            </div>
            <div style="font-size:0.84rem; color:var(--text-secondary); margin-top:2px;">
                Natural Language Workflow Generation, Interactive Flowchart & Audited Execution
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_theme_btn:
    st.markdown('<div style="padding-top:0.6rem; text-align:right;">', unsafe_allow_html=True)
    if st.session_state.theme == "dark":
        if st.button("☀️ Light Mode", key="theme_toggle", use_container_width=True):
            st.session_state.theme = "light"
            st.rerun()
    else:
        if st.button("🌙 Dark Mode", key="theme_toggle", use_container_width=True):
            st.session_state.theme = "dark"
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("---")


# ── Handle Confirmed Execution (from Dialog) ─────────────────────────────────
if st.session_state._exec_confirmed:
    st.session_state._exec_confirmed = False
    collected = st.session_state._exec_inputs
    executor = WorkflowExecutor(st.session_state.workflow_obj, inputs=collected)
    st.session_state.executor = executor
    with st.spinner("⚡ Running workflow…"):
        res = executor.execute()
        st.session_state.execution_result = res
    st.session_state.phase = "executed"
    st.rerun()


# ── Render Dialogs if Flagged ────────────────────────────────────────────────
if st.session_state._show_dialog == "valid":
    _show_valid_popup()
elif st.session_state._show_dialog == "invalid":
    _show_invalid_popup()


# ── Chatbot Feed: Flowchart & Results ────────────────────────────────────────
chat_html_parts = []

# Assistant Greeting
chat_html_parts.append(
    '<div class="chat-msg" style="margin-bottom:1rem;">'
    '<div class="sender sender-ai">⚡ Workflow Assistant</div>'
    '<div class="bubble bubble-ai">'
    '👋 Hello! I am your <strong>Workflow Assistant</strong>. '
    'Describe any business task in natural language — I will convert it into a '
    'structured, validated flowchart and provide you with an executable task.<br><br>'
    '<span style="color:var(--text-muted); font-size:0.78rem;">'
    '💡 <em>Tip: Pick an example from the left panel or type your own instructions below.</em>'
    '</span>'
    '</div></div>'
)

# Workflow plan bubble (when generated)
if st.session_state.workflow_data and st.session_state.phase in ("generated", "executed"):
    wf = st.session_state.workflow_data
    val = st.session_state.validation_status

    # User message
    if st.session_state.messages:
        user_msg = st.session_state.messages[-1]
        chat_html_parts.append(
            f'<div class="chat-msg" style="margin-bottom:1rem;">'
            f'<div class="sender sender-you">You</div>'
            f'<div class="bubble bubble-user">{user_msg}</div>'
            f'</div>'
        )

    # Validation summary badge
    if val["valid"]:
        valid_html = '<span class="status-dot dot-green"></span> Workflow verified and schema-valid'
    else:
        valid_html = '<span class="status-dot dot-red"></span> Workflow validation issues found:'
        for err in val.get("errors", []):
            valid_html += f'<br><span style="color:var(--danger);font-size:0.8rem;">• {err}</span>'

    summary_html = (
        f'<div class="summary-card">'
        f'<div class="summary-title">{wf.get("name", "Generated Workflow")}</div>'
        f'<div class="summary-desc">{wf.get("description", "")}</div>'
        f'<div style="margin-top:8px; font-size:0.8rem;">{valid_html}</div>'
        f'</div>'
    )

    flow_html = _build_flowchart(wf.get("steps", []))
    source_label = val.get("source", "engine")
    step_count = len(wf.get("steps", []))

    chat_html_parts.append(
        f'<div class="chat-msg" style="margin-bottom:1rem;">'
        f'<div class="sender sender-ai">⚡ Workflow Assistant</div>'
        f'<div class="bubble bubble-ai">'
        f'I analyzed your requirement and built a <strong>{step_count}-step execution pipeline</strong>. '
        f'Here is the visual flowchart:'
        f'{summary_html}'
        f'{flow_html}'
        f'<span style="font-size:0.72rem; color:var(--text-muted);">Engine Source: {source_label}</span>'
        f'</div></div>'
    )

# Execution results bubble (when executed)
if st.session_state.phase == "executed" and st.session_state.execution_result:
    res = st.session_state.execution_result
    logs = res.get("logs", [])

    if res["status"] == "completed":
        status_html = '<span class="status-dot dot-green"></span> <strong>Execution Completed Successfully</strong>'
    elif res["status"] == "paused_approval":
        status_html = '<span class="status-dot dot-green"></span> <strong>Execution Paused — Awaiting Operator Approval</strong>'
    elif res["status"] == "cancelled":
        status_html = '<span class="status-dot dot-red"></span> <strong>Workflow Cancelled by Operator</strong>'
    else:
        err_msg = res.get("error", "An error occurred during step execution.")
        status_html = f'<span class="status-dot dot-red"></span> <strong>Execution Error:</strong> {err_msg}'

    results_html = _build_exec_results(logs)
    chat_html_parts.append(
        f'<div class="chat-msg" style="margin-bottom:1rem;">'
        f'<div class="sender sender-ai">⚡ Workflow Assistant</div>'
        f'<div class="bubble bubble-ai">'
        f'<div style="margin-bottom:0.7rem;">{status_html}</div>'
        f'<div style="font-size:0.8rem; font-weight:600; color:var(--text-secondary); margin-bottom:0.8rem;">'
        f'Audit Trail & Step Results:'
        f'</div>'
        f'{results_html}'
        f'</div></div>'
    )

# Render full chat conversation cleanly using st.html (zero markdown indentation bug!)
full_chat = '<div class="chat-wrap">' + "".join(chat_html_parts) + '</div>'
st.html(_clean_html(full_chat))

st.markdown("---")


# ═════════════════════════════════════════════════════════════════════════════
#                           INTERACTIVE CONTROLS
# ═════════════════════════════════════════════════════════════════════════════

# ── PHASE: IDLE — Task input ─────────────────────────────────────────────────
if st.session_state.phase == "idle":
    st.markdown('<div class="input-label">💬 Describe what you want to automate</div>', unsafe_allow_html=True)

    user_task = st.text_area(
        "Task Description",
        value=st.session_state.task_prompt_val,
        height=85,
        key="task_input_area",
        label_visibility="collapsed",
        placeholder="e.g. Check whether an email is valid. Convert customer name to uppercase..."
    )

    col_gen, _ = st.columns([2, 8])
    with col_gen:
        generate_btn = st.button("⚡ Generate Workflow", type="primary", use_container_width=True)

    if generate_btn:
        if not user_task.strip():
            st.error("Please provide a task description first.")
        else:
            st.session_state.messages = [user_task.strip()]
            with st.spinner("🧠 Synthesizing workflow steps…"):
                generator = WorkflowGenerator()
                gen_result = generator.generate_workflow(user_task)

            if not gen_result["success"]:
                st.error(f"Generation error: {gen_result['error']}")
            else:
                raw_json = gen_result["workflow_data"]
                st.session_state.workflow_data = raw_json

                is_valid, errors, warnings, wf_obj = WorkflowValidator.validate_raw(raw_json)
                st.session_state.validation_status = {
                    "valid": is_valid,
                    "errors": errors,
                    "warnings": warnings,
                    "source": gen_result["source"]
                }
                st.session_state.workflow_obj = wf_obj
                st.session_state.executor = None
                st.session_state.execution_result = None

                if wf_obj:
                    required_inputs = WorkflowValidator.extract_input_placeholders(wf_obj)
                    defaults = {"email": "customer@example.com", "customer_name": "John Doe"}
                    st.session_state.workflow_inputs = {
                        inp: defaults.get(inp, "test_value") for inp in required_inputs
                    }

                st.session_state.phase = "generated"
                for wk in ("input_email", "input_name"):
                    st.session_state.pop(wk, None)
                st.rerun()


# ── PHASE: GENERATED + VALID — Input Test Data & Execute with Popup ──────────
elif st.session_state.phase == "generated" and st.session_state.validation_status.get("valid") and st.session_state.workflow_obj:

    wf_obj = st.session_state.workflow_obj
    required_inputs = WorkflowValidator.extract_input_placeholders(wf_obj)

    st.markdown('<div class="input-label">📝 Provide test data to execute the workflow</div>', unsafe_allow_html=True)

    # Preset selection
    col_preset, _ = st.columns([5, 5])
    with col_preset:
        test_case = st.radio(
            "Test scenario preset",
            options=["✅ Valid Customer (Normal Flow)", "❌ Invalid Email (Error Flow)"],
            horizontal=True,
            key="test_scenario_radio",
            label_visibility="collapsed",
        )

    # Synchronize preset radio with text boxes
    if st.session_state._prev_radio != test_case:
        st.session_state._prev_radio = test_case
        if "Valid" in test_case:
            st.session_state["input_email"] = "customer@example.com"
            st.session_state["input_name"] = "John Doe"
        else:
            st.session_state["input_email"] = "invalid-email@@bad"
            st.session_state["input_name"] = "Jane Smith"
        st.rerun()

    col_e, col_n = st.columns(2)
    with col_e:
        default_e = "customer@example.com" if "Valid" in test_case else "invalid-email@@bad"
        email_val = st.text_input("Customer Email", value=st.session_state.get("input_email", default_e), key="input_email")
    with col_n:
        default_n = "John Doe" if "Valid" in test_case else "Jane Smith"
        name_val = st.text_input("Customer Name", value=st.session_state.get("input_name", default_n), key="input_name")

    # Build collected inputs map
    collected = {
        "email": email_val,
        "email_address": email_val,
        "customer_email": email_val,
        "customer_name": name_val,
        "name": name_val,
    }
    for k in required_inputs:
        if k not in collected:
            if "email" in k.lower():
                collected[k] = email_val
            elif "name" in k.lower() or "text" in k.lower():
                collected[k] = name_val
            else:
                collected[k] = "sample_value"

    st.markdown("")
    col_run, col_reset, _ = st.columns([2, 1.2, 6.8])
    with col_run:
        run_btn = st.button("▶️ Execute Workflow", type="primary", use_container_width=True)
    with col_reset:
        if st.button("🔄 Reset", use_container_width=True):
            _reset_all()
            st.rerun()

    # When user clicks Execute: validate test data and trigger corresponding dialog popup
    if run_btn:
        st.session_state._exec_inputs = collected

        # Check for empty fields
        empty_fields = []
        if not str(email_val).strip():
            empty_fields.append("Customer Email")
        if not str(name_val).strip():
            empty_fields.append("Customer Name")

        if empty_fields:
            st.session_state._show_dialog = "invalid"
            st.session_state._invalid_reason = f"Required field(s) cannot be empty: {', '.join(empty_fields)}"
            st.rerun()

        # Check email format validity
        email_check = _quick_validate_email(email_val)
        if email_check.get("is_valid", False):
            # VALID -> Ask confirmation popup to execute
            st.session_state._show_dialog = "valid"
            st.rerun()
        else:
            # INVALID -> Pop up as invalid
            st.session_state._show_dialog = "invalid"
            st.session_state._invalid_reason = email_check.get("reason", "RFC 5322 regex validation failed.")
            st.rerun()


# ── PHASE: GENERATED + INVALID — Show retry option ───────────────────────────
elif st.session_state.phase == "generated" and not st.session_state.validation_status.get("valid"):
    st.markdown('<div class="input-label">⚠️ Workflow validation failed</div>', unsafe_allow_html=True)
    st.error("The synthesized workflow failed schema or semantic checks. Try adjusting your description.")

    col_retry, _ = st.columns([2, 8])
    with col_retry:
        if st.button("🔄 Try Another Task", type="primary", use_container_width=True):
            _reset_all()
            st.rerun()


# ── PHASE: EXECUTED — Results, approval handling & new workflow ──────────────
elif st.session_state.phase == "executed":

    # Approval Gate handling
    if (st.session_state.execution_result
            and st.session_state.execution_result.get("status") == "paused_approval"):
        st.markdown('<div class="input-label">🛡️ Human Approval Required to Continue</div>', unsafe_allow_html=True)
        st.warning("This step requires explicit sign-off from an authorized operator before executing.")

        col_app, col_rej, _ = st.columns([1.5, 1.5, 7])
        with col_app:
            if st.button("✅ Approve", type="primary", use_container_width=True):
                executor = st.session_state.executor
                res = executor.handle_approval(approved=True)
                st.session_state.execution_result = res
                st.rerun()
        with col_rej:
            if st.button("❌ Reject", use_container_width=True):
                executor = st.session_state.executor
                res = executor.handle_approval(approved=False)
                st.session_state.execution_result = res
                st.rerun()

    st.markdown("")
    col_new, _ = st.columns([2, 8])
    with col_new:
        if st.button("⚡ Create New Workflow", use_container_width=True):
            _reset_all()
            st.rerun()
