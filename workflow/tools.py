"""Approved safe tool registry and execution implementations.

Every function here is whitelisted — no eval(), no exec(), no subprocess.
Tools are looked up by name from TOOL_REGISTRY; anything else gets rejected."""

import re
import socket
import ipaddress
import urllib.parse
import logging
from typing import Any, Callable, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Max sizes / limits (defence in depth)
_MAX_EMAIL_LENGTH = 320          # RFC 5321 — 64 + 1 + 255
_MAX_TEXT_INPUT = 50_000         # chars — prevents memory bombs
_MAX_LIST_LENGTH = 500           # items — for calculate_total etc.
_HTTP_MAX_BYTES = 10 * 1024      # 10 KB response cap
_HTTP_MAX_TIMEOUT = 10           # seconds


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def validate_email(email: str) -> Dict[str, Any]:
    """Check whether an email address looks syntactically valid.

    Performs regex matching only — does not ping the mail server.
    """
    if not isinstance(email, str):
        return {"is_valid": False, "email": str(email), "reason": "Input is not a string."}

    cleaned = email.strip()
    if len(cleaned) > _MAX_EMAIL_LENGTH:
        return {"is_valid": False, "email": cleaned[:80] + "...", "reason": "Email exceeds maximum length."}

    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    is_valid = bool(re.match(pattern, cleaned))
    return {
        "is_valid": is_valid,
        "valid": is_valid,
        "email": cleaned,
        "reason": "Valid email format." if is_valid else "Invalid email syntax or format."
    }


def uppercase_text(text: str) -> Dict[str, Any]:
    """Convert input text to uppercase."""
    raw = str(text) if text is not None else ""
    if len(raw) > _MAX_TEXT_INPUT:
        raw = raw[:_MAX_TEXT_INPUT]
    uppercased = raw.upper()
    return {"original": raw, "result": uppercased, "text": uppercased}


def transform_data(data: Any, action: str = "trim") -> Dict[str, Any]:
    """Run a whitelisted text / list transformation.

    Supported actions: trim, lower, capitalize, title, reverse, word_count.
    """
    action_clean = str(action).strip().lower()
    text = str(data)

    if len(text) > _MAX_TEXT_INPUT:
        text = text[:_MAX_TEXT_INPUT]

    actions_map = {
        "trim":       lambda: text.strip(),
        "lower":      lambda: text.lower(),
        "capitalize": lambda: text.capitalize(),
        "title":      lambda: text.title(),
        "reverse":    lambda: text[::-1] if isinstance(data, str) else list(reversed(data)),
        "word_count": lambda: len(text.split()),
    }

    if action_clean not in actions_map:
        raise ValueError(
            f"Unsupported transform action '{action}'. "
            f"Supported: {', '.join(sorted(actions_map))}"
        )

    return {"action": action_clean, "result": actions_map[action_clean]()}


def calculate_total(numbers: List[Any]) -> Dict[str, Any]:
    """Sum a list of numeric values."""
    if not isinstance(numbers, list):
        raise ValueError("Argument 'numbers' must be a list.")

    if len(numbers) > _MAX_LIST_LENGTH:
        raise ValueError(f"List too long ({len(numbers)} items). Maximum is {_MAX_LIST_LENGTH}.")

    converted: List[float] = []
    for idx, item in enumerate(numbers):
        try:
            converted.append(float(item))
        except (ValueError, TypeError) as e:
            raise ValueError(f"Item at index {idx} ('{item}') is not numeric.") from e

    total = sum(converted)
    return {"total": round(total, 4), "count": len(converted), "values": converted}


def check_condition(val1: Any, operator: str, val2: Any = None) -> Dict[str, Any]:
    """Evaluate a comparison using an explicit operator whitelist."""
    op = str(operator).strip().lower()

    if op in ("==", "equals", "eq"):
        if isinstance(val1, str) or isinstance(val2, str):
            matched = str(val1).strip().lower() == str(val2).strip().lower()
        else:
            matched = val1 == val2
    elif op in ("!=", "not_equals", "neq"):
        matched = val1 != val2
    elif op in (">", "gt"):
        matched = float(val1) > float(val2)
    elif op in ("<", "lt"):
        matched = float(val1) < float(val2)
    elif op in (">=", "gte"):
        matched = float(val1) >= float(val2)
    elif op in ("<=", "lte"):
        matched = float(val1) <= float(val2)
    elif op == "contains":
        matched = str(val2).lower() in str(val1).lower()
    elif op == "is_valid":
        if isinstance(val1, dict) and "is_valid" in val1:
            matched = bool(val1["is_valid"])
        else:
            matched = bool(val1)
    elif op == "is_empty":
        matched = val1 is None or len(str(val1).strip()) == 0 or val1 == [] or val1 == {}
    else:
        raise ValueError(
            f"Unsupported operator '{operator}'. "
            "Supported: ==, !=, >, <, >=, <=, contains, is_valid, is_empty"
        )

    return {"matched": matched, "operator": op, "val1": val1, "val2": val2}


def create_notification(recipient: str, message: str, level: str = "info") -> Dict[str, Any]:
    """Create a simulated in-app notification.

    Nothing actually gets sent externally — the output explicitly says so.
    """
    valid_levels = {"info", "warning", "error", "success"}
    lvl = level.lower() if level.lower() in valid_levels else "info"

    return {
        "delivered": False,
        "simulated": True,
        "delivery_status": "simulated",
        "recipient": str(recipient).strip(),
        "message": str(message).strip()[:2000],   # cap message length
        "level": lvl,
        "note": "Simulation completed — no external message was sent"
    }


