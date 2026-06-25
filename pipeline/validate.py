"""
Validate step: turn a raw row + its mapper into either a valid PaymentEvent
or a structured rejection. Nothing crashes the whole run; bad rows are
quarantined with a reason so we can report a per-source compliance rate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from pydantic import ValidationError

from schema.canonical import PaymentEvent


@dataclass
class Rejection:
    source_system: str
    source_event_id: str
    reason: str
    raw: dict


@dataclass
class ValidationResult:
    valid: list[PaymentEvent] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)

    @property
    def compliance_rate(self) -> float:
        total = len(self.valid) + len(self.rejected)
        return (len(self.valid) / total) if total else 0.0


def validate_rows(rows: list[dict], mapper: Callable, source: str) -> ValidationResult:
    result = ValidationResult()
    for row in rows:
        try:
            result.valid.append(mapper(row))
        except (ValidationError, KeyError, ValueError) as exc:
            sid = row.get("id") or row.get("txn_id") or row.get(
                "transfer_reference", "UNKNOWN")
            result.rejected.append(
                Rejection(source, str(sid), f"{type(exc).__name__}: {exc}", row))
    return result
