from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time

logger = logging.getLogger(__name__)


def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def b64url_decode(s: str) -> bytes:
    # Ensure correct base64 padding
    rem = len(s) % 4
    if rem > 0:
        s += "=" * (4 - rem)
    return base64.urlsafe_b64decode(s.encode("utf-8"))


def sign_session_token(email: str, secret_key: str, expiry_seconds: int = 86400) -> str:
    """Generate a signed JWT-like token containing the user email and an expiry time."""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"email": email, "exp": int(time.time()) + expiry_seconds}

    header_part = b64url_encode(json.dumps(header).encode("utf-8"))
    payload_part = b64url_encode(json.dumps(payload).encode("utf-8"))

    msg = f"{header_part}.{payload_part}".encode("utf-8")
    sig = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).digest()
    sig_part = b64url_encode(sig)

    return f"{header_part}.{payload_part}.{sig_part}"


def verify_session_token(token: str, secret_key: str) -> str | None:
    """Verify a signed token. Returns the email if valid, or None if invalid/expired."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_part, payload_part, sig_part = parts

        # Verify signature first
        msg = f"{header_part}.{payload_part}".encode("utf-8")
        expected_sig = hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).digest()
        actual_sig = b64url_decode(sig_part)

        if not hmac.compare_digest(expected_sig, actual_sig):
            logger.warning("Session token signature verification failed.")
            return None

        # Decode and verify payload
        payload = json.loads(b64url_decode(payload_part).decode("utf-8"))
        exp = payload.get("exp")

        if exp is None or int(time.time()) > exp:
            logger.warning("Session token has expired.")
            return None

        return payload.get("email")
    except Exception as exc:
        logger.warning("Failed to parse/verify session token: %s", exc)
        return None
