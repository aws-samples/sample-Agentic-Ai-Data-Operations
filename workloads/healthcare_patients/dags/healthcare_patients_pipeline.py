"""
Healthcare Patients Data Pipeline - HIPAA Compliant
Airflow DAG for Bronze → Silver → Gold transformation with HIPAA compliance checks

Schedule: Daily at 2:00 AM UTC
SLA: 2 hours
Owner: Healthcare Operations Team
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.operators.python import PythonOperator
from airflow.utils.task_group import TaskGroup
from airflow.models import Variable

# Default arguments
default_args = {
    'owner': 'Healthcare Operations Team',
    'depends_on_past': False,
    'email': [Variable.get('healthcare_email', default_var='healthcare-ops-team@hospital.com')],
    'email_on_failure': True,
    'email_on_retry': False,
    'retries': 3,
    'retry_delay': timedelta(seconds=60),
    'retry_exponential_backoff': True,
    'max_retry_delay': timedelta(seconds=600),
    'execution_timeout': timedelta(minutes=120),
}

# Configuration from Airflow Variables
GLUE_SCRIPT_PATH = Variable.get('glue_script_s3_path', default_var='s3://amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a/scripts/healthcare_patients/')
GLUE_IAM_ROLE = Variable.get('glue_iam_role', default_var='arn:aws:iam::133661573128:role/GlueServiceRole')
AWS_ACCOUNT_ID = Variable.get('aws_account_id', default_var='133661573128')
KMS_KEY_ALIAS = Variable.get('kms_key_alias', default_var='alias/hipaa-phi-key')

# S3 paths
SOURCE_PATH = 's3://prod-data-lake/raw/healthcare/patients/'
BRONZE_PATH = 's3://prod-data-lake/bronze/healthcare_patients/'
SILVER_DATABASE = 'healthcare_patients_silver'
SILVER_TABLE = 'patient_visits'
GOLD_DATABASE = 'healthcare_patients_gold'

# Run ID for lineage tracking
RUN_ID = "{{ run_id }}"

def log_pipeline_completion(**context):
    """Log pipeline completion for HIPAA audit trail"""
    from datetime import datetime
    import json

    run_id = context['run_id']
    execution_date = context['execution_date']

    audit_log = {
        'timestamp': datetime.utcnow().isoformat(),
        'dag_id': 'healthcare_patients_pipeline',
        'run_id': run_id,
        'execution_date': str(execution_date),
        'action': 'PIPELINE_COMPLETE',
        'zones': ['BRONZE', 'SILVER', 'GOLD'],
        'phi_masked': True,
        'hipaa_compliant': True,
        'quality_gate_passed': True,
        'encryption': KMS_KEY_ALIAS,
        'user': 'Airflow',
        'status': 'SUCCESS'
    }

    print(json.dumps(audit_log, indent=2))
    return audit_log

# DAG definition with context manager
with DAG(
    'healthcare_patients_pipeline',
    default_args=default_args,
    description='HIPAA-compliant patient visit data pipeline (Bronze → Silver → Gold)',
    schedule_interval='0 2 * * *',  # Daily at 2 AM UTC
    start_date=datetime(2026, 3, 24),
    catchup=False,
    max_active_runs=1,
    tags=['healthcare', 'hipaa', 'production', 'patients'],
    doc_md="""
    # Healthcare Patients Data Pipeline

    **HIPAA Compliant** - Protected Health Information (PHI) handling

    ## Data Flow
    1. **Bronze**: Raw CSV ingestion with KMS encryption
    2. **Silver**: Cleaned data with PII masking (hash SSN, mask email, tokenize MRN)
    3. **Gold**: Star schema with de-identified aggregations

    ## Compliance Controls
    - Encryption: AES-256 via alias/hipaa-phi-key
    - PII Masking: 5 PHI columns masked in Silver
    - Audit Logging: All PHI access logged to CloudTrail
    - TBAC: Minimum necessary access (Provider cannot access SSN)
    - Retention: 2555 days (7 years - HIPAA minimum)

    ## Quality Gates
    - Silver: 80% overall score, 0 critical failures
    - Gold: 95% overall score, 0 critical failures, all HIPAA checks pass

    ## Owner
    Healthcare Operations Team (healthcare-ops-team@hospital.com)
    """,
) as dag:

    # ========================================
    # TASK GROUP: EXTRACT (Bronze Zone)
    # ========================================

    with TaskGroup(group_id='extract_bronze', tooltip='Extract raw data to Bronze zone') as extract_bronze:

        landing_to_s3 = GlueJobOperator(
            task_id='landing_to_s3',
            job_name='healthcare_patients_landing_to_s3',
            script_location=f'{GLUE_SCRIPT_PATH}/extract/landing_to_s3.py',
            iam_role_name=GLUE_IAM_ROLE.split('/')[-1],
            s3_bucket='amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a',
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
                'Timeout': 30,
                'DefaultArguments': {
                    '--enable-metrics': 'true',
                    '--enable-continuous-cloudwatch-log': 'true',
                    '--enable-spark-ui': 'true',
                    '--source_path': SOURCE_PATH,
                    '--landing_path': BRONZE_PATH,
                    '--kms_key_alias': KMS_KEY_ALIAS,
                    '--run_id': RUN_ID,
                },
            },
            region_name='us-east-1',
            wait_for_completion=True,
            execution_timeout=timedelta(minutes=30),
            doc_md="""
            ## Bronze Zone Extraction

            **Purpose**: Copy raw CSV to S3 with KMS encryption

            **Compliance**:
            - Encryption: alias/hipaa-phi-key (AES-256)
            - Partitioning: year/month/day
            - Immutable: write-once, append-only
            - Audit: All ingestion logged

            **SLA**: 20 minutes
            """,
        )

    # ========================================
    # TASK GROUP: TRANSFORM (Silver Zone)
    # ========================================

    with TaskGroup(group_id='transform_silver', tooltip='Clean and mask data in Silver zone') as transform_silver:

        staging_clean = GlueJobOperator(
            task_id='staging_clean',
            job_name='healthcare_patients_staging_clean',
            script_location=f'{GLUE_SCRIPT_PATH}/transform/staging_clean.py',
            iam_role_name=GLUE_IAM_ROLE.split('/')[-1],
            s3_bucket='amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a',
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 5,
                'WorkerType': 'G.1X',
                'Timeout': 60,
                'DefaultArguments': {
                    '--enable-metrics': 'true',
                    '--enable-continuous-cloudwatch-log': 'true',
                    '--enable-spark-ui': 'true',
                    '--bronze_path': BRONZE_PATH,
                    '--silver_database': SILVER_DATABASE,
                    '--silver_table': SILVER_TABLE,
                    '--kms_key_alias': KMS_KEY_ALIAS,
                    '--run_id': RUN_ID,
                    '--datalake-formats': 'iceberg',
                },
            },
            region_name='us-east-1',
            wait_for_completion=True,
            execution_timeout=timedelta(minutes=60),
            doc_md="""
            ## Silver Zone Transformation

            **Purpose**: Clean data with HIPAA PII masking

            **Transformations**:
            - Deduplication: patient_id + visit_date (keep latest)
            - Null handling: Drop critical nulls, keep non-critical
            - Type casting: treatment_cost to DECIMAL, dates to DATE
            - Validation: blood_type, state, cost, dates
            - **PII Masking**:
              - ssn → SHA-256 hash
              - patient_name → SHA-256 hash
              - email → mask_email (j***@email.com)
              - phone → mask_partial (555-***-4567)
              - medical_record_number → tokenize

            **Output**: Apache Iceberg table (ACID, time-travel)

            **SLA**: 40 minutes
            """,
        )

    # ========================================
    # TASK GROUP: QUALITY (HIPAA Compliance)
    # ========================================

    with TaskGroup(group_id='quality_checks', tooltip='Run quality and HIPAA compliance checks') as quality_checks:

        run_quality_checks = GlueJobOperator(
            task_id='run_quality_checks',
            job_name='healthcare_patients_quality_checks',
            script_location=f'{GLUE_SCRIPT_PATH}/quality/run_checks.py',
            iam_role_name=GLUE_IAM_ROLE.split('/')[-1],
            s3_bucket='amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a',
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 2,
                'WorkerType': 'G.1X',
                'Timeout': 30,
                'DefaultArguments': {
                    '--enable-metrics': 'true',
                    '--enable-continuous-cloudwatch-log': 'true',
                    '--silver_database': SILVER_DATABASE,
                    '--silver_table': SILVER_TABLE,
                    '--kms_key_alias': KMS_KEY_ALIAS,
                    '--run_id': RUN_ID,
                },
            },
            region_name='us-east-1',
            wait_for_completion=True,
            execution_timeout=timedelta(minutes=30),
            doc_md="""
            ## Quality & HIPAA Compliance Checks

            **Standard Checks**:
            - Completeness: 100% for critical columns
            - Uniqueness: 100% for patient_id + visit_date
            - Validity: blood_type, state, cost, dates

            **HIPAA Checks** (100% threshold):
            1. PHI columns encrypted (alias/hipaa-phi-key)
            2. PHI columns tagged (LF-Tags applied)
            3. Audit logging active (CloudTrail enabled)
            4. No PHI in application logs
            5. Minimum necessary access (Provider cannot access SSN)
            6. KMS key rotation enabled (annual)

            **Quality Gate**: 95% overall score, 0 critical failures

            **SLA**: 20 minutes
            """,
        )

    # ========================================
    # TASK GROUP: PUBLISH (Gold Zone)
    # ========================================

    with TaskGroup(group_id='publish_gold', tooltip='Create star schema in Gold zone') as publish_gold:

        publish_star_schema = GlueJobOperator(
            task_id='publish_star_schema',
            job_name='healthcare_patients_publish_star_schema',
            script_location=f'{GLUE_SCRIPT_PATH}/transform/publish_star_schema.py',
            iam_role_name=GLUE_IAM_ROLE.split('/')[-1],
            s3_bucket='amazon-sagemaker-133661573128-us-east-1-e8cea5855b8a',
            create_job_kwargs={
                'GlueVersion': '4.0',
                'NumberOfWorkers': 5,
                'WorkerType': 'G.1X',
                'Timeout': 60,
                'DefaultArguments': {
                    '--enable-metrics': 'true',
                    '--enable-continuous-cloudwatch-log': 'true',
                    '--enable-spark-ui': 'true',
                    '--silver_database': SILVER_DATABASE,
                    '--silver_table': SILVER_TABLE,
                    '--gold_database': GOLD_DATABASE,
                    '--kms_key_alias': KMS_KEY_ALIAS,
                    '--run_id': RUN_ID,
                    '--datalake-formats': 'iceberg',
                },
            },
            region_name='us-east-1',
            wait_for_completion=True,
            execution_timeout=timedelta(minutes=60),
            doc_md="""
            ## Gold Zone Star Schema

            **Purpose**: Create de-identified aggregated tables for analytics

            **Dimensions**:
            - dim_geography (state, city, zip)
            - dim_diagnosis (diagnosis)
            - dim_insurance (insurance_provider)

            **Facts**:
            - fact_patient_visits (detailed with dimension keys)
            - fact_patient_visits_agg (de-identified aggregates by date/state/diagnosis)
            - summary_metrics (daily totals)

            **De-Identification**: fact_patient_visits_agg contains ONLY aggregated data, no individual PHI

            **Output**: Apache Iceberg tables partitioned by visit_date

            **SLA**: 30 minutes
            """,
        )

    # ========================================
    # TASK GROUP: AUDIT (HIPAA Audit Trail)
    # ========================================

    with TaskGroup(group_id='audit_trail', tooltip='HIPAA audit trail logging') as audit_trail:

        log_completion = PythonOperator(
            task_id='log_pipeline_completion',
            python_callable=log_pipeline_completion,
            provide_context=True,
            doc_md="""
            ## HIPAA Audit Trail

            **Purpose**: Log pipeline completion for compliance audit

            **Logged Information**:
            - Pipeline execution details
            - PHI masking confirmation
            - Encryption confirmation
            - Quality gate results
            - Timestamp and run ID

            **Retention**: 2555 days (7 years - HIPAA minimum)
            """,
        )

    # ========================================
    # TASK DEPENDENCIES
    # ========================================

    # Bronze → Silver → Quality → Gold → Audit
    extract_bronze >> transform_silver >> quality_checks >> publish_gold >> audit_trail

    # Set SLAs
    landing_to_s3.sla = timedelta(minutes=20)
    staging_clean.sla = timedelta(minutes=40)
    run_quality_checks.sla = timedelta(minutes=20)
    publish_star_schema.sla = timedelta(minutes=30)
