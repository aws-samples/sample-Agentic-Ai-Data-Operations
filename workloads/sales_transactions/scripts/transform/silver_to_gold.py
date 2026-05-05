"""
Silver-to-Gold aggregation for sales_transactions workload.

Reads cleaned data from the Silver zone, creates a summary table grouped
by region and product_category, and writes to the Gold zone.

The Gold table provides a curated structure; the AWS Semantic Layer consumer decides
what further metrics to compute on top of it.

Usage:
    python3 scripts/transform/silver_to_gold.py
"""

import csv
import logging
import os
from collections import defaultdict

import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))

CONFIG_PATH = os.path.join(WORKLOAD_DIR, "config", "transformations.yaml")
SILVER_INPUT = os.path.join(
    WORKLOAD_DIR, "data", "silver", "sales_transactions_clean.csv"
)
GOLD_DIR = os.path.join(WORKLOAD_DIR, "data", "gold")
GOLD_OUTPUT = os.path.join(GOLD_DIR, "sales_summary_by_region_category.csv")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("silver_to_gold")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config(path: str) -> dict:
    """Load and return the transformations YAML config."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def read_silver(path: str) -> list[dict]:
    """Read the Silver CSV and return a list of row dicts."""
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def safe_float(value: str, default: float = 0.0) -> float:
    """Convert *value* to float, returning *default* on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: str, default: int = 0) -> int:
    """Convert *value* to int, returning *default* on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def write_csv(rows: list[dict], path: str, fieldnames: list[str]) -> None:
    """Write *rows* to a CSV file at *path*, creating directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def aggregate(rows: list[dict], group_by: list[str]) -> list[dict]:
    """Aggregate *rows* by *group_by* columns.

    Produces one output row per unique combination of the group_by
    columns with the following measures:
        - total_revenue   (sum of revenue)
        - avg_revenue     (mean of revenue, rounded to 2 dp)
        - min_revenue     (minimum revenue)
        - max_revenue     (maximum revenue)
        - total_quantity  (sum of quantity)
        - order_count     (count of distinct order_ids)
    """
    buckets: dict[tuple, dict] = defaultdict(
        lambda: {
            "revenues": [],
            "quantities": [],
            "order_ids": set(),
        }
    )

    for row in rows:
        key = tuple(row.get(col, "") for col in group_by)
        rev = safe_float(row.get("revenue", "0"))
        qty = safe_int(row.get("quantity", "0"))
        oid = row.get("order_id", "")

        buckets[key]["revenues"].append(rev)
        buckets[key]["quantities"].append(qty)
        if oid:
            buckets[key]["order_ids"].add(oid)

    result: list[dict] = []
    for key, data in sorted(buckets.items()):
        revenues = data["revenues"]
        row_out = {}
        for i, col in enumerate(group_by):
            row_out[col] = key[i]
        row_out["total_revenue"] = round(sum(revenues), 2)
        row_out["avg_revenue"] = round(
            sum(revenues) / len(revenues), 2
        ) if revenues else 0.0
        row_out["min_revenue"] = round(min(revenues), 2) if revenues else 0.0
        row_out["max_revenue"] = round(max(revenues), 2) if revenues else 0.0
        row_out["total_quantity"] = sum(data["quantities"])
        row_out["order_count"] = len(data["order_ids"])
        result.append(row_out)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
GOLD_FIELDNAMES = [
    "region",
    "product_category",
    "total_revenue",
    "avg_revenue",
    "min_revenue",
    "max_revenue",
    "total_quantity",
    "order_count",
]


def run(
    config_path: str = CONFIG_PATH,
    silver_input: str = SILVER_INPUT,
    gold_output: str = GOLD_OUTPUT,
) -> dict:
    """Execute the Silver-to-Gold aggregation pipeline.

    Returns a summary dict for logging / testing.
    """
    config = load_config(config_path)
    s2g = config.get("silver_to_gold", {})
    group_by = s2g.get("aggregation", {}).get("group_by", ["region", "product_category"])

    # ---- 1. Read Silver data ----
    rows = read_silver(silver_input)
    logger.info("Read %d rows from Silver zone: %s", len(rows), silver_input)

    # ---- 2. Aggregate ----
    agg_rows = aggregate(rows, group_by)
    logger.info(
        "Aggregated into %d groups by %s", len(agg_rows), group_by
    )

    # ---- 3. Write Gold output ----
    write_csv(agg_rows, gold_output, GOLD_FIELDNAMES)
    logger.info("Gold output written: %s (%d rows)", gold_output, len(agg_rows))

    summary = {
        "silver_input_rows": len(rows),
        "gold_output_rows": len(agg_rows),
        "group_by": group_by,
        "gold_output": gold_output,
    }
    logger.info("Pipeline summary: %s", summary)
    return summary


if __name__ == "__main__":
    run()
