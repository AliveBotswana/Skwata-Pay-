from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.schemas import AuthorizeIn, AuthorizeOut
from app.services.authorize import authorize as run_authorize

router = APIRouter()

@router.post("/authorize", response_model=AuthorizeOut)
def authorize(req: AuthorizeIn, db: Session = Depends(get_db)):
    return run_authorize(db, req)