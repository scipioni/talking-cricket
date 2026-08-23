from __future__ import annotations

from calobot.telemetry.auth import sign_session_token, verify_session_token


def test_sign_and_verify_valid_token():
    secret = "my-secret-key-123"
    email = "scipio.it@gmail.com"
    token = sign_session_token(email, secret, expiry_seconds=3600)

    verified = verify_session_token(token, secret)
    assert verified == email


def test_verify_expired_token():
    secret = "my-secret-key-123"
    email = "scipio.it@gmail.com"
    # Create an expired token (negative expiry)
    token = sign_session_token(email, secret, expiry_seconds=-10)

    verified = verify_session_token(token, secret)
    assert verified is None


def test_verify_forged_token():
    secret = "my-secret-key-123"
    wrong_secret = "hacker-secret-key"
    email = "scipio.it@gmail.com"
    token = sign_session_token(email, wrong_secret, expiry_seconds=3600)

    verified = verify_session_token(token, secret)
    assert verified is None


def test_verify_invalid_token_format():
    secret = "my-secret-key-123"
    assert verify_session_token("not-a-token", secret) is None
    assert verify_session_token("one.two", secret) is None
    assert verify_session_token("one.two.three.four", secret) is None
