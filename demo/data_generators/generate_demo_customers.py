"""Generate synthetic customer data for Claude Code demo.

Mix of PII columns (EMAIL, PHONE, SSN, CC, NAME, ADDRESS, DOB, IP) and
clean business columns (balance, tier, signup_date) so the PII detector
has positives and negatives to classify.

Output: demo/sample_data/demo_customers.csv (~500 rows)
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(20260417)

FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Emma", "Frank", "Grace", "Henry",
    "Isabella", "James", "Kate", "Liam", "Mia", "Noah", "Olivia", "Paul",
    "Quinn", "Rachel", "Sam", "Tara", "Uma", "Victor", "Wendy", "Xander",
    "Yara", "Zach", "Aisha", "Diego", "Fatima", "Hiro", "Ingrid", "Jamal",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Gonzalez",
    "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark",
    "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King",
]
EMAIL_DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "icloud.com", "proton.me"]
STREETS = ["Main St", "Oak Ave", "Maple Dr", "Cedar Ln", "Elm Way", "Pine Rd",
           "Birch Blvd", "Walnut Ct", "Chestnut Pl", "Spruce Ter"]
CITIES_STATES = [
    ("Boston", "MA", "021"), ("New York", "NY", "100"), ("Chicago", "IL", "606"),
    ("Los Angeles", "CA", "900"), ("Seattle", "WA", "981"), ("Austin", "TX", "787"),
    ("Denver", "CO", "802"), ("Atlanta", "GA", "303"), ("Miami", "FL", "331"),
    ("Portland", "OR", "972"), ("Phoenix", "AZ", "850"), ("Minneapolis", "MN", "554"),
]
TIERS = ["bronze", "silver", "gold", "platinum"]
TIER_WEIGHTS = [0.50, 0.30, 0.15, 0.05]
CC_PREFIXES = ["4532", "4485", "5425", "5105", "3714", "3485"]

N_ROWS = 500

def gen_ssn(i: int) -> str:
    return f"{(100 + i) % 900 + 100:03d}-{(i * 7) % 100:02d}-{(i * 13) % 10000:04d}"

def gen_phone() -> str:
    return f"({random.randint(200, 999)}) {random.randint(100, 999)}-{random.randint(1000, 9999)}"

def gen_cc() -> str:
    prefix = random.choice(CC_PREFIXES)
    rest = "".join(str(random.randint(0, 9)) for _ in range(12))
    raw = prefix + rest
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}"

def gen_dob() -> str:
    start = date(1950, 1, 1)
    end = date(2005, 12, 31)
    delta = (end - start).days
    d = start + timedelta(days=random.randint(0, delta))
    return d.strftime("%m/%d/%Y")

def gen_signup() -> str:
    start = date(2020, 1, 1)
    end = date(2026, 4, 1)
    delta = (end - start).days
    d = start + timedelta(days=random.randint(0, delta))
    return d.isoformat()

def gen_ip() -> str:
    return f"{random.randint(10, 223)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(1, 254)}"

def gen_address(city_state):
    city, state, zip_prefix = city_state
    num = random.randint(100, 9999)
    street = random.choice(STREETS)
    zip_code = f"{zip_prefix}{random.randint(0, 99):02d}"
    return f"{num} {street}", city, state, zip_code

def main():
    out_dir = Path(__file__).resolve().parent.parent / "sample_data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "demo_customers.csv"

    fieldnames = [
        "customer_id", "first_name", "last_name", "email", "phone", "ssn",
        "dob", "credit_card", "street_address", "city", "state", "zip_code",
        "ip_address", "account_balance", "loyalty_tier", "signup_date",
        "lifetime_orders", "marketing_opt_in",
    ]

    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i in range(1, N_ROWS + 1):
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            domain = random.choice(EMAIL_DOMAINS)
            email = f"{fn.lower()}.{ln.lower()}{random.randint(1, 999)}@{domain}"
            city_state = random.choice(CITIES_STATES)
            street, city, state, zip_code = gen_address(city_state)
            tier = random.choices(TIERS, weights=TIER_WEIGHTS, k=1)[0]
            balance = round(random.uniform(50, 50000), 2)
            orders = random.randint(0, 200)
            opt_in = random.choice([True, False])
            w.writerow({
                "customer_id": f"C{i:05d}",
                "first_name": fn,
                "last_name": ln,
                "email": email,
                "phone": gen_phone(),
                "ssn": gen_ssn(i),
                "dob": gen_dob(),
                "credit_card": gen_cc(),
                "street_address": street,
                "city": city,
                "state": state,
                "zip_code": zip_code,
                "ip_address": gen_ip(),
                "account_balance": balance,
                "loyalty_tier": tier,
                "signup_date": gen_signup(),
                "lifetime_orders": orders,
                "marketing_opt_in": opt_in,
            })

    print(f"Wrote {N_ROWS} rows to {out_path}")
    print(f"Size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
