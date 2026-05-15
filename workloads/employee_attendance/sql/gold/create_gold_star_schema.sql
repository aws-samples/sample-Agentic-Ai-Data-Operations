-- Gold star schema: fact_attendance + dim_employee + dim_location
-- Tool routing: glue-athena MCP → Iceberg DDL
-- Gold format decision (TOOL_ROUTING.md Step 5): Star schema — use case is Reporting & Dashboards

-- Fact table
CREATE TABLE IF NOT EXISTS s3tablesbucket.employee_attendance_gold_db.fact_attendance (
    employee_id     STRING      NOT NULL,
    attendance_date DATE        NOT NULL,
    location        STRING,
    hours_worked    DOUBLE,
    status          STRING,
    is_remote       BOOLEAN
)
USING iceberg
PARTITIONED BY (days(attendance_date))
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2'
);

-- Dimension: Employee (SCD Type 2)
CREATE TABLE IF NOT EXISTS s3tablesbucket.employee_attendance_gold_db.dim_employee (
    employee_id     STRING      NOT NULL,
    full_name       STRING,
    email           STRING,
    department      STRING,
    manager_id      STRING,
    effective_from  DATE,
    effective_to    DATE,
    is_current      BOOLEAN
)
USING iceberg
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2'
);

-- Dimension: Location
CREATE TABLE IF NOT EXISTS s3tablesbucket.employee_attendance_gold_db.dim_location (
    location_code   STRING      NOT NULL
)
USING iceberg
TBLPROPERTIES (
    'table_type' = 'ICEBERG',
    'format-version' = '2'
);
