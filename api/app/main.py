from fastapi import FastAPI
from app.core.db import Base, engine
from app.models import models  # noqa: F401
from app.routers.authorize import router as authorize_router
from app.routers.admin import router as admin_router

app = FastAPI(title="Skwata Pay Kernel", version="0.2.0")
app.include_router(authorize_router)
app.include_router(admin_router)

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok", "service": "skwata-pay-kernel"}