from __future__ import annotations

import hashlib
from typing import Any


def anonymize_chat_id(chat_id: int | str | None) -> str:
    if chat_id is None:
        return "anonymous"
    # Create a stable, short 8-char hex hash from the chat_id
    hasher = hashlib.sha256(f"calobot-salt-{chat_id}".encode("utf-8"))
    return hasher.hexdigest()[:8]


def scrub_telemetry_event(event: dict[str, Any]) -> dict[str, Any]:
    """Scrub personal and sensitive information from a telemetry event for public view."""
    scrubbed = dict(event)

    # Anonymize chat_id
    if "chat_id" in scrubbed:
        scrubbed["chat_id"] = anonymize_chat_id(scrubbed["chat_id"])

    ev_type = scrubbed.get("type")

    if ev_type == "incoming_update":
        scrubbed["username"] = None
        scrubbed["text"] = "[Messaggio dell'utente]"
        if "callback_data" in scrubbed and scrubbed["callback_data"]:
            scrubbed["callback_data"] = "[Payload opzione]"

    elif ev_type == "outgoing_response":
        scrubbed["text"] = "[Risposta di Calobot]"
        if "options" in scrubbed and scrubbed["options"]:
            # Keep button labels but scrub actual callback data
            scrubbed["options"] = {label: "[Payload opzione]" for label in scrubbed["options"]}

    elif ev_type == "llm_transaction":
        # Keep non-sensitive metadata (step, model, latency, success)
        # Strip raw textual prompts and completions
        for key in [
            "system_prompt",
            "prompt",
            "response_raw",
            "response_parsed",
            "error",
            "validation_attempts",
        ]:
            if key in scrubbed:
                scrubbed.pop(key)

    # Clean up top-level collections if present
    if "activities" in scrubbed:
        scrubbed.pop("activities")
    if "llm_interactions" in scrubbed:
        scrubbed.pop("llm_interactions")

    return scrubbed
