"""PSP funding lifecycle with mock adapter: pending -> callback -> ledger."""
import uuid
import pytest
from decimal import Decimal
from sqlalchemy import text
from app.core.db import SessionLocal, Base, engine
from app.services.seeds import seed
from app.services import contributions, funding
from app.models.models import Wallet, Envelope, Transaction

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
    e = {x.name: x for x in db.query(Envelope).filter_by(wallet_id=w.id).all()}
    link = contributions.create_link(db, e["Grooming"].id, "Grooming")
    contributions.approve_link(db, link.token)
    yield {"db": db, "w": w, "e": e, "link": link}
    db.close()

def test_initiate_is_pending_no_ledger(ctx):
    r = funding.initiate(ctx["db"], ctx["link"].token, Decimal("300"),
                         "Kabelo M", "+26771000003", "Treat yourself")
    ctx["ref"] = r["reference"]
    assert r["session"]["provider"] == "mock"
    txn = ctx["db"].query(Transaction).filter_by(idempotency_key=r["reference"]).one()
    assert txn.status == "pending_psp"
    ctx["db"].refresh(ctx["e"]["Grooming"])
    assert ctx["e"]["Grooming"].balance_bwp == Decimal("0.00")   # nothing yet

def test_success_callback_posts_ledger(ctx):
    out = funding.handle_callback(ctx["db"], {"reference": ctx["ref"],
                                              "status": "success",
                                              "amount_bwp": "300"})
    assert out["status"] == "approved"
    ctx["db"].refresh(ctx["e"]["Grooming"])
    assert ctx["e"]["Grooming"].balance_bwp == Decimal("300.00")

def test_duplicate_callback_idempotent(ctx):
    out = funding.handle_callback(ctx["db"], {"reference": ctx["ref"],
                                              "status": "success",
                                              "amount_bwp": "300"})
    assert out.get("idempotent") is True
    ctx["db"].refresh(ctx["e"]["Grooming"])
    assert ctx["e"]["Grooming"].balance_bwp == Decimal("300.00")  # not doubled

def test_failed_callback_declines(ctx):
    r = funding.initiate(ctx["db"], ctx["link"].token, Decimal("100"),
                         "Kea", "+26771000004", None)
    out = funding.handle_callback(ctx["db"], {"reference": r["reference"],
                                              "status": "failed",
                                              "amount_bwp": "100"})
    assert out["status"] == "declined"
    ctx["db"].refresh(ctx["e"]["Grooming"])
    assert ctx["e"]["Grooming"].balance_bwp == Decimal("300.00")  # unchanged