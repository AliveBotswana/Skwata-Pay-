"""Authorization pipeline — spec section 3. Order matters; fail fast."""
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import (
    Wallet, Person, Envelope, EnvelopeCategory, WalletBlock,
    Merchant, MccCategoryMap, Transaction,
)
from app.core.security import parse_code, verify_code, verify_pin
from app.services.ledger import post_transaction
from app.schemas import AuthorizeIn, AuthorizeOut

BLOCK_ONLY = {"alcohol", "gambling"}

def _out(decision, reason, msg, amount=Decimal("0"), envelope=None, ask=False, auth_id=None):
    return AuthorizeOut(decision=decision, approved_amount_bwp=amount, envelope=envelope,
                        reason_code=reason, display_message=msg,
                        ask_guardian_available=ask, auth_id=auth_id)

def _decline(db, req, wallet_id, envelope_id, merchant_id, reason):
    txn = Transaction(kind="purchase", wallet_id=wallet_id, envelope_id=envelope_id,
                      merchant_id=merchant_id, amount_bwp=req.amount_bwp,
                      status="declined", decline_reason=reason, rail=req.rail,
                      idempotency_key=req.idempotency_key)
    db.add(txn); db.commit()
    return txn

def _replay(txn: Transaction) -> AuthorizeOut:
    if txn.status == "approved":
        return _out("approved", "DUPLICATE", "Already processed",
                    txn.amount_bwp, auth_id=str(txn.id))
    return _out("declined", txn.decline_reason or "DUPLICATE",
                "Already processed (declined)", auth_id=str(txn.id))

def authorize(db: Session, req: AuthorizeIn) -> AuthorizeOut:
    # 0. idempotency replay
    existing = db.query(Transaction).filter_by(idempotency_key=req.idempotency_key).first()
    if existing:
        return _replay(existing)

    # 1. instrument -> wallet
    if req.instrument.type != "barcode":
        return _out("declined", "INVALID_CODE", "Unsupported instrument in this build")
    payload = parse_code(req.instrument.value)
    if payload is None:
        return _out("declined", "INVALID_CODE", "Code unreadable")
    wallet = db.get(Wallet, uuid.UUID(payload["w"])) if _is_uuid(payload.get("w")) else None
    if wallet is None:
        return _out("declined", "INVALID_CODE", "Unknown wallet")
    state = verify_code(payload, wallet.barcode_secret)
    if state == "bad_sig":
        return _out("declined", "INVALID_CODE", "Code signature invalid")
    if state == "expired":
        return _out("declined", "EXPIRED_CODE", "Code expired - refresh and rescan")

    # 2. wallet status
    if wallet.status != "active":
        _decline(db, req, wallet.id, None, None, "WALLET_FROZEN")
        return _out("declined", "WALLET_FROZEN", "Wallet is frozen")

    # 3. resolve category
    merchant = None
    if req.merchant.merchant_id and _is_uuid(req.merchant.merchant_id):
        merchant = db.get(Merchant, uuid.UUID(req.merchant.merchant_id))
    if merchant is not None:
        category = merchant.category
    elif req.merchant.mcc:
        row = db.get(MccCategoryMap, req.merchant.mcc)
        category = row.category if row else "other"
    else:
        category = "other"
    merchant_id = merchant.id if merchant else None

    # 4. hard blocks (before envelope routing; blocks beat everything)
    blocked = {b.category for b in db.query(WalletBlock).filter_by(wallet_id=wallet.id)}
    if category in blocked or category in (BLOCK_ONLY & blocked):
        _decline(db, req, wallet.id, None, merchant_id, "CATEGORY_BLOCKED")
        return _out("declined", "CATEGORY_BLOCKED", f"Blocked category: {category.title()}")

    # 5. PIN tier
    amount = Decimal(req.amount_bwp)
    needs_pin = (amount > wallet.tap_limit_bwp or
                 wallet.cum_tap_spent_bwp + amount > wallet.cum_tap_limit_bwp)
    pin_ok = False
    if needs_pin:
        if not req.pin_provided:
            return _out("pin_required", "PIN_REQUIRED", "Enter PIN to continue", ask=False)
        owner = db.get(Person, wallet.owner_id)
        if not owner.pin_hash or not verify_pin(owner.pin_hash, req.pin_value or ""):
            _decline(db, req, wallet.id, None, merchant_id, "PIN_INVALID")
            return _out("declined", "PIN_INVALID", "Incorrect PIN")
        pin_ok = True

    # 6. envelope routing (most-specific eligible envelope with funds)
    envs = (db.query(Envelope).join(EnvelopeCategory, EnvelopeCategory.envelope_id == Envelope.id)
              .filter(Envelope.wallet_id == wallet.id, EnvelopeCategory.category == category).all())
    if not envs:
        _decline(db, req, wallet.id, None, merchant_id, "NO_ENVELOPE_FOR_CATEGORY")
        return _out("declined", "NO_ENVELOPE_FOR_CATEGORY",
                    f"No envelope covers {category.title()}")
    def specificity(e):
        return db.query(EnvelopeCategory).filter_by(envelope_id=e.id).count()
    funded = sorted([e for e in envs if e.balance_bwp >= amount], key=specificity)
    if not funded:
        _decline(db, req, wallet.id, envs[0].id, merchant_id, "INSUFFICIENT_ENVELOPE")
        return _out("declined", "INSUFFICIENT_ENVELOPE",
                    f"{envs[0].name} envelope short", ask=True)
    env = funded[0]

    # 7. commit (ledger sum = 0)
    commission = (amount * Decimal(merchant.commission_bps if merchant else 250)
                  / Decimal(10000)).quantize(Decimal("0.01"))
    net = amount - commission
    txn = Transaction(kind="purchase", wallet_id=wallet.id, envelope_id=env.id,
                      merchant_id=merchant_id, amount_bwp=amount, status="approved",
                      rail=req.rail, idempotency_key=req.idempotency_key,
                      pin_verified=pin_ok)
    post_transaction(db, txn, [
        {"account_type": "envelope",         "account_id": env.id,      "amount_bwp": -amount},
        {"account_type": "merchant_payable", "account_id": merchant_id, "amount_bwp": net},
        {"account_type": "platform_fee",     "account_id": None,        "amount_bwp": commission},
    ])
    if pin_ok:
        wallet.cum_tap_spent_bwp = Decimal("0")
    else:
        wallet.cum_tap_spent_bwp = wallet.cum_tap_spent_bwp + amount
    db.commit()

    # 8. notify (async in commit 3 — WhatsApp module)
    return _out("approved", "APPROVED", f"Paid from {env.name}",
                amount, envelope=env.name, auth_id=str(txn.id))

def _is_uuid(v) -> bool:
    try:
        uuid.UUID(str(v)); return True
    except Exception:
        return False