-- Bronze table: raw attendance data partitioned by ingestion date
-- Tool routing: glue-athena MCP → create_database + Glue Crawler for auto-registration
-- Bronze format: Parquet (raw source preserved)

CREATE EXTERNAL TABLE IF NOT EXISTS employee_attendance_db.bronze_employee_attendance (
    employee_id   STRING,
    full_name     STRING,
    email         STRING,
    department    STRING,
    check_in      STRING,
    check_out     STRING,
    location      STRING,
    hours_worked  STRING,
    status        STRING,
    manager_id    STRING
)
PARTITIONED BY (ingestion_date STRING)
STORED AS PARQUET
LOCATION 's3://${var:data_lake_bucket}/bronze/employee_attendance/'
TBLPROPERTIES ('classification' = 'parquet');
