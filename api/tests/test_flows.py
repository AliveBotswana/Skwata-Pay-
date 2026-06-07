"""Contribution links (R1/R2) and Ask-Mma end-to-end."""
import uuid
import pytest
from decimal import Decimal
from sqlalchemy import text
from app.core.db import SessionLocal, Base, engine
from app.services.seeds import seed
from app.services import contributions, ask_mma
from app.models.models import Wallet, Merchant, Envelope

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
    e = {x.name: x for x in db.query(Envelope).filter_by(wallet_id=w.id).all()}
    yield {"db": db, "w": w, "m": m, "e": e}
    db.close()

def test_link_requires_guardian_for_minor(ctx):
    link = contributions.create_link(ctx["db"], ctx["e"]["Grooming"].id, "Grooming")
    assert link.status == "pending_guardian_approval"
    with pytest.raises(ValueError):
        contributions.contribute(ctx["db"], link.token, Decimal("300"),
                                 "Kabelo M", "+26771000003", None)
    contributions.approve_link(ctx["db"], link.token)
    ctx["link"] = link

def test_contribution_credits_envelope_blind(ctx):
    r = contributions.contribute(ctx["db"], ctx["link"].token, Decimal("300"),
                                 "Kabelo M", "+26771000003", "Treat yourself")
    assert r["delivered"] is True and r["fee_bwp"] == "15.00"
    assert set(r.keys()) == {"delivered", "envelope", "owner_first_name",
                             "amount_bwp", "fee_bwp", "total_charged_bwp"}  # R2: nothing else
    ctx["db"].refresh(ctx["e"]["Grooming"])
    assert ctx["e"]["Grooming"].balance_bwp == Decimal("300.00")

def test_closed_envelope_rejects_link(ctx):
    with pytest.raises(ValueError):
        contributions.create_link(ctx["db"], ctx["e"]["Food"].id, "Food")

def test_ask_mma_full_loop(ctx):
    pr = ask_mma.create_request(ctx["db"], ctx["w"].id,
                                ctx["m"]["Choppies Gaborone West"].id, Decimal("380"))
    assert pr.status == "pending" and pr.shortfall_bwp == Decimal("30.00")
    done = ask_mma.approve(ctx["db"], pr.id)
    assert done.status == "approved" and done.txn_id is not None
    ctx["db"].refresh(ctx["e"]["Food"])
    assert ctx["e"]["Food"].balance_bwp == Decimal("0.00")   # 350+30-380
    again = ask_mma.approve(ctx["db"], pr.id)                # idempotent
    assert again.txn_id == done.txn_id