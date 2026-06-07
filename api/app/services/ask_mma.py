"""Ask-Mma: payment request -> guardian approval -> top-up + purchase, atomically."""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import (
    PaymentRequest, Wallet, Person, WalletMember, Merchant,
    Envelope, EnvelopeCategory, Transaction,
)
from app.services.ledger import post_transaction
from app.notify.whatsapp import send_text

TTL = timedelta(minutes=5)

def _best_envelope(db, wallet_id, category):
    envs = (db.query(Envelope).join(EnvelopeCategory,
            EnvelopeCategory.envelope_id == Envelope.id)
            .filter(Envelope.wallet_id == wallet_id,
                    EnvelopeCategory.category == category).all())
    return max(envs, key=lambda e: e.balance_bwp) if envs else None

def create_request(db: Session, wallet_id: uuid.UUID, merchant_id: uuid.UUID,
                   amount: Decimal) -> PaymentRequest:
    wallet = db.get(Wallet, wallet_id)
    merchant = db.get(Merchant, merchant_id)
    if wallet is None or merchant is None:
        raise ValueError("wallet or merchant not found")
    guardian = (db.query(WalletMember)
                .filter_by(wallet_id=wallet.id, role="guardian", status="active").first())
    if guardian is None:
        raise ValueError("no guardian on wallet")
    env = _best_envelope(db, wallet.id, merchant.category)
    shortfall = (Decimal(amount) - (env.balance_bwp if env else Decimal("0"))
                 ).quantize(Decimal("0.01"))
    if shortfall <= 0:
        raise ValueError("no shortfall - pay normally")
    pr = PaymentRequest(wallet_id=wallet.id, guardian_id=guardian.person_id,
                        merchant_id=merchant.id, amount_bwp=Decimal(amount),
                        shortfall_bwp=shortfall)
    db.add(pr); db.commit()
    owner = db.get(Person, wallet.owner_id)
    gp = db.get(Person, guardian.person_id)
    send_text(gp.phone_e164,
              f"{owner.full_name} is at {merchant.display_name} - P{amount} "
              f"(short P{shortfall}). Approve: /payment-requests/{pr.id}/approve")
    return pr

def _expire_if_old(db, pr: PaymentRequest):
    created = pr.created_at if pr.created_at.tzinfo else pr.created_at.replace(tzinfo=timezone.utc)
    if pr.status == "pending" and datetime.now(timezone.utc) - created > TTL:
        pr.status = "expired"; db.commit()

def get_request(db: Session, pr_id: uuid.UUID) -> PaymentRequest | None:
    pr = db.get(PaymentRequest, pr_id)
    if pr:
        _expire_if_old(db, pr)
    return pr

def approve(db: Session, pr_id: uuid.UUID) -> PaymentRequest:
    pr = db.get(PaymentRequest, pr_id)
    if pr is None:
        raise ValueError("request not found")
    _expire_if_old(db, pr)
    if pr.status != "pending":
        return pr                                   # idempotent
    wallet = db.get(Wallet, pr.wallet_id)
    merchant = db.get(Merchant, pr.merchant_id)
    env = _best_envelope(db, wallet.id, merchant.category)
    if env is None:
        pr.status = "declined"; db.commit(); return pr

    # 1) guardian top-up of the shortfall (mock PSP capture)
    topup = Transaction(kind="topup", wallet_id=wallet.id, envelope_id=env.id,
                        contributor_id=pr.guardian_id, amount_bwp=pr.shortfall_bwp,
                        status="approved", rail="psp_mock",
                        idempotency_key=f"PRT-{pr.id}")
    post_transaction(db, topup, [
        {"account_type": "psp_clearing", "account_id": None,   "amount_bwp": -pr.shortfall_bwp},
        {"account_type": "envelope",     "account_id": env.id, "amount_bwp": pr.shortfall_bwp},
    ])
    # 2) the purchase itself (same commission math as authorize step 7)
    commission = (pr.amount_bwp * Decimal(merchant.commission_bps)
                  / Decimal(10000)).quantize(Decimal("0.01"))
    purchase = Transaction(kind="purchase", wallet_id=wallet.id, envelope_id=env.id,
                           merchant_id=merchant.id, amount_bwp=pr.amount_bwp,
                           status="approved", rail="sticker",
                           idempotency_key=f"PRP-{pr.id}")
    post_transaction(db, purchase, [
        {"account_type": "envelope",         "account_id": env.id,      "amount_bwp": -pr.amount_bwp},
        {"account_type": "merchant_payable", "account_id": merchant.id, "amount_bwp": pr.amount_bwp - commission},
        {"account_type": "platform_fee",     "account_id": None,        "amount_bwp": commission},
    ])
    pr.status = "approved"; pr.txn_id = purchase.id
    db.commit()
    owner = db.get(Person, wallet.owner_id)
    send_text(owner.phone_e164,
              f"Mma approved P{pr.amount_bwp} at {merchant.display_name}. Paid.")
    return pr