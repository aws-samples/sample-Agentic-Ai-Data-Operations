#!/usr/bin/env python3
"""Quick dashboard generator from CSV data"""

import pandas as pd
from pathlib import Path
from datetime import datetime

# Load data
stocks = pd.read_csv("sample_data/stocks.csv")
portfolios = pd.read_csv("sample_data/portfolios.csv")
positions = pd.read_csv("sample_data/positions.csv")

# Join
df = positions.merge(stocks[['ticker', 'company_name', 'sector', 'industry']], on='ticker', how='left', suffixes=('_pos', ''))
df = df.merge(portfolios[['portfolio_id', 'manager_name', 'strategy']], on='portfolio_id', how='left')

# Prepare data
top_positions = df.nlargest(5, 'unrealized_gain_loss')
recent_trades = df.sort_values('entry_date', ascending=False).head(5)
manager_perf = df.groupby('manager_name').agg({'market_value': 'sum', 'unrealized_gain_loss': 'sum'}).reset_index()
manager_perf.columns = ['manager_name', 'market_value', 'total_gain_loss']
sector_alloc = df.groupby('sector').agg({'market_value': 'sum'}).reset_index()
sector_alloc['pct'] = (sector_alloc['market_value'] / sector_alloc['market_value'].sum() * 100)

# KPIs
total_pos = len(df)
total_val = df['market_value'].sum()
total_gl = df['unrealized_gain_loss'].sum()
avg_pct = df['unrealized_gain_loss_pct'].mean()

