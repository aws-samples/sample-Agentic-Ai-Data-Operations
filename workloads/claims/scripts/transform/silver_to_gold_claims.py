#!/usr/bin/env python3
"""
Silver → Gold transformation for claims
Flat denormalized Iceberg table for analytical reporting

Adds derived columns: claim_amount_tier, member_age_group
All PHI already masked in Silver — Gold inherits masked values
"""

import sys
import json
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.structured_logger import StructuredLogger
from shared.utils.script_tracer import ScriptTracer


def transform_glue_mode(glue_context, args):
    """Transform using AWS Glue (PySpark + Iceberg)"""
    from pyspark.sql import functions as F

    spark = glue_context.spark_session
    silver_df = spark.table("glue_catalog.claims_db.silver_claims")
    input_rows = silver_df.count()

    # Add Gold-specific derived columns
    gold_df = silver_df \
        .withColumn("claim_amount_tier",
                    F.when(F.col("billed_amount") < 200, "Low")
                     .when(F.col("billed_amount") <= 1000, "Medium")
                     .otherwise("High")) \
        .withColumn("member_age_group",
                    F.when(F.col("member_age") < 18, "Under 18")
                     .when(F.col("member_age") <= 34, "18-34")
                     .when(F.col("member_age") <= 49, "35-49")
                     .when(F.col("member_age") <= 64, "50-64")
                     .otherwise("65+"))

    # Write to Gold Iceberg table
    table_name = "glue_catalog.claims_db.gold_claims_analytical"
    gold_df.write \
        .format("iceberg") \
        .mode("overwrite") \
        .option("write.format.default", "parquet") \
        .saveAsTable(table_name)

    output_rows = gold_df.count()

    return {
        "workload": "claims",
        "transformation": "silver_to_gold",
        "source": "glue_catalog.claims_db.silver_claims",
        "target": table_name,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": output_rows,
        "transformations_applied": ["derived_claim_amount_tier", "derived_member_age_group"]
    }


def transform_local_mode(silver_path, gold_path, tracer=None):
    """Transform using pandas (local testing)"""
    import pandas as pd

    if tracer is None:
        tracer = ScriptTracer.for_script(__file__)

    log = StructuredLogger("Transform", "claims", f"run-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}")

    df = pd.read_parquet(silver_path)
    input_rows = len(df)
    log.info("Read silver data", rows=input_rows)
    tracer.log_start(rows_in=input_rows, source=silver_path)

    # Derived columns for Gold
    df['claim_amount_tier'] = pd.cut(
        df['billed_amount'],
        bins=[-1, 200, 1000, float('inf')],
        labels=['Low', 'Medium', 'High']
    ).astype(str)

    df['member_age_group'] = pd.cut(
        df['member_age'],
        bins=[-1, 17, 34, 49, 64, float('inf')],
        labels=['Under 18', '18-34', '35-49', '50-64', '65+']
    ).astype(str)

    # Write Gold
    Path(gold_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(gold_path, index=False, engine='pyarrow')
    output_rows = len(df)
    log.info("Gold written", path=gold_path, rows=output_rows)

    lineage = {
        "workload": "claims",
        "transformation": "silver_to_gold",
        "source": silver_path,
        "target": gold_path,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "input_rows": input_rows,
        "output_rows": output_rows,
        "transformations_applied": ["derived_claim_amount_tier", "derived_member_age_group"]
    }

    lineage_path = gold_path.replace('.parquet', '_lineage.json')
    with open(lineage_path, 'w') as f:
        json.dump(lineage, f, indent=2)

    tracer.log_rows(rows_in=input_rows, rows_out=output_rows, quarantined=0)
    tracer.log_complete(status="success", rows_out=output_rows, output_path=gold_path)
    tracer.close()

    return lineage


if __name__ == "__main__":
    if "--local" in sys.argv:
        silver_idx = sys.argv.index("--silver_path") + 1
        gold_idx = sys.argv.index("--gold_path") + 1
        silver_path = sys.argv[silver_idx]
        gold_path = sys.argv[gold_idx]

        with ScriptTracer.for_script(__file__) as tracer:
            lineage = transform_local_mode(silver_path, gold_path, tracer=tracer)
        print(f"\n✓ Silver → Gold complete")
        print(f"  Input: {lineage['input_rows']}, Output: {lineage['output_rows']}")
    else:
        from awsglue.utils import getResolvedOptions
        from pyspark.context import SparkContext
        from awsglue.context import GlueContext
        from awsglue.job import Job

        args = getResolvedOptions(sys.argv, ['JOB_NAME', 'silver_path', 'gold_path'])
        sc = SparkContext()
        glue_context = GlueContext(sc)
        job = Job(glue_context)
        job.init(args['JOB_NAME'], args)

        lineage = transform_glue_mode(glue_context, args)
        print(f"\n✓ Silver → Gold complete (Glue)")
        print(f"  Input: {lineage['input_rows']}, Output: {lineage['output_rows']}")

        job.commit()
