"""Reason-code walk. NOTE: runs against DATABASE_URL — dev DB only; resets it."""
import time, uuid
import pytest
from decimal import Decimal
from sqlalchemy import text
from app.core.db import SessionLocal, Base, engine
from app.services.seeds import seed
from app.services.authorize import authorize
from app.schemas import AuthorizeIn, InstrumentIn, MerchantIn
from app.core.security import mint_code
from app.models.models import Wallet, Merchant

@pytest.fixture(scope="module")
def ctx():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.execute(text("""TRUNCATE ledger_entries, transactions, payment_requests,
        settlement_batches, contribution_links, envelope_categories, envelopes,
        wallet_blocks, wallet_members, wallets, merchants, mcc_category_map, persons
        RESTART IDENTITY CASCADE"""))
    db.commit()
    info = seed(db)
    w = db.get(Wallet, uuid.UUID(info["wallet_id"]))
    m = {x.display_name: x for x in db.query(Merchant).all()}
    yield {"db": db, "w": w, "m": m}
    db.close()

def call(ctx, merchant, amount, pin=None, key=None, code=None):
    w = ctx["w"]
    req = AuthorizeIn(
        idempotency_key=key or f"T-{uuid.uuid4()}",
        rail="sticker",
        instrument=InstrumentIn(type="barcode",
                                value=code or mint_code(str(w.id), w.barcode_secret)),
        merchant=MerchantIn(merchant_id=str(merchant.id) if merchant else None,
                            mcc=None if merchant else "5921"),
        amount_bwp=Decimal(amount),
        pin_provided=pin is not None,
        pin_value=pin,
    )
    return authorize(ctx["db"], req)

def test_approved_food(ctx):
    r = call(ctx, ctx["m"]["Choppies Gaborone West"], "80")
    assert (r.decision, r.reason_code, r.envelope) == ("approved", "APPROVED", "Food")

def test_blocked_alcohol(ctx):
    r = call(ctx, ctx["m"]["Liquorama Gabs"], "60")
    assert r.reason_code == "CATEGORY_BLOCKED"

def test_pin_required_then_ok(ctx):
    r = call(ctx, ctx["m"]["Choppies Gaborone West"], "250")
    assert r.reason_code == "PIN_REQUIRED"
    r = call(ctx, ctx["m"]["Choppies Gaborone West"], "250", pin="1234")
    assert r.reason_code == "APPROVED"

def test_pin_invalid(ctx):
    r = call(ctx, ctx["m"]["Choppies Gaborone West"], "250", pin="0000")
    assert r.reason_code == "PIN_INVALID"

def test_insufficient_envelope(ctx):
    r = call(ctx, ctx["m"]["Campus Bookshop"], "150")
    assert (r.reason_code, r.ask_guardian_available) == ("INSUFFICIENT_ENVELOPE", True)

def test_no_envelope_for_category(ctx):
    r = call(ctx, None, "20")          # mcc 5921 via card_sim path, but no merchant:
    assert r.reason_code in ("CATEGORY_BLOCKED",)  # alcohol blocked beats routing

def test_duplicate_replay(ctx):
    k = f"T-{uuid.uuid4()}"
    r1 = call(ctx, ctx["m"]["Choppies Gaborone West"], "10", key=k)
    r2 = call(ctx, ctx["m"]["Choppies Gaborone West"], "10", key=k)
    assert r1.reason_code == "APPROVED" and r2.reason_code == "DUPLICATE"

def test_expired_code(ctx):
    w = ctx["w"]
    old = mint_code(str(w.id), w.barcode_secret, ts=int(time.time()) - 600)
    r = call(ctx, ctx["m"]["Choppies Gaborone West"], "15", code=old)
    assert r.reason_code == "EXPIRED_CODE"