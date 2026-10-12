"""Workflow generator supporting cloud LLM APIs (OpenRouter and Google Gemini).

Converts plain-English requests into structured workflow JSON with token-efficient
prompting, automatic provider detection, and deterministic offline fallbacks.
"""

import os
import json
import re
import logging
from typing import Any, Dict, Optional
import requests
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compact, token-optimized system instruction
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """You are a workflow generator. Convert the user's task description into an executable JSON workflow. Output ONLY valid JSON — no markdown fences, no explanatory text.

Schema:
{
  "name": "Short workflow name",
  "description": "One sentence summary",
  "steps": [
    {
      "id": "step_1",
      "type": "tool" | "condition" | "approval",
      "tool": "tool_name",
      "args": { "param": "value" },
      "condition": { "operator": "==", "left": "{{step_1.output.result}}", "right": "value" },
      "if_true": "step_id" | "END",
      "if_false": "step_id" | "END",
      "requires_approval": false,
      "description": "What this step does"
    }
  ]
}

Approved tools:
- validate_email(email: str)
- uppercase_text(text: str)
- transform_data(data: any, action: "trim" | "lower" | "capitalize" | "title" | "reverse" | "word_count")
- calculate_total(numbers: list[float])
- check_condition(val1: any, operator: "==" | "!=" | ">" | "<" | ">=" | "<=" | "contains" | "is_valid" | "is_empty", val2: any)
- create_notification(recipient: str, message: str, level: "info" | "warning" | "error" | "success")
- http_get(url: str, timeout: int)

Rules:
1. User input fields: {{input.email}} for customer email, {{input.customer_name}} for customer name.
2. Step output keys:
   - validate_email output: {{step_id.output.is_valid}}, {{step_id.output.email}}
   - uppercase_text output: {{step_id.output.result}}
   - transform_data output: {{step_id.output.result}}
   - calculate_total output: {{step_id.output.total}}
3. For condition steps, 'condition' and at least one of 'if_true'/'if_false' are mandatory.
4. For approval steps, set type="approval" or requires_approval=true.
5. Never output arbitrary code or functions outside the approved list.
"""


# ---------------------------------------------------------------------------
# Built-in demo templates (offline fallback / rapid testing)
# ---------------------------------------------------------------------------
DEMO_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "email_validation": {
        "name": "Email Validation and Notification",
        "description": "Validates email syntax, uppercases customer name, and branches on validation result.",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "validate_email",
                "args": {"email": "{{input.email}}"},
                "description": "Check whether customer's email address is syntactically valid."
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "{{input.customer_name}}"},
                "description": "Convert customer's name to uppercase."
            },
            {
                "id": "step_3",
                "type": "condition",
                "condition": {
                    "operator": "is_valid",
                    "left": "{{step_1.output.is_valid}}"
                },
                "if_true": "step_4",
                "if_false": "step_5",
                "description": "Branch based on email validation result."
            },
            {
                "id": "step_4",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "{{step_1.output.email}}",
                    "message": "Welcome {{step_2.output.result}}! Your account registration is verified.",
                    "level": "success"
                },
                "description": "Create success notification for valid email."
            },
            {
                "id": "step_5",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "admin@example.com",
                    "message": "Registration failed: invalid email provided for {{step_2.output.result}}.",
                    "level": "error"
                },
                "description": "Create alert for invalid email."
            }
        ]
    },
    "order_approval": {
        "name": "High-Value Order Calculation and Approval",
        "description": "Calculates order total from item prices, requests human approval if total exceeds $80, and dispatches invoice.",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "calculate_total",
                "args": {"numbers": [45.5, 20.0, 35.0]},
                "description": "Calculate total cost from order item amounts."
            },
            {
                "id": "step_2",
                "type": "condition",
                "condition": {
                    "operator": ">",
                    "left": "{{step_1.output.total}}",
                    "right": 80.0
                },
                "if_true": "step_3",
                "if_false": "step_4",
                "description": "Check if order total is greater than $80."
            },
            {
                "id": "step_3",
                "type": "approval",
                "requires_approval": True,
                "tool": "create_notification",
                "args": {
                    "recipient": "finance@company.com",
                    "message": "High-value purchase approved for amount: ${{step_1.output.total}}.",
                    "level": "warning"
                },
                "description": "Human approval required for orders above $80 before notifying finance."
            },
            {
                "id": "step_4",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "customer@company.com",
                    "message": "Standard order processed successfully. Total: ${{step_1.output.total}}.",
                    "level": "info"
                },
                "description": "Notify customer of regular order processing."
            }
        ]
    },
    "text_transformation": {
        "name": "Customer Data Normalization",
        "description": "Cleans raw whitespace from name, converts to uppercase, and confirms formatting.",
        "steps": [
            {
                "id": "step_1",
                "type": "tool",
                "tool": "transform_data",
                "args": {"data": "   sarah connor   ", "action": "trim"},
                "description": "Trim leading and trailing whitespace from name."
            },
            {
                "id": "step_2",
                "type": "tool",
                "tool": "uppercase_text",
                "args": {"text": "{{step_1.output.result}}"},
                "description": "Convert trimmed name to uppercase."
            },
            {
                "id": "step_3",
                "type": "tool",
                "tool": "create_notification",
                "args": {
                    "recipient": "crm_system",
                    "message": "Customer profile normalized: {{step_2.output.result}}",
                    "level": "info"
                },
                "description": "Send notification to CRM system."
            }
        ]
    }
}


class WorkflowGenerator:
    """Translates user natural language instructions into structured workflow JSON.

    Supports OpenRouter API (sk-or-v1-*) and Google Gemini API, with automatic fallback
    to deterministic offline templates in demo mode or if no key is provided.
    """

    OPENROUTER_MODELS = [
        "google/gemini-2.5-flash",
        "google/gemini-2.5-flash-lite",
        "google/gemma-4-26b-a4b-it:free",
        "google/gemma-4-31b-it:free"
    ]
    GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]

    def __init__(self, api_key: Optional[str] = None):
        key = (
            api_key
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or os.getenv("API_KEY")
            or ""
        ).strip()
        self.api_key = key
        self._gemini_client = None

    def has_api_key(self) -> bool:
        """Check if an API key is configured (excluding placeholder defaults)."""
        if not self.api_key:
            return False
        return self.api_key not in ("your_gemini_api_key_here", "your_actual_gemini_api_key_here")

    def is_openrouter(self) -> bool:
        """Check whether the API key is an OpenRouter key."""
        return self.api_key.startswith("sk-or-v1-") or self.api_key.startswith("sk-or-")

    def generate_workflow(self, user_prompt: str, use_demo_fallback: bool = False) -> Dict[str, Any]:
        """Convert a natural language task description into a workflow dictionary."""
        cleaned_prompt = user_prompt.strip()
        if not cleaned_prompt:
            return {
                "success": False,
                "workflow_data": None,
                "raw_text": "",
                "error": "Task description cannot be empty.",
                "source": "error"
            }

        # Use demo fallback if explicitly asked or if no valid API key exists
        if use_demo_fallback or not self.has_api_key():
            return self._pick_demo_template(cleaned_prompt)

        # Provider routing based on key prefix
        if self.is_openrouter():
            return self._call_openrouter(cleaned_prompt)
        else:
            return self._call_gemini(cleaned_prompt)

    def _call_openrouter(self, prompt: str) -> Dict[str, Any]:
        """Generate workflow via OpenRouter API with optimal max_tokens to avoid credit reservation rejection."""
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8502",
            "X-Title": "Natural Language Workflow Generator"
        }

        last_error = None
        for model in self.OPENROUTER_MODELS:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": f"Generate workflow JSON for:\n\n{prompt}"}
                ],
                "temperature": 0.2,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"}
            }

            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=45)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        raw_text = choices[0].get("message", {}).get("content", "")
                        parsed = self._clean_and_parse_json(raw_text)
                        return {
                            "success": True,
                            "workflow_data": parsed,
                            "raw_text": raw_text,
                            "error": None,
                            "source": f"openrouter ({model})"
                        }
                else:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    logger.warning("OpenRouter model %s error: %s", model, last_error)
            except Exception as e:
                last_error = str(e)
                logger.warning("OpenRouter model %s failed: %s", model, e)
                continue

        return {
            "success": False,
            "workflow_data": None,
            "raw_text": "",
            "error": f"OpenRouter request failed: {last_error}",
            "source": "error"
        }

    def _call_gemini(self, prompt: str) -> Dict[str, Any]:
        """Generate workflow via Google Gemini SDK."""
        try:
            from google import genai
            from google.genai import types

            if self._gemini_client is None:
                self._gemini_client = genai.Client(api_key=self.api_key)

            client = self._gemini_client
            response = None
            last_err = None

            for model_name in self.GEMINI_MODELS:
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=f"Generate workflow JSON for:\n\n{prompt}",
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            response_mime_type="application/json",
                            temperature=0.2,
                        )
                    )
                    if response and response.text:
                        break
                except Exception as err:
                    last_err = err
                    continue

            if response is None or not response.text:
                raise last_err or RuntimeError("No response returned from Gemini API.")

            raw_text = response.text
            parsed = self._clean_and_parse_json(raw_text)

            return {
                "success": True,
                "workflow_data": parsed,
                "raw_text": raw_text,
                "error": None,
                "source": "gemini"
            }

        except Exception as exc:
            err_str = str(exc)
            if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str:
                msg = "API quota or rate limit exceeded. You can toggle Demo Mode to continue testing."
            elif "API_KEY_INVALID" in err_str or "400" in err_str:
                msg = "Invalid API key provided. Please verify the key."
            else:
                msg = f"API request failed: {err_str}"

            return {
                "success": False,
                "workflow_data": None,
                "raw_text": "",
                "error": msg,
                "source": "error"
            }

    def _pick_demo_template(self, prompt: str) -> Dict[str, Any]:
        """Select a representative offline demo workflow based on prompt keywords."""
        p = prompt.lower()
        if any(w in p for w in ("order", "calculate", "total", "price", "sum", "cost")):
            key = "order_approval"
        elif any(w in p for w in ("trim", "clean", "normalize", "uppercase", "lowercase")):
            key = "text_transformation"
        else:
            key = "email_validation"

        data = DEMO_TEMPLATES[key]
        return {
            "success": True,
            "workflow_data": data,
            "raw_text": json.dumps(data, indent=2),
            "error": None,
            "source": "demo"
        }

    @staticmethod
    def _clean_and_parse_json(text: str) -> Dict[str, Any]:
        """Safely parse JSON from model output, stripping markdown codeblocks if present."""
        cleaned = text.strip()

        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        match = re.search(r"(\{.*\})", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Could not parse valid JSON from model response: {text[:200]}...")
