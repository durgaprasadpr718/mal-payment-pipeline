"""
Canonical Payment Event schema for Mal (multi-product Islamic neobank, UAE).

Design goals:
  - ONE event shape that all three squads (Cards, Transfers, Bill Payments)
    map into, so downstream teams query a single table.
  - Extensible: new payment types need only a new `PaymentType` value + a
    source mapper. The open `attributes` dict absorbs source-specific fields
    without schema migrations.
  - Shariah-aware: Islamic banking earns `profit`/`fee`, never interest, so we
    model `fee_amount` + `is_shariah_compliant` as first-class fields.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "v2"  # current contract version (see schema/versioning.py)


class PaymentType(str, Enum):
    CARD_TRANSACTION = "card_transaction"
    TRANSFER = "transfer"
    BILL_PAYMENT = "bill_payment"
    # add future types here (e.g. WALLET_TOPUP) -> only a mapper is needed


class PaymentStatus(str, Enum):
    """Unified status vocabulary. Each squad's local codes map onto these."""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"


class PaymentMethod(str, Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"
    DIRECT_DEBIT = "direct_debit"
    UNKNOWN = "unknown"


class SourceSystem(str, Enum):
    CARDS = "cards_squad"
    TRANSFERS = "transfers_squad"
    BILL_PAYMENTS = "bill_payments_squad"


class PaymentEvent(BaseModel):
    """The canonical record. Every payment in Mal becomes one of these."""

    # --- identity / lineage ---
    event_id: str = Field(..., description="Mal-wide unique id (uuid)")
    source_event_id: str = Field(..., description="Original id from the squad")
    source_system: SourceSystem
    schema_version: str = SCHEMA_VERSION

    # --- core payment facts ---
    payment_type: PaymentType
    payment_method: PaymentMethod = PaymentMethod.UNKNOWN
    status: PaymentStatus
    amount: Decimal = Field(..., ge=0, description="Principal amount")
    fee_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="AED", min_length=3, max_length=3)

    # --- party ---
    customer_id: str

    # --- Islamic-banking metadata ---
    is_shariah_compliant: bool = True

    # --- time ---
    event_timestamp: datetime = Field(..., description="When the payment occurred (UTC)")
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- extensibility escape hatch (source-specific fields live here) ---
    attributes: dict = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, v: str) -> str:
        return v.upper()

    @field_validator("event_timestamp", "ingested_at")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v.astimezone(timezone.utc)

    def to_row(self) -> dict:
        """Flat dict ready for Parquet / DuckDB (Decimals -> float, enums -> str)."""
        return {
            "event_id": self.event_id,
            "source_event_id": self.source_event_id,
            "source_system": self.source_system.value,
            "schema_version": self.schema_version,
            "payment_type": self.payment_type.value,
            "payment_method": self.payment_method.value,
            "status": self.status.value,
            "amount": float(self.amount),
            "fee_amount": float(self.fee_amount),
            "currency": self.currency,
            "customer_id": self.customer_id,
            "is_shariah_compliant": self.is_shariah_compliant,
            "event_timestamp": self.event_timestamp,
            "ingested_at": self.ingested_at,
            "attributes": str(self.attributes),
        }
