"""
Generate synthetic product inventory data with realistic quality issues.

Quality issues embedded:
1. Duplicate SKUs (3 exact dupes)
2. Negative quantity_on_hand (2 rows — data entry errors)
3. Null supplier_id/supplier_name (5 rows — missing supplier info)
4. Inconsistent category casing ("Electronics" vs "electronics" vs "ELECTRONICS")
5. Future last_restocked_date (2 rows)
6. cost_price > unit_price (3 rows — margin anomaly)
7. Null expiry_date for perishable items (2 rows — should have expiry)
8. Whitespace in product_name (3 rows — leading/trailing spaces)
9. Invalid status values (1 row — "aktive" typo)
10. Null reorder_level (2 rows)
"""

import csv
import random
from datetime import datetime, timedelta

random.seed(42)

CATEGORIES = {
    "Electronics": ["Smartphones", "Laptops", "Tablets", "Accessories", "Audio"],
    "Grocery": ["Dairy", "Snacks", "Beverages", "Canned Goods", "Condiments"],
    "Clothing": ["Men", "Women", "Kids", "Footwear", "Accessories"],
    "Home & Garden": ["Furniture", "Kitchen", "Lighting", "Decor", "Tools"],
    "Sports": ["Fitness", "Outdoor", "Team Sports", "Water Sports", "Cycling"],
}

BRANDS = [
    "AcmeCo", "BrightStar", "CoreTech", "DailyFresh", "EverGreen",
    "FitPro", "GlobeMax", "HomeNest", "IronClad", "JustRight",
    "KingSize", "LuxLine", "MegaByte", "NaturePlus", "OptiGear",
    "PrimePick", "QuickServe", "RapidFlow", "SilverEdge", "TopShelf",
]

WAREHOUSES = ["WH-EAST-01", "WH-EAST-02", "WH-WEST-01", "WH-WEST-02", "WH-CENTRAL-01"]

SUPPLIERS = [
    ("SUP-001", "Global Supply Co"),
    ("SUP-002", "Pacific Trading Ltd"),
    ("SUP-003", "Atlantic Distributors"),
    ("SUP-004", "Midwest Wholesale Inc"),
    ("SUP-005", "Southern Goods LLC"),
    ("SUP-006", "Nordic Imports AB"),
    ("SUP-007", "Eastern Markets Corp"),
    ("SUP-008", "Fresh Farm Direct"),
    ("SUP-009", "TechSource Partners"),
    ("SUP-010", "Heritage Brands Co"),
]

STATUSES = ["active", "discontinued", "out_of_stock"]


def random_date(start_year=2024, end_year=2026):
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 3, 15)
    delta = end - start
    return start + timedelta(days=random.randint(0, delta.days))


def future_date():
    start = datetime(2026, 6, 1)
    return start + timedelta(days=random.randint(1, 180))


def generate_rows(n=120):
    rows = []
    product_id = 1000

    for i in range(n):
        product_id += 1
        category = random.choice(list(CATEGORIES.keys()))
        subcategory = random.choice(CATEGORIES[category])
        brand = random.choice(BRANDS)
        supplier = random.choice(SUPPLIERS)
        cost = round(random.uniform(2.0, 500.0), 2)
        markup = random.uniform(1.15, 2.5)
        unit_price = round(cost * markup, 2)

        row = {
            "product_id": f"PROD-{product_id}",
            "sku": f"SKU-{random.randint(10000, 99999)}",
            "product_name": f"{brand} {subcategory} {random.choice(['Pro', 'Basic', 'Elite', 'Standard', 'Plus', 'Max'])}",
            "category": category,
            "subcategory": subcategory,
            "brand": brand,
            "unit_price": unit_price,
            "cost_price": cost,
            "quantity_on_hand": random.randint(0, 5000),
            "reorder_level": random.randint(10, 200),
            "reorder_quantity": random.randint(50, 1000),
            "warehouse_location": random.choice(WAREHOUSES),
            "supplier_id": supplier[0],
            "supplier_name": supplier[1],
            "last_restocked_date": random_date().strftime("%Y-%m-%d"),
            "expiry_date": (random_date(2026, 2027).strftime("%Y-%m-%d")
                           if category == "Grocery" else ""),
            "weight_kg": round(random.uniform(0.05, 25.0), 2),
            "status": random.choice(STATUSES),
        }
        rows.append(row)

    # --- Inject quality issues ---

    # 1. Duplicate SKUs (3 exact row dupes at random positions)
    for _ in range(3):
        dupe = dict(random.choice(rows[:80]))
        rows.append(dupe)

    # 2. Negative quantity_on_hand (2 rows)
    for idx in random.sample(range(len(rows)), 2):
        rows[idx]["quantity_on_hand"] = -random.randint(1, 50)

    # 3. Null supplier info (5 rows)
    for idx in random.sample(range(len(rows)), 5):
        rows[idx]["supplier_id"] = ""
        rows[idx]["supplier_name"] = ""

    # 4. Inconsistent category casing (6 rows)
    case_targets = random.sample(range(len(rows)), 6)
    for i, idx in enumerate(case_targets):
        if i < 3:
            rows[idx]["category"] = rows[idx]["category"].lower()
        else:
            rows[idx]["category"] = rows[idx]["category"].upper()

    # 5. Future last_restocked_date (2 rows)
    for idx in random.sample(range(len(rows)), 2):
        rows[idx]["last_restocked_date"] = future_date().strftime("%Y-%m-%d")

    # 6. cost_price > unit_price (margin anomaly, 3 rows)
    for idx in random.sample(range(len(rows)), 3):
        rows[idx]["cost_price"] = round(rows[idx]["unit_price"] * random.uniform(1.1, 1.5), 2)

    # 7. Null expiry_date for Grocery items (2 rows that should have expiry)
    grocery_rows = [i for i, r in enumerate(rows) if r["category"].lower() == "grocery"]
    if len(grocery_rows) >= 2:
        for idx in random.sample(grocery_rows, 2):
            rows[idx]["expiry_date"] = ""

    # 8. Whitespace in product_name (3 rows)
    for idx in random.sample(range(len(rows)), 3):
        rows[idx]["product_name"] = f"  {rows[idx]['product_name']}  "

    # 9. Invalid status value (1 row — typo)
    rows[random.randint(0, len(rows) - 1)]["status"] = "aktive"

    # 10. Null reorder_level (2 rows)
    for idx in random.sample(range(len(rows)), 2):
        rows[idx]["reorder_level"] = ""

    # Shuffle to spread issues around
    random.shuffle(rows)
    return rows


if __name__ == "__main__":
    rows = generate_rows(120)
    fieldnames = [
        "product_id", "sku", "product_name", "category", "subcategory",
        "brand", "unit_price", "cost_price", "quantity_on_hand",
        "reorder_level", "reorder_quantity", "warehouse_location",
        "supplier_id", "supplier_name", "last_restocked_date",
        "expiry_date", "weight_kg", "status",
    ]

    output = "sample_data/product_inventory.csv"
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Generated {len(rows)} rows -> {output}")
    print(f"Columns: {len(fieldnames)}")
    print(f"\nQuality issues embedded:")
    print(f"  - 3 duplicate SKU rows")
    print(f"  - 2 negative quantity_on_hand")
    print(f"  - 5 missing supplier info")
    print(f"  - 6 inconsistent category casing")
    print(f"  - 2 future last_restocked_date")
    print(f"  - 3 cost > price (margin anomaly)")
    print(f"  - 2 missing expiry for Grocery")
    print(f"  - 3 whitespace in product_name")
    print(f"  - 1 invalid status ('aktive')")
    print(f"  - 2 missing reorder_level")
