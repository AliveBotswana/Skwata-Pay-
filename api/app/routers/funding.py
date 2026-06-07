from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.services import funding

router = APIRouter(prefix="/fund")

class InitiateIn(BaseModel):
    link_token: str
    amount_bwp: Decimal
    funder_name: str
    funder_phone: str
    message: str | None = None

@router.post("/initiate")
def initiate(body: InitiateIn, db: Session = Depends(get_db)):
    try:
        return funding.initiate(db, body.link_token, body.amount_bwp,
                                body.funder_name, body.funder_phone, body.message)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.post("/tingg/callback")
async def tingg_callback(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    # TODO before live: verify per Tingg webhook security doc
    # (signature header / IP allowlist) - confirm mechanism with Cellulant.
    return funding.handle_callback(db, payload)

@router.post("/mock/callback")
def mock_callback(payload: dict, db: Session = Depends(get_db)):
    return funding.handle_callback(db, payload)

@router.get("/result")
def result(ref: str, s: int):
    return {"reference": ref, "outcome": "success" if s == 1 else "failed",
            "note": "redirect landing for funder browser; UI replaces this"}