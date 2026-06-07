import uuid
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services import contributions, ask_mma

router = APIRouter()

class LinkIn(BaseModel):
    envelope_id: str
    label: str | None = None

class ContributeIn(BaseModel):
    amount_bwp: Decimal
    contributor_name: str
    contributor_phone: str
    message: str | None = None

class RequestIn(BaseModel):
    wallet_id: str
    merchant_id: str
    amount_bwp: Decimal

def _try(fn):
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/links")
def create_link(body: LinkIn, db: Session = Depends(get_db)):
    link = _try(lambda: contributions.create_link(db, uuid.UUID(body.envelope_id), body.label))
    return {"token": link.token, "status": link.status}

@router.post("/links/{token}/approve")
def approve_link(token: str, db: Session = Depends(get_db)):
    link = _try(lambda: contributions.approve_link(db, token))
    return {"token": link.token, "status": link.status}

@router.post("/contribute/{token}")
def contribute(token: str, body: ContributeIn, db: Session = Depends(get_db)):
    return _try(lambda: contributions.contribute(
        db, token, body.amount_bwp, body.contributor_name,
        body.contributor_phone, body.message))

@router.post("/payment-requests")
def create_request(body: RequestIn, db: Session = Depends(get_db)):
    pr = _try(lambda: ask_mma.create_request(
        db, uuid.UUID(body.wallet_id), uuid.UUID(body.merchant_id), body.amount_bwp))
    return {"id": str(pr.id), "status": pr.status, "shortfall_bwp": str(pr.shortfall_bwp)}

@router.get("/payment-requests/{pr_id}")
def poll_request(pr_id: str, db: Session = Depends(get_db)):
    pr = ask_mma.get_request(db, uuid.UUID(pr_id))
    if pr is None:
        raise HTTPException(404, "not found")
    return {"id": str(pr.id), "status": pr.status,
            "txn_id": str(pr.txn_id) if pr.txn_id else None}

@router.post("/payment-requests/{pr_id}/approve")
def approve_request(pr_id: str, db: Session = Depends(get_db)):
    pr = _try(lambda: ask_mma.approve(db, uuid.UUID(pr_id)))
    return {"id": str(pr.id), "status": pr.status,
            "txn_id": str(pr.txn_id) if pr.txn_id else None}