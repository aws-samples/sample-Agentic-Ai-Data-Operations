#!/usr/bin/env python3
"""
Bronze → Silver transformation for claims
AWS Glue ETL script with local mode fallback

Transformations:
- Deduplication by claim_id (keep latest)
- Null PK rows dropped (claim_id only)
- Type casting: dates, decimals
- Validations: claim_type, status, amounts
- PII masking: SSN hashed, names hashed, email masked, phone masked
- Output: Apache Iceberg table in Silver zone
"""

import sys
import json
import hashlib
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger
from shared.utils.script_tracer import ScriptTracer


def hash_value(value):
    if value is None or str(value).strip() == '':
        return None
    return hashlib.sha256(str(value).encode()).hexdigest()


def mask_email(email):
    if email is None or '@' not in str(email):
        return email
    local, domain = str(email).split('@', 1)
    return f"{local[0]}***@{domain}"


def mask_phone(phone):
    if phone is None or len(str(phone)) < 10:
        return phone
    phone_str = str(phone)
    return f"{phone_str[:5]}***{phone_str[-4:]}"


def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    bronze_df = glue_context.create_dynamic_frame.from_options(
        connection_type="s3",
        connection_options={"paths": [args['bronze_path']]},
        format="csv",
        format_options={"withHeader": True, "separator": ",", "quoteChar": '"'}
    ).toDF()

    input_rows = bronze_df.count()

    # Drop null PKs
    bronze_df = bronze_df.filter(F.col("claim_id").isNotNull())
    after_null_drop = bronze_df.count()

    # Dedup by claim_id
    window = Window.partitionBy("claim_id").orderBy(F.desc("submission_date"))
    deduped_df = bronze_df \
        .withColumn("row_num", F.row_number().over(window)) \
        .filter(F.col("row_num") == 1) \
        .drop("row_num")

    dedup_rows = deduped_df.count()

    # Type casting
    typed_df = deduped_df \
        .withColumn("service_date", F.to_date("service_date", "yyyy-MM-dd")) \
        .withColumn("submission_date", F.to_date("submission_date", "yyyy-MM-dd")) \
        .withColumn("member_dob", F.to_date("member_dob", "yyyy-MM-dd")) \
        .withColumn("billed_amount", F.col("billed_amount").cast("decimal(10,2)")) \
        .withColumn("allowed_amount", F.col("allowed_amount").cast("decimal(10,2)")) \
        .withColumn("paid_amount", F.col("paid_amount").cast("decimal(10,2)")) \
        .withColumn("patient_responsibility", F.col("patient_responsibility").cast("decimal(10,2)"))

    # Validations
    valid_df = typed_df.filter(
        (F.col("claim_type").isin("medical", "dental", "vision", "pharmacy")) &
        (F.col("claim_status").isin("paid", "denied", "pending", "appealed")) &
        (F.col("billed_amount") >= 0) &
        (F.col("service_date") <= F.current_date())
    )

    quarantine_df = typed_df.subtract(valid_df)
    valid_rows = valid_df.count()
    quarantine_rows = quarantine_df.count()

    # PII masking
    masked_df = valid_df \
        .withColumn("member_ssn", F.sha2(F.col("member_ssn"), 256)) \
        .withColumn("member_first_name", F.sha2(F.col("member_first_name"), 256)) \
        .withColumn("member_last_name", F.sha2(F.col("member_last_name"), 256)) \
        .withColumn("member_email",
                    F.concat(F.substring(F.col("member_email"), 1, 1), F.lit("***@"),
                             F.element_at(F.split(F.col("member_email"), "@"), 2))) \
        .withColumn("member_phone",
                    F.concat(F.substring(F.col("member_phone"), 1, 5), F.lit("***"),
                             F.substring(F.col("member_phone"), -4, 4)))

    # Derived columns
    masked_df = masked_df \
        .withColumn("member_age", F.year(F.current_date()) - F.year(F.col("member_dob"))) \
        .withColumn("days_to_submission", F.datediff(F.col("submission_date"), F.col("service_date"))) \
        .withColumn("payer_coverage_pct",
                    F.when(F.col("billed_amount") > 0,
                           (F.col("paid_amount") / F.col("billed_amount")) * 100).otherwise(0))

    # Write to Iceberg
    table_name = "glue_catalog.claims_db.silver_claims"
    masked_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .saveAsTable(table_name)

    # Quarantine
    if quarantine_rows > 0:
        quarantine_path = args['bronze_path'].replace('/bronze/', '/quarantine/')
        quarantine_df \
            .withColumn("quarantine_timestamp", F.current_timestamp()) \
            .withColumn("quarantine_reason", F.lit("Validation failure")) \
            .write.format("parquet").mode("append").save(quarantine_path)

    return {
        "workload": "claims",
        "transformation": "bronze_to_silver",
        "source": args['bronze_path'],
        "target": table_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "null_pk_dropped": input_rows - after_null_drop,
        "duplicate_rows": after_null_drop - dedup_rows,
        "output_rows": valid_rows,
        "quarantined_rows": quarantine_rows,
        "transformations_applied": [
            "drop_null_pk",
            "deduplication_by_claim_id",
            "type_casting",
            "validation_checks",
            "pii_masking_hipaa",
            "derived_columns"
        ]
    }


def transform_local_mode(bronze_path, silver_path, tracer=None):
    """Transform using pandas (local testing)"""
    import pandas as pd

    if tracer is None:
        tracer = ScriptTracer.for_script(__file__)

    log = StructuredLogger("Transform", "claims", f"run-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")

    df = pd.read_csv(bronze_path)
    input_rows = len(df)
    log.info("Read bronze data", rows=input_rows, source=bronze_path)
    tracer.log_start(rows_in=input_rows, source=bronze_path)

    # Drop null PKs
    df = df.dropna(subset=['claim_id'])
    after_null_drop = len(df)
    log.info("Dropped null PKs", dropped=input_rows - after_null_drop)

    # Dedup by claim_id
    df = df.sort_values('submission_date', ascending=False).drop_duplicates(subset=['claim_id'], keep='first')
    dedup_rows = len(df)
    log.info("Deduplicated", duplicates_removed=after_null_drop - dedup_rows)
    tracer.log_transform("deduplicate", key="claim_id", duplicates_removed=after_null_drop - dedup_rows)

    # Type casting
    df['service_date'] = pd.to_datetime(df['service_date'])
    df['submission_date'] = pd.to_datetime(df['submission_date'])
    df['member_dob'] = pd.to_datetime(df['member_dob'])
    for col in ['billed_amount', 'allowed_amount', 'paid_amount', 'patient_responsibility']:
        df[col] = pd.to_numeric(df[col], errors='coerce').round(2)

    # Validations
    valid_mask = (
        df['claim_type'].isin(['medical', 'dental', 'vision', 'pharmacy']) &
        df['claim_status'].isin(['paid', 'denied', 'pending', 'appealed']) &
        (df['billed_amount'] >= 0) &
        (df['service_date'] <= pd.Timestamp.now())
    )

    quarantine_df = df[~valid_mask].copy()
    valid_df = df[valid_mask].copy()
    valid_rows = len(valid_df)
    quarantine_rows = len(quarantine_df)
    log.info("Validation complete", valid=valid_rows, quarantined=quarantine_rows)
    tracer.log_quality_check("validation", passed=(quarantine_rows == 0),
                             valid_count=valid_rows, quarantine_count=quarantine_rows)

    # PII masking (HIPAA)
    valid_df['member_ssn'] = valid_df['member_ssn'].apply(hash_value)
    valid_df['member_first_name'] = valid_df['member_first_name'].apply(hash_value)
    valid_df['member_last_name'] = valid_df['member_last_name'].apply(hash_value)
    valid_df['member_email'] = valid_df['member_email'].apply(mask_email)
    valid_df['member_phone'] = valid_df['member_phone'].apply(mask_phone)

    # Derived columns
    valid_df['member_age'] = (pd.Timestamp.now() - valid_df['member_dob']).dt.days // 365
    valid_df['days_to_submission'] = (valid_df['submission_date'] - valid_df['service_date']).dt.days
    valid_df['payer_coverage_pct'] = (
        valid_df['paid_amount'] / valid_df['billed_amount'] * 100
    ).where(valid_df['billed_amount'] > 0, 0).round(2)

    # Write Silver
    Path(silver_path).parent.mkdir(parents=True, exist_ok=True)
    valid_df.to_parquet(silver_path, index=False, engine='pyarrow')
    log.info("Silver written", path=silver_path, rows=valid_rows)

    # Write quarantine
    if quarantine_rows > 0:
        quarantine_path = silver_path.replace('/silver/', '/quarantine/').replace('.parquet', '_quarantine.parquet')
        Path(quarantine_path).parent.mkdir(parents=True, exist_ok=True)
        quarantine_df['quarantine_timestamp'] = datetime.utcnow().isoformat() + "Z"
        quarantine_df['quarantine_reason'] = 'Validation failure'
        quarantine_df.to_parquet(quarantine_path, index=False, engine='pyarrow')

    # Lineage
    lineage = {
        "workload": "claims",
        "transformation": "bronze_to_silver",
        "source": bronze_path,
        "target": silver_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "null_pk_dropped": input_rows - after_null_drop,
        "duplicate_rows": after_null_drop - dedup_rows,
        "output_rows": valid_rows,
        "quarantined_rows": quarantine_rows,
        "transformations_applied": [
            "drop_null_pk", "deduplication_by_claim_id", "type_casting",
            "validation_checks", "pii_masking_hipaa", "derived_columns"
        ]
    }

    lineage_path = silver_path.replace('.parquet', '_lineage.json')
    with open(lineage_path, 'w') as f:
        json.dump(lineage, f, indent=2)

    tracer.log_rows(rows_in=input_rows, rows_out=valid_rows, quarantined=quarantine_rows)
    tracer.log_complete(status="success", rows_out=valid_rows, output_path=silver_path)
    tracer.close()

    return lineage


if __name__ == "__main__":
    if "--local" in sys.argv:
        bronze_idx = sys.argv.index("--bronze_path") + 1
        silver_idx = sys.argv.index("--silver_path") + 1
        bronze_path = sys.argv[bronze_idx]
        silver_path = sys.argv[silver_idx]

        with ScriptTracer.for_script(__file__) as tracer:
            lineage = transform_local_mode(bronze_path, silver_path, tracer=tracer)
        print(f"\n✓ Bronze → Silver complete")
        print(f"  Input: {lineage['input_rows']}, Output: {lineage['output_rows']}")
        print(f"  Null PK dropped: {lineage['null_pk_dropped']}")
        print(f"  Duplicates: {lineage['duplicate_rows']}")
        print(f"  Quarantined: {lineage['quarantined_rows']}")
    else:
        from awsglue.utils import getResolvedOptions
        from pyspark.context import SparkContext
        from awsglue.context import GlueContext
        from awsglue.job import Job

        args = getResolvedOptions(sys.argv, ['JOB_NAME', 'bronze_path', 'silver_path'])
        sc = SparkContext()
        glue_context = GlueContext(sc)
        job = Job(glue_context)
        job.init(args['JOB_NAME'], args)

        lineage = transform_glue_mode(glue_context, args)
        print(f"\n✓ Bronze → Silver complete (Glue)")
        print(f"  Input: {lineage['input_rows']}, Output: {lineage['output_rows']}")

        job.commit()
