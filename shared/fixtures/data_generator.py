"""
Synthetic data generator for demo/testing.
Produces customers.csv and orders.csv with realistic data, intentional quality issues,
and a 1:many FK relationship (orders.customer_id -> customers.customer_id).

Usage:
    python3 -m shared.fixtures.data_generator --customers 50 --orders 150 --seed 42
    python3 shared/fixtures/data_generator.py --customers 50 --orders 150 --seed 42
"""

import argparse
import csv
import os
import random
import string
from datetime import date, timedelta
from pathlib import Path

FIRST_NAMES = [
    "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
    "David", "Elizabeth", "William", "Barbara", "Richard", "Susan", "Joseph", "Jessica",
    "Thomas", "Sarah", "Charles", "Karen", "Christopher", "Lisa", "Daniel", "Nancy",
    "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Steven", "Kimberly", "Paul", "Emily", "Andrew", "Donna", "Joshua", "Michelle",
    "Kenneth", "Carol", "Kevin", "Amanda", "Brian", "Dorothy", "George", "Melissa",
    "Timothy", "Deborah", "Ronald", "Stephanie", "Edward", "Rebecca", "Jason", "Sharon",
    "Jeffrey", "Laura", "Ryan", "Cynthia",
]

LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson",
    "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Perez", "Thompson",
    "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker",
    "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
]

COUNTRIES = {"US": 0.60, "UK": 0.20, "CA": 0.10, "DE": 0.10}
SEGMENTS = {"Enterprise": 0.20, "SMB": 0.50, "Individual": 0.30}
STATUSES_CUSTOMER = {"Active": 0.85, "Inactive": 0.10, "Churned": 0.05}
INDUSTRIES = [
    "Technology", "Healthcare", "Finance", "Retail", "Manufacturing",
    "Education", "Energy", "Media", "Real Estate", "Logistics",
]

PRODUCTS = {
    "Electronics": [
        ("Laptop Pro 15", 899.99), ("Wireless Mouse", 29.99), ("USB-C Hub", 49.99),
        ("Monitor 27in", 349.99), ("Keyboard Mechanical", 79.99), ("Webcam HD", 59.99),
        ("Headphones Noise-Cancel", 199.99), ("Tablet 10in", 449.99),
        ("External SSD 1TB", 89.99), ("Smart Speaker", 39.99),
    ],
    "Furniture": [
        ("Standing Desk", 599.99), ("Ergonomic Chair", 449.99), ("Bookshelf Oak", 199.99),
        ("Filing Cabinet", 149.99), ("Desk Lamp LED", 34.99), ("Monitor Stand", 44.99),
        ("Whiteboard 4x3", 89.99), ("Conference Table", 799.99),
    ],
    "Supplies": [
        ("Paper Ream A4", 8.99), ("Pen Pack 12", 5.99), ("Sticky Notes 6pk", 4.99),
        ("Binder Clips 100ct", 6.99), ("Printer Ink Black", 24.99),
        ("Folders Manila 50pk", 12.99), ("Tape Dispenser", 7.99),
        ("Stapler Heavy Duty", 15.99), ("Envelopes 100ct", 9.99),
    ],
}

REGIONS = {"East": 0.30, "West": 0.25, "Central": 0.25, "South": 0.20}
ORDER_STATUSES = {"Completed": 0.80, "Pending": 0.15, "Cancelled": 0.05}

ANNUAL_VALUE_RANGES = {
    "Enterprise": (50_000, 500_000),
    "SMB": (5_000, 50_000),
    "Individual": (500, 5_000),
}


def _weighted_choice(rng, distribution):
    """Pick a key from a {key: probability} dict."""
    keys = list(distribution.keys())
    weights = list(distribution.values())
    return rng.choices(keys, weights=weights, k=1)[0]


def _random_date(rng, start, end):
    """Random date between start and end (inclusive)."""
    delta = (end - start).days
    return start + timedelta(days=rng.randint(0, delta))


def generate_customers(n=50, seed=42):
    """Generate n customer records with intentional quality issues."""
    rng = random.Random(seed)
    rows = []

    for i in range(1, n + 1):
        cid = f"CUST-{i:03d}"
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)
        name = f"{first} {last}"

        # 10% null emails
        if rng.random() < 0.10:
            email = ""
        else:
            email = f"{first.lower()}.{last.lower()}{rng.randint(1,99)}@example.com"

        phone = f"(555) {rng.randint(100,999)}-{rng.randint(1000,9999)}"
        segment = _weighted_choice(rng, SEGMENTS)
        country = _weighted_choice(rng, COUNTRIES)
        industry = rng.choice(INDUSTRIES)
        status = _weighted_choice(rng, STATUSES_CUSTOMER)
        join_date = _random_date(rng, date(2022, 1, 1), date(2025, 6, 30))

        lo, hi = ANNUAL_VALUE_RANGES[segment]
        annual_value = round(rng.uniform(lo, hi), 2)

        credit_limit = round(annual_value * rng.uniform(0.3, 1.5), 2)

        rows.append({
            "customer_id": cid,
            "name": name,
            "email": email,
            "phone": phone,
            "segment": segment,
            "industry": industry,
            "country": country,
            "status": status,
            "join_date": join_date.isoformat(),
            "annual_value": annual_value,
            "credit_limit": credit_limit,
        })

    # 5% duplicates (copy random rows with same customer_id)
    n_dupes = max(1, int(n * 0.05))
    for _ in range(n_dupes):
        dupe = dict(rng.choice(rows))
        rows.append(dupe)

    rng.shuffle(rows)
    return rows


def generate_orders(n=150, customers=None, seed=42):
    """Generate n order records with FK to customers. 2% orphan orders for testing."""
    rng = random.Random(seed + 1)  # different seed from customers
    if customers is None:
        customers = generate_customers(seed=seed)

    customer_ids = [c["customer_id"] for c in customers]
    customer_join_dates = {c["customer_id"]: date.fromisoformat(c["join_date"]) for c in customers}

    rows = []
    for i in range(1, n + 1):
        oid = f"ORD-{i:05d}"

        # 2% orphan orders (FK won't match)
        if rng.random() < 0.02:
            cid = f"CUST-{rng.randint(900,999):03d}"
            join_dt = date(2023, 1, 1)
        else:
            cid = rng.choice(customer_ids)
            join_dt = customer_join_dates.get(cid, date(2023, 1, 1))

        # Order date after customer join date
        order_start = max(join_dt, date(2024, 1, 1))
        order_date = _random_date(rng, order_start, date(2025, 12, 31))

        # 3% future dates for quality testing
        if rng.random() < 0.03:
            order_date = date(2027, rng.randint(1, 6), rng.randint(1, 28))

        category = _weighted_choice(rng, {"Electronics": 0.40, "Furniture": 0.30, "Supplies": 0.30})
        product_name, base_price = rng.choice(PRODUCTS[category])
        quantity = rng.randint(1, 20)
        unit_price = round(base_price * rng.uniform(0.9, 1.1), 2)
        discount_pct = round(rng.choice([0, 0, 0, 0.05, 0.10, 0.15, 0.20, 0.25]), 2)
        revenue = round(quantity * unit_price * (1 - discount_pct), 2)
        status = _weighted_choice(rng, ORDER_STATUSES)
        region = _weighted_choice(rng, REGIONS)

        rows.append({
            "order_id": oid,
            "customer_id": cid,
            "order_date": order_date.isoformat(),
            "product_name": product_name,
            "category": category,
            "quantity": quantity,
            "unit_price": unit_price,
            "discount_pct": discount_pct,
            "revenue": revenue,
            "status": status,
            "region": region,
        })

    # 5% duplicate order_ids
    n_dupes = max(1, int(n * 0.05))
    for _ in range(n_dupes):
        dupe = dict(rng.choice(rows))
        rows.append(dupe)

    rng.shuffle(rows)
    return rows


def write_csv(rows, filepath):
    """Write list of dicts to CSV."""
    if not rows:
        return
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Written: {filepath} ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic customer & order data")
    parser.add_argument("--customers", type=int, default=50, help="Number of customers")
    parser.add_argument("--orders", type=int, default=150, help="Number of orders")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory")
    args = parser.parse_args()

    if args.output_dir:
        out_dir = Path(args.output_dir)
    else:
        out_dir = Path(__file__).parent

    print(f"Generating data (seed={args.seed})...")
    customers = generate_customers(n=args.customers, seed=args.seed)
    orders = generate_orders(n=args.orders, customers=customers, seed=args.seed)

    write_csv(customers, out_dir / "customers.csv")
    write_csv(orders, out_dir / "orders.csv")

    # Summary stats
    unique_custs = len(set(c["customer_id"] for c in customers))
    total_custs = len(customers)
    null_emails = sum(1 for c in customers if c["email"] == "")
    cust_dupes = total_custs - unique_custs

    unique_orders = len(set(o["order_id"] for o in orders))
    total_orders = len(orders)
    order_dupes = total_orders - unique_orders
    cust_ids_in_orders = set(o["customer_id"] for o in orders)
    cust_ids_in_customers = set(c["customer_id"] for c in customers)
    orphans = len(cust_ids_in_orders - cust_ids_in_customers)

    print(f"\nCustomers: {total_custs} rows ({unique_custs} unique, {cust_dupes} duplicates, {null_emails} null emails)")
    print(f"Orders:    {total_orders} rows ({unique_orders} unique, {order_dupes} duplicates, {orphans} orphan customer_ids)")
    print(f"FK integrity: {len(cust_ids_in_orders & cust_ids_in_customers)}/{len(cust_ids_in_orders)} customer_ids match")
    print("Done.")


if __name__ == "__main__":
    main()
