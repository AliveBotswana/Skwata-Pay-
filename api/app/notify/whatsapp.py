"""WhatsApp via Meta Cloud API — motokare pattern. Dev mode: logs only."""
import httpx
from app.core.config import settings

def send_text(phone_e164: str, body: str) -> dict:
    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_ID:
        print(f"[WHATSAPP-DEV] to={phone_e164} :: {body}")
        return {"dev": True}
    try:
        r = httpx.post(
            f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_ID}/messages",
            headers={"Authorization": f"Bearer {settings.WHATSAPP_TOKEN}"},
            json={"messaging_product": "whatsapp", "to": phone_e164.lstrip("+"),
                  "type": "text", "text": {"body": body}},
            timeout=10,
        )
        return r.json()
    except Exception as e:                      # never let notify break money
        print(f"[WHATSAPP-ERR] {e}")
        return {"error": str(e)}