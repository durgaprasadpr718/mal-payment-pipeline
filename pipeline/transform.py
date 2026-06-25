"""
Transform step: map each squad's raw row -> a canonical PaymentEvent.

Each squad has a different field vocabulary, status codes and timestamp format.
A mapper is the ONLY thing a new source needs to onboard, so this file is where
"platform reuse" actually pays off: downstream never sees these differences.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from schema.canonical import (
    PaymentEvent, PaymentMethod, PaymentStatus, PaymentType, SourceSystem,
)


def _eid() -> str:
    return f"evt-{uuid.uuid4().hex[:12]}"


# --- status vocabularies, one per squad, all -> PaymentStatus ---------------
_CARD_STATUS = {
    "SETTLED": PaymentStatus.COMPLETED, "AUTH": PaymentStatus.PENDING,
    "DECLINED": PaymentStatus.FAILED, "REVERSED": PaymentStatus.REVERSED,
}
_TRANSFER_STATUS = {
    "SUCCESS": PaymentStatus.COMPLETED, "INITIATED": PaymentStatus.PENDING,
    "FAILED": PaymentStatus.FAILED, "REVERSED": PaymentStatus.REVERSED,
}
_BILL_STATUS = {  # bill squad uses numeric codes
    "1": PaymentStatus.COMPLETED, "0": PaymentStatus.PENDING,
    "2": PaymentStatus.FAILED,
}


def map_card(row: dict) -> PaymentEvent:
    ts = datetime.fromtimestamp(int(row["txn_epoch"]), tz=timezone.utc)
    return PaymentEvent(
        event_id=_eid(),
        source_event_id=row["txn_id"],
        source_system=SourceSystem.CARDS,
        payment_type=PaymentType.CARD_TRANSACTION,
        payment_method=PaymentMethod.CARD,
        status=_CARD_STATUS[row["txn_status"].upper()],
        amount=Decimal(row["txn_amount"]),
        currency=row["txn_currency"],
        customer_id=row["card_holder_id"],
        event_timestamp=ts,
        attributes={
            "merchant_name": row["merchant_name"],
            "card_last4": row["card_last4"],
            "mcc": row["mcc"],
        },
    )


def map_transfer(row: dict) -> PaymentEvent:
    ts = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    return PaymentEvent(
        event_id=_eid(),
        source_event_id=row["transfer_reference"],
        source_system=SourceSystem.TRANSFERS,
        payment_type=PaymentType.TRANSFER,
        payment_method=PaymentMethod.BANK_TRANSFER,
        status=_TRANSFER_STATUS[row["state"].upper()],
        amount=Decimal(row["value"]),
        currency=row["ccy"],
        customer_id=row["sender_id"],
        event_timestamp=ts,
        attributes={
            "receiver_id": row["receiver_id"],
            "transfer_type": row["transfer_type"],
            "purpose_code": row["purpose_code"],
        },
    )


def map_bill(row: dict) -> PaymentEvent:
    ts = datetime.strptime(row["timestamp"], "%d/%m/%Y %H:%M")
    return PaymentEvent(
        event_id=_eid(),
        source_event_id=row["id"],
        source_system=SourceSystem.BILL_PAYMENTS,
        payment_type=PaymentType.BILL_PAYMENT,
        payment_method=PaymentMethod.DIRECT_DEBIT,
        status=_BILL_STATUS[row["payment_status"]],
        amount=Decimal(row["paid_amount"]),
        currency=row["currency_code"],
        customer_id=row["user"],
        event_timestamp=ts,
        attributes={
            "biller_id": row["biller_id"],
            "biller_category": row["biller_category"],
            "channel": row["channel"],
        },
    )


# registry: source name -> (csv path key, mapper). Add a row to onboard a squad.
MAPPERS = {
    SourceSystem.CARDS: map_card,
    SourceSystem.TRANSFERS: map_transfer,
    SourceSystem.BILL_PAYMENTS: map_bill,
}
