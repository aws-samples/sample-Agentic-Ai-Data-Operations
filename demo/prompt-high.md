Onboard e-commerce orders from s3://data-onboarding-landing-133661573128-us-east-1/ecommerce_orders/

  - CSV, 50 rows, GDPR, daily 09:30 UTC batch
  - Gold: flat denormalized table for ad-hoc queries (no star schema)
  - DQ: completeness > 85%, validate dates/emails/phones, quarantine bad rows
  - Transforms: mask credit cards, standardize phones, cast dates, derive order_month + days_to_ship

  Print a status box after each phase. Don't ask questions — use defaults and keep moving.