"""PIN hashing (argon2) and TOTP-style barcode mint/verify."""
import base64, hashlib, hmac, json, time
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

ph = PasswordHasher()
CODE_WINDOW_SECONDS = 60

def hash_pin(pin: str) -> str:
    return ph.hash(pin)

def verify_pin(pin_hash: str, pin: str) -> bool:
    try:
        return ph.verify(pin_hash, pin)
    except VerifyMismatchError:
        return False

def _sig(payload_b64: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode().rstrip("=")[:22]

def mint_code(wallet_id: str, secret: str, ts: int | None = None) -> str:
    payload = {"w": str(wallet_id), "t": ts or int(time.time())}
    p64 = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return f"SKW1.{p64}.{_sig(p64, secret)}"

def parse_code(code: str) -> dict | None:
    """Returns {'w':..., 't':...} or None if malformed. Signature NOT yet verified."""
    try:
        scheme, p64, sig = code.split(".")
        if scheme != "SKW1":
            return None
        pad = "=" * (-len(p64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(p64 + pad))
        payload["_p64"], payload["_sig"] = p64, sig
        return payload
    except Exception:
        return None

def verify_code(payload: dict, secret: str, now: int | None = None) -> str:
    """Returns 'ok' | 'bad_sig' | 'expired'."""
    if not hmac.compare_digest(_sig(payload["_p64"], secret), payload["_sig"]):
        return "bad_sig"
    if abs((now or int(time.time())) - int(payload["t"])) > CODE_WINDOW_SECONDS:
        return "expired"
    return "ok"