"""
Data contract versioning: a worked v1 -> v2 migration.

Versioning rule of thumb used across Mal:
  NON-BREAKING (minor bump, e.g. v1.0 -> v1.1):
    - adding an OPTIONAL field with a default
    - adding a new enum value
    - widening a type
  BREAKING (major bump, e.g. v1 -> v2):
    - removing/renaming a field
    - making an optional field required
    - changing a field's type or semantics

What changed v1 -> v2 (this is a BREAKING change, hence the major bump):
  - renamed `txn_amount`        -> `amount`
  - made `fee_amount`           a NEW required-with-default field
  - added `is_shariah_compliant` (required, defaults True)
  - `status` moved from free text -> the PaymentStatus enum vocabulary

Old v1 records on disk stay readable: `migrate_v1_to_v2` upgrades them in
place so the lake holds a single current shape. Producers are migrated one
squad at a time (see docs/architecture_strategy.md, Phased Migration Plan).
"""
from __future__ import annotations

from decimal import Decimal

# A frozen example of the OLD contract, kept for documentation / tests.
V1_EXAMPLE = {
    "event_id": "evt-001",
    "source_event_id": "card-9001",
    "source_system": "cards_squad",
    "schema_version": "v1",
    "payment_type": "card_transaction",
    "txn_amount": "120.50",          # renamed in v2
    "currency": "AED",
    "customer_id": "cust-1",
    "status": "SETTLED",             # free text in v1
    "event_timestamp": "2026-06-01T10:00:00Z",
}

_V1_STATUS_MAP = {
    "SETTLED": "completed", "AUTH": "pending", "DECLINED": "failed",
    "SUCCESS": "completed", "REVERSED": "reversed",
}


def migrate_v1_to_v2(record: dict) -> dict:
    """Upgrade a single v1 record to the v2 contract shape (non-destructive)."""
    r = dict(record)
    r["amount"] = r.pop("txn_amount", r.get("amount", "0"))   # rename
    r["fee_amount"] = r.get("fee_amount", str(Decimal("0")))  # backfill default
    r["is_shariah_compliant"] = r.get("is_shariah_compliant", True)
    r["status"] = _V1_STATUS_MAP.get(str(r.get("status", "")).upper(),
                                     str(r.get("status", "pending")).lower())
    r["payment_method"] = r.get("payment_method", "card")
    r["schema_version"] = "v2"
    return r


if __name__ == "__main__":
    import json
    print(json.dumps(migrate_v1_to_v2(V1_EXAMPLE), indent=2))
