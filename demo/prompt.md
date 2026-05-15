Onboard a new e-commerce orders dataset.

  **Source:**
  - Location: s3://data-onboarding-landing-133661573128-us-east-1/ecommerce_orders/
  - Format: CSV, 50 rows, batch ingestion
  - Refresh: Daily at 09:30 UTC

  **Compliance:** GDPR
  - PII columns: customer_email, customer_phone, credit_card_number, customer_name, shipping_address
  - Require consent tracking, right-to-erasure support, 365-day retention

  **Gold Zone:** Flat denormalized table for ad-hoc analytics (NO star schema)
 
  **Data Quality Rules:**
  - Completeness threshold: 85% (block promotion if below)
  - Validate order_date format (reject invalid dates like month > 12)
  - Validate customer_email format (must contain @)
  - Validate customer_phone format (reject non-numeric junk)
  - Flag invalid credit_card_number values
  - Flag rows missing city/state/zip as incomplete
  - Anomaly: flag orders where total_amount != quantity × unit_price × (1 - discount_pct)

  **Transformations (Bronze → Silver):**
  - Standardize phone to E.164 format
  - Mask credit_card_number (show last 4 only: ****-****-****-1234)
  - Cast order_date and ship_date to DATE type
  - Trim whitespace on all string columns
  - Quarantine rows with invalid dates (don't drop silently)

  **Transformations (Silver → Gold):**
  - Flatten all columns into single wide table
  - Add derived columns: order_month, days_to_ship, is_returned, is_high_value (total > $100)
  - Keep only delivered + returned orders (exclude processing/cancelled)

  **Schedule:** Daily batch at 09:30 UTC, retries=3, exponential backoff, alert on failure

  **Logging:** enable AgentTracer (trace_events.jsonl), StructuredLogger in all scripts, decisions array in every sub-agent output
 
  After EACH phase, print a status box:
 
  ┌──────────────────────────────────────────┐
  │ ✅ PHASE X COMPLETE — [phase name]       │
  │ Outputs: ...                             │
  │ DQ Score: X.XX                           │
  │ Records: XX passed / XX quarantined      │
  │ Next: Phase Y — [description]            │
  └──────────────────────────────────────────┘