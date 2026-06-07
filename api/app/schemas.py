from decimal import Decimal
from pydantic import BaseModel

class InstrumentIn(BaseModel):
    type: str                      # barcode | nfc_tag | card_token
    value: str

class MerchantIn(BaseModel):
    merchant_id: str | None = None
    raw_descriptor: str | None = None
    mcc: str | None = None

class AuthorizeIn(BaseModel):
    idempotency_key: str
    rail: str                      # sticker | card_sim | card | retail_pos
    instrument: InstrumentIn
    merchant: MerchantIn
    amount_bwp: Decimal
    pin_provided: bool = False
    pin_value: str | None = None

class AuthorizeOut(BaseModel):
    decision: str                  # approved | declined | pin_required
    approved_amount_bwp: Decimal
    envelope: str | None = None
    reason_code: str
    display_message: str
    ask_guardian_available: bool = False
    auth_id: str | None = None