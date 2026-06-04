# spec_hash: 42a25f7a26d311110b5eb01a98632e25fa5349059a9cb9f3965096a693c81416
# template_id: silver_transform
# template_hash: 270b6c620017cf1f7d46bc7032e845e1775a1a43f588767631c3df9bd48f2f6c
# schema_version: v1
# rendered_at: 2026-06-03T00:00:00Z
import sys
import hashlib
from datetime import datetime
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

logger = StructuredLogger(
    agent="silver_transform",
    workload="customer_master",
    run_id="standalone",
)


def transform(glue_context, args):
    spark = glue_context.spark_session
    logger.log("info", "transform_start", source="glue_catalog.customer_master_db.bronze_customer_master")

    bronze_df = spark.table("glue_catalog.customer_master_db.bronze_customer_master")
    input_rows = bronze_df.count()
    logger.log("info", "input_count", rows=input_rows)

    # Drop rows with null primary key columns
    bronze_df = bronze_df.filter(F.col("customer_id").isNotNull())
    after_pk_filter = bronze_df.count()

    # Deduplication: keep_latest
    window = Window.partitionBy(
        "customer_id",
    ).orderBy(F.desc("account_open_date"))
    deduped_df = bronze_df \
        .withColumn("_row_num", F.row_number().over(window)) \
        .filter(F.col("_row_num") == 1) \
        .drop("_row_num")
    dedup_rows = deduped_df.count()

    # Type casting
    typed_df = deduped_df
    typed_df = typed_df.withColumn(
        "date_of_birth",
        F.to_date(F.col("date_of_birth"), "yyyy-MM-dd")
    )
    typed_df = typed_df.withColumn(
        "account_open_date",
        F.to_date(F.col("account_open_date"), "yyyy-MM-dd")
    )
    typed_df = typed_df.withColumn(
        "annual_income",
        F.col("annual_income").cast("int")
    )
    typed_df = typed_df.withColumn(
        "credit_score",
        F.col("credit_score").cast("int")
    )

    # Pre-PII derived columns (computed before masking, e.g. extract domain from raw email)
    pre_pii_df = typed_df
    pre_pii_df = pre_pii_df.withColumn(
        "email_domain",
        F.expr("substring_index(email, \u0027@\u0027, -1)")
    )

    # PII masking
    masked_df = pre_pii_df
    masked_df = masked_df.withColumn(
        "ssn",
        F.sha2(F.col("ssn").cast("string"), 256)
    )
    masked_df = masked_df.withColumn(
        "email",
        F.sha2(F.col("email").cast("string"), 256)
    )
    masked_df = masked_df.withColumn(
        "phone",
        F.sha2(F.col("phone").cast("string"), 256)
    )
    masked_df = masked_df.withColumn(
        "date_of_birth",
        F.lit("***REDACTED***")
    )
    masked_df = masked_df.withColumn(
        "address",
        F.lit("***REDACTED***")
    )

    # Derived columns (computed AFTER PII masking — sentinel cleanup, literals, partition keys)
    derived_df = masked_df
    derived_df = derived_df.withColumn(
        "age_years",
        F.expr("floor(datediff(current_date(), date_of_birth) / 365.25)")
    )
    derived_df = derived_df.withColumn(
        "customer_tenure_months",
        F.expr("floor(months_between(current_date(), account_open_date))")
    )
    derived_df = derived_df.withColumn(
        "income_bucket",
        F.expr("CASE WHEN annual_income \u003c 75000 THEN \u0027Low\u0027 WHEN annual_income \u003c 150000 THEN \u0027Mid\u0027 WHEN annual_income \u003c 300000 THEN \u0027High\u0027 ELSE \u0027Ultra\u0027 END")
    )
    derived_df = derived_df.withColumn(
        "geographic_region",
        F.expr("CASE WHEN state IN (\u0027CT\u0027,\u0027ME\u0027,\u0027MA\u0027,\u0027NH\u0027,\u0027RI\u0027,\u0027VT\u0027,\u0027NJ\u0027,\u0027NY\u0027,\u0027PA\u0027) THEN \u0027Northeast\u0027 WHEN state IN (\u0027IL\u0027,\u0027IN\u0027,\u0027IA\u0027,\u0027KS\u0027,\u0027MI\u0027,\u0027MN\u0027,\u0027MO\u0027,\u0027NE\u0027,\u0027ND\u0027,\u0027OH\u0027,\u0027SD\u0027,\u0027WI\u0027) THEN \u0027Midwest\u0027 WHEN state IN (\u0027AL\u0027,\u0027AR\u0027,\u0027DE\u0027,\u0027FL\u0027,\u0027GA\u0027,\u0027KY\u0027,\u0027LA\u0027,\u0027MD\u0027,\u0027MS\u0027,\u0027NC\u0027,\u0027OK\u0027,\u0027SC\u0027,\u0027TN\u0027,\u0027TX\u0027,\u0027VA\u0027,\u0027WV\u0027,\u0027DC\u0027) THEN \u0027Southeast\u0027 WHEN state IN (\u0027AZ\u0027,\u0027CO\u0027,\u0027ID\u0027,\u0027MT\u0027,\u0027NV\u0027,\u0027NM\u0027,\u0027UT\u0027,\u0027WY\u0027) THEN \u0027Southwest\u0027 WHEN state IN (\u0027AK\u0027,\u0027CA\u0027,\u0027HI\u0027,\u0027OR\u0027,\u0027WA\u0027) THEN \u0027West\u0027 ELSE \u0027Unknown\u0027 END")
    )
    derived_df = derived_df.withColumn(
        "employment_category",
        F.expr("CASE WHEN employment_status = \u0027Employed\u0027 THEN \u0027W2\u0027 WHEN employment_status = \u0027Self-Employed\u0027 THEN \u00271099\u0027 WHEN employment_status = \u0027Retired\u0027 THEN \u0027Retired\u0027 ELSE \u0027Other\u0027 END")
    )
    derived_df = derived_df.withColumn(
        "wealth_tier",
        F.expr("CASE WHEN annual_income \u003e= 300000 AND credit_score \u003e= 750 THEN \u0027Ultra High Net Worth\u0027 WHEN annual_income \u003e= 150000 AND credit_score \u003e= 720 THEN \u0027High Net Worth\u0027 WHEN annual_income \u003e= 75000 AND credit_score \u003e= 680 THEN \u0027Mass Affluent\u0027 ELSE \u0027Mass Market\u0027 END")
    )
    derived_df = derived_df.withColumn(
        "lifecycle_stage",
        F.expr("CASE WHEN floor(months_between(current_date(), account_open_date)) \u003c 6 THEN \u0027New\u0027 WHEN floor(months_between(current_date(), account_open_date)) \u003c 24 THEN \u0027Growing\u0027 WHEN floor(months_between(current_date(), account_open_date)) \u003c 60 THEN \u0027Mature\u0027 ELSE \u0027Loyal\u0027 END")
    )
    derived_df = derived_df.withColumn(
        "lawful_basis",
        F.expr("\u0027contract\u0027")
    )
    derived_df = derived_df.withColumn(
        "consent_status",
        F.expr("\u0027active\u0027")
    )
    derived_df = derived_df.withColumn(
        "retention_expiry_date",
        F.expr("date_add(current_date(), 365)")
    )
    derived_df = derived_df.withColumn(
        "ssn_duplicate_flag",
        F.expr("CASE WHEN count(1) OVER (PARTITION BY ssn) \u003e 1 THEN true ELSE false END")
    )

    final_df = derived_df

    # Write to Iceberg Silver table
    table_name = "glue_catalog.customer_master_db.silver_customer_master"
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
        "workload": "customer_master",
        "transformation": "bronze_to_silver",
        "source": "glue_catalog.customer_master_db.bronze_customer_master",
        "target": table_name,
        "input_rows": input_rows,
        "output_rows": output_rows,
    }


if __name__ == "__main__":
    args = getResolvedOptions(sys.argv, ["JOB_NAME"])
    sc = SparkContext()
    glue_context = GlueContext(sc)
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)
    result = transform(glue_context, args)
    job.commit()
