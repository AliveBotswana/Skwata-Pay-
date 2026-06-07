"""PSP adapter protocol. Every provider implements exactly two verbs:
create_session: returns whatever the funder-facing page needs to take payment.
parse_callback: normalizes a provider webhook into {reference, status, amount}."""
from typing import Protocol
from decimal import Decimal

class FundingSession(dict):
    """provider, reference, and provider-specific fields (url/params)."""

class PSPAdapter(Protocol):
    def create_session(self, reference: str, amount_bwp: Decimal,
                       funder_name: str, funder_phone: str,
                       description: str) -> FundingSession: ...
    def parse_callback(self, payload: dict) -> dict: ...