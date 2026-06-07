from fastapi import FastAPI
from app.core.db import Base, engine
from app.models import models  # noqa: F401  (register tables)

app = FastAPI(title="Skwata Pay Kernel", version="0.1.0")

@app.on_event("startup")
def startup():
    # Dev convenience; Alembic takes over before anything touches Railway.
    Base.metadata.create_all(bind=engine)

@app.get("/health")
def health():
    return {"status": "ok", "service": "skwata-pay-kernel"}