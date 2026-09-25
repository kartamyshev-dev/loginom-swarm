"""Sanitize external output before any persisted worker log or report."""
import re

PATTERNS = [
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer\s+)?)[^\s\"']+"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"(?i)((?:password|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"),
    re.compile(r"-----BEGIN [^-]*PRIVATE KEY-----[\s\S]*?-----END [^-]*PRIVATE KEY-----"),
]


def redact(text, secrets=()):
    for secret in sorted((x for x in secrets if x), key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    for pattern in PATTERNS:
        text = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", text)
    return text


def public_codex_event(event):
    """Use an allowlist: reasoning and raw provider payloads are never logged."""
    kind = event.get("type")
    if kind == "thread.started":
        return {"type": kind, "thread_id": event.get("thread_id")}
    if kind == "turn.completed":
        usage = event.get("usage", {})
        return {"type": kind, "usage": {k: usage[k] for k in ("input_tokens", "output_tokens", "cached_input_tokens") if k in usage}}
    if kind == "item.completed" and event.get("item", {}).get("type") == "agent_message":
        return {"type": kind, "item": {"type": "agent_message", "text": event["item"].get("text", "")}}
    if kind in {"error", "turn.failed"}:
        return {"type": kind, "message": "Model execution failed; reconcile provider authorization and run status."}
    return None
