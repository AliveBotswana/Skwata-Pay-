"""Dev/demo admin: reset + reseed, mint a fresh code for a wallet."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.db import get_db
from app.core.config import settings
from app.core.security import mint_code
from app.models.models import Wallet
from app.services.seeds import seed
import uuid

router = APIRouter(prefix="/admin")

def _guard(token: str | None):
    if token != settings.ADMIN_RESET_TOKEN:
        raise HTTPException(403, "bad admin token")

@router.post("/reset")
def reset(x_admin_token: str | None = Header(None), db: Session = Depends(get_db)):
    _guard(x_admin_token)
    db.execute(text("""
        TRUNCATE ledger_entries, transactions, payment_requests, settlement_batches,
                 contribution_links, envelope_categories, envelopes, wallet_blocks,
                 wallet_members, wallets, merchants, mcc_category_map, persons
        RESTART IDENTITY CASCADE
    """))
    db.commit()
    return {"reset": True, "seed": seed(db)}

@router.get("/mint/{wallet_id}")
def mint(wallet_id: str, x_admin_token: str | None = Header(None), db: Session = Depends(get_db)):
    _guard(x_admin_token)
    w = db.get(Wallet, uuid.UUID(wallet_id))
    if not w:
        raise HTTPException(404, "wallet not found")
    return {"code": mint_code(str(w.id), w.barcode_secret)}