import uuid
from datetime import datetime, date
from sqlalchemy import (
    Column, Text, Boolean, Date, DateTime, Numeric, SmallInteger,
    BigInteger, ForeignKey, UniqueConstraint, CheckConstraint, CHAR
)
from sqlalchemy.dialects.postgresql import UUID
from app.core.db import Base

def uid():
    return uuid.uuid4()

class Person(Base):
    __tablename__ = "persons"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    phone_e164 = Column(Text, unique=True, nullable=False)
    full_name = Column(Text, nullable=False)
    date_of_birth = Column(Date)            # NULL => treat as minor (rule R1)
    pin_hash = Column(Text)                 # argon2
    kyc_level = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Wallet(Base):
    __tablename__ = "wallets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False)
    status = Column(Text, nullable=False, default="active")  # active|frozen|closed
    tap_limit_bwp = Column(Numeric(10, 2), nullable=False, default=200)
    cum_tap_limit_bwp = Column(Numeric(10, 2), nullable=False, default=500)
    cum_tap_spent_bwp = Column(Numeric(10, 2), nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class WalletMember(Base):
    __tablename__ = "wallet_members"
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), primary_key=True)
    person_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), primary_key=True)
    role = Column(Text, primary_key=True)   # guardian|contributor
    status = Column(Text, nullable=False, default="active")  # pending_guardian_approval|active|revoked
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class Envelope(Base):
    __tablename__ = "envelopes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)
    name = Column(Text, nullable=False)
    balance_bwp = Column(Numeric(12, 2), nullable=False, default=0)
    open_to_contributions = Column(Boolean, nullable=False, default=False)
    rule_set_by = Column(UUID(as_uuid=True), ForeignKey("persons.id"))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    __table_args__ = (CheckConstraint("balance_bwp >= 0", name="ck_envelope_nonneg"),)

class EnvelopeCategory(Base):
    __tablename__ = "envelope_categories"
    envelope_id = Column(UUID(as_uuid=True), ForeignKey("envelopes.id"), primary_key=True)
    category = Column(Text, primary_key=True)

class WalletBlock(Base):
    __tablename__ = "wallet_blocks"
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), primary_key=True)
    category = Column(Text, primary_key=True)
    set_by = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False)

class Merchant(Base):
    __tablename__ = "merchants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    display_name = Column(Text, nullable=False)
    raw_descriptor = Column(Text)
    category = Column(Text, nullable=False)
    mcc = Column(CHAR(4))
    places_id = Column(Text)
    rail = Column(Text, nullable=False, default="sticker")   # sticker|card|retail_pos
    payout_method = Column(Text, nullable=False, default="orange_money")
    payout_ref = Column(Text, nullable=False, default="")
    settlement_policy = Column(Text, nullable=False, default="weekly")
    commission_bps = Column(SmallInteger, nullable=False, default=250)
    kyc_level = Column(SmallInteger, nullable=False, default=1)
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class MccCategoryMap(Base):
    __tablename__ = "mcc_category_map"
    mcc = Column(CHAR(4), primary_key=True)
    category = Column(Text, nullable=False)
    confidence = Column(Text, nullable=False, default="high")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    kind = Column(Text, nullable=False)  # purchase|topup|contribution|payout|refund|reversal|adjustment
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"))
    envelope_id = Column(UUID(as_uuid=True), ForeignKey("envelopes.id"))
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"))
    contributor_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"))
    amount_bwp = Column(Numeric(12, 2), nullable=False)
    status = Column(Text, nullable=False)  # approved|declined|pending_guardian|settled|refunded
    decline_reason = Column(Text)
    rail = Column(Text, nullable=False, default="sticker")
    external_ref = Column(Text)
    idempotency_key = Column(Text, unique=True)
    pin_verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class LedgerEntry(Base):
    __tablename__ = "ledger_entries"
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    txn_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    account_type = Column(Text, nullable=False)  # envelope|merchant_payable|platform_fee|psp_clearing|trust_float
    account_id = Column(UUID(as_uuid=True))
    amount_bwp = Column(Numeric(12, 2), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class ContributionLink(Base):
    __tablename__ = "contribution_links"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    envelope_id = Column(UUID(as_uuid=True), ForeignKey("envelopes.id"), nullable=False)
    token = Column(Text, unique=True, nullable=False)
    label = Column(Text)
    fixed_amount_bwp = Column(Numeric(10, 2))
    schedule = Column(Text)                 # NULL one-off | monthly
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class PaymentRequest(Base):
    __tablename__ = "payment_requests"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    wallet_id = Column(UUID(as_uuid=True), ForeignKey("wallets.id"), nullable=False)
    guardian_id = Column(UUID(as_uuid=True), ForeignKey("persons.id"), nullable=False)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"))
    amount_bwp = Column(Numeric(10, 2), nullable=False)
    shortfall_bwp = Column(Numeric(10, 2))
    status = Column(Text, nullable=False, default="pending")  # pending|approved|declined|expired
    txn_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

class SettlementBatch(Base):
    __tablename__ = "settlement_batches"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uid)
    merchant_id = Column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    gross_bwp = Column(Numeric(12, 2))
    commission_bwp = Column(Numeric(12, 2))
    net_bwp = Column(Numeric(12, 2))
    payout_status = Column(Text, nullable=False, default="pending")
    payout_ref = Column(Text)
    paid_at = Column(DateTime(timezone=True))