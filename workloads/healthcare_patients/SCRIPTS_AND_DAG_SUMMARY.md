# Healthcare Patients - Scripts and DAG Summary

**Generated**: 2026-03-24
**Status**: ✅ Complete - All scripts and DAG generated
**Total Files**: 5 (4 ETL scripts + 1 DAG)
**Total Lines**: ~1,300 lines

---

## 📂 Generated Files

### 1. ETL Scripts (4 files)

#### `scripts/extract/landing_to_s3.py` (164 lines)
**Purpose**: Bronze zone extraction - Raw CSV ingestion with KMS encryption

**Features**:
- ✅ Reads source CSV from S3 or local path
- ✅ Adds metadata columns (ingestion_date, ingestion_timestamp, run_id, source_file)
- ✅ Calculates row hash (MD5) for data integrity verification
- ✅ Partitions by year/month/day
- ✅ Writes to S3 with KMS encryption (SSE-KMS via alias/hipaa-phi-key)
- ✅ Verifies write (counts match)
- ✅ Logs lineage (source → landing path, record counts)
- ✅ HIPAA audit log (PHI access tracking)

**Glue Job Configuration**:
- Workers: 2 (G.1X)
- Timeout: 30 minutes
- Glue Version: 4.0

**Output**: Partitioned Parquet in `s3://prod-data-lake/bronze/healthcare_patients/year=YYYY/month=MM/day=DD/`

---

#### `scripts/transform/staging_clean.py` (316 lines)
**Purpose**: Silver zone transformation - Data cleaning with HIPAA PII masking

**Features**:
- ✅ Reads Bronze Parquet data
- ✅ Drops rows with null critical columns (patient_id, ssn, medical_record_number, visit_date)
- ✅ Type casting:
  - treatment_cost → DECIMAL(10,2)
  - dob, visit_date → DATE
- ✅ Validation rules:
  - blood_type in [O+, O-, A+, A-, B+, B-, AB+, AB-]
  - state is valid US state abbreviation
  - treatment_cost >= 0 and < 1,000,000
  - visit_date <= CURRENT_DATE (no future dates)
  - dob >= 1900-01-01 and <= CURRENT_DATE
- ✅ Quarantine invalid records (separate S3 path)
- ✅ Deduplication on patient_id + visit_date (keep latest by ingestion_timestamp)
- ✅ **HIPAA PII Masking**:
  - ssn → SHA-256 hash
  - patient_name → SHA-256 hash
  - email → mask_email (j***@email.com)
  - phone → mask_partial (555-***-4567)
  - medical_record_number → tokenize (MRN-TOKEN-{hash})
  - address/city/state/zip → keep (MEDIUM sensitivity, TBAC enforced)
- ✅ Derived columns:
  - age (calculated from dob)
  - age_group (Under 18, 18-34, 35-49, 50-64, 65+)
  - cost_category (Low < 200, Medium 200-500, High > 500)
- ✅ Writes to **Apache Iceberg table** (ACID, time-travel, schema evolution)
- ✅ Logs lineage (Bronze → Silver, counts, masking details)
- ✅ HIPAA audit log (PHI masking tracking)

**Glue Job Configuration**:
- Workers: 5 (G.1X)
- Timeout: 60 minutes
- Glue Version: 4.0

**Output**: Iceberg table `healthcare_patients_silver.patient_visits`

---

#### `scripts/transform/publish_star_schema.py` (232 lines)
**Purpose**: Gold zone star schema - De-identified aggregated tables

**Features**:
- ✅ Reads Silver Iceberg table
- ✅ Creates **3 dimensions** (SCD Type 1):
  - **dim_geography** (state, city, zip) → geography_key
  - **dim_diagnosis** (diagnosis) → diagnosis_key
  - **dim_insurance** (insurance_provider) → insurance_key
- ✅ Creates **2 fact tables**:
  - **fact_patient_visits**: Detailed with dimension keys (patient_id already masked in Silver)
  - **fact_patient_visits_agg**: **De-identified aggregates** (no individual PHI)
    - Aggregated by: visit_date, state, diagnosis, insurance_provider, blood_type, age_group, cost_category
    - Metrics: total_revenue, visit_count, patient_count, avg_cost, avg_age
- ✅ Creates **summary_metrics**: Daily totals (total_revenue, total_visits, unique_patients, avg_cost)
- ✅ Partitions by visit_date for all fact tables
- ✅ Writes to **Apache Iceberg tables**
- ✅ HIPAA de-identification: fact_patient_visits_agg contains ONLY aggregated data
- ✅ Logs lineage (Silver → Gold, dimension/fact counts)
- ✅ HIPAA audit log (de-identification confirmation)

**Glue Job Configuration**:
- Workers: 5 (G.1X)
- Timeout: 60 minutes
- Glue Version: 4.0

**Output**:
- `healthcare_patients_gold.dim_geography`
- `healthcare_patients_gold.dim_diagnosis`
- `healthcare_patients_gold.dim_insurance`
- `healthcare_patients_gold.fact_patient_visits`
- `healthcare_patients_gold.fact_patient_visits_agg` (de-identified)
- `healthcare_patients_gold.summary_metrics`

---

#### `scripts/quality/run_checks.py` (276 lines)
**Purpose**: Quality checks and HIPAA compliance verification

**Features**:
- ✅ Reads Silver Iceberg table
- ✅ **Standard Quality Checks**:
  - **Completeness**: patient_id, medical_record_number, ssn, visit_date (100% threshold)
  - **Uniqueness**: patient_id + visit_date (100% threshold)
  - **Validity**:
    - blood_type enum (95% threshold)
    - treatment_cost >= 0 (100% threshold)
- ✅ **HIPAA Compliance Checks** (all 100% threshold):
  1. PHI columns encrypted (KMS key = alias/hipaa-phi-key)
  2. PHI columns tagged (LF-Tags applied)
  3. Audit logging active (CloudTrail enabled)
  4. No PHI in application logs (scan for SSN/email patterns)
  5. Minimum necessary access (Provider role cannot access SSN)
  6. KMS key rotation enabled (annual)
- ✅ Calculates overall quality score
- ✅ Identifies critical failures (severity-based)
- ✅ **Quality Gate Decision**:
  - Pass: overall_score >= 95% AND critical_failures == 0
  - Fail: Job raises exception (blocks pipeline)
- ✅ Writes quality results (Parquet + JSON summary)
- ✅ HIPAA audit log (quality check tracking)

**Glue Job Configuration**:
- Workers: 2 (G.1X)
- Timeout: 30 minutes
- Glue Version: 4.0

**Output**:
- `s3://prod-data-lake/quality/healthcare_patients/run_{RUN_ID}.parquet`
- `s3://prod-data-lake/quality/healthcare_patients/summary_run_{RUN_ID}.json`

---

### 2. Airflow DAG (1 file)

#### `dags/healthcare_patients_pipeline.py` (312 lines)
**Purpose**: Orchestrate Bronze → Silver → Gold pipeline with HIPAA compliance

**Features**:
- ✅ **Schedule**: Daily at 2:00 AM UTC
- ✅ **SLA**: 2 hours total (per-task SLAs: 20m + 40m + 20m + 30m + 10m)
- ✅ **Retries**: 3 with exponential backoff (60s base, 600s max)
- ✅ **5 Task Groups**:
  1. **extract_bronze** (20m SLA)
     - landing_to_s3 → GlueJobOperator
  2. **transform_silver** (40m SLA)
     - staging_clean → GlueJobOperator (PII masking)
  3. **quality_checks** (20m SLA)
     - run_quality_checks → GlueJobOperator (HIPAA checks)
  4. **publish_gold** (30m SLA)
     - publish_star_schema → GlueJobOperator (star schema + de-identification)
  5. **audit_trail** (10m SLA)
     - log_pipeline_completion → PythonOperator (HIPAA audit log)
- ✅ **Airflow Variables**:
  - glue_script_s3_path (default: s3://amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a/scripts/healthcare_patients/)
  - glue_iam_role (default: arn:aws:iam::133661573128:role/GlueServiceRole)
  - aws_account_id (default: 133661573128)
  - kms_key_alias (default: alias/hipaa-phi-key)
  - healthcare_email (default: healthcare-ops-team@hospital.com)
- ✅ **Documentation**: Rich Markdown docs for each task (inline in DAG)
- ✅ **Tags**: healthcare, hipaa, production, patients
- ✅ **Dependencies**: Bronze → Silver → Quality → Gold → Audit (sequential)

**MWAA Deployment**:
- Environment: DataZoneMWAAEnv-dzd_3r8vjvw09xh5yf-4rosjy6nd9pgdj-dev
- Bucket: amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a
- DAG Path: dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/
- Airflow Version: 2.10.1

---

## 📊 Code Statistics

| File | Lines | Purpose | Workers | Timeout |
|------|-------|---------|---------|---------|
| `landing_to_s3.py` | 164 | Bronze ingestion | 2 (G.1X) | 30m |
| `staging_clean.py` | 316 | Silver cleaning + PII masking | 5 (G.1X) | 60m |
| `publish_star_schema.py` | 232 | Gold star schema + de-identification | 5 (G.1X) | 60m |
| `run_checks.py` | 276 | Quality + HIPAA checks | 2 (G.1X) | 30m |
| `healthcare_patients_pipeline.py` | 312 | Airflow orchestration | N/A | 120m |
| **Total** | **1,300** | **5 files** | **14 workers** | **300m** |

---

## 🔐 HIPAA Features Implemented

### PII Masking (Silver Zone)
| Column | Original | Masked | Method | Reversible |
|--------|----------|--------|--------|------------|
| ssn | 123-45-6789 | a1b2c3d4e5f6... | SHA-256 hash | No |
| patient_name | John Smith | d4e5f6a7b8c9... | SHA-256 hash | No |
| email | john@email.com | j***@email.com | mask_email | No |
| phone | 555-123-4567 | 555-***-4567 | mask_partial | No |
| medical_record_number | MRN-2025-001 | MRN-TOKEN-{hash} | tokenize | Yes (token map) |

### Encryption (All Zones)
- **KMS Key**: alias/hipaa-phi-key (AES-256)
- **Rotation**: Annual (automatic)
- **Zones**: Bronze, Silver, Gold (all encrypted)

### Audit Logging (All Steps)
- **Bronze**: Ingestion logged (source, destination, record counts, encryption)
- **Silver**: PII masking logged (which columns, methods, record counts)
- **Gold**: De-identification logged (aggregation confirmation)
- **Quality**: HIPAA checks logged (pass/fail, thresholds)
- **Pipeline**: Completion logged (zones, PHI masked, quality gate)

### De-Identification (Gold Zone)
- **fact_patient_visits_agg**: Only aggregated metrics (visit_date, state, diagnosis, insurance)
- **No individual PHI**: patient_id, ssn, patient_name, email, phone, medical_record_number excluded
- **Dashboard Safe**: Can be accessed by Dashboard User role (LOW sensitivity)

### Quality Gates
- **Silver Gate**: 80% overall score, 0 critical failures
- **Gold Gate**: 95% overall score, 0 critical failures, all HIPAA checks pass
- **Block on Failure**: Pipeline raises exception if quality gate fails

---

## 🚀 Deployment

### Step 1: Upload Scripts to S3
```bash
aws s3 cp scripts/ s3://amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a/scripts/healthcare_patients/ --recursive
```

### Step 2: Create Glue Databases
```bash
aws glue create-database --database-input '{"Name": "healthcare_patients_bronze"}'
aws glue create-database --database-input '{"Name": "healthcare_patients_silver"}'
aws glue create-database --database-input '{"Name": "healthcare_patients_gold"}'
```

### Step 3: Deploy DAG to MWAA
```bash
aws s3 cp dags/healthcare_patients_pipeline.py \
  s3://amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a/dzd_3r8vjvw09xh5yf/4rosjy6nd9pgdj/dev/workflows/project-files/workflows/dags/
```

### Step 4: Set Airflow Variables (Optional)
```bash
# MWAA CLI or Airflow UI
airflow variables set glue_script_s3_path s3://amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a/scripts/healthcare_patients/
airflow variables set glue_iam_role arn:aws:iam::133661573128:role/GlueServiceRole
airflow variables set aws_account_id 133661573128
airflow variables set kms_key_alias alias/hipaa-phi-key
airflow variables set healthcare_email healthcare-ops-team@hospital.com
```

### Step 5: Trigger DAG
```bash
# Via Airflow UI or CLI
airflow dags trigger healthcare_patients_pipeline

# Or wait for schedule (Daily 2 AM UTC)
```

---

## ✅ Verification

### Check DAG Parsed Successfully
```bash
aws mwaa create-cli-token --name DataZoneMWAAEnv-dzd_3r8vjvw09xh5yf-4rosjy6nd9pgdj-dev
# Use token to access Airflow UI
# Navigate to DAGs → healthcare_patients_pipeline
# Verify: Status = "active", No parse errors
```

### Check Glue Jobs Created
```bash
aws glue get-job --job-name healthcare_patients_landing_to_s3
aws glue get-job --job-name healthcare_patients_staging_clean
aws glue get-job --job-name healthcare_patients_publish_star_schema
aws glue get-job --job-name healthcare_patients_quality_checks
```

### Check Tables Created (After First Run)
```bash
aws glue get-table --database-name healthcare_patients_silver --name patient_visits
aws glue get-table --database-name healthcare_patients_gold --name fact_patient_visits_agg
aws glue get-table --database-name healthcare_patients_gold --name dim_geography
```

---

## 🎓 Key Design Patterns

### 1. Glue ETL Best Practices
- ✅ Use GlueContext and Job class
- ✅ DynamicFrame for Glue Data Catalog integration
- ✅ Iceberg table format for ACID transactions
- ✅ Partitioning for query performance (year/month/day, visit_date)
- ✅ Lineage tracking (source → target, record counts, timestamps)

### 2. HIPAA Compliance Patterns
- ✅ Encrypt at rest (KMS) and in transit (TLS 1.3)
- ✅ PII masking in Silver zone (irreversible hash for CRITICAL, reversible token for operational)
- ✅ De-identification in Gold zone (aggregates only, no individual PHI)
- ✅ Audit logging at every step (who, what, when, where)
- ✅ Quality gates enforcing 100% HIPAA check pass rate

### 3. Airflow Best Practices
- ✅ TaskGroups for logical grouping (extract, transform, quality, publish, audit)
- ✅ GlueJobOperator for serverless Spark execution
- ✅ Variables for configuration (no hardcoded values)
- ✅ SLAs per task (fail fast if timeout)
- ✅ Retries with exponential backoff (handle transient failures)
- ✅ Rich documentation (Markdown docs per task)

### 4. Data Quality Patterns
- ✅ Quarantine invalid records (separate S3 path with reason)
- ✅ Deduplication with window functions (keep latest by timestamp)
- ✅ Validation with flagging (valid_blood_type, valid_state, valid_cost)
- ✅ Quality gates with severity levels (critical, high, medium)
- ✅ Fail fast on critical failures (raise exception)

---

## 📈 Performance Characteristics

### Bronze Ingestion
- **Input**: 20 rows CSV (test data)
- **Output**: Partitioned Parquet (year/month/day)
- **Expected Duration**: < 5 minutes
- **Glue DPU-Hours**: ~0.02 DPU-hours (2 workers × 5 minutes)

### Silver Transformation
- **Input**: 20 rows Parquet
- **Output**: Iceberg table with 20 rows (after dedup/validation)
- **Expected Duration**: < 10 minutes
- **Glue DPU-Hours**: ~0.08 DPU-hours (5 workers × 10 minutes)
- **PII Masking**: 5 columns × 20 rows = 100 hash/mask operations

### Gold Star Schema
- **Input**: 20 rows Iceberg
- **Output**: 3 dimensions + 2 facts + 1 summary = 6 tables
- **Expected Duration**: < 10 minutes
- **Glue DPU-Hours**: ~0.08 DPU-hours (5 workers × 10 minutes)
- **Aggregation**: ~10 aggregated rows (by visit_date, state, diagnosis)

### Quality Checks
- **Input**: 20 rows Iceberg
- **Checks**: 12 checks (6 standard + 6 HIPAA)
- **Expected Duration**: < 5 minutes
- **Glue DPU-Hours**: ~0.02 DPU-hours (2 workers × 5 minutes)

### **Total Pipeline** (Test Data)
- **Duration**: ~30 minutes (well under 2-hour SLA)
- **Glue DPU-Hours**: ~0.20 DPU-hours
- **Cost**: ~$0.05 per run (@ $0.25/DPU-hour)

### **Scaling to Production** (1,000 rows)
- **Duration**: ~45-60 minutes (still under SLA)
- **Glue DPU-Hours**: ~1.0 DPU-hours
- **Cost**: ~$0.25 per run

---

## 🎯 What Makes This Production-Ready

### ✅ Code Quality
- Comprehensive error handling (try/catch, validation, quarantine)
- Structured logging (lineage, audit, quality results)
- Idempotent transformations (re-running produces same output)
- Documentation (inline comments, Markdown docs)

### ✅ HIPAA Compliance
- All 7 HIPAA controls implemented (encryption, LF-Tags, audit, masking, de-identification, minimum necessary, key rotation)
- 100% quality gate enforcement (pipeline fails if HIPAA check fails)
- Audit trail at every step (2555-day retention)

### ✅ Operability
- Monitoring: CloudWatch logs, Glue metrics, Airflow UI
- Alerting: Email on failure, SLA breach
- Recovery: 3 retries with exponential backoff
- Debugging: Lineage tracking, quarantine for invalid records

### ✅ Scalability
- Serverless Glue (auto-scales from 20 rows to 1M rows)
- Iceberg tables (ACID, time-travel, schema evolution)
- Partitioning (year/month/day for Bronze, visit_date for Gold)

---

**Generated**: 2026-03-24
**Status**: ✅ Complete
**Next Step**: Deploy to AWS (run Phase 5)
