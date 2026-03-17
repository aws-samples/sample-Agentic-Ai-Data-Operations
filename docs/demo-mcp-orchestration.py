#!/usr/bin/env python3
"""
Demo: MCP-Based Data Onboarding Orchestration

This script demonstrates the full data onboarding pipeline using MCP servers.
All AWS operations go through standardized MCP interfaces with visual logging.

Run: python3 demo_mcp_orchestration.py
"""

import sys
from pathlib import Path

# Add shared to path
sys.path.insert(0, str(Path(__file__).parent / "shared" / "mcp"))

from orchestrator import MCPOrchestrator


def main():
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║                                                                           ║
║           Agentic Data Onboarding System - MCP Demo                      ║
║                                                                           ║
║  All operations are routed through Model Context Protocol (MCP) servers  ║
║  for auditability, repeatability, and standardization.                   ║
║                                                                           ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)

    # Initialize orchestrator
    workload_name = "sales_transactions"
    print(f"Initializing orchestration for workload: {workload_name}\n")
    orch = MCPOrchestrator(workload_name=workload_name)

    print("═" * 80)
    print("PHASE 1: ROUTER AGENT - Check for Existing Workload")
    print("═" * 80)
    print()

    # Step 1: Router checks for existing workloads
    orch.call_mcp(
        step_name="Check Existing Workloads",
        mcp_server="local-filesystem",
        tool="list_workloads",
        params={},
        description="Router Agent scans workloads/ directory to prevent duplicates"
    )

    # Step 2: Search for similar sources
    orch.call_mcp(
        step_name="Search for Similar Sources",
        mcp_server="local-filesystem",
        tool="search_workloads_by_source",
        params={
            "source_type": "s3",
            "location_pattern": "sales"
        },
        description="Check if this data source is already onboarded"
    )

    orch.phase_summary(
        phase_name="Router Agent",
        summary="""
        ✓ Scanned existing workloads
        ✓ No duplicate sources found
        → Proceeding to data discovery
        """
    )

    print("═" * 80)
    print("PHASE 2: DATA ONBOARDING AGENT - Discovery")
    print("═" * 80)
    print()

    print("(User answers discovery questions - skipped in demo)\n")

    print("═" * 80)
    print("PHASE 3: METADATA AGENT - Schema Discovery & Profiling")
    print("═" * 80)
    print()

    # Step 3: Create Glue Crawler for schema discovery
    orch.call_mcp(
        step_name="Schema Discovery (Glue Crawler)",
        mcp_server="aws-dataprocessing",
        tool="create_crawler",
        params={
            "Name": f"{workload_name}_source_crawler",
            "Role": "arn:aws:iam::123456789012:role/GlueCrawlerRole",
            "DatabaseName": f"{workload_name}_db",
            "Targets": {
                "S3Targets": [{
                    "Path": f"s3://data-bronze/{workload_name}/",
                    "Exclusions": ["_tmp/**", "_spark_metadata/**"]
                }]
            },
            "SchemaChangePolicy": {
                "UpdateBehavior": "UPDATE_IN_DATABASE",
                "DeleteBehavior": "LOG"
            }
        },
        description="Discover schema from raw S3 data using Glue Crawler"
    )

    # Step 4: Profile data with Athena (5% sample)
    orch.call_mcp(
        step_name="Data Profiling (Athena 5% Sample)",
        mcp_server="aws-dataprocessing",
        tool="start_query_execution",
        params={
            "QueryString": f"""
                WITH sample AS (
                    SELECT * FROM "{workload_name}_db"."{workload_name}"
                    TABLESAMPLE BERNOULLI(5)
                )
                SELECT
                    COUNT(*) AS sample_rows,
                    COUNT(order_id) AS order_id_non_null,
                    COUNT(DISTINCT order_id) AS order_id_distinct,
                    MIN(revenue) AS revenue_min,
                    MAX(revenue) AS revenue_max,
                    AVG(revenue) AS revenue_avg
                FROM sample
            """,
            "QueryExecutionContext": {
                "Database": f"{workload_name}_db",
                "Catalog": "AwsDataCatalog"
            },
            "ResultConfiguration": {
                "OutputLocation": f"s3://athena-results/profiling/{workload_name}/",
                "EncryptionConfiguration": {
                    "EncryptionOption": "SSE_KMS",
                    "KmsKey": "alias/athena-kms-key"
                }
            }
        },
        description="Profile data quality and statistics on 5% sample"
    )

    # Step 5: Store business metadata in SageMaker Catalog
    orch.call_mcp(
        step_name="Store Business Metadata",
        mcp_server="sagemaker-catalog",
        tool="put_custom_metadata",
        params={
            "database": f"{workload_name}_db",
            "table": f"{workload_name}_silver",
            "custom_metadata": {
                "dataset": {
                    "name": workload_name,
                    "description": "Sales transaction data",
                    "owner": "data-team@company.com",
                    "grain": "order_id"
                },
                "columns": {
                    "order_id": {
                        "role": "identifier",
                        "business_name": "Order ID",
                        "pii": False
                    },
                    "customer_id": {
                        "role": "identifier",
                        "business_name": "Customer ID",
                        "pii": True
                    },
                    "revenue": {
                        "role": "measure",
                        "default_aggregation": "sum",
                        "business_name": "Total Revenue",
                        "pii": False
                    },
                    "region": {
                        "role": "dimension",
                        "business_name": "Sales Region",
                        "pii": False,
                        "hierarchy": ["region", "country"]
                    },
                    "order_date": {
                        "role": "temporal",
                        "business_name": "Order Date",
                        "time_intelligence": {
                            "fiscal_year_start": "2025-01-01"
                        }
                    }
                }
            }
        },
        description="Store column roles, PII flags, and business context in SageMaker Catalog"
    )

    orch.phase_summary(
        phase_name="Metadata Agent",
        summary="""
        ✓ Schema discovered via Glue Crawler
        ✓ Data profiled via Athena (5% sample)
        ✓ Business metadata stored in SageMaker Catalog
        → Ready for transformation
        """
    )

    print("═" * 80)
    print("PHASE 4: TRANSFORMATION AGENT - Bronze → Silver Pipeline")
    print("═" * 80)
    print()

    # Step 6: Create Bronze → Silver ETL job
    orch.call_mcp(
        step_name="Create Bronze → Silver ETL Job",
        mcp_server="aws-dataprocessing",
        tool="create_job",
        params={
            "Name": f"{workload_name}_bronze_to_silver",
            "Role": "arn:aws:iam::123456789012:role/GlueETLRole",
            "Command": {
                "Name": "glueetl",
                "ScriptLocation": f"s3://glue-scripts/{workload_name}/bronze_to_silver.py",
                "PythonVersion": "3"
            },
            "DefaultArguments": {
                "--job-language": "python",
                "--enable-spark-ui": "true",
                "--enable-glue-datacatalog": "true",
                "--enable-metrics": "true",
                "--TempDir": f"s3://glue-temp/{workload_name}/",
                "--source_database": f"{workload_name}_db",
                "--source_table": workload_name,
                "--target_database": f"{workload_name}_db",
                "--target_table": f"{workload_name}_silver",
                "--iceberg_catalog": "glue_catalog"
            },
            "MaxRetries": 3,
            "Timeout": 120,
            "GlueVersion": "4.0",
            "NumberOfWorkers": 10,
            "WorkerType": "G.1X"
        },
        description="Create Glue ETL job for Bronze → Silver transformation (Iceberg)"
    )

    # Step 7: Create Silver Iceberg table
    orch.call_mcp(
        step_name="Create Silver Iceberg Table",
        mcp_server="s3-tables",
        tool="create_table",
        params={
            "name": f"{workload_name}_silver",
            "namespace": f"{workload_name}_db",
            "table_bucket_arn": f"arn:aws:s3tables:us-east-1:123456789012:bucket/{workload_name}-silver-bucket",
            "format": "ICEBERG"
        },
        description="Create Apache Iceberg table for Silver zone data"
    )

    orch.phase_summary(
        phase_name="Transformation Agent",
        summary="""
        ✓ Bronze → Silver ETL job created
        ✓ Silver Iceberg table created (S3 Tables)
        → Ready for quality validation
        """
    )

    print("═" * 80)
    print("PHASE 5: QUALITY AGENT - Data Quality Validation")
    print("═" * 80)
    print()

    # Step 8: Create Data Quality Ruleset
    orch.call_mcp(
        step_name="Create Data Quality Ruleset",
        mcp_server="aws-dataprocessing",
        tool="create_data_quality_ruleset",
        params={
            "Name": f"{workload_name}_silver_quality",
            "Ruleset": """
                Rules = [
                    Completeness "order_id" > 0.99,
                    Uniqueness "order_id" = 1.0,
                    ColumnValues "revenue" between 0 and 1000000,
                    ColumnValues "order_date" <= today,
                    CustomSql "SELECT COUNT(*) FROM silver WHERE order_date > ship_date" = 0
                ]
            """,
            "TargetTable": {
                "DatabaseName": f"{workload_name}_db",
                "TableName": f"{workload_name}_silver",
                "CatalogId": "123456789012"
            },
            "Description": "Data quality rules for Silver zone (threshold >= 0.80)"
        },
        description="Define data quality rules for Silver zone validation"
    )

    # Step 9: Publish quality score to CloudWatch
    orch.call_mcp(
        step_name="Publish Quality Score Metric",
        mcp_server="cloudwatch",
        tool="put_metric_data",
        params={
            "Namespace": "DataOnboarding/Quality",
            "MetricData": [{
                "MetricName": "QualityScore",
                "Dimensions": [
                    {"Name": "Workload", "Value": workload_name},
                    {"Name": "Zone", "Value": "Silver"}
                ],
                "Value": 0.95,
                "Unit": "None"
            }]
        },
        description="Publish quality score as CloudWatch custom metric"
    )

    orch.phase_summary(
        phase_name="Quality Agent",
        summary="""
        ✓ Data quality ruleset created
        ✓ Quality score published to CloudWatch (0.95)
        → Quality gate passed (threshold: 0.80)
        """
    )

    print("═" * 80)
    print("PHASE 6: STORE SEMANTIC LAYER - SynoDB")
    print("═" * 80)
    print()

    # Step 10: Store seed queries in SynoDB (DynamoDB)
    orch.call_mcp(
        step_name="Store Seed Queries in SynoDB",
        mcp_server="dynamodb",
        tool="put_item",
        params={
            "TableName": "synodb_queries",
            "Item": {
                "query_id": f"{workload_name}_q1",
                "workload": workload_name,
                "natural_language": "total revenue by region",
                "sql": f"SELECT region, SUM(revenue) AS total_revenue FROM {workload_name}_db.{workload_name}_silver GROUP BY region",
                "created_at": "2025-03-15T10:00:00Z",
                "validated": True
            }
        },
        description="Store seed SQL query examples for Analysis Agent"
    )

    orch.phase_summary(
        phase_name="Semantic Layer Storage",
        summary="""
        ✓ Seed queries stored in SynoDB (DynamoDB)
        → Analysis Agent can now answer natural language questions
        """
    )

    print("═" * 80)
    print("PHASE 7: ORCHESTRATION DAG AGENT - Workflow Automation")
    print("═" * 80)
    print()

    # Step 11: Create Step Functions state machine
    orch.call_mcp(
        step_name="Create Step Functions State Machine",
        mcp_server="stepfunctions",
        tool="create_state_machine",
        params={
            "name": f"{workload_name}_pipeline",
            "definition": {
                "Comment": f"Data onboarding pipeline for {workload_name}",
                "StartAt": "RunCrawler",
                "States": {
                    "RunCrawler": {
                        "Type": "Task",
                        "Resource": "arn:aws:states:::glue:startCrawler.sync",
                        "Parameters": {
                            "Name": f"{workload_name}_source_crawler"
                        },
                        "Next": "RunETLJob"
                    },
                    "RunETLJob": {
                        "Type": "Task",
                        "Resource": "arn:aws:states:::glue:startJobRun.sync",
                        "Parameters": {
                            "JobName": f"{workload_name}_bronze_to_silver"
                        },
                        "Next": "RunQualityCheck"
                    },
                    "RunQualityCheck": {
                        "Type": "Task",
                        "Resource": "arn:aws:states:::glue:startDataQualityRulesetEvaluationRun.sync",
                        "Parameters": {
                            "DataSource": {
                                "GlueTable": {
                                    "DatabaseName": f"{workload_name}_db",
                                    "TableName": f"{workload_name}_silver"
                                }
                            },
                            "RulesetNames": [f"{workload_name}_silver_quality"]
                        },
                        "Next": "CheckQualityScore"
                    },
                    "CheckQualityScore": {
                        "Type": "Choice",
                        "Choices": [{
                            "Variable": "$.ResultIds[0]",
                            "IsPresent": True,
                            "Next": "Success"
                        }],
                        "Default": "Failed"
                    },
                    "Success": {
                        "Type": "Succeed"
                    },
                    "Failed": {
                        "Type": "Fail",
                        "Error": "QualityCheckFailed",
                        "Cause": "Data quality score below threshold"
                    }
                }
            },
            "roleArn": "arn:aws:iam::123456789012:role/StepFunctionsRole"
        },
        description="Create Step Functions state machine for end-to-end orchestration"
    )

    # Step 12: Create SNS topic for alerts
    orch.call_mcp(
        step_name="Create SNS Alert Topic",
        mcp_server="sns-sqs",
        tool="create_topic",
        params={
            "Name": f"{workload_name}_alerts",
            "Tags": [
                {"Key": "workload", "Value": workload_name},
                {"Key": "managed-by", "Value": "data-onboarding-agent"}
            ]
        },
        description="Create SNS topic for pipeline failure alerts"
    )

    orch.phase_summary(
        phase_name="Orchestration DAG Agent",
        summary="""
        ✓ Step Functions state machine created
        ✓ SNS alert topic created
        → Automated pipeline ready for scheduled execution
        """
    )

    print("═" * 80)
    print("FINAL SUMMARY")
    print("═" * 80)
    print()

    print(f"""
    Workload: {workload_name}

    ✓ Phase 1: Router Agent - No duplicates found
    ✓ Phase 2: Discovery - User questions answered
    ✓ Phase 3: Metadata Agent - Schema discovered and profiled
    ✓ Phase 4: Transformation Agent - Bronze → Silver pipeline created
    ✓ Phase 5: Quality Agent - Quality rules defined and validated
    ✓ Phase 6: Semantic Layer - Business metadata and queries stored
    ✓ Phase 7: Orchestration - Automated workflow created

    📂 Artifacts Created:
       • Glue Crawler: {workload_name}_source_crawler
       • Glue ETL Job: {workload_name}_bronze_to_silver
       • S3 Table: {workload_name}_silver (Iceberg)
       • Data Quality Ruleset: {workload_name}_silver_quality
       • Step Functions: {workload_name}_pipeline
       • SNS Topic: {workload_name}_alerts

    📊 Logs:
       • Console: {orch.console_log_path}
       • JSON:    {orch.json_log_path}

    🚀 Next Steps:
       1. Review artifacts in AWS Console
       2. Execute Step Functions pipeline manually
       3. Set up EventBridge schedule for automation
       4. Query Gold zone via Analysis Agent
    """)


if __name__ == "__main__":
    main()
