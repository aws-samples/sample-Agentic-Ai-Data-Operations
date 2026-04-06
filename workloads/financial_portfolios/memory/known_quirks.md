---
name: Known quirks
description: pe_ratio and dividend_yield have expected nulls, do not quarantine
type: project
---

## Expected Null Patterns

- **pe_ratio** column in stocks table has ~5% expected nulls for growth stocks that have no earnings yet. This is NOT a quality failure — do not quarantine these rows. The quality rule uses severity=warning with a valid range of -100 to 1000.
- **dividend_yield** is null for non-dividend-paying stocks (growth companies). This is expected behavior and should not trigger completeness alerts.

## PII Flagging Notes

- **manager_name** in portfolios is flagged as NAME with MEDIUM sensitivity and SOX compliance tags. This is for SOX audit trail tracking, NOT for PII masking. The manager name must remain readable in reports for regulatory accountability.
- **company_name** and **portfolio_name** are flagged as NAME with LOW sensitivity — public information, no masking needed.

## Calculation Consistency

- `market_value = shares * current_price` must match within $1.00 tolerance
- `unrealized_gain_loss = market_value - cost_basis` must match within $1.00
- `weight_pct` values per portfolio should sum to approximately 100%
