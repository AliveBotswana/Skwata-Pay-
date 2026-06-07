"""Tingg Express Checkout adapter.
create_session builds and AES-encrypts the payload exactly as Cellulant's
official cellulant-checkout-encryption package does; the funder-facing page
then POSTs {access_key, encrypted_payload} to TINGG_EXPRESS_URL (their
hosted page), and Tingg calls our callback_url when payment completes."""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from cellulant_checkout_encryption import Encryption
from app.core.config import settings
from app.services.psp.base import FundingSession

class TinggAdapter:
    def create_session(self, reference: str, amount_bwp: Decimal,
                       funder_name: str, funder_phone: str,
                       description: str) -> FundingSession:
        parts = (funder_name or "Funder").split()
        first, last = parts[0], (parts[-1] if len(parts) > 1 else parts[0])
        due = (datetime.now(timezone.utc) + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        cb = f"{settings.PUBLIC_BASE_URL}/fund/tingg/callback"
        payload = {
            "merchant_transaction_id": reference,
            "account_number": reference,
            "msisdn": funder_phone.lstrip("+"),
            "service_code": settings.TINGG_SERVICE_CODE,
            "country_code": settings.TINGG_COUNTRY_CODE,
            "currency_code": settings.TINGG_CURRENCY_CODE,
            "customer_first_name": first,
            "customer_last_name": last,
            "customer_email": "noreply@skwata.com",
            "request_amount": str(amount_bwp),
            "due_date": due,
            "language_code": "en",
            "request_description": description[:100],
            "success_redirect_url": f"{settings.PUBLIC_BASE_URL}/fund/result?ref={reference}&s=1",
            "fail_redirect_url": f"{settings.PUBLIC_BASE_URL}/fund/result?ref={reference}&s=0",
            "callback_url": cb,
        }
        enc = Encryption.Encryption(settings.TINGG_IV_KEY, settings.TINGG_SECRET_KEY)
        return FundingSession(
            provider="tingg",
            reference=reference,
            express_url=settings.TINGG_EXPRESS_URL,
            access_key=settings.TINGG_ACCESS_KEY,
            encrypted_payload=enc.encrypt(json.dumps(payload)),
        )

    def parse_callback(self, payload: dict) -> dict:
        """Normalize Tingg's callback. Field names per their webhook doc;
        tolerate both camel and snake variants seen in their examples."""
        ref = (payload.get("merchant_transaction_id")
               or payload.get("merchantTransactionID") or "")
        status_code = str(payload.get("request_status_code")
                          or payload.get("requestStatusCode") or "")
        amount = (payload.get("amount_paid") or payload.get("amountPaid")
                  or payload.get("request_amount") or "0")
        # 178 = fully paid in Tingg's status vocabulary; verify in their docs
        status = "success" if status_code == "178" else "failed"
        return {"reference": ref, "status": status,
                "amount_bwp": Decimal(str(amount))}