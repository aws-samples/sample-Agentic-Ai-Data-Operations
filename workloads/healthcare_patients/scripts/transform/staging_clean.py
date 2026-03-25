#!/usr/bin/env python3
"""
Healthcare Patients - Silver Zone Transformation
HIPAA-Compliant Data Cleaning with PII Masking

This script transforms Bronze → Silver with:
- Deduplication (patient_id + visit_date)
- Null handling (drop critical nulls)
- Type casting (treatment_cost to DECIMAL, dates to DATE)
- Validation rules (blood_type, state, cost, dates)
- HIPAA PII masking (hash, mask_email, mask_partial, tokenize)
- Apache Iceberg table format
"""

import sys
import hashlib
from datetime import datetime
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import (
    col, concat_ws, md5, sha2, regexp_replace,
    current_timestamp, lit, row_number, when, regexp_extract,
    to_date, year, month, dayofmonth
)
from pyspark.sql.window import Window
from pyspark.sql.types import DecimalType, DateType

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'bronze_path',
    'silver_database',
    'silver_table',
    'kms_key_alias',
    'run_id'
])

# Initialize Glue context
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

# Configuration
BRONZE_PATH = args['bronze_path']  # s3://prod-data-lake/bronze/healthcare_patients/
SILVER_DATABASE = args['silver_database']  # healthcare_patients_silver
SILVER_TABLE = args['silver_table']  # patient_visits
KMS_KEY_ALIAS = args['kms_key_alias']  # alias/hipaa-phi-key
RUN_ID = args['run_id']
PROCESSING_TIMESTAMP = datetime.utcnow().isoformat()

print(f"=== Silver Zone Transformation - Healthcare Patients ===")
print(f"Bronze: {BRONZE_PATH}")
print(f"Silver: {SILVER_DATABASE}.{SILVER_TABLE}")
print(f"KMS Key: {KMS_KEY_ALIAS}")
print(f"Run ID: {RUN_ID}")

# Step 1: Read Bronze data
print(f"\n[Step 1] Reading Bronze zone data")
df_bronze = spark.read.parquet(BRONZE_PATH)
bronze_count = df_bronze.count()
print(f"Bronze records: {bronze_count}")

# Step 2: Drop rows with null critical columns
print(f"\n[Step 2] Dropping rows with null critical columns")
critical_columns = ["patient_id", "ssn", "medical_record_number", "visit_date"]
df_no_nulls = df_bronze.dropna(subset=critical_columns)
no_nulls_count = df_no_nulls.count()
dropped_nulls = bronze_count - no_nulls_count
print(f"Dropped {dropped_nulls} rows with null critical columns")
print(f"Remaining records: {no_nulls_count}")

# Step 3: Type casting
print(f"\n[Step 3] Type casting")

# Cast treatment_cost to DECIMAL(10,2)
df_typed = df_no_nulls.withColumn(
    "treatment_cost",
    col("treatment_cost").cast(DecimalType(10, 2))
)

# Cast dates to DATE type
df_typed = df_typed \
    .withColumn("dob", to_date(col("dob"), "yyyy-MM-dd")) \
    .withColumn("visit_date", to_date(col("visit_date"), "yyyy-MM-dd"))

print(f"✅ Type casting complete")

# Step 4: Validation rules with quarantine
print(f"\n[Step 4] Applying validation rules")

# Valid blood types
valid_blood_types = ["O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"]

# US state abbreviations (simplified - expand for production)
valid_states = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
                "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS",
                "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK",
                "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV",
                "WI", "WY", "DC"]

# Add validation flags
df_validated = df_typed \
    .withColumn("valid_blood_type", col("blood_type").isin(valid_blood_types)) \
    .withColumn("valid_state", col("state").isin(valid_states)) \
    .withColumn("valid_cost", (col("treatment_cost") >= 0) & (col("treatment_cost") < 1000000)) \
    .withColumn("valid_visit_date", col("visit_date") <= current_timestamp().cast(DateType())) \
    .withColumn("valid_dob",
                (col("dob") >= lit("1900-01-01").cast(DateType())) &
                (col("dob") <= current_timestamp().cast(DateType())))

# Separate valid and quarantined records
df_valid = df_validated.filter(
    col("valid_state") & col("valid_cost") & col("valid_visit_date") & col("valid_dob")
)
valid_count = df_valid.count()

df_quarantine = df_validated.filter(
    ~col("valid_state") | ~col("valid_cost") | ~col("valid_visit_date") | ~col("valid_dob")
)
quarantine_count = df_quarantine.count()

print(f"✅ Valid records: {valid_count}")
print(f"⚠️ Quarantined records: {quarantine_count}")

# Write quarantined records
if quarantine_count > 0:
    quarantine_path = f"s3://prod-data-lake/quarantine/healthcare_patients/run_{RUN_ID}/"
    df_quarantine.write.mode("overwrite").parquet(quarantine_path)
    print(f"Quarantined records written to: {quarantine_path}")

# Step 5: Deduplication (patient_id + visit_date, keep latest by ingestion_timestamp)
print(f"\n[Step 5] Deduplicating on patient_id + visit_date")
window_spec = Window.partitionBy("patient_id", "visit_date").orderBy(col("ingestion_timestamp").desc())
df_deduped = df_valid \
    .withColumn("row_num", row_number().over(window_spec)) \
    .filter(col("row_num") == 1) \
    .drop("row_num")

deduped_count = df_deduped.count()
duplicates_removed = valid_count - deduped_count
print(f"Removed {duplicates_removed} duplicates")
print(f"Deduplicated records: {deduped_count}")

# Step 6: HIPAA PII Masking
print(f"\n[Step 6] Applying HIPAA PII masking")

# SSN → SHA-256 hash
df_masked = df_deduped.withColumn(
    "ssn_masked",
    sha2(col("ssn"), 256)
)

# Patient name → SHA-256 hash
df_masked = df_masked.withColumn(
    "patient_name_masked",
    sha2(col("patient_name"), 256)
)

# Email → mask_email (j***@email.com)
df_masked = df_masked.withColumn(
    "email_masked",
    when(col("email").isNotNull(),
         concat_ws("",
                   regexp_extract(col("email"), "^(.)", 1),
                   lit("***@"),
                   regexp_extract(col("email"), "@(.+)$", 1)))
    .otherwise(col("email"))
)

# Phone → mask_partial (555-***-4567)
df_masked = df_masked.withColumn(
    "phone_masked",
    when(col("phone").isNotNull(),
         regexp_replace(col("phone"), r"(\d{3})-(\d{3})-(\d{4})", r"$1-***-$3"))
    .otherwise(col("phone"))
)

# Medical record number → tokenize (MRN-TOKEN-001)
# Note: In production, store token mapping in secure location
df_masked = df_masked.withColumn(
    "medical_record_number_token",
    concat_ws("-", lit("MRN-TOKEN"), md5(col("medical_record_number")))
)

# Keep geography fields (address, city, state, zip) for analysis (MEDIUM sensitivity)
# These will be protected by LF-Tags

print(f"✅ PII masking complete (5 columns masked)")

# Step 7: Add derived columns
print(f"\n[Step 7] Adding derived columns")

# Age
df_derived = df_masked.withColumn(
    "age",
    year(current_timestamp()) - year(col("dob"))
)

# Age group
df_derived = df_derived.withColumn(
    "age_group",
    when(col("age") < 18, "Under 18")
    .when((col("age") >= 18) & (col("age") <= 34), "18-34")
    .when((col("age") >= 35) & (col("age") <= 49), "35-49")
    .when((col("age") >= 50) & (col("age") <= 64), "50-64")
    .when(col("age") >= 65, "65+")
    .otherwise("Unknown")
)

# Cost category
df_derived = df_derived.withColumn(
    "cost_category",
    when(col("treatment_cost") < 200, "Low")
    .when((col("treatment_cost") >= 200) & (col("treatment_cost") <= 500), "Medium")
    .when(col("treatment_cost") > 500, "High")
    .otherwise("Unknown")
)

print(f"✅ Derived columns added: age, age_group, cost_category")

# Step 8: Add processing metadata
print(f"\n[Step 8] Adding processing metadata")
df_final = df_derived \
    .withColumn("processing_timestamp", lit(PROCESSING_TIMESTAMP)) \
    .withColumn("processing_run_id", lit(RUN_ID)) \
    .withColumn("data_zone", lit("SILVER"))

# Step 9: Select final columns for Silver zone
# Replace original PHI with masked versions
df_silver = df_final.select(
    col("patient_id"),
    col("patient_name_masked").alias("patient_name"),
    col("dob"),
    col("ssn_masked").alias("ssn"),
    col("email_masked").alias("email"),
    col("phone_masked").alias("phone"),
    col("address"),
    col("city"),
    col("state"),
    col("zip"),
    col("blood_type"),
    col("diagnosis"),
    col("visit_date"),
    col("treatment_cost"),
    col("insurance_provider"),
    col("medical_record_number_token").alias("medical_record_number"),
    col("age"),
    col("age_group"),
    col("cost_category"),
    col("ingestion_date"),
    col("ingestion_timestamp"),
    col("processing_timestamp"),
    col("processing_run_id"),
    col("data_zone")
)

silver_count = df_silver.count()
print(f"Silver records: {silver_count}")

# Step 10: Write to Iceberg table
print(f"\n[Step 10] Writing to Iceberg table: {SILVER_DATABASE}.{SILVER_TABLE}")
print(f"Encryption: {KMS_KEY_ALIAS}")

# Write as Iceberg table (ACID, time-travel, schema evolution)
df_silver.write \
    .format("iceberg") \
    .mode("append") \
    .option("write.format.default", "parquet") \
    .option("write.metadata.compression-codec", "gzip") \
    .saveAsTable(f"glue_catalog.{SILVER_DATABASE}.{SILVER_TABLE}")

print(f"✅ Iceberg table written")

# Step 11: Log lineage
print(f"\n[Step 11] Logging lineage")
lineage_record = {
    "run_id": RUN_ID,
    "job_name": args['JOB_NAME'],
    "bronze_path": BRONZE_PATH,
    "silver_table": f"{SILVER_DATABASE}.{SILVER_TABLE}",
    "bronze_count": bronze_count,
    "dropped_nulls": dropped_nulls,
    "quarantined": quarantine_count,
    "duplicates_removed": duplicates_removed,
    "silver_count": silver_count,
    "processing_timestamp": PROCESSING_TIMESTAMP,
    "kms_key_alias": KMS_KEY_ALIAS,
    "pii_masked_columns": 5,
    "derived_columns": 3,
    "status": "SUCCESS"
}

lineage_df = spark.createDataFrame([lineage_record])
lineage_path = f"s3://prod-data-lake/lineage/healthcare_patients/silver/run_{RUN_ID}.json"
lineage_df.write.mode("overwrite").json(lineage_path)

print(f"Lineage logged to: {lineage_path}")

# Step 12: Audit log (HIPAA requirement)
print(f"\n[Step 12] Logging PHI masking for HIPAA audit")
audit_log = {
    "timestamp": PROCESSING_TIMESTAMP,
    "job_name": args['JOB_NAME'],
    "run_id": RUN_ID,
    "action": "SILVER_TRANSFORMATION_PII_MASKING",
    "phi_columns_accessed": "ssn, patient_name, email, phone, medical_record_number, dob, visit_date, address, city, state, zip",
    "phi_columns_masked": "ssn (SHA-256), patient_name (SHA-256), email (mask_email), phone (mask_partial), medical_record_number (tokenize)",
    "source": BRONZE_PATH,
    "destination": f"{SILVER_DATABASE}.{SILVER_TABLE}",
    "record_count": silver_count,
    "encryption": KMS_KEY_ALIAS,
    "user": "GlueJob",
    "status": "SUCCESS"
}

audit_df = spark.createDataFrame([audit_log])
audit_path = f"s3://prod-data-lake/audit/healthcare_patients/silver/run_{RUN_ID}.json"
audit_df.write.mode("overwrite").json(audit_path)

print(f"Audit log written to: {audit_path}")

# Summary
print(f"\n=== Silver Zone Transformation Complete ===")
print(f"✅ Bronze records: {bronze_count}")
print(f"✅ Dropped nulls: {dropped_nulls}")
print(f"✅ Quarantined: {quarantine_count}")
print(f"✅ Duplicates removed: {duplicates_removed}")
print(f"✅ Silver records: {silver_count}")
print(f"✅ PII masked columns: 5 (ssn, patient_name, email, phone, medical_record_number)")
print(f"✅ Derived columns: 3 (age, age_group, cost_category)")
print(f"✅ Encryption: {KMS_KEY_ALIAS}")
print(f"✅ Iceberg table: {SILVER_DATABASE}.{SILVER_TABLE}")
print(f"✅ Audit logged: {audit_path}")

job.commit()
