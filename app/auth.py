import base64
import hashlib
import hmac
import os
import time

SESSION_COOKIE = "session"
SESSION_TTL = 7 * 24 * 3600


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    except ValueError:
        return False
    return hmac.compare_digest(dk.hex(), dk_hex)


def _sign(secret: str, payload: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def make_session_token(secret: str, user_id: int, now: float | None = None) -> str:
    expires = int((time.time() if now is None else now) + SESSION_TTL)
    payload = base64.urlsafe_b64encode(f"{user_id}:{expires}".encode()).decode()
    return f"{payload}.{_sign(secret, payload)}"


def verify_session_token(secret: str, token: str | None, now: float | None = None) -> int | None:
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(secret, payload)):
        return None
    try:
        user_id, expires = base64.urlsafe_b64decode(payload.encode()).decode().split(":")
        if int(expires) < (time.time() if now is None else now):
            return None
        return int(user_id)
    except ValueError:
        return None
