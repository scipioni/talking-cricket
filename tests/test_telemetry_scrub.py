from __future__ import annotations

from calobot.telemetry.scrub import anonymize_chat_id, scrub_telemetry_event


def test_anonymize_chat_id():
    cid = 1915982318
    anon = anonymize_chat_id(cid)
    assert len(anon) == 8
    assert anon == anonymize_chat_id(cid)  # stable
    assert anon != anonymize_chat_id(123456)  # distinct


def test_scrub_incoming_update():
    event = {
        "type": "incoming_update",
        "chat_id": 123456,
        "text": "la mia data di nascita è 16/5/72",
        "username": "Ilafav",
        "callback_data": "ans:sì",
    }
    scrubbed = scrub_telemetry_event(event)
    assert scrubbed["chat_id"] == anonymize_chat_id(123456)
    assert scrubbed["text"] == "[Messaggio dell'utente]"
    assert scrubbed["username"] is None
    assert scrubbed["callback_data"] == "[Payload opzione]"


def test_scrub_outgoing_response():
    event = {
        "type": "outgoing_response",
        "chat_id": 123456,
        "text": "Fatto: data di nascita aggiornato a 1972-05-16.",
        "options": {"✏️ modifica": "entry:modifica:food:131"},
    }
    scrubbed = scrub_telemetry_event(event)
    assert scrubbed["text"] == "[Risposta di Calobot]"
    assert scrubbed["options"] == {"✏️ modifica": "[Payload opzione]"}


def test_scrub_llm_transaction():
    event = {
        "type": "llm_transaction",
        "chat_id": 123456,
        "step": "classify",
        "model": "qwen3-vl:30b-a3b-instruct",
        "system_prompt": "Sei il classificatore...",
        "prompt": "la mia data di nascita è 16/5/72",
        "response_raw": '{"intent": "profile"}',
        "response_parsed": {"intent": "profile"},
        "latency_seconds": 0.45,
        "success": True,
    }
    scrubbed = scrub_telemetry_event(event)
    assert "system_prompt" not in scrubbed
    assert "prompt" not in scrubbed
    assert "response_raw" not in scrubbed
    assert "response_parsed" not in scrubbed
    assert scrubbed["step"] == "classify"
    assert scrubbed["latency_seconds"] == 0.45
    assert scrubbed["success"] is True