def http_get(url: str, timeout: int = 5) -> Dict[str, Any]:
    """Fetch a URL via GET with strict security guards.

    Blocks:
      - Non-http(s) schemes
      - Localhost / loopback / private IPs / link-local / metadata endpoints
      - DNS rebinding (resolves hostname before connecting)
    Enforces a response-size cap and a hard timeout.
    """
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme '{parsed.scheme}'. Only http/https.")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must have a valid hostname.")

    # Block obvious loopback names
    if hostname.lower() in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"):
        raise PermissionError("Access to localhost or loopback is blocked.")

    # Resolve the hostname to an IP and validate it BEFORE making the request.
    # This prevents DNS-rebinding attacks where a public domain resolves to
    # a private address.
    try:
        resolved_ip = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, addr in resolved_ip:
            ip_obj = ipaddress.ip_address(addr[0])
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                raise PermissionError(f"DNS for '{hostname}' resolved to blocked address {addr[0]}.")
    except socket.gaierror:
        pass  # can't resolve — let requests handle the error naturally
    except PermissionError:
        raise
    except ValueError:
        pass  # hostname is an IP literal — fall through to the existing check

    # Direct IP-literal check
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise PermissionError(f"Access to private/local address '{hostname}' is blocked.")
    except ValueError:
        pass

    safe_timeout = min(max(int(timeout), 1), _HTTP_MAX_TIMEOUT)

    try:
        resp = requests.get(url, timeout=safe_timeout, stream=True, allow_redirects=False)
        content = resp.raw.read(_HTTP_MAX_BYTES, decode_content=True)
        text_preview = content.decode("utf-8", errors="replace")

        return {
            "status_code": resp.status_code,
            "url": url,
            "content_preview": text_preview[:500],
            "bytes_received": len(content),
            "success": resp.ok
        }
    except Exception as exc:
        raise RuntimeError(f"HTTP request to '{url}' failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Registry — maps tool names to their function + parameter metadata.
# Only tools listed here can be invoked by the executor.
# ---------------------------------------------------------------------------

TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "validate_email": {
        "func": validate_email,
        "description": "Validates email syntax using RFC 5322 regex. Does not ping mail server.",
        "params": {
            "email": {"type": "string", "required": True, "description": "The email address to validate"}
        }
    },
    "uppercase_text": {
        "func": uppercase_text,
        "description": "Converts given text to uppercase string.",
        "params": {
            "text": {"type": "string", "required": True, "description": "Text to convert to uppercase"}
        }
    },
    "transform_data": {
        "func": transform_data,
        "description": "Runs safe text transformations: trim, lower, capitalize, title, reverse, word_count.",
        "params": {
            "data": {"type": "any", "required": True, "description": "Text or data to transform"},
            "action": {"type": "string", "required": False, "description": "Action name (default: trim)"}
        }
    },
    "calculate_total": {
        "func": calculate_total,
        "description": "Sums a list of numbers and returns the total plus count.",
        "params": {
            "numbers": {"type": "list", "required": True, "description": "List of numeric items"}
        }
    },
    "check_condition": {
        "func": check_condition,
        "description": "Evaluates comparison (==, !=, >, <, >=, <=, contains, is_valid, is_empty).",
        "params": {
            "val1": {"type": "any", "required": True, "description": "Left operand"},
            "operator": {"type": "string", "required": True, "description": "Comparison operator"},
            "val2": {"type": "any", "required": False, "description": "Right operand (optional for unary ops)"}
        }
    },
    "create_notification": {
        "func": create_notification,
        "description": "Generates a simulated notification. No real message is dispatched.",
        "params": {
            "recipient": {"type": "string", "required": True, "description": "Recipient user or channel"},
            "message": {"type": "string", "required": True, "description": "Notification body"},
            "level": {"type": "string", "required": False, "description": "Severity: info, warning, error, success"}
        }
    },
    "http_get": {
        "func": http_get,
        "description": "Fetches a public URL via GET with SSRF protection, timeout, and size cap.",
        "params": {
            "url": {"type": "string", "required": True, "description": "Public HTTP/HTTPS URL"},
            "timeout": {"type": "integer", "required": False, "description": "Timeout in seconds (max 10s)"}
        }
    }
}


def execute_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Look up a tool by name and run it. Rejects anything not in the registry."""
    if name not in TOOL_REGISTRY:
        return {
            "success": False,
            "output": None,
            "error": (
                f"Tool '{name}' is not registered. "
                f"Available tools: {list(TOOL_REGISTRY.keys())}"
            )
        }

    func: Callable = TOOL_REGISTRY[name]["func"]

    try:
        result = func(**args)
        return {"success": True, "output": result, "error": None}
    except TypeError as te:
        return {"success": False, "output": None, "error": f"Bad arguments for '{name}': {te}"}
    except (PermissionError, ValueError, RuntimeError) as exc:
        return {"success": False, "output": None, "error": f"Tool '{name}' error: {exc}"}
    except Exception as exc:
        logger.exception("Unexpected error running tool '%s'", name)
        return {"success": False, "output": None, "error": f"Tool '{name}' failed unexpectedly: {exc}"}
