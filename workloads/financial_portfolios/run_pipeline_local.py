#!/usr/bin/env python3
"""
Local Pipeline Runner - Simulates the full ETL pipeline locally
Generates HTML dashboard preview
"""

import subprocess
import sys
from pathlib import Path
from datetime import datetime
import pandas as pd
import json

def log(msg, level="INFO"):
    """Print log message"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{level}] {msg}")

def run_pipeline_local():
    """Run the full pipeline locally"""
    log("=" * 80)
    log("FINANCIAL PORTFOLIOS PIPELINE - LOCAL EXECUTION")
    log("=" * 80)

    base_path = Path("workloads/financial_portfolios")
    output_path = Path("output/financial_portfolios")
    output_path.mkdir(parents=True, exist_ok=True)

    # Step 1: Bronze Ingestion (copy CSV files)
    log("Step 1: Bronze Ingestion")
    bronze_path = output_path / "bronze"
    bronze_path.mkdir(exist_ok=True)

    source_files = [
        "sample_data/stocks.csv",
        "sample_data/portfolios.csv",
        "sample_data/positions.csv"
    ]

    for src in source_files:
        if Path(src).exists():
            dest = bronze_path / Path(src).name
            import shutil
            shutil.copy(src, dest)
            log(f"  ✓ Copied {Path(src).name} to Bronze zone")

    # Step 2: Silver Transformation
    log("\nStep 2: Silver Transformation (Bronze → Silver)")
    silver_path = output_path / "silver"
    silver_path.mkdir(exist_ok=True)

    transform_scripts = [
        "scripts/transform/bronze_to_silver_stocks.py",
        "scripts/transform/bronze_to_silver_portfolios.py",
        "scripts/transform/bronze_to_silver_positions.py"
    ]

    for script in transform_scripts:
        script_path = base_path / script
        if script_path.exists():
            table_name = script_path.stem.replace('bronze_to_silver_', '')
            bronze_file = bronze_path / f"{table_name}.csv"
            silver_file = silver_path / f"{table_name}.parquet"

            cmd = [
                "python3",
                str(script_path),
                "--local",
                "--bronze_path", str(bronze_file),
                "--silver_path", str(silver_file)
            ]

            # Add reference data for positions (FK validation)
            if table_name == 'positions':
                cmd.extend([
                    "--stocks_path", str(silver_path / "stocks.parquet"),
                    "--portfolios_path", str(silver_path / "portfolios.parquet")
                ])

            log(f"  Running: {table_name} transformation...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                log(f"  ✓ {table_name.capitalize()} transformation complete")
            else:
                log(f"  ✗ {table_name.capitalize()} transformation failed", "ERROR")
                log(result.stderr, "ERROR")

    # Step 3: Quality Checks
    log("\nStep 3: Quality Checks on Silver Zone")
    quality_script = base_path / "scripts/quality/run_quality_checks.py"
    if quality_script.exists():
        cmd = [
            "python3",
            str(quality_script),
            str(base_path / "config/quality_rules.yaml"),
            str(silver_path),
            "silver"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            log("  ✓ Quality checks PASSED")
            log(result.stdout)
        else:
            log("  ✗ Quality checks FAILED", "ERROR")
            log(result.stderr, "ERROR")

    # Step 4: Gold Transformation
    log("\nStep 4: Gold Transformation (Silver → Gold)")
    gold_path = output_path / "gold"
    gold_path.mkdir(exist_ok=True)

    gold_scripts = [
        "scripts/transform/silver_to_gold_dim_stocks.py",
        "scripts/transform/silver_to_gold_dim_portfolios.py",
        "scripts/transform/silver_to_gold_fact_positions.py",
        "scripts/transform/silver_to_gold_portfolio_summary.py"
    ]

    for script in gold_scripts:
        script_path = base_path / script
        if script_path.exists():
            table_name = script_path.stem.replace('silver_to_gold_', '')

            # Map table names to input files and build commands
            if table_name == 'dim_stocks':
                cmd = [
                    "python3", str(script_path), "--local",
                    "--silver_path", str(silver_path / "stocks.parquet"),
                    "--gold_path", str(gold_path / "dim_stocks.parquet")
                ]
            elif table_name == 'dim_portfolios':
                cmd = [
                    "python3", str(script_path), "--local",
                    "--silver_path", str(silver_path / "portfolios.parquet"),
                    "--gold_path", str(gold_path / "dim_portfolios.parquet")
                ]
            elif table_name == 'fact_positions':
                # Positions is partitioned, so pass the directory
                cmd = [
                    "python3", str(script_path), "--local",
                    "--positions_path", str(silver_path / "positions"),
                    "--stocks_path", str(silver_path / "stocks.parquet"),
                    "--portfolios_path", str(silver_path / "portfolios.parquet"),
                    "--gold_path", str(gold_path / "fact_positions.parquet")
                ]
            elif table_name == 'portfolio_summary':
                cmd = [
                    "python3", str(script_path), "--local",
                    "--fact_positions_path", str(gold_path / "fact_positions.parquet"),
                    "--gold_path", str(gold_path / "portfolio_summary.parquet")
                ]

            log(f"  Running: {table_name} transformation...")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                log(f"  ✓ {table_name.capitalize()} transformation complete")
            else:
                log(f"  ✗ {table_name.capitalize()} transformation failed", "ERROR")
                log(result.stderr, "ERROR")

    # Step 5: Generate Dashboard
    log("\nStep 5: Generate Dashboard HTML Preview")
    generate_dashboard_html(gold_path, output_path)

    log("\n" + "=" * 80)
    log("PIPELINE COMPLETE ✓")
    log("=" * 80)
    log(f"\nOutput files:")
    log(f"  Bronze:  {bronze_path}")
    log(f"  Silver:  {silver_path}")
    log(f"  Gold:    {gold_path}")
    log(f"  Dashboard: {output_path / 'dashboard.html'}")


def generate_dashboard_html(gold_path, output_path):
    """Generate HTML dashboard preview"""

    # Load Gold zone data (handle partitioned datasets)
    try:
        # fact_positions is partitioned by sector
        fact_positions = pd.read_parquet(gold_path / "fact_positions")
        dim_stocks = pd.read_parquet(gold_path / "dim_stocks.parquet")
        dim_portfolios = pd.read_parquet(gold_path / "dim_portfolios.parquet")
        portfolio_summary = pd.read_parquet(gold_path / "portfolio_summary.parquet")
        log(f"  ✓ Loaded Gold zone tables: {len(fact_positions)} positions, {len(dim_stocks)} stocks, {len(dim_portfolios)} portfolios")
    except Exception as e:
        log(f"  ✗ Failed to load Gold zone data: {e}", "ERROR")
        return

    # Join data for visualizations
    positions_with_stocks = fact_positions.merge(
        dim_stocks[['ticker', 'company_name', 'sector', 'industry']],
        on='ticker',
        how='left'
    )

    positions_with_all = positions_with_stocks.merge(
        dim_portfolios[['portfolio_id', 'manager_name', 'strategy']],
        on='portfolio_id',
        how='left'
    )

    # Visual 1: Top 5 Positions by Unrealized Gain
    top_positions = positions_with_all.nlargest(5, 'unrealized_gain_loss')[
        ['ticker', 'company_name', 'unrealized_gain_loss', 'sector', 'market_value']
    ]

    # Visual 2: Top 5 Recent Trades
    recent_trades = positions_with_all.nlargest(5, 'entry_date')[
        ['entry_date', 'ticker', 'shares', 'purchase_price', 'market_value', 'unrealized_gain_loss_pct']
    ]

    # Visual 3: Portfolio Performance by Manager
    manager_performance = positions_with_all.groupby('manager_name').agg({
        'market_value': 'sum',
        'unrealized_gain_loss': 'sum',
        'position_id': 'count'
    }).reset_index()
    manager_performance.columns = ['manager_name', 'total_value', 'total_gain_loss', 'num_positions']

    # Visual 4: Sector Allocation
    sector_allocation = positions_with_all.groupby('sector').agg({
        'market_value': 'sum'
    }).reset_index()
    sector_allocation['percentage'] = (sector_allocation['market_value'] / sector_allocation['market_value'].sum() * 100).round(2)

    # KPIs
    total_positions = len(fact_positions)
    total_value = fact_positions['market_value'].sum()
    total_gain_loss = fact_positions['unrealized_gain_loss'].sum()
    avg_gain_pct = fact_positions['unrealized_gain_loss_pct'].mean()

    # Generate HTML
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Financial Portfolios Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Amazon Ember', 'Helvetica Neue', Helvetica, Arial, sans-serif;
            background: #f0f2f5;
            color: #16191f;
        }}

        .header {{
            background: #232f3e;
            color: white;
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        .logo {{
            font-size: 24px;
            font-weight: bold;
            color: #ff9900;
        }}

        .subtitle {{
            color: #aab7b8;
            font-size: 14px;
        }}

        .container {{
            max-width: 1600px;
            margin: 0 auto;
            padding: 30px;
        }}

        .kpi-row {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}

        .kpi-card {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-left: 4px solid #232f3e;
        }}

        .kpi-card.positive {{
            border-left-color: #037f0c;
        }}

        .kpi-card.negative {{
            border-left-color: #d13212;
        }}

        .kpi-label {{
            font-size: 13px;
            color: #687078;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }}

        .kpi-value {{
            font-size: 36px;
            font-weight: 700;
            color: #16191f;
            line-height: 1;
        }}

        .kpi-subtext {{
            font-size: 13px;
            color: #687078;
            margin-top: 8px;
        }}

        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 20px;
            margin-bottom: 20px;
        }}

        .chart-card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 20px;
        }}

        .chart-title {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 15px;
            color: #16191f;
            border-bottom: 2px solid #f0f2f5;
            padding-bottom: 10px;
        }}

        .chart {{
            height: 400px;
        }}

        .table-wrapper {{
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}

        th {{
            background: #f8f9fa;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #dee2e6;
            color: #232f3e;
        }}

        td {{
            padding: 12px;
            border-bottom: 1px solid #e9ecef;
        }}

        tr:hover {{
            background: #f8f9fa;
        }}

        .positive {{
            color: #037f0c;
        }}

        .negative {{
            color: #d13212;
        }}

        .footer {{
            text-align: center;
            color: #687078;
            font-size: 13px;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #dee2e6;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <div class="logo">📊 Financial Portfolios</div>
            <div class="subtitle">Real-time Portfolio Analytics Dashboard</div>
        </div>
        <div class="subtitle">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>

    <div class="container">
        <!-- KPI Cards -->
        <div class="kpi-row">
            <div class="kpi-card">
                <div class="kpi-label">Total Positions</div>
                <div class="kpi-value">{total_positions:,}</div>
                <div class="kpi-subtext">Open positions</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Total Market Value</div>
                <div class="kpi-value">${total_value:,.0f}</div>
                <div class="kpi-subtext">Across all portfolios</div>
            </div>
            <div class="kpi-card {'positive' if total_gain_loss > 0 else 'negative'}">
                <div class="kpi-label">Unrealized Gain/Loss</div>
                <div class="kpi-value {'positive' if total_gain_loss > 0 else 'negative'}">${total_gain_loss:,.0f}</div>
                <div class="kpi-subtext">Mark-to-market</div>
            </div>
            <div class="kpi-card {'positive' if avg_gain_pct > 0 else 'negative'}">
                <div class="kpi-label">Avg Gain/Loss %</div>
                <div class="kpi-value {'positive' if avg_gain_pct > 0 else 'negative'}">{avg_gain_pct:.2f}%</div>
                <div class="kpi-subtext">Portfolio average</div>
            </div>
        </div>

        <!-- Visualizations -->
        <div class="dashboard-grid">
            <!-- Visual 1: Top Positions -->
            <div class="chart-card">
                <div class="chart-title">Top 5 Positions by Unrealized Gain</div>
                <div id="chart1" class="chart"></div>
            </div>

            <!-- Visual 4: Sector Allocation -->
            <div class="chart-card">
                <div class="chart-title">Sector Allocation</div>
                <div id="chart4" class="chart"></div>
            </div>
        </div>

        <div class="dashboard-grid">
            <!-- Visual 2: Recent Trades -->
            <div class="chart-card">
                <div class="chart-title">Top 5 Recent Trades</div>
                <div class="table-wrapper">
                    <table>
                        <thead>
                            <tr>
                                <th>Trade Date</th>
                                <th>Ticker</th>
                                <th>Shares</th>
                                <th>Purchase Price</th>
                                <th>Market Value</th>
                                <th>Gain/Loss %</th>
                            </tr>
                        </thead>
                        <tbody>
                            {generate_trades_table_rows(recent_trades)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Visual 3: Manager Performance -->
            <div class="chart-card">
                <div class="chart-title">Portfolio Performance by Manager</div>
                <div id="chart3" class="chart"></div>
            </div>
        </div>

        <div class="footer">
            Generated by Financial Portfolios Data Pipeline | Data as of {datetime.now().strftime('%Y-%m-%d')}
        </div>
    </div>

    <script>
        // Chart 1: Top Positions (Bar Chart)
        var chart1Data = [{{
            x: {json.dumps(top_positions['ticker'].tolist())},
            y: {json.dumps(top_positions['unrealized_gain_loss'].tolist())},
            type: 'bar',
            marker: {{
                color: {json.dumps(['#037f0c' if x > 0 else '#d13212' for x in top_positions['unrealized_gain_loss']])},
            }},
            text: {json.dumps(['$' + str(int(x)) for x in top_positions['unrealized_gain_loss']])},
            textposition: 'outside',
            hovertemplate: '<b>%{{x}}</b><br>Gain/Loss: $%{{y:,.0f}}<extra></extra>'
        }}];

        var chart1Layout = {{
            margin: {{t: 20, b: 60, l: 80, r: 20}},
            xaxis: {{title: 'Ticker'}},
            yaxis: {{title: 'Unrealized Gain/Loss ($)'}},
            plot_bgcolor: '#f8f9fa',
            paper_bgcolor: 'white'
        }};

        Plotly.newPlot('chart1', chart1Data, chart1Layout, {{responsive: true}});

        // Chart 3: Manager Performance (Bar Chart)
        var chart3Data = [{{
            x: {json.dumps(manager_performance['manager_name'].tolist())},
            y: {json.dumps(manager_performance['total_gain_loss'].tolist())},
            type: 'bar',
            marker: {{
                color: {json.dumps(['#037f0c' if x > 0 else '#d13212' for x in manager_performance['total_gain_loss']])},
            }},
            text: {json.dumps(['$' + str(int(x)) for x in manager_performance['total_gain_loss']])},
            textposition: 'outside',
            hovertemplate: '<b>%{{x}}</b><br>Total Gain/Loss: $%{{y:,.0f}}<extra></extra>'
        }}];

        var chart3Layout = {{
            margin: {{t: 20, b: 100, l: 80, r: 20}},
            xaxis: {{title: 'Manager', tickangle: -45}},
            yaxis: {{title: 'Total Gain/Loss ($)'}},
            plot_bgcolor: '#f8f9fa',
            paper_bgcolor: 'white'
        }};

        Plotly.newPlot('chart3', chart3Data, chart3Layout, {{responsive: true}});

        // Chart 4: Sector Allocation (Pie Chart)
        var chart4Data = [{{
            labels: {json.dumps(sector_allocation['sector'].tolist())},
            values: {json.dumps(sector_allocation['market_value'].tolist())},
            type: 'pie',
            hole: 0.4,
            marker: {{
                colors: ['#232f3e', '#3f51b5', '#00897b', '#ff9900', '#d13212', '#6a1b9a', '#00796b', '#f57c00']
            }},
            textinfo: 'label+percent',
            hovertemplate: '<b>%{{label}}</b><br>Value: $%{{value:,.0f}}<br>%{{percent}}<extra></extra>'
        }}];

        var chart4Layout = {{
            margin: {{t: 20, b: 20, l: 20, r: 20}},
            paper_bgcolor: 'white'
        }};

        Plotly.newPlot('chart4', chart4Data, chart4Layout, {{responsive: true}});
    </script>
</body>
</html>
"""

    # Generate table rows
    def generate_trades_table_rows(trades_df):
        rows = []
        for _, row in trades_df.iterrows():
            gain_class = 'positive' if row['unrealized_gain_loss_pct'] > 0 else 'negative'
            rows.append(f"""
                <tr>
                    <td>{row['entry_date']}</td>
                    <td><strong>{row['ticker']}</strong></td>
                    <td>{row['shares']:,}</td>
                    <td>${row['purchase_price']:.2f}</td>
                    <td>${row['market_value']:,.0f}</td>
                    <td class="{gain_class}">{row['unrealized_gain_loss_pct']:.2f}%</td>
                </tr>
            """)
        return ''.join(rows)

    html = html.replace('{generate_trades_table_rows(recent_trades)}', generate_trades_table_rows(recent_trades))

    # Save HTML
    dashboard_path = output_path / "dashboard.html"
    with open(dashboard_path, 'w') as f:
        f.write(html)

    log(f"  ✓ Dashboard HTML generated: {dashboard_path}")
    log(f"  ℹ  Open in browser: file://{dashboard_path.absolute()}")


if __name__ == "__main__":
    run_pipeline_local()
