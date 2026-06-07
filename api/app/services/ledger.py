"""Ledger service: the ONLY way money moves. Enforces double-entry Sum=0."""
import uuid
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.models import LedgerEntry, Transaction, Envelope

class LedgerImbalance(Exception):
    pass

def post_transaction(db: Session, txn: Transaction, entries: list[dict]) -> Transaction:
    """
    entries: [{account_type, account_id, amount_bwp}, ...]  signed Decimals.
    Writes transaction + entries atomically; refuses if Sum != 0.
    Envelope cache balances are adjusted here and only here.
    """
    total = sum(Decimal(str(e["amount_bwp"])) for e in entries)
    if total != Decimal("0"):
        raise LedgerImbalance(f"entries sum to {total}, must be 0")

    db.add(txn)
    db.flush()  # txn.id available

    for e in entries:
        db.add(LedgerEntry(
            txn_id=txn.id,
            account_type=e["account_type"],
            account_id=e.get("account_id"),
            amount_bwp=Decimal(str(e["amount_bwp"])),
        ))
        if e["account_type"] == "envelope" and e.get("account_id") is not None:
            env = db.get(Envelope, e["account_id"], with_for_update=True)
            if env is None:
                raise LedgerImbalance("envelope not found for ledger entry")
            new_balance = env.balance_bwp + Decimal(str(e["amount_bwp"]))
            if new_balance < 0:
                raise LedgerImbalance("envelope balance would go negative")
            env.balance_bwp = new_balance

    return txn

def new_txn_id() -> uuid.UUID:
    return uuid.uuid4()