"""Contribution links — rules R1 (minor gate) and R2 (contributor blindness)."""
import secrets, uuid
from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import (
    ContributionLink, Envelope, Wallet, Person, WalletMember, Transaction,
)
from app.services.ledger import post_transaction
from app.notify.whatsapp import send_text

SENDER_FEE_RATE = Decimal("0.05")
SENDER_FEE_CAP  = Decimal("25.00")

def _is_minor(p: Person) -> bool:
    if p.date_of_birth is None:
        return True                       # unverified => treat as minor (R1)
    today = date.today()
    age = today.year - p.date_of_birth.year - (
        (today.month, today.day) < (p.date_of_birth.month, p.date_of_birth.day))
    return age < 18

def create_link(db: Session, envelope_id: uuid.UUID, label: str | None) -> ContributionLink:
    env = db.get(Envelope, envelope_id)
    if env is None or not env.open_to_contributions:
        raise ValueError("envelope not open to contributions")
    wallet = db.get(Wallet, env.wallet_id)
    owner = db.get(Person, wallet.owner_id)
    status = "pending_guardian_approval" if _is_minor(owner) else "active"
    link = ContributionLink(envelope_id=env.id, token=secrets.token_urlsafe(8),
                            label=label, status=status)
    db.add(link); db.commit()
    if status == "pending_guardian_approval":
        for g in db.query(WalletMember).filter_by(wallet_id=wallet.id, role="guardian",
                                                  status="active"):
            gp = db.get(Person, g.person_id)
            send_text(gp.phone_e164,
                      f"{owner.full_name} wants to open '{env.name}' for contributions. "
                      f"Approve: /links/{link.token}/approve")
    return link

def approve_link(db: Session, token: str) -> ContributionLink:
    link = db.query(ContributionLink).filter_by(token=token).first()
    if link is None:
        raise ValueError("link not found")
    if link.status == "pending_guardian_approval":
        link.status = "active"; db.commit()
    return link

def contribute(db: Session, token: str, amount: Decimal,
               contributor_name: str, contributor_phone: str,
               message: str | None) -> dict:
    link = db.query(ContributionLink).filter_by(token=token).first()
    if link is None or link.status != "active":
        raise ValueError("link not active")
    env = db.get(Envelope, link.envelope_id)
    wallet = db.get(Wallet, env.wallet_id)
    owner = db.get(Person, wallet.owner_id)

    amount = Decimal(amount)
    fee = min((amount * SENDER_FEE_RATE).quantize(Decimal("0.01")), SENDER_FEE_CAP)

    contributor = db.query(Person).filter_by(phone_e164=contributor_phone).first()
    if contributor is None:
        contributor = Person(phone_e164=contributor_phone, full_name=contributor_name)
        db.add(contributor); db.flush()

    # MOCK PSP capture (amount + fee). psp_clearing negative = claim on PSP funds.
    txn = Transaction(kind="contribution", wallet_id=wallet.id, envelope_id=env.id,
                      contributor_id=contributor.id, amount_bwp=amount,
                      status="approved", rail="psp_mock",
                      idempotency_key=f"C-{uuid.uuid4()}")
    post_transaction(db, txn, [
        {"account_type": "psp_clearing", "account_id": None,   "amount_bwp": -(amount + fee)},
        {"account_type": "envelope",     "account_id": env.id, "amount_bwp": amount},
        {"account_type": "platform_fee", "account_id": None,   "amount_bwp": fee},
    ])
    db.commit()

    note = f' - "{message}"' if message else ""
    send_text(owner.phone_e164,
              f"{contributor_name} sent P{amount} to your {env.name} envelope{note}")
    # R2: contributor learns delivery only — no balance, no spending.
    return {"delivered": True, "envelope": env.name, "owner_first_name":
            owner.full_name.split()[0], "amount_bwp": str(amount),
            "fee_bwp": str(fee), "total_charged_bwp": str(amount + fee)}