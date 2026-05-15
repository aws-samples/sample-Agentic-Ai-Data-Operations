-- Silver table: cleaned, deduplicated attendance — Apache Iceberg on S3 Tables
-- Tool routing: glue-athena MCP → Iceberg DDL (Silver is ALWAYS Iceberg)

CREATE TABLE IF NOT EXISTS s3tablesbucket.employee_attendance_db.silver_employee_attendance (
    employee_id     STRING      NOT NULL,
    full_name       STRING      NOT NULL,
    email           STRING,
    department      STRING,
    check_in        TIMESTAMP,
    check_out       TIMESTAMP,
    location        STRING,
    hours_worked    DOUBLE,
    status          STRING      NOT NULL,
    manager_id      STRING,
    attendance_date DATE,
    is_remote       BOOLEAN,
    ingestion_ts    TIMESTAMP
)
USING iceberg
PARTITIONED BY (department, days(attendance_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2',
    'write.metadata.compression-codec' = 'gzip'
);
