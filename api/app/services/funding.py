"""Funding lifecycle: initiate (pending, no ledger) -> callback (post ledger).
Replaces the instant-credit behavior in contributions for PSP-routed money."""
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import Transaction, ContributionLink, Envelope, Wallet, Person
from app.services.ledger import post_transaction
from app.services.psp import get_psp
from app.services.contributions import SENDER_FEE_RATE, SENDER_FEE_CAP
from app.notify.whatsapp import send_text

def initiate(db: Session, link_token: str, amount: Decimal,
             funder_name: str, funder_phone: str, message: str | None) -> dict:
    link = db.query(ContributionLink).filter_by(token=link_token).first()
    if link is None or link.status != "active":
        raise ValueError("link not active")
    env = db.get(Envelope, link.envelope_id)
    wallet = db.get(Wallet, env.wallet_id)

    funder = db.query(Person).filter_by(phone_e164=funder_phone).first()
    if funder is None:
        funder = Person(phone_e164=funder_phone, full_name=funder_name)
        db.add(funder); db.flush()

    reference = f"FND-{uuid.uuid4().hex[:12]}"
    txn = Transaction(kind="contribution", wallet_id=wallet.id, envelope_id=env.id,
                      contributor_id=funder.id, amount_bwp=Decimal(amount),
                      status="pending_psp", rail="psp",
                      idempotency_key=reference, external_ref=message)
    db.add(txn); db.commit()

    session = get_psp().create_session(reference, Decimal(amount),
                                       funder_name, funder_phone,
                                       f"Skwata: {env.name} for {wallet.owner_id}")
    return {"reference": reference, "session": dict(session)}

def handle_callback(db: Session, raw_payload: dict) -> dict:
    norm = get_psp().parse_callback(raw_payload)
    txn = db.query(Transaction).filter_by(idempotency_key=norm["reference"]).first()
    if txn is None:
        return {"ok": False, "reason": "unknown reference"}
    if txn.status != "pending_psp":
        return {"ok": True, "idempotent": True, "status": txn.status}

    if norm["status"] != "success":
        txn.status = "declined"; txn.decline_reason = "PSP_FAILED"
        db.commit()
        return {"ok": True, "status": "declined"}

    amount = txn.amount_bwp
    fee = min((amount * SENDER_FEE_RATE).quantize(Decimal("0.01")), SENDER_FEE_CAP)
    txn.status = "approved"
    post_transaction(db, None_safe(txn), [])  # no-op guard; real entries below
    # post entries against the EXISTING txn (no new Transaction row):
    from app.models.models import LedgerEntry
    entries = [
        {"account_type": "psp_clearing", "account_id": None,        "amount_bwp": -(amount + fee)},
        {"account_type": "envelope",     "account_id": txn.envelope_id, "amount_bwp": amount},
        {"account_type": "platform_fee", "account_id": None,        "amount_bwp": fee},
    ]
    total = sum(Decimal(str(e["amount_bwp"])) for e in entries)
    assert total == Decimal("0")
    env = db.get(Envelope, txn.envelope_id)
    for e in entries:
        db.add(LedgerEntry(txn_id=txn.id, account_type=e["account_type"],
                           account_id=e.get("account_id"),
                           amount_bwp=Decimal(str(e["amount_bwp"]))))
    env.balance_bwp = env.balance_bwp + amount
    db.commit()

    wallet = db.get(Wallet, txn.wallet_id)
    owner = db.get(Person, wallet.owner_id)
    funder = db.get(Person, txn.contributor_id)
    note = f' - "{txn.external_ref}"' if txn.external_ref else ""
    send_text(owner.phone_e164,
              f"{funder.full_name} sent P{amount} to your {env.name} envelope{note}")
    return {"ok": True, "status": "approved"}

def None_safe(txn):
    """post_transaction requires a txn; here entries=[] so it only validates.
    Kept to reuse the imbalance guard shape without double-adding the txn."""
    class _T:  # sentinel; never persisted
        id = txn.id
    return txn