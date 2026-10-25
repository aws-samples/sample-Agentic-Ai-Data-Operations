# spec_hash: e6752176e4d492ffd3c292691fc506739b65a2f54733568470cdbb38f7e0098e
# template_id: silver_transform
# template_hash: bdb637285fc5a991dd50a3d67700137528294982728158338f9e90f291f036ce
# schema_version: v1
# rendered_at: 2026-10-22T18:18:44Z
import os
import sys
import hashlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger
from shared.utils.pii_detection_and_tagging import detect_pii_by_column_name

logger = StructuredLogger(
    agent="silver_transform",
    workload="customer_orders",
    run_id="local",
)


def _configure_logger(args):
    """Use Airflow's ADOP_RUN_ID while keeping direct local calls testable."""
    logger.context["run_id"] = (
        args.get("ADOP_RUN_ID") or os.environ.get("ADOP_RUN_ID") or "local"
    )


def _log_pii_inventory(df):
    """Log column metadata only; detection never reads values or changes the dataframe."""
    inventory = {}
    for column_name in df.columns:
        detected = detect_pii_by_column_name(column_name)
        if detected:
            inventory[column_name] = [
                {"pii_type": pii_type, "sensitivity": sensitivity}
                for pii_type, sensitivity in detected
            ]
    logger.log(
        "info",
        "pii_inventory_detected",
        detected_columns=inventory,
        detected_column_count=len(inventory),
    )



@lru_cache(maxsize=None)
def _phi_salt(secret_id: str) -> str:
    """Fetch a hashing salt from Secrets Manager. Cached: one call per secret per run.

    An unsalted SHA-256 of a low-cardinality identifier is not a one-way function in any
    useful sense. A date of birth is roughly 40,000 candidate values, so the digest can be
    reversed by enumerating them — and a plan member-id space is often smaller still. The
    salt is what makes the digest irreversible without it.

    Raises rather than falling back. A masking step that silently degrades to an
    enumerable digest is worse than one that fails, because the spec, the LF-Tags and the
    audit record would all still claim the column was protected.

    The salt reaches Spark via F.lit(), so it is present in the query plan for the life of
    the job. That is the accepted trade against a per-row UDF; it is never written to the
    output, and only the secret ID appears in the spec.
    """
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    salt = response.get("SecretString")
    if not salt:
        raise RuntimeError(
            f"Secret '{secret_id}' has no SecretString. PHI masking cannot proceed "
            f"unsalted — that would emit an enumerable digest while the spec records a "
            f"salted one."
        )
    return salt


@lru_cache(maxsize=None)
def _token_secret(secret_id: str) -> str:
    """Fetch the runtime tokenization key; never fall back to an unkeyed digest."""
    import boto3

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    secret = response.get("SecretString")
    if not secret:
        raise RuntimeError(
            f"Secret '{secret_id}' has no SecretString. Tokenization cannot proceed "
            "without its runtime key."
        )
    return secret



def _resolve(value, args, slot):
    """Substitute ${NAME} job arguments, and refuse to proceed if any survive."""
    for name in ("CUSTOMER_ORDERS_QUARANTINE_URI", "CUSTOMER_ORDERS_TOKEN_SECRET_ID", ):
        value = value.replace("${" + name + "}", args[name])
    if "${" in value:
        raise ValueError(
            f"{slot} still holds an unresolved placeholder after substitution: {value!r}. "
            f"Pass it as a Glue job argument. For quarantine this would write PHI to a "
            f"prefix named after the placeholder; for a salt secret ID the lookup fails."
        )
    return value


def transform(glue_context, args):
    _configure_logger(args)
    spark = glue_context.spark_session
    logger.log("info", "transform_start", source="glue_catalog.customer_orders_db.bronze_customer_orders")

    bronze_df = spark.table("glue_catalog.customer_orders_db.bronze_customer_orders")
    input_rows = bronze_df.count()
    logger.log("info", "input_count", rows=input_rows)

    # Null handling: quarantine over order_id, customer_id, order_date, product_id, quantity, unit_price, discount_pct, payment_method, order_status
    _null_in_checked = (F.col("order_id").isNull() | F.col("customer_id").isNull() | F.col("order_date").isNull() | F.col("product_id").isNull() | F.col("quantity").isNull() | F.col("unit_price").isNull() | F.col("discount_pct").isNull() | F.col("payment_method").isNull() | F.col("order_status").isNull())
    null_rows = bronze_df.filter(_null_in_checked).count()

    if null_rows > 0:
        # Appended, and written before the count is logged: a later run must not erase rows
        # awaiting review, and a failed write must not read as "no offending rows".
        bronze_df.filter(_null_in_checked).write.mode("append").parquet(
            _resolve("${CUSTOMER_ORDERS_QUARANTINE_URI}", args, "quarantine.location")
        )
    bronze_df = bronze_df.filter(~_null_in_checked)
    null_rows_dropped, null_rows_retained, null_rows_quarantined = 0, 0, null_rows
    after_pk_filter = bronze_df.count()

    deduped_df = bronze_df
    dedup_rows = deduped_df.count()

    # Type casting
    typed_df = deduped_df
    _invalid_order_date = (
        F.col("order_date").isNotNull()
        & F.to_date(F.col("order_date"), "yyyy-MM-dd").isNull()
    )
    _invalid_order_date_count = typed_df.filter(_invalid_order_date).count()
    if _invalid_order_date_count > 0:
        typed_df.filter(_invalid_order_date).withColumn(
            "_adop_quarantine_reason",
            F.lit("invalid_order_date"),
        ).write.mode("append").parquet(
            _resolve("${CUSTOMER_ORDERS_QUARANTINE_URI}", args, "quarantine.location")
        )
        typed_df = typed_df.filter(~_invalid_order_date)
        logger.log(
            "warn",
            "invalid_cast_rows_quarantined",
            column="order_date",
            rows=_invalid_order_date_count,
            target=_resolve("${CUSTOMER_ORDERS_QUARANTINE_URI}", args, "quarantine.location"),
        )
    typed_df = typed_df.withColumn(
        "order_date",
        F.to_date(F.col("order_date"), "yyyy-MM-dd")
    )
    _invalid_ship_date = (
        F.col("ship_date").isNotNull()
        & F.to_date(F.col("ship_date"), "yyyy-MM-dd").isNull()
    )
    _invalid_ship_date_count = typed_df.filter(_invalid_ship_date).count()
    if _invalid_ship_date_count > 0:
        typed_df.filter(_invalid_ship_date).withColumn(
            "_adop_quarantine_reason",
            F.lit("invalid_ship_date"),
        ).write.mode("append").parquet(
            _resolve("${CUSTOMER_ORDERS_QUARANTINE_URI}", args, "quarantine.location")
        )
        typed_df = typed_df.filter(~_invalid_ship_date)
        logger.log(
            "warn",
            "invalid_cast_rows_quarantined",
            column="ship_date",
            rows=_invalid_ship_date_count,
            target=_resolve("${CUSTOMER_ORDERS_QUARANTINE_URI}", args, "quarantine.location"),
        )
    typed_df = typed_df.withColumn(
        "ship_date",
        F.to_date(F.col("ship_date"), "yyyy-MM-dd")
    )
    typed_df = typed_df.withColumn(
        "quantity",
        F.col("quantity").cast("int")
    )
    typed_df = typed_df.withColumn(
        "unit_price",
        F.col("unit_price").cast("decimal(10,2)")
    )
    typed_df = typed_df.withColumn(
        "discount_pct",
        F.col("discount_pct").cast("decimal(5,2)")
    )

    pre_pii_df = typed_df

    # PII masking
    masked_df = pre_pii_df
    masked_df = masked_df.withColumn(
        "customer_email",
        F.sha2(F.col("customer_email").cast("string"), 256)
    )
    masked_df = masked_df.withColumn(
        "customer_phone",
        F.concat(F.substring(F.col("customer_phone"), 1, 2), F.lit("****"))
    )
    masked_df = masked_df.withColumn(
        "credit_card_token",
        F.when(
            F.col("credit_card_number").isNull(),
            F.lit(None),
        ).otherwise(
            F.sha2(
                F.concat(
                    F.lit(_token_secret(_resolve("${CUSTOMER_ORDERS_TOKEN_SECRET_ID}", args, "pii_masking.token_secret_id"))),
                    F.col("credit_card_number").cast("string"),
                ),
                256,
            )
        )
    )
    masked_df = masked_df.withColumn(
        "customer_name",
        F.concat(F.substring(F.col("customer_name"), 1, 2), F.lit("****"))
    )
    masked_df = masked_df.withColumn(
        "shipping_address",
        F.lit("***REDACTED***")
    )
    masked_df = masked_df.withColumn(
        "city",
        F.lit("***REDACTED***")
    )
    masked_df = masked_df.withColumn(
        "state",
        F.lit("***REDACTED***")
    )
    masked_df = masked_df.withColumn(
        "zip_code",
        F.lit("***REDACTED***")
    )

    # Derived columns (computed AFTER PII masking — sentinel cleanup, literals, partition keys)
    derived_df = masked_df
    derived_df = derived_df.withColumn(
        "revenue",
        F.expr("CAST(ROUND(quantity * unit_price * (1 - discount_pct), 2) AS DECIMAL(12,2))")
    )
    derived_df = derived_df.withColumn(
        "data_subject_id",
        F.expr("customer_id")
    )
    derived_df = derived_df.withColumn(
        "consent_given",
        F.expr("CAST(true AS BOOLEAN)")
    )
    derived_df = derived_df.withColumn(
        "consent_timestamp",
        F.expr("CAST(\u00272026-10-22 18:18:44\u0027 AS TIMESTAMP)")
    )
    derived_df = derived_df.withColumn(
        "is_deleted",
        F.expr("CAST(false AS BOOLEAN)")
    )
    derived_df = derived_df.withColumn(
        "deletion_requested_at",
        F.expr("CAST(NULL AS TIMESTAMP)")
    )

    # Drop original columns superseded by hashes / derived columns
    final_df = derived_df.drop("credit_card_number")

    # Write to Iceberg Silver table
    table_name = "glue_catalog.customer_orders_db.silver_customer_orders"
    _log_pii_inventory(final_df)
    final_df.writeTo(table_name) \
        .using("iceberg") \
        .createOrReplace()

    output_rows = final_df.count()
    logger.log("info", "transform_complete",
        input_rows=input_rows,
        pk_null_dropped=input_rows - after_pk_filter,
        duplicates_removed=after_pk_filter - dedup_rows,
        output_rows=output_rows,
        target_table=table_name,
        quality_threshold=0.8)

    return {
        "workload": "customer_orders",
        "transformation": "bronze_to_silver",
        "source": "glue_catalog.customer_orders_db.bronze_customer_orders",
        "target": table_name,
        "input_rows": input_rows,
        "output_rows": output_rows,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME", "ADOP_RUN_ID", "CUSTOMER_ORDERS_QUARANTINE_URI", "CUSTOMER_ORDERS_TOKEN_SECRET_ID"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    result = transform(glue_context, args)
    job.commit()
