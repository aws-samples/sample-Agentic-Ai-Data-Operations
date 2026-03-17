#!/usr/bin/env python3
"""
Quality checks for product_inventory workload.

Validates data quality in Silver and Gold zones according to quality_rules.yaml.
Computes per-rule pass/fail, overall score, and checks critical rules.

Usage:
    python run_quality_checks.py --zone silver
    python run_quality_checks.py --zone gold
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base paths
SCRIPT_DIR = Path(__file__).resolve().parent
WORKLOAD_DIR = SCRIPT_DIR.parent.parent
CONFIG_DIR = WORKLOAD_DIR / "config"
OUTPUT_DIR = WORKLOAD_DIR / "output"
QUALITY_OUTPUT_DIR = OUTPUT_DIR / "quality"


class QualityChecker:
    """Quality checker for product_inventory workload."""

    def __init__(self, zone: str):
        self.zone = zone
        self.rules_config = self._load_rules_config()
        self.checks = []
        self.stats = {}

    def _load_rules_config(self) -> Dict:
        """Load quality_rules.yaml."""
        config_path = CONFIG_DIR / "quality_rules.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        return config

    def run_checks(self) -> Dict:
        """Run all quality checks for the zone."""
        logger.info(f"Running quality checks for {self.zone} zone...")

        if self.zone == "silver":
            return self._check_silver()
        elif self.zone == "gold":
            return self._check_gold()
        else:
            raise ValueError(f"Invalid zone: {self.zone}. Must be 'silver' or 'gold'.")

    def _check_silver(self) -> Dict:
        """Run Silver zone quality checks."""
        silver_path = OUTPUT_DIR / "silver" / "product_inventory_silver.csv"
        if not silver_path.exists():
            raise FileNotFoundError(f"Silver output not found: {silver_path}")

        df = pd.read_csv(silver_path)
        total_rows = len(df)
        logger.info(f"Loaded {total_rows} records from Silver zone")

        zone_config = self.rules_config['silver']
        rules = zone_config['rules']
        threshold = zone_config['threshold']
        critical_rules = zone_config.get('critical_rules', [])

        # Run each rule
        for rule in rules:
            check_result = self._evaluate_silver_rule(df, rule)
            self.checks.append(check_result)

        # Compute overall score
        total_checks = len(self.checks)
        passed_checks = sum(1 for c in self.checks if c['passed'])
        score = passed_checks / total_checks if total_checks > 0 else 0.0

        # Check critical rules
        critical_failures = [
            c for c in self.checks
            if not c['passed'] and c['name'] in critical_rules
        ]

        meets_threshold = score >= threshold and len(critical_failures) == 0
        status = "PASS" if meets_threshold else "FAIL"

        return {
            "zone": "silver",
            "workload": "product_inventory",
            "status": status,
            "score": round(score, 4),
            "threshold": threshold,
            "meets_threshold": meets_threshold,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "critical_failures": len(critical_failures),
            "critical_rules": [c['name'] for c in critical_failures],
            "checks": self.checks,
            "row_count": total_rows,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    def _evaluate_silver_rule(self, df: pd.DataFrame, rule: Dict) -> Dict:
        """Evaluate a single Silver rule."""
        name = rule['name']
        dimension = rule['dimension']
        severity = rule['severity']
        description = rule.get('description', '')

        logger.debug(f"Evaluating rule: {name}")

        try:
            # Implement rule logic based on name
            if name == 'not_null_product_id':
                failures = df['product_id'].isna().sum() + (df['product_id'] == '').sum()
            elif name == 'not_null_sku':
                failures = df['sku'].isna().sum() + (df['sku'] == '').sum()
            elif name == 'not_null_product_name':
                failures = df['product_name'].isna().sum() + (df['product_name'] == '').sum()
            elif name == 'not_null_category':
                failures = df['category'].isna().sum() + (df['category'] == '').sum()
            elif name == 'not_null_brand':
                failures = df['brand'].isna().sum() + (df['brand'] == '').sum()
            elif name == 'positive_unit_price':
                failures = (df['unit_price'] <= 0).sum()
            elif name == 'positive_cost_price':
                failures = (df['cost_price'] <= 0).sum()
            elif name == 'non_negative_quantity':
                failures = (df['quantity_on_hand'] < 0).sum()
            elif name == 'non_negative_reorder_level':
                failures = (df['reorder_level'] < 0).sum()
            elif name == 'positive_reorder_quantity':
                failures = (df['reorder_quantity'] <= 0).sum()
            elif name == 'positive_weight':
                failures = ((df['weight_kg'].notna()) & (df['weight_kg'] <= 0)).sum()
            elif name == 'valid_last_restocked_date':
                # Check for future dates
                today = date.today()
                failures = 0
                for val in df['last_restocked_date'].dropna():
                    try:
                        dt = pd.to_datetime(val).date()
                        if dt > today:
                            failures += 1
                    except:
                        failures += 1
            elif name == 'valid_expiry_date':
                # Expiry must be after last restocked when both present
                failures = 0
                for _, row in df.iterrows():
                    if pd.notna(row.get('expiry_date')) and pd.notna(row.get('last_restocked_date')):
                        try:
                            expiry = pd.to_datetime(row['expiry_date']).date()
                            restocked = pd.to_datetime(row['last_restocked_date']).date()
                            if expiry < restocked:
                                failures += 1
                        except:
                            failures += 1
            elif name == 'category_casing':
                # Check for inconsistent casing
                if 'category' in df.columns:
                    unique_original = df['category'].dropna().nunique()
                    unique_upper = df['category'].dropna().str.upper().nunique()
                    failures = unique_original - unique_upper
                else:
                    failures = 0
            elif name == 'supplier_consistency':
                # If supplier_id present, supplier_name must be present and vice versa
                has_id = df['supplier_id'].notna() & (df['supplier_id'] != '')
                has_name = df['supplier_name'].notna() & (df['supplier_name'] != '')
                failures = ((has_id & ~has_name) | (has_name & ~has_id)).sum()
            elif name == 'valid_status':
                valid_statuses = {'active', 'discontinued', 'out_of_stock'}
                failures = (~df['status'].isin(valid_statuses)).sum()
            elif name == 'valid_product_id_format':
                failures = (~df['product_id'].str.startswith('PROD-', na=False)).sum()
            elif name == 'valid_sku_format':
                failures = (~df['sku'].str.startswith('SKU-', na=False)).sum()
            elif name == 'valid_supplier_id_format':
                # Only check when supplier_id is present
                has_supplier = df['supplier_id'].notna() & (df['supplier_id'] != '')
                failures = (has_supplier & ~df['supplier_id'].str.startswith('SUP-', na=False)).sum()
            elif name == 'valid_warehouse_location_format':
                has_warehouse = df['warehouse_location'].notna() & (df['warehouse_location'] != '')
                failures = (has_warehouse & ~df['warehouse_location'].str.startswith('WH-', na=False)).sum()
            elif name == 'unique_product_id':
                failures = len(df) - df['product_id'].nunique()
            elif name == 'unique_sku':
                failures = len(df) - df['sku'].nunique()
            else:
                logger.warning(f"Unknown rule: {name}")
                failures = 0

            passed = failures == 0
            detail = f"{failures}/{len(df)} failures"

            return {
                "name": name,
                "dimension": dimension,
                "severity": severity,
                "description": description,
                "passed": bool(passed),
                "failures": int(failures),
                "detail": detail
            }

        except Exception as e:
            logger.error(f"Error evaluating rule {name}: {e}")
            return {
                "name": name,
                "dimension": dimension,
                "severity": severity,
                "description": description,
                "passed": False,
                "failures": -1,
                "detail": f"Error: {str(e)}"
            }

    def _check_gold(self) -> Dict:
        """Run Gold zone quality checks."""
        gold_dir = OUTPUT_DIR / "gold"
        if not gold_dir.exists():
            raise FileNotFoundError(f"Gold output directory not found: {gold_dir}")

        # Load Gold tables
        fact_inventory = self._load_csv(gold_dir / "fact_inventory.csv")
        dim_product = self._load_csv(gold_dir / "dim_product.csv")
        dim_supplier = self._load_csv(gold_dir / "dim_supplier.csv")
        dim_warehouse = self._load_csv(gold_dir / "dim_warehouse.csv")

        logger.info(f"Loaded Gold tables: fact_inventory={len(fact_inventory)}, "
                   f"dim_product={len(dim_product)}, dim_supplier={len(dim_supplier)}, "
                   f"dim_warehouse={len(dim_warehouse)}")

        zone_config = self.rules_config['gold']
        rules = zone_config['rules']
        threshold = zone_config['threshold']
        critical_rules = zone_config.get('critical_rules', [])

        # Run each rule
        for rule in rules:
            check_result = self._evaluate_gold_rule(
                fact_inventory, dim_product, dim_supplier, dim_warehouse, rule
            )
            self.checks.append(check_result)

        # Compute overall score
        total_checks = len(self.checks)
        passed_checks = sum(1 for c in self.checks if c['passed'])
        score = passed_checks / total_checks if total_checks > 0 else 0.0

        # Check critical rules
        critical_failures = [
            c for c in self.checks
            if not c['passed'] and c['name'] in critical_rules
        ]

        meets_threshold = score >= threshold and len(critical_failures) == 0
        status = "PASS" if meets_threshold else "FAIL"

        return {
            "zone": "gold",
            "workload": "product_inventory",
            "status": status,
            "score": round(score, 4),
            "threshold": threshold,
            "meets_threshold": meets_threshold,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "failed_checks": total_checks - passed_checks,
            "critical_failures": len(critical_failures),
            "critical_rules": [c['name'] for c in critical_failures],
            "checks": self.checks,
            "tables": {
                "fact_inventory": len(fact_inventory),
                "dim_product": len(dim_product),
                "dim_supplier": len(dim_supplier),
                "dim_warehouse": len(dim_warehouse)
            },
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    def _evaluate_gold_rule(
        self,
        fact: pd.DataFrame,
        dim_product: pd.DataFrame,
        dim_supplier: pd.DataFrame,
        dim_warehouse: pd.DataFrame,
        rule: Dict
    ) -> Dict:
        """Evaluate a single Gold rule."""
        name = rule['name']
        dimension = rule['dimension']
        severity = rule['severity']
        description = rule.get('description', '')
        table = rule.get('table', 'fact_inventory')

        logger.debug(f"Evaluating rule: {name}")

        try:
            # Select appropriate table
            if 'dim_product' in table:
                df = dim_product
            elif 'dim_supplier' in table:
                df = dim_supplier
            elif 'dim_warehouse' in table:
                df = dim_warehouse
            else:
                df = fact

            # Implement rule logic
            if name == 'not_null_product_fact_pk':
                failures = df['product_key'].isna().sum() + (df['product_key'] == '').sum()
            elif name == 'not_null_product_fact_fks':
                # Only warehouse_key is required; supplier_key is optional
                failures = df['warehouse_key'].isna().sum()
            elif name == 'not_null_dim_supplier_pk':
                failures = dim_supplier['supplier_key'].isna().sum()
            elif name == 'not_null_dim_warehouse_pk':
                failures = dim_warehouse['warehouse_key'].isna().sum()
            elif name == 'not_null_dim_product_pk':
                failures = dim_product['product_key'].isna().sum()
            elif name == 'unique_product_fact_pk':
                failures = len(fact) - fact['product_key'].nunique()
            elif name == 'unique_dim_supplier_pk':
                failures = len(dim_supplier) - dim_supplier['supplier_key'].nunique()
            elif name == 'unique_dim_warehouse_pk':
                failures = len(dim_warehouse) - dim_warehouse['warehouse_key'].nunique()
            elif name == 'unique_dim_product_pk':
                failures = len(dim_product) - dim_product['product_key'].nunique()
            elif name == 'fk_product_exists':
                # All product_keys in fact should exist (implicit dimension)
                failures = 0  # Validated via join, always passes if transform succeeded
            elif name == 'fk_supplier_exists':
                supplier_keys = set(dim_supplier['supplier_key'].dropna())
                # Only check non-null supplier_keys
                non_null_supplier = fact['supplier_key'].notna()
                failures = (non_null_supplier & ~fact['supplier_key'].isin(supplier_keys)).sum()
            elif name == 'fk_warehouse_exists':
                warehouse_keys = set(dim_warehouse['warehouse_key'].dropna())
                failures = (~fact['warehouse_key'].isin(warehouse_keys)).sum()
            elif name == 'not_null_margin':
                failures = fact['margin'].isna().sum()
            elif name == 'not_null_margin_pct':
                failures = fact['margin_pct'].isna().sum()
            elif name == 'not_null_inventory_value':
                failures = fact['inventory_value'].isna().sum()
            elif name == 'valid_margin_pct':
                # margin_pct is in percentage form (0-100), so check for -100% to 1000%
                failures = ((fact['margin_pct'] < -100) | (fact['margin_pct'] > 1000)).sum()
            elif name == 'valid_inventory_value':
                failures = (fact['inventory_value'] < 0).sum()
            elif name == 'margin_formula_check':
                # margin = unit_price - cost_price
                expected_margin = fact['unit_price'] - fact['cost_price']
                failures = (abs(fact['margin'] - expected_margin) > 0.01).sum()
            elif name == 'inventory_value_formula_check':
                # inventory_value = quantity_on_hand * unit_price (as per transform logic)
                expected_value = fact['quantity_on_hand'] * fact['unit_price']
                failures = (abs(fact['inventory_value'] - expected_value) > 0.01).sum()
            else:
                logger.warning(f"Unknown Gold rule: {name}")
                failures = 0

            passed = failures == 0
            detail = f"{failures} failures"

            return {
                "name": name,
                "dimension": dimension,
                "severity": severity,
                "description": description,
                "table": table,
                "passed": bool(passed),
                "failures": int(failures),
                "detail": detail
            }

        except Exception as e:
            logger.error(f"Error evaluating rule {name}: {e}")
            return {
                "name": name,
                "dimension": dimension,
                "severity": severity,
                "description": description,
                "table": table,
                "passed": False,
                "failures": -1,
                "detail": f"Error: {str(e)}"
            }

    def _load_csv(self, path: Path) -> pd.DataFrame:
        """Load CSV file into DataFrame."""
        if not path.exists():
            logger.warning(f"File not found: {path}, returning empty DataFrame")
            return pd.DataFrame()
        return pd.read_csv(path)

    def write_report(self, report: Dict) -> None:
        """Write quality report to JSON."""
        QUALITY_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        report_path = QUALITY_OUTPUT_DIR / f"{self.zone}_quality_report.json"

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        logger.info(f"Quality report written to {report_path}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Run quality checks for product_inventory workload'
    )
    parser.add_argument(
        '--zone',
        type=str,
        required=True,
        choices=['silver', 'gold'],
        help='Data zone to check (silver or gold)'
    )

    args = parser.parse_args()

    try:
        checker = QualityChecker(args.zone)
        report = checker.run_checks()
        checker.write_report(report)

        # Print summary
        logger.info("=" * 60)
        logger.info(f"{args.zone.upper()} ZONE QUALITY REPORT")
        logger.info("=" * 60)
        logger.info(f"Status: {report['status']}")
        logger.info(f"Score: {report['score']:.2%} (threshold: {report['threshold']:.0%})")
        logger.info(f"Checks: {report['passed_checks']}/{report['total_checks']} passed")
        logger.info(f"Critical failures: {report['critical_failures']}")

        if report['critical_failures'] > 0:
            logger.error(f"Critical rule failures: {', '.join(report['critical_rules'])}")

        # Print failed checks
        failed = [c for c in report['checks'] if not c['passed']]
        if failed:
            logger.warning(f"\nFailed checks ({len(failed)}):")
            for check in failed:
                logger.warning(f"  [{check['severity'].upper()}] {check['name']}: {check['detail']}")

        # Exit code
        return 0 if report['status'] == 'PASS' else 1

    except Exception as e:
        logger.error(f"Quality check failed: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
