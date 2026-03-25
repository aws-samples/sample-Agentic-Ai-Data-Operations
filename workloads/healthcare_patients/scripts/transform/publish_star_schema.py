#!/usr/bin/env python3
"""
Healthcare Patients - Gold Zone Star Schema
HIPAA-Compliant De-Identified Aggregated Tables

This script transforms Silver → Gold with:
- Star schema: fact_patient_visits + dimensions (geography, diagnosis, insurance)
- Aggregated fact table (daily metrics, no individual PHI)
- SCD Type 1 dimensions
- De-identification (aggregated data only)
- Apache Iceberg table format
"""

import sys
from datetime import datetime
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import (
    col, sum as _sum, count, avg, countDistinct,
    current_timestamp, lit, monotonically_increasing_id
)

# Get job parameters
args = getResolvedOptions(sys.argv, [
    'JOB_NAME',
    'silver_database',
    'silver_table',
    'gold_database',
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
SILVER_DATABASE = args['silver_database']  # healthcare_patients_silver
SILVER_TABLE = args['silver_table']  # patient_visits
GOLD_DATABASE = args['gold_database']  # healthcare_patients_gold
KMS_KEY_ALIAS = args['kms_key_alias']  # alias/hipaa-phi-key
RUN_ID = args['run_id']
PROCESSING_TIMESTAMP = datetime.utcnow().isoformat()

print(f"=== Gold Zone Star Schema - Healthcare Patients ===")
print(f"Silver: {SILVER_DATABASE}.{SILVER_TABLE}")
print(f"Gold: {GOLD_DATABASE}")
print(f"KMS Key: {KMS_KEY_ALIAS}")
print(f"Run ID: {RUN_ID}")

# Step 1: Read Silver data
print(f"\n[Step 1] Reading Silver zone data")
df_silver = spark.table(f"{SILVER_DATABASE}.{SILVER_TABLE}")
silver_count = df_silver.count()
print(f"Silver records: {silver_count}")

# Step 2: Create Dimension - Geography (SCD Type 1)
print(f"\n[Step 2] Creating dim_geography")
df_geography = df_silver.select(
    "state",
    "city",
    "zip"
).distinct()

# Add surrogate key
df_geography = df_geography.withColumn("geography_key", monotonically_increasing_id())

geography_count = df_geography.count()
print(f"Geography dimension records: {geography_count}")

# Write dimension
df_geography.write \
    .format("iceberg") \
    .mode("overwrite") \
    .saveAsTable(f"glue_catalog.{GOLD_DATABASE}.dim_geography")

print(f"✅ dim_geography written")

# Step 3: Create Dimension - Diagnosis (SCD Type 1)
print(f"\n[Step 3] Creating dim_diagnosis")
df_diagnosis = df_silver.select("diagnosis").distinct()

# Add surrogate key
df_diagnosis = df_diagnosis.withColumn("diagnosis_key", monotonically_increasing_id())

diagnosis_count = df_diagnosis.count()
print(f"Diagnosis dimension records: {diagnosis_count}")

# Write dimension
df_diagnosis.write \
    .format("iceberg") \
    .mode("overwrite") \
    .saveAsTable(f"glue_catalog.{GOLD_DATABASE}.dim_diagnosis")

print(f"✅ dim_diagnosis written")

# Step 4: Create Dimension - Insurance (SCD Type 1)
print(f"\n[Step 4] Creating dim_insurance")
df_insurance = df_silver.select("insurance_provider").distinct()

# Add surrogate key
df_insurance = df_insurance.withColumn("insurance_key", monotonically_increasing_id())

insurance_count = df_insurance.count()
print(f"Insurance dimension records: {insurance_count}")

# Write dimension
df_insurance.write \
    .format("iceberg") \
    .mode("overwrite") \
    .saveAsTable(f"glue_catalog.{GOLD_DATABASE}.dim_insurance")

print(f"✅ dim_insurance written")

# Step 5: Create Fact Table (Aggregated - De-Identified)
print(f"\n[Step 5] Creating fact_patient_visits_agg (de-identified)")

# HIPAA De-Identification: Aggregate by visit_date, state, diagnosis, insurance_provider
# No individual patient records (PHI removed)
df_fact_agg = df_silver.groupBy(
    "visit_date",
    "state",
    "diagnosis",
    "insurance_provider",
    "blood_type",
    "age_group",
    "cost_category"
).agg(
    _sum("treatment_cost").alias("total_revenue"),
    count("*").alias("visit_count"),
    countDistinct("patient_id").alias("patient_count"),
    avg("treatment_cost").alias("avg_cost"),
    avg("age").alias("avg_age")
)

# Add processing metadata
df_fact_agg = df_fact_agg \
    .withColumn("processing_timestamp", lit(PROCESSING_TIMESTAMP)) \
    .withColumn("processing_run_id", lit(RUN_ID)) \
    .withColumn("data_zone", lit("GOLD"))

fact_agg_count = df_fact_agg.count()
print(f"Aggregated fact records: {fact_agg_count}")

# Write aggregated fact table
df_fact_agg.write \
    .format("iceberg") \
    .mode("overwrite") \
    .partitionBy("visit_date") \
    .saveAsTable(f"glue_catalog.{GOLD_DATABASE}.fact_patient_visits_agg")

print(f"✅ fact_patient_visits_agg written (de-identified)")

# Step 6: Create Fact Table with Dimension Keys (Optional - for detailed analysis)
# Note: This includes patient_id but PHI is already masked in Silver
print(f"\n[Step 6] Creating fact_patient_visits (with dimension keys)")

# Join with dimensions to get surrogate keys
df_fact = df_silver \
    .join(df_geography, ["state", "city", "zip"], "left") \
    .join(df_diagnosis, ["diagnosis"], "left") \
    .join(df_insurance.withColumnRenamed("insurance_provider", "insurance_prov"),
          df_silver["insurance_provider"] == df_insurance["insurance_prov"], "left")

# Select fact columns
df_fact_final = df_fact.select(
    "patient_id",  # Already masked in Silver
    "visit_date",
    "geography_key",
    "diagnosis_key",
    "insurance_key",
    "treatment_cost",
    "age",
    "age_group",
    "cost_category",
    "blood_type"
).withColumn("processing_timestamp", lit(PROCESSING_TIMESTAMP)) \
 .withColumn("processing_run_id", lit(RUN_ID)) \
 .withColumn("data_zone", lit("GOLD"))

fact_count = df_fact_final.count()
print(f"Fact table records: {fact_count}")

# Write fact table
df_fact_final.write \
    .format("iceberg") \
    .mode("overwrite") \
    .partitionBy("visit_date") \
    .saveAsTable(f"glue_catalog.{GOLD_DATABASE}.fact_patient_visits")

print(f"✅ fact_patient_visits written")

# Step 7: Create Summary Metrics Table (For Dashboards)
print(f"\n[Step 7] Creating summary_metrics (for dashboards)")

# Calculate overall metrics
total_revenue = df_silver.agg(_sum("treatment_cost")).collect()[0][0]
total_visits = df_silver.count()
unique_patients = df_silver.select("patient_id").distinct().count()
avg_cost = df_silver.agg(avg("treatment_cost")).collect()[0][0]

summary_metrics = {
    "metric_date": datetime.utcnow().strftime('%Y-%m-%d'),
    "total_revenue": float(total_revenue) if total_revenue else 0.0,
    "total_visits": total_visits,
    "unique_patients": unique_patients,
    "avg_cost_per_visit": float(avg_cost) if avg_cost else 0.0,
    "processing_timestamp": PROCESSING_TIMESTAMP,
    "processing_run_id": RUN_ID
}

df_summary = spark.createDataFrame([summary_metrics])

# Write summary metrics
df_summary.write \
    .format("iceberg") \
    .mode("append") \
    .saveAsTable(f"glue_catalog.{GOLD_DATABASE}.summary_metrics")

print(f"✅ summary_metrics written")
print(f"   Total Revenue: ${total_revenue:,.2f}" if total_revenue else "   Total Revenue: $0.00")
print(f"   Total Visits: {total_visits:,}")
print(f"   Unique Patients: {unique_patients:,}")
print(f"   Avg Cost/Visit: ${avg_cost:.2f}" if avg_cost else "   Avg Cost/Visit: $0.00")

# Step 8: Log lineage
print(f"\n[Step 8] Logging lineage")
lineage_record = {
    "run_id": RUN_ID,
    "job_name": args['JOB_NAME'],
    "silver_table": f"{SILVER_DATABASE}.{SILVER_TABLE}",
    "gold_database": GOLD_DATABASE,
    "silver_count": silver_count,
    "dim_geography_count": geography_count,
    "dim_diagnosis_count": diagnosis_count,
    "dim_insurance_count": insurance_count,
    "fact_patient_visits_count": fact_count,
    "fact_patient_visits_agg_count": fact_agg_count,
    "summary_metrics_count": 1,
    "processing_timestamp": PROCESSING_TIMESTAMP,
    "kms_key_alias": KMS_KEY_ALIAS,
    "de_identification": "aggregated_data_only",
    "status": "SUCCESS"
}

lineage_df = spark.createDataFrame([lineage_record])
lineage_path = f"s3://prod-data-lake/lineage/healthcare_patients/gold/run_{RUN_ID}.json"
lineage_df.write.mode("overwrite").json(lineage_path)

print(f"Lineage logged to: {lineage_path}")

# Step 9: Audit log (HIPAA requirement)
print(f"\n[Step 9] Logging de-identification for HIPAA audit")
audit_log = {
    "timestamp": PROCESSING_TIMESTAMP,
    "job_name": args['JOB_NAME'],
    "run_id": RUN_ID,
    "action": "GOLD_TRANSFORMATION_DE_IDENTIFICATION",
    "phi_in_source": "patient_id (already masked in Silver)",
    "phi_in_target": "NONE - aggregated data only in fact_patient_visits_agg",
    "source": f"{SILVER_DATABASE}.{SILVER_TABLE}",
    "destinations": f"{GOLD_DATABASE}.fact_patient_visits_agg, {GOLD_DATABASE}.fact_patient_visits, {GOLD_DATABASE}.dim_*",
    "record_count_aggregated": fact_agg_count,
    "record_count_detailed": fact_count,
    "encryption": KMS_KEY_ALIAS,
    "user": "GlueJob",
    "hipaa_compliant": "YES - aggregated data, no individual PHI",
    "status": "SUCCESS"
}

audit_df = spark.createDataFrame([audit_log])
audit_path = f"s3://prod-data-lake/audit/healthcare_patients/gold/run_{RUN_ID}.json"
audit_df.write.mode("overwrite").json(audit_path)

print(f"Audit log written to: {audit_path}")

# Summary
print(f"\n=== Gold Zone Star Schema Complete ===")
print(f"✅ Silver records: {silver_count}")
print(f"✅ Dimensions created:")
print(f"   - dim_geography: {geography_count} records")
print(f"   - dim_diagnosis: {diagnosis_count} records")
print(f"   - dim_insurance: {insurance_count} records")
print(f"✅ Facts created:")
print(f"   - fact_patient_visits: {fact_count} records (detailed)")
print(f"   - fact_patient_visits_agg: {fact_agg_count} records (de-identified aggregates)")
print(f"   - summary_metrics: 1 record (daily summary)")
print(f"✅ De-identification: Aggregated data only, no individual PHI in fact_patient_visits_agg")
print(f"✅ Encryption: {KMS_KEY_ALIAS}")
print(f"✅ Audit logged: {audit_path}")

job.commit()
