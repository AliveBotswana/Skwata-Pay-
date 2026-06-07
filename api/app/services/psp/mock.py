"""Mock PSP: returns a fake session; the demo 'pays' by hitting the
callback endpoint directly with status=success (or via /admin tools)."""
from decimal import Decimal
from app.services.psp.base import FundingSession

class MockAdapter:
    def create_session(self, reference: str, amount_bwp: Decimal,
                       funder_name: str, funder_phone: str,
                       description: str) -> FundingSession:
        return FundingSession(provider="mock", reference=reference,
                              pay_url=f"/dev/mock-pay/{reference}",
                              note="POST the callback endpoint to simulate payment")

    def parse_callback(self, payload: dict) -> dict:
        return {"reference": payload.get("reference"),
                "status": payload.get("status", "success"),
                "amount_bwp": Decimal(str(payload.get("amount_bwp", "0")))}