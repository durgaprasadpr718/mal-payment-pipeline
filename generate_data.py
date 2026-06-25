"""
generate_data.py - synthetic payment data generator (stdlib only, no licenses).

Produces the three squads' CSVs at any volume, in their native (inconsistent)
formats, with UAE / Islamic-banking realism. Deliberately injects:
  - a small % of BAD rows per source  -> exercises validation + compliance %
  - one low-volume "anomaly day"       -> exercises dashboard anomaly detection
  - a small % of empty customer ids    -> a schema-valid but DQ-flagged issue

Usage:
  python generate_data.py                # default 5000 rows over 30 days
  python generate_data.py --rows 20000 --days 45 --bad-rate 0.03 --seed 7
"""
from __future__ import annotations

import argparse
import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

INPUT = Path(__file__).parent / "input"
INPUT.mkdir(exist_ok=True)

# --- UAE-flavoured reference pools ------------------------------------------
MERCHANTS = [
    ("Carrefour Dubai", 5411), ("Lulu Hypermarket", 5411), ("Noon.com", 5942),
    ("Amazon.ae", 5999), ("Talabat", 5814), ("Deliveroo UAE", 5814),
    ("Careem", 4121), ("ADNOC Station", 5541), ("Apple Store UAE", 5732),
    ("IKEA UAE", 5712), ("Namshi", 5651), ("Sharaf DG", 5732),
]
FX_MERCHANTS = [("Amazon US", "USD", 5999), ("Booking.com", "EUR", 4722),
                ("AliExpress", "USD", 5999), ("Steam", "USD", 5816)]
BILLERS = [
    ("DEWA", "UTILITIES"), ("SEWA", "UTILITIES"), ("ADDC", "UTILITIES"),
    ("ETISALAT", "TELECOM"), ("DU", "TELECOM"), ("SALIK", "TOLL"),
    ("RTA_FINES", "GOVERNMENT"), ("Empower", "UTILITIES"),
]
PURPOSE = ["GIFT", "FAMILY_SUPPORT", "SPLIT_BILL", "RENT", "PROPERTY", "SALARY"]
CUSTOMERS = [f"CUST-{1000 + i}" for i in range(300)]

CARD_STATUS = ["SETTLED"] * 80 + ["AUTH"] * 10 + ["DECLINED"] * 7 + ["REVERSED"] * 3
TRF_STATUS = ["SUCCESS"] * 82 + ["INITIATED"] * 8 + ["FAILED"] * 7 + ["REVERSED"] * 3
BILL_STATUS = ["1"] * 85 + ["0"] * 8 + ["2"] * 7  # 1=completed 0=pending 2=failed


def _ts_pool(days: int, n: int, anomaly_day: int) -> list[datetime]:
    """Timestamps spread over `days`, with one day deliberately under-weighted."""
    now = datetime.now(timezone.utc)
    out = []
    for _ in range(n):
        d = random.randint(0, days - 1)
        # collapse most events away from the anomaly day to create a volume dip
        if d == anomaly_day and random.random() < 0.8:
            d = random.randint(0, days - 1)
        out.append(now - timedelta(days=d, hours=random.randint(0, 23),
                                   minutes=random.randint(0, 59)))
    return out


def gen_cards(n: int, days: int, bad_rate: float, anomaly_day: int):
    rows, ts = [], _ts_pool(days, n, anomaly_day)
    for i in range(n):
        bad = random.random() < bad_rate
        if random.random() < 0.08:                      # FX transaction
            name, ccy, mcc = random.choice(FX_MERCHANTS)
        else:
            name, mcc = random.choice(MERCHANTS); ccy = "AED"
        amt = round(random.uniform(5, 4000), 2)
        rows.append({
            "txn_id": f"CARD-{90000 + i}",
            "card_holder_id": random.choice(CUSTOMERS),
            "txn_amount": -amt if bad else amt,         # bad: negative amount
            "txn_currency": ccy,
            "txn_status": "BOGUS" if bad and random.random() < 0.5
                          else random.choice(CARD_STATUS),
            "merchant_name": name,
            "card_last4": f"{random.randint(0, 9999):04d}",
            "mcc": mcc,
            "txn_epoch": int(ts[i].timestamp()),
        })
    return rows


def gen_transfers(n: int, days: int, bad_rate: float, anomaly_day: int):
    rows, ts = [], _ts_pool(days, n, anomaly_day)
    for i in range(n):
        bad = random.random() < bad_rate
        ttype = random.choice(["P2P", "IBAN"])
        receiver = (f"EXT-IBAN-{random.randint(100, 999)}" if ttype == "IBAN"
                    else random.choice(CUSTOMERS))
        sender = random.choice(CUSTOMERS)
        rows.append({
            "transfer_reference": f"TRF-{50000 + i}",
            # ~2% empty sender: passes schema, flagged as DQ issue downstream
            "sender_id": "" if random.random() < 0.02 else sender,
            "receiver_id": receiver,
            "value": -1 if bad else round(random.uniform(50, 30000), 2),
            "ccy": "AED",
            "state": "WEIRD" if bad and random.random() < 0.5
                     else random.choice(TRF_STATUS),
            "transfer_type": ttype,
            "purpose_code": random.choice(PURPOSE),
            "created_at": ts[i].strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows


def gen_bills(n: int, days: int, bad_rate: float, anomaly_day: int):
    rows, ts = [], _ts_pool(days, n, anomaly_day)
    for i in range(n):
        bad = random.random() < bad_rate
        biller, cat = random.choice(BILLERS)
        rows.append({
            "id": f"BILL-{70000 + i}",
            "user": random.choice(CUSTOMERS),
            "paid_amount": round(random.uniform(20, 3000), 2),
            "currency_code": "AED",
            "payment_status": "9" if bad else random.choice(BILL_STATUS),  # 9=unknown
            "biller_id": biller,
            "biller_category": cat,
            "channel": random.choice(["APP", "WEB"]),
            "timestamp": ts[i].strftime("%d/%m/%Y %H:%M"),
        })
    return rows


def write(path: Path, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5000, help="total rows across squads")
    ap.add_argument("--days", type=int, default=30, help="date range to spread over")
    ap.add_argument("--bad-rate", type=float, default=0.02, help="fraction of bad rows")
    ap.add_argument("--seed", type=int, default=42)
    a = ap.parse_args()
    random.seed(a.seed)

    # split: cards 50%, transfers 25%, bills 25% (realistic for a card-led neobank)
    n_card, n_trf = int(a.rows * 0.5), int(a.rows * 0.25)
    n_bill = a.rows - n_card - n_trf
    anomaly = a.days // 2  # the "dip" day sits mid-range

    write(INPUT / "cards_raw.csv", gen_cards(n_card, a.days, a.bad_rate, anomaly))
    write(INPUT / "transfers_raw.csv", gen_transfers(n_trf, a.days, a.bad_rate, anomaly))
    write(INPUT / "bill_payments_raw.csv", gen_bills(n_bill, a.days, a.bad_rate, anomaly))

    print(f"Generated {n_card} card / {n_trf} transfer / {n_bill} bill rows "
          f"over {a.days} days (bad-rate {a.bad_rate:.0%}, anomaly day = "
          f"{a.days - anomaly} days ago).")


if __name__ == "__main__":
    main()