# Generate HTML
html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Financial Portfolios Dashboard</title>
<style>
body {{font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; margin: 0; background: #f5f7fa;}}
.header {{background: linear-gradient(135deg, #232f3e 0%, #3f4e5f 100%); color: white; padding: 30px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);}}
.header h1 {{margin: 0; font-size: 32px;}}
.header p {{margin: 5px 0 0 0; opacity: 0.9;}}
.container {{max-width: 1400px; margin: 0 auto; padding: 30px;}}
.kpis {{display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px;}}
.kpi {{background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 4px solid #232f3e;}}
.kpi.positive {{border-left-color: #10b981;}}
.kpi.negative {{border-left-color: #ef4444;}}
.kpi-label {{font-size: 13px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 10px;}}
.kpi-value {{font-size: 36px; font-weight: 700; color: #111827;}}
.kpi-value.positive {{color: #10b981;}}
.kpi-value.negative {{color: #ef4444;}}
.charts {{display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px;}}
.chart {{background: white; padding: 25px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);}}
.chart h2 {{margin: 0 0 20px 0; font-size: 18px; color: #111827; border-bottom: 2px solid #e5e7eb; padding-bottom: 12px;}}
table {{width: 100%; border-collapse: collapse; font-size: 14px;}}
th {{background: #f9fafb; padding: 12px; text-align: left; font-weight: 600; color: #374151; border-bottom: 2px solid #e5e7eb;}}
td {{padding: 12px; border-bottom: 1px solid #f3f4f6;}}
tr:hover {{background: #f9fafb;}}
.positive {{color: #10b981; font-weight: 600;}}
.negative {{color: #ef4444; font-weight: 600;}}
.footer {{text-align: center; color: #9ca3af; margin-top: 40px; padding: 20px;}}
</style>
</head>
<body>

<div class="header">
    <h1>📊 Financial Portfolios Dashboard</h1>
    <p>Real-time Portfolio Analytics & Performance Metrics | Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
</div>

<div class="container">
    <div class="kpis">
        <div class="kpi">
            <div class="kpi-label">Total Positions</div>
            <div class="kpi-value">{total_pos:,}</div>
        </div>
        <div class="kpi">
            <div class="kpi-label">Total Market Value</div>
            <div class="kpi-value">${total_val:,.0f}</div>
        </div>
        <div class="kpi {'positive' if total_gl > 0 else 'negative'}">
            <div class="kpi-label">Unrealized Gain/Loss</div>
            <div class="kpi-value {'positive' if total_gl > 0 else 'negative'}">${total_gl:,.0f}</div>
        </div>
        <div class="kpi {'positive' if avg_pct > 0 else 'negative'}">
            <div class="kpi-label">Avg G/L Percentage</div>
            <div class="kpi-value {'positive' if avg_pct > 0 else 'negative'}">{avg_pct:.2f}%</div>
        </div>
    </div>

    <div class="charts">
        <div class="chart">
            <h2>Top 5 Positions by Unrealized Gain</h2>
            <table>
                <thead>
                    <tr>
                        <th>Ticker</th>
                        <th>Company</th>
                        <th>Sector</th>
                        <th>Unrealized G/L</th>
                    </tr>
                </thead>
                <tbody>
"""

for _, r in top_positions.iterrows():
    html += f"""                    <tr>
                        <td><strong>{r['ticker']}</strong></td>
                        <td>{r['company_name']}</td>
                        <td>{r['sector']}</td>
                        <td class="positive">${r['unrealized_gain_loss']:,.0f}</td>
                    </tr>
"""

html += """                </tbody>
            </table>
        </div>

        <div class="chart">
            <h2>Top 5 Recent Trades</h2>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Ticker</th>
                        <th>Shares</th>
                        <th>Market Value</th>
                        <th>G/L %</th>
                    </tr>
                </thead>
                <tbody>
"""

for _, r in recent_trades.iterrows():
    gl_class = 'positive' if r['unrealized_gain_loss_pct'] > 0 else 'negative'
    html += f"""                    <tr>
                        <td>{r['entry_date']}</td>
                        <td><strong>{r['ticker']}</strong></td>
                        <td>{r['shares']:,}</td>
                        <td>${r['market_value']:,.0f}</td>
                        <td class="{gl_class}">{r['unrealized_gain_loss_pct']:.2f}%</td>
                    </tr>
"""

html += """                </tbody>
            </table>
        </div>

        <div class="chart">
            <h2>Portfolio Performance by Manager</h2>
            <table>
                <thead>
                    <tr>
                        <th>Manager</th>
                        <th>Total Value</th>
                        <th>Gain/Loss</th>
                    </tr>
                </thead>
                <tbody>
"""

for _, r in manager_perf.sort_values('total_gain_loss', ascending=False).iterrows():
    gl_class = 'positive' if r['total_gain_loss'] > 0 else 'negative'
    html += f"""                    <tr>
                        <td>{r['manager_name']}</td>
                        <td>${r['market_value']:,.0f}</td>
                        <td class="{gl_class}">${r['total_gain_loss']:,.0f}</td>
                    </tr>
"""

html += """                </tbody>
            </table>
        </div>

        <div class="chart">
            <h2>Sector Allocation</h2>
            <table>
                <thead>
                    <tr>
                        <th>Sector</th>
                        <th>Market Value</th>
                        <th>% of Total</th>
                    </tr>
                </thead>
                <tbody>
"""

for _, r in sector_alloc.sort_values('market_value', ascending=False).iterrows():
    html += f"""                    <tr>
                        <td>{r['sector']}</td>
                        <td>${r['market_value']:,.0f}</td>
                        <td>{r['pct']:.1f}%</td>
                    </tr>
"""

html += """                </tbody>
            </table>
        </div>
    </div>

    <div class="footer">
        Generated by Financial Portfolios Data Pipeline | AWS Glue + Athena + QuickSight
    </div>
</div>

</body>
</html>"""

# Save
output_path = Path("output/financial_portfolios")
output_path.mkdir(parents=True, exist_ok=True)
with open(output_path / "dashboard.html", "w") as f:
    f.write(html)

print(f"✅ Dashboard generated: {output_path / 'dashboard.html'}")
print(f"   Open in browser: file://{(output_path / 'dashboard.html').absolute()}")
