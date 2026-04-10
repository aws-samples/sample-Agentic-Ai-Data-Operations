"""
Bronze-to-Silver transformation for sales_transactions workload.

Reads raw CSV from the Bronze zone (sample_data/), applies cleaning rules
defined in config/transformations.yaml, and writes:
  - Cleaned records  -> data/silver/sales_transactions_clean.csv
  - Quarantined rows -> data/quarantine/quarantined_records.csv

This script is idempotent: running it multiple times produces identical output.

Tracing: All transformations are traced via ScriptTracer for observability.

Usage:
    python3 scripts/transform/bronze_to_silver.py
"""

import csv
import hashlib
import logging
import os
import re
import sys
from datetime import datetime

import yaml

# Add project root to path for shared imports
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKLOAD_DIR = os.path.dirname(os.path.dirname(SCRIPT_DIR))
PROJECT_ROOT = os.path.dirname(os.path.dirname(WORKLOAD_DIR))
sys.path.insert(0, PROJECT_ROOT)

from shared.utils.script_tracer import ScriptTracer

# ---------------------------------------------------------------------------
# Path setup (already set above for shared imports)
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(WORKLOAD_DIR, "config", "transformations.yaml")
SOURCE_CSV = os.path.join(PROJECT_ROOT, "sample_data", "sales_transactions.csv")
SILVER_DIR = os.path.join(WORKLOAD_DIR, "data", "silver")
QUARANTINE_DIR = os.path.join(WORKLOAD_DIR, "data", "quarantine")
SILVER_OUTPUT = os.path.join(SILVER_DIR, "sales_transactions_clean.csv")
QUARANTINE_OUTPUT = os.path.join(QUARANTINE_DIR, "quarantined_records.csv")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("bronze_to_silver")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_config(path: str) -> dict:
    """Load and return the transformations YAML config."""
    with open(path, "r") as f:
        return yaml.safe_load(f)


def sha256_hash(value: str) -> str:
    """Return the SHA-256 hex digest of *value*."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def mask_value(value: str, rule: dict) -> str:
    """Apply a PII masking rule to a single value.

    Returns the masked version, or the original if the value is empty/null.
    """
    if not value or value.strip() == "":
        return value
    strategy = rule.get("strategy", "hash_sha256")
    if strategy == "hash_sha256":
        return sha256_hash(value)
    elif strategy == "redact":
        return rule.get("replacement", "***")
    return value


def validate_date(value: str, fmt: str) -> bool:
    """Return True if *value* matches *fmt*, False otherwise."""
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def is_null_or_empty(value) -> bool:
    """Return True when *value* is None or a blank string."""
    if value is None:
        return True
    return str(value).strip() == ""


# ---------------------------------------------------------------------------
# Transformation pipeline
# ---------------------------------------------------------------------------
def read_bronze(path: str) -> list[dict]:
    """Read the raw CSV and return a list of row dicts."""
    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def deduplicate(rows: list[dict], key: str, strategy: str) -> tuple[list[dict], int]:
    """Remove duplicate rows based on *key*.

    *strategy* is currently ``keep_first`` (the only supported value).
    Returns (deduplicated rows, count of duplicates removed).
    """
    seen: set[str] = set()
    deduped: list[str] = []
    dup_count = 0
    for row in rows:
        k = row.get(key, "")
        if k in seen:
            dup_count += 1
            continue
        seen.add(k)
        deduped.append(row)
    return deduped, dup_count


def quarantine_null_pk(rows: list[dict], pk_column: str) -> tuple[list[dict], list[dict]]:
    """Separate rows with null/empty PK into a quarantine list."""
    clean: list[dict] = []
    quarantined: list[dict] = []
    for row in rows:
        if is_null_or_empty(row.get(pk_column)):
            quarantined.append(row)
        else:
            clean.append(row)
    return clean, quarantined


def trim_whitespace(rows: list[dict], string_columns: list[str]) -> list[dict]:
    """Strip leading/trailing whitespace from specified columns."""
    for row in rows:
        for col in string_columns:
            if col in row and row[col] is not None:
                row[col] = row[col].strip()
    return rows


def lowercase_columns(rows: list[dict], columns: list[str]) -> list[dict]:
    """Lowercase values in the given columns."""
    for row in rows:
        for col in columns:
            if col in row and row[col] is not None:
                row[col] = row[col].lower()
    return rows


def validate_dates(rows: list[dict], date_rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """Validate date columns; quarantine rows with invalid non-null dates."""
    valid: list[dict] = []
    invalid: list[dict] = []
    for row in rows:
        row_ok = True
        for rule in date_rules:
            col = rule["column"]
            fmt = rule["format"]
            nullable = rule.get("nullable", True)
            value = row.get(col, "")
            if is_null_or_empty(value):
                if not nullable:
                    row["_quarantine_reason"] = f"null_non_nullable_date:{col}"
                    row_ok = False
                    break
                # Null is allowed — skip validation
                continue
            if not validate_date(value, fmt):
                row["_quarantine_reason"] = f"invalid_date_format:{col}={value}"
                row_ok = False
                break
        if row_ok:
            valid.append(row)
        else:
            invalid.append(row)
    return valid, invalid


def apply_pii_masking(rows: list[dict], pii_rules: list[dict]) -> list[dict]:
    """Apply PII masking rules to the specified columns."""
    for row in rows:
        for rule in pii_rules:
            col = rule["column"]
            if col in row:
                row[col] = mask_value(row[col], rule)
    return rows


def get_string_columns(config: dict) -> list[str]:
    """Return a list of column names that have target_type 'string'."""
    type_rules = config.get("bronze_to_silver", {}).get("type_casting", {}).get("rules", [])
    return [r["column"] for r in type_rules if r.get("target_type") == "string"]


def write_csv(rows: list[dict], path: str, fieldnames: list[str]) -> None:
    """Write *rows* to a CSV file at *path*, creating directories as needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run(
    config_path: str = CONFIG_PATH,
    source_csv: str = SOURCE_CSV,
    silver_output: str = SILVER_OUTPUT,
    quarantine_output: str = QUARANTINE_OUTPUT,
    tracer: ScriptTracer = None,
) -> dict:
    """Execute the full Bronze-to-Silver transformation pipeline.

    Returns a summary dict with counts for logging / testing.
    """
    # Initialize tracer if not provided
    if tracer is None:
        tracer = ScriptTracer.for_script(__file__)

    config = load_config(config_path)
    b2s = config["bronze_to_silver"]

    # ---- 1. Read raw data ----
    rows = read_bronze(source_csv)
    original_count = len(rows)
    logger.info("Read %d rows from Bronze zone: %s", original_count, source_csv)
    tracer.log_start(rows_in=original_count, source=source_csv)

    # Capture original fieldnames (from the first row's keys)
    fieldnames = list(rows[0].keys()) if rows else []

    # ---- 2. Deduplication ----
    dedup_cfg = b2s.get("deduplication", {})
    dup_count = 0
    if dedup_cfg.get("enabled"):
        rows, dup_count = deduplicate(
            rows, dedup_cfg["key"], dedup_cfg.get("strategy", "keep_first")
        )
        logger.info(
            "Deduplication on '%s' (strategy=%s): removed %d duplicates, %d rows remain",
            dedup_cfg["key"],
            dedup_cfg.get("strategy"),
            dup_count,
            len(rows),
        )
        tracer.log_transform(
            "deduplicate",
            key=dedup_cfg["key"],
            strategy=dedup_cfg.get("strategy"),
            duplicates_removed=dup_count,
            rows_remaining=len(rows),
        )

    # ---- 3. Quarantine null PKs ----
    quarantined: list[dict] = []
    quarantine_cfg = b2s.get("quarantine", {})
    if quarantine_cfg.get("enabled"):
        for cond in quarantine_cfg.get("conditions", []):
            if cond["name"] == "null_primary_key":
                rows, q = quarantine_null_pk(rows, cond["column"])
                for r in q:
                    r["_quarantine_reason"] = "null_primary_key"
                quarantined.extend(q)
                logger.info(
                    "Quarantined %d rows with null PK '%s'",
                    len(q),
                    cond["column"],
                )
                tracer.log_transform(
                    "quarantine_null_pk",
                    column=cond["column"],
                    quarantined_count=len(q),
                )

    # ---- 4. String normalisation: trim whitespace ----
    string_cols = get_string_columns(config)
    trim_cfg = b2s.get("string_normalization", {}).get("trim_whitespace", {})
    if trim_cfg.get("enabled"):
        rows = trim_whitespace(rows, string_cols)
        logger.info("Trimmed whitespace on %d string columns", len(string_cols))
        tracer.log_transform("trim_whitespace", columns=string_cols)

    # ---- 5. String normalisation: lowercase ----
    lower_cfg = b2s.get("string_normalization", {}).get("lowercase", {})
    if lower_cfg.get("enabled"):
        lc_cols = lower_cfg.get("columns", [])
        rows = lowercase_columns(rows, lc_cols)
        logger.info("Lowercased columns: %s", lc_cols)
        tracer.log_transform("lowercase", columns=lc_cols)

    # ---- 6. Date validation ----
    date_rules = b2s.get("date_validation", {}).get("rules", [])
    if date_rules:
        rows, bad_dates = validate_dates(rows, date_rules)
        quarantined.extend(bad_dates)
        logger.info(
            "Date validation: %d rows quarantined for invalid dates, %d rows pass",
            len(bad_dates),
            len(rows),
        )
        tracer.log_quality_check(
            "date_validation",
            passed=(len(bad_dates) == 0),
            invalid_count=len(bad_dates),
            valid_count=len(rows),
        )

    # ---- 7. PII masking ----
    pii_cfg = b2s.get("pii_masking", {})
    if pii_cfg.get("enabled"):
        pii_rules = pii_cfg.get("rules", [])
        rows = apply_pii_masking(rows, pii_rules)
        masked_cols = [r["column"] for r in pii_rules]
        logger.info(
            "PII masking applied to %d columns: %s",
            len(pii_rules),
            masked_cols,
        )
        tracer.log_transform("pii_masking", columns_masked=masked_cols)

    # ---- 8. Write outputs ----
    write_csv(rows, silver_output, fieldnames)
    logger.info("Silver output written: %s (%d rows)", silver_output, len(rows))

    # Always write quarantine file (even if empty) for idempotency checks
    quarantine_fieldnames = fieldnames + ["_quarantine_reason"]
    write_csv(quarantined, quarantine_output, quarantine_fieldnames)
    logger.info(
        "Quarantine output written: %s (%d rows)", quarantine_output, len(quarantined)
    )

    summary = {
        "input_rows": original_count,
        "duplicates_removed": dup_count,
        "quarantined_rows": len(quarantined),
        "silver_rows": len(rows),
        "silver_output": silver_output,
        "quarantine_output": quarantine_output,
    }
    logger.info("Pipeline summary: %s", summary)

    # ---- Final trace events ----
    tracer.log_rows(
        rows_in=original_count,
        rows_out=len(rows),
        quarantined=len(quarantined),
    )
    tracer.log_complete(
        status="success",
        rows_out=len(rows),
        quarantined=len(quarantined),
        output_path=silver_output,
    )
    tracer.close()

    return summary


if __name__ == "__main__":
    with ScriptTracer.for_script(__file__) as tracer:
        run(tracer=tracer)
