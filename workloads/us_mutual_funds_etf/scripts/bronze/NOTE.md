# Bronze Data Generation - Demo Only

**File**: `bronze_data_generation.py`

This script generates **synthetic mutual fund data** for demonstration purposes.

## Production vs Demo

### Demo (This Workload)
- Uses `bronze_data_generation.py` to create fake data
- Generates 130 funds, market data, and NAV prices with quality issues
- Purpose: Testing and demonstrating the platform

### Production (Customer Onboarding)
- Connects to customer's real data source (PostgreSQL, S3, Snowflake, APIs)
- No data generation - reads existing customer data
- Bronze scripts would be extraction/ingestion from real sources

## When to Use This

✅ **Use for:**
- Platform demos
- Development testing
- CI/CD pipelines
- Learning how the system works

❌ **Do NOT use for:**
- Real customer data onboarding
- Production pipelines

## Real Customer Equivalent

For a real mutual fund customer, the Bronze extraction would look like:

```python
# Bronze extraction from customer's database
def extract_from_customer_db():
    connection = psycopg2.connect(
        host=customer_db_host,
        database=customer_db_name,
        user=secrets_manager.get("customer_db_user"),
        password=secrets_manager.get("customer_db_password")
    )

    # Read real fund data
    funds_df = pd.read_sql("SELECT * FROM funds", connection)

    # Upload to S3 Bronze (immutable)
    funds_df.to_parquet(f"s3://bronze/funds/date={today}/funds.parquet")
```

**No synthetic data generation in production.**
