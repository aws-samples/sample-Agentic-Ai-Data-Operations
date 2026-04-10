#!/usr/bin/env python3
"""
Data Quality Checks for financial_portfolios workload
Runs completeness, uniqueness, validity, consistency, accuracy checks

Supports 5 quality dimensions:
1. Completeness - no nulls in required columns
2. Uniqueness - no duplicate PKs
3. Validity - values within acceptable ranges
4. Consistency - referential integrity and business rule compliance
5. Anomaly Detection - statistical outliers

Tracing: All quality checks are traced via ScriptTracer for observability.

Usage:
  python run_quality_checks.py <rules_path> <data_path> <zone>

Example:
  python run_quality_checks.py \\
    workloads/financial_portfolios/config/quality_rules.yaml \\
    output/financial_portfolios/silver \\
    silver
"""

import pandas as pd
import yaml
import json
from pathlib import Path
from datetime import datetime
import numpy as np
import sys
from typing import Dict, List, Any

# Add project root to path for shared imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from shared.utils.script_tracer import ScriptTracer


class QualityChecker:
    """Execute data quality checks based on YAML rules"""

    def __init__(self, rules_path: str, data_path: str, zone: str, tracer: ScriptTracer = None):
        self.rules = self.load_rules(rules_path)
        self.data_path = Path(data_path)
        self.zone = zone
        self.results = []
        self.quarantine_records = {}
        self.tracer = tracer or ScriptTracer.for_script(__file__)

    def load_rules(self, path: str) -> Dict[str, Any]:
        """Load quality rules from YAML file"""
        with open(path) as f:
            return yaml.safe_load(f)

    def check_completeness(self, table_name: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Check for nulls in required columns"""
        table_rules = self.rules['tables'][table_name]
        results = []

        for rule in table_rules.get('completeness_rules', []):
            for col in rule['columns']:
                if col not in df.columns:
                    results.append({
                        'dimension': 'completeness',
                        'table': table_name,
                        'column': col,
                        'rule': 'column_exists',
                        'expected': True,
                        'actual': False,
                        'passed': False,
                        'severity': 'critical',
                        'action': 'reject',
                        'reason': f"Column {col} missing from dataset"
                    })
                    continue

                null_count = df[col].isnull().sum()
                null_pct = null_count / len(df) if len(df) > 0 else 0
                completeness = 1 - null_pct

                passed = completeness >= rule['threshold']
                results.append({
                    'dimension': 'completeness',
                    'table': table_name,
                    'column': col,
                    'rule': 'not_null',
                    'expected': float(rule['threshold']),
                    'actual': round(float(completeness), 4),
                    'passed': bool(passed),
                    'severity': rule['severity'],
                    'action': rule.get('action'),
                    'reason': rule.get('reason'),
                    'null_count': int(null_count),
                    'total_rows': int(len(df))
                })

        return results

    def check_uniqueness(self, table_name: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Check for duplicate PKs"""
        table_rules = self.rules['tables'][table_name]
        results = []

        for rule in table_rules.get('uniqueness_rules', []):
            col = rule['column']

            if col not in df.columns:
                results.append({
                    'dimension': 'uniqueness',
                    'table': table_name,
                    'column': col,
                    'rule': 'unique',
                    'expected': rule['threshold'],
                    'actual': 0.0,
                    'passed': False,
                    'severity': 'critical',
                    'action': 'reject',
                    'reason': f"Column {col} missing from dataset"
                })
                continue

            dup_count = df[col].duplicated().sum()
            uniqueness = 1 - (dup_count / len(df)) if len(df) > 0 else 1.0

            passed = uniqueness >= rule['threshold']

            # Quarantine duplicate records
            if not passed and rule.get('action') == 'quarantine':
                dup_values = df[df[col].duplicated(keep=False)][col].unique()
                self.quarantine_records[f"{table_name}_duplicates"] = df[df[col].isin(dup_values)]

            results.append({
                'dimension': 'uniqueness',
                'table': table_name,
                'column': col,
                'rule': 'unique',
                'expected': rule['threshold'],
                'actual': round(float(uniqueness), 4),
                'passed': bool(passed),
                'severity': rule['severity'],
                'action': rule.get('action'),
                'reason': rule.get('reason'),
                'duplicate_count': int(dup_count),
                'total_rows': len(df)
            })

        return results

    def check_validity(self, table_name: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Check value ranges and data types"""
        table_rules = self.rules['tables'][table_name]
        results = []

        for rule in table_rules.get('validity_rules', []):
            col = rule['column']
            rule_type = rule['rule']

            if col not in df.columns:
                results.append({
                    'dimension': 'validity',
                    'table': table_name,
                    'column': col,
                    'rule': rule_type,
                    'expected': 1.0,
                    'actual': 0.0,
                    'passed': False,
                    'severity': 'critical',
                    'action': 'reject',
                    'reason': f"Column {col} missing from dataset"
                })
                continue

            # Skip nulls for validity checks
            non_null_df = df[df[col].notna()]

            if len(non_null_df) == 0:
                validity = 1.0
                valid_count = 0
                invalid_count = 0
            else:
                if rule_type == 'greater_than':
                    valid_mask = non_null_df[col] > rule['value']
                elif rule_type == 'greater_than_or_equal':
                    valid_mask = non_null_df[col] >= rule['value']
                elif rule_type == 'between':
                    valid_mask = (non_null_df[col] >= rule['min']) & (non_null_df[col] <= rule['max'])
                elif rule_type == 'date_not_future':
                    valid_mask = pd.to_datetime(non_null_df[col]) <= pd.Timestamp.now()
                else:
                    valid_mask = pd.Series([True] * len(non_null_df), index=non_null_df.index)

                valid_count = valid_mask.sum()
                invalid_count = len(non_null_df) - valid_count
                validity = valid_count / len(non_null_df)

                # Quarantine invalid records
                if invalid_count > 0 and rule.get('action') == 'quarantine':
                    invalid_records = df.loc[non_null_df[~valid_mask].index]
                    qkey = f"{table_name}_{col}_{rule_type}_invalid"
                    if qkey in self.quarantine_records:
                        self.quarantine_records[qkey] = pd.concat([self.quarantine_records[qkey], invalid_records])
                    else:
                        self.quarantine_records[qkey] = invalid_records

            passed = validity >= 0.98  # Default validity threshold

            results.append({
                'dimension': 'validity',
                'table': table_name,
                'column': col,
                'rule': rule_type,
                'expected': 0.98,
                'actual': round(float(validity), 4),
                'passed': bool(passed),
                'severity': rule['severity'],
                'action': rule.get('action'),
                'reason': rule.get('reason'),
                'valid_count': int(valid_count),
                'invalid_count': int(invalid_count),
                'total_rows': len(non_null_df)
            })

        return results

    def check_referential_integrity(self, table_name: str, df: pd.DataFrame,
                                   ref_dfs: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Check FK references"""
        table_rules = self.rules['tables'][table_name]
        results = []

        for fk_rule in table_rules.get('foreign_keys', []):
            col = fk_rule['column']
            ref_table = fk_rule['reference_table']
            ref_col = fk_rule['reference_column']

            if col not in df.columns:
                results.append({
                    'dimension': 'consistency',
                    'table': table_name,
                    'column': col,
                    'rule': 'foreign_key',
                    'reference': f"{ref_table}.{ref_col}",
                    'expected': 1.0,
                    'actual': 0.0,
                    'passed': False,
                    'severity': 'critical',
                    'action': 'reject',
                    'reason': f"Column {col} missing from dataset"
                })
                continue

            if ref_table not in ref_dfs:
                results.append({
                    'dimension': 'consistency',
                    'table': table_name,
                    'column': col,
                    'rule': 'foreign_key',
                    'reference': f"{ref_table}.{ref_col}",
                    'expected': 1.0,
                    'actual': 0.0,
                    'passed': False,
                    'severity': 'critical',
                    'action': 'reject',
                    'reason': f"Reference table {ref_table} not found"
                })
                continue

            ref_df = ref_dfs[ref_table]

            if ref_col not in ref_df.columns:
                results.append({
                    'dimension': 'consistency',
                    'table': table_name,
                    'column': col,
                    'rule': 'foreign_key',
                    'reference': f"{ref_table}.{ref_col}",
                    'expected': 1.0,
                    'actual': 0.0,
                    'passed': False,
                    'severity': 'critical',
                    'action': 'reject',
                    'reason': f"Reference column {ref_col} not found in {ref_table}"
                })
                continue

            valid_values = set(ref_df[ref_col].dropna())
            invalid_mask = ~df[col].isin(valid_values)
            invalid_count = invalid_mask.sum()
            integrity = 1 - (invalid_count / len(df)) if len(df) > 0 else 1.0

            # Quarantine records with invalid FKs
            if invalid_count > 0 and fk_rule.get('action') == 'quarantine':
                qkey = f"{table_name}_invalid_fk_{col}"
                self.quarantine_records[qkey] = df[invalid_mask]

            results.append({
                'dimension': 'consistency',
                'table': table_name,
                'column': col,
                'rule': 'foreign_key',
                'reference': f"{ref_table}.{ref_col}",
                'expected': 1.0,
                'actual': round(float(integrity), 4),
                'passed': bool(integrity == 1.0),
                'severity': fk_rule['severity'],
                'action': fk_rule.get('action'),
                'reason': fk_rule.get('reason'),
                'invalid_count': int(invalid_count),
                'total_rows': len(df)
            })

        return results

    def check_consistency_rules(self, table_name: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Check business rule consistency"""
        table_rules = self.rules['tables'][table_name]
        results = []

        for rule in table_rules.get('consistency_rules', []):
            rule_name = rule['rule']
            expression = rule['expression']

            # Parse and evaluate expression (simplified for common patterns)
            passed = True
            violated_count = 0

            try:
                if rule_name == 'cash_balance_less_than_total_value':
                    if 'cash_balance' in df.columns and 'total_value' in df.columns:
                        violated_mask = df['cash_balance'] > df['total_value']
                        violated_count = violated_mask.sum()
                        passed = violated_count == 0

                elif rule_name == 'market_value_calculation':
                    if all(c in df.columns for c in ['shares', 'current_price', 'market_value']):
                        calculated = df['shares'] * df['current_price']
                        diff = abs(calculated - df['market_value'])
                        violated_mask = diff >= 1.0
                        violated_count = violated_mask.sum()
                        passed = violated_count == 0

                elif rule_name == 'unrealized_gain_loss_calculation':
                    if all(c in df.columns for c in ['market_value', 'cost_basis', 'unrealized_gain_loss']):
                        calculated = df['market_value'] - df['cost_basis']
                        diff = abs(calculated - df['unrealized_gain_loss'])
                        violated_mask = diff >= 1.0
                        violated_count = violated_mask.sum()
                        passed = violated_count == 0

            except Exception as e:
                passed = False
                violated_count = -1

            results.append({
                'dimension': 'consistency',
                'table': table_name,
                'rule': rule_name,
                'expression': expression,
                'passed': bool(passed),
                'severity': rule['severity'],
                'reason': rule.get('reason'),
                'violated_count': int(violated_count),
                'total_rows': len(df)
            })

        return results

    def detect_anomalies(self, table_name: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Detect statistical outliers"""
        table_rules = self.rules['tables'][table_name]
        results = []

        for rule in table_rules.get('anomaly_detection', []):
            col = rule['column']
            method = rule['method']
            threshold = rule['threshold']

            if col not in df.columns:
                continue

            # Skip if column is not numeric
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue

            non_null_data = df[col].dropna()

            if len(non_null_data) < 3:
                # Not enough data for anomaly detection
                results.append({
                    'dimension': 'anomaly',
                    'table': table_name,
                    'column': col,
                    'method': method,
                    'outliers': 0,
                    'outlier_percentage': 0.0,
                    'severity': rule['severity'],
                    'description': rule.get('description'),
                    'note': 'Insufficient data for anomaly detection'
                })
                continue

            if method == 'z_score':
                mean = non_null_data.mean()
                std = non_null_data.std()
                if std > 0:
                    z_scores = np.abs((non_null_data - mean) / std)
                    outlier_count = (z_scores > threshold).sum()
                else:
                    outlier_count = 0

            elif method == 'interquartile_range':
                Q1 = non_null_data.quantile(0.25)
                Q3 = non_null_data.quantile(0.75)
                IQR = Q3 - Q1
                if IQR > 0:
                    outlier_count = ((non_null_data < (Q1 - threshold * IQR)) |
                                   (non_null_data > (Q3 + threshold * IQR))).sum()
                else:
                    outlier_count = 0
            else:
                outlier_count = 0

            outlier_pct = outlier_count / len(non_null_data) if len(non_null_data) > 0 else 0

            results.append({
                'dimension': 'anomaly',
                'table': table_name,
                'column': col,
                'method': method,
                'outliers': int(outlier_count),
                'outlier_percentage': round(outlier_pct, 4),
                'severity': rule['severity'],
                'description': rule.get('description')
            })

        return results

    def generate_quality_score(self, all_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate overall quality score"""
        # Separate by severity
        critical_results = [r for r in all_results if r.get('severity') == 'critical' and 'passed' in r]
        warning_results = [r for r in all_results if r.get('severity') == 'warning' and 'passed' in r]

        critical_passed = sum(1 for r in critical_results if r.get('passed', True))
        critical_total = len(critical_results) if critical_results else 1

        warning_passed = sum(1 for r in warning_results if r.get('passed', True))
        warning_total = len(warning_results) if warning_results else 1

        # Weighted score: 80% critical, 20% warnings
        score = (0.8 * (critical_passed / critical_total)) + (0.2 * (warning_passed / warning_total))

        # Check if passes threshold
        threshold = self.rules['quality_thresholds']['overall_score']
        passes = score >= threshold

        # Additional checks for zone promotion
        critical_failures = [r for r in critical_results if not r.get('passed', True)]
        blocks_promotion = len(critical_failures) > 0

        return {
            'overall_score': round(score, 3),
            'critical_passed': critical_passed,
            'critical_total': critical_total,
            'critical_failures': len(critical_failures),
            'warning_passed': warning_passed,
            'warning_total': warning_total,
            'passes_threshold': passes,
            'blocks_promotion': blocks_promotion,
            'threshold': threshold
        }

    def save_quarantine_records(self):
        """Save quarantined records to files"""
        if not self.quarantine_records:
            return

        quarantine_dir = self.data_path / 'quarantine'
        quarantine_dir.mkdir(exist_ok=True)

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        for key, df in self.quarantine_records.items():
            filename = f"{key}_{timestamp}.parquet"
            filepath = quarantine_dir / filename
            df.to_parquet(filepath, index=False)
            print(f"  → Quarantined {len(df)} records to {filepath}")

    def run_all_checks(self) -> Dict[str, Any]:
        """Execute all quality checks"""
        print(f"\n{'='*80}")
        print(f"Running Quality Checks: {self.rules['workload']} - {self.zone} zone")
        print(f"{'='*80}\n")

        self.tracer.log_start(workload=self.rules['workload'], zone=self.zone)

        # Load data for each table
        tables = ['stocks', 'portfolios', 'positions']
        dfs = {}

        for table in tables:
            file_path = self.data_path / f"{table}.parquet"
            if file_path.exists():
                dfs[table] = pd.read_parquet(file_path)
                print(f"✓ Loaded {table}: {len(dfs[table])} rows")
            else:
                print(f"⚠ {table} not found at {file_path}")

        if not dfs:
            print("\nERROR: No data files found")
            return {
                'workload': self.rules['workload'],
                'zone': self.zone,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'quality_score': {'overall_score': 0.0, 'passes_threshold': False},
                'checks': [],
                'error': 'No data files found'
            }

        # Run checks
        all_results = []

        for table_name, df in dfs.items():
            print(f"\nChecking {table_name}...")

            # 1. Completeness
            completeness_results = self.check_completeness(table_name, df)
            all_results.extend(completeness_results)
            passed = sum(1 for r in completeness_results if r.get('passed', True))
            self.tracer.log_quality_check(f"completeness_{table_name}", passed=(passed == len(completeness_results)),
                                          checks=len(completeness_results), passed_count=passed)
            print(f"  ✓ Completeness: {len(completeness_results)} checks")

            # 2. Uniqueness
            uniqueness_results = self.check_uniqueness(table_name, df)
            all_results.extend(uniqueness_results)
            passed = sum(1 for r in uniqueness_results if r.get('passed', True))
            self.tracer.log_quality_check(f"uniqueness_{table_name}", passed=(passed == len(uniqueness_results)),
                                          checks=len(uniqueness_results), passed_count=passed)
            print(f"  ✓ Uniqueness: {len(uniqueness_results)} checks")

            # 3. Validity
            validity_results = self.check_validity(table_name, df)
            all_results.extend(validity_results)
            passed = sum(1 for r in validity_results if r.get('passed', True))
            self.tracer.log_quality_check(f"validity_{table_name}", passed=(passed == len(validity_results)),
                                          checks=len(validity_results), passed_count=passed)
            print(f"  ✓ Validity: {len(validity_results)} checks")

            # 4. Consistency - business rules
            consistency_results = self.check_consistency_rules(table_name, df)
            all_results.extend(consistency_results)
            passed = sum(1 for r in consistency_results if r.get('passed', True))
            self.tracer.log_quality_check(f"consistency_{table_name}", passed=(passed == len(consistency_results)),
                                          checks=len(consistency_results), passed_count=passed)
            print(f"  ✓ Consistency: {len(consistency_results)} checks")

            # 5. Referential integrity (for positions)
            if table_name == 'positions':
                fk_results = self.check_referential_integrity(table_name, df, dfs)
                all_results.extend(fk_results)
                passed = sum(1 for r in fk_results if r.get('passed', True))
                self.tracer.log_quality_check(f"foreign_keys_{table_name}", passed=(passed == len(fk_results)),
                                              checks=len(fk_results), passed_count=passed)
                print(f"  ✓ Foreign Keys: {len(fk_results)} checks")

            # 6. Anomaly detection
            anomaly_results = self.detect_anomalies(table_name, df)
            all_results.extend(anomaly_results)
            self.tracer.log_quality_check(f"anomaly_{table_name}", passed=True,
                                          checks=len(anomaly_results))
            print(f"  ✓ Anomaly Detection: {len(anomaly_results)} checks")

        # Generate overall score
        quality_score = self.generate_quality_score(all_results)

        # Save quarantined records
        if self.quarantine_records:
            print(f"\nQuarantining {len(self.quarantine_records)} record sets...")
            self.save_quarantine_records()

        # Generate report
        report = {
            'workload': self.rules['workload'],
            'zone': self.zone,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'compliance': self.rules['compliance'],
            'quality_score': quality_score,
            'checks': all_results,
            'quarantined_record_sets': len(self.quarantine_records),
            'sox_compliant': quality_score['passes_threshold'] and not quality_score['blocks_promotion']
        }

        # Save report
        report_path = self.data_path / f'quality_report_{self.zone}.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n{'='*80}")
        print(f"QUALITY SCORE: {quality_score['overall_score']:.1%}")
        print(f"Critical: {quality_score['critical_passed']}/{quality_score['critical_total']} passed")
        print(f"Warnings: {quality_score['warning_passed']}/{quality_score['warning_total']} passed")
        print(f"Threshold: {quality_score['threshold']:.1%}")
        print(f"Passes Threshold: {'✓' if quality_score['passes_threshold'] else '✗'}")
        print(f"Blocks Promotion: {'YES' if quality_score['blocks_promotion'] else 'NO'}")
        print(f"SOX Compliant: {'✓' if report['sox_compliant'] else '✗'}")
        print(f"\nReport saved to: {report_path}")
        print(f"{'='*80}\n")

        # Final trace event
        self.tracer.log_complete(
            status="success" if quality_score['passes_threshold'] else "failed",
            overall_score=quality_score['overall_score'],
            critical_passed=quality_score['critical_passed'],
            critical_total=quality_score['critical_total'],
            sox_compliant=report['sox_compliant'],
        )
        self.tracer.close()

        return report


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python run_quality_checks.py <rules_path> <data_path> <zone>")
        print("\nExample:")
        print("  python run_quality_checks.py \\")
        print("    workloads/financial_portfolios/config/quality_rules.yaml \\")
        print("    output/financial_portfolios/silver \\")
        print("    silver")
        sys.exit(1)

    rules_path = sys.argv[1]
    data_path = sys.argv[2]
    zone = sys.argv[3]

    with ScriptTracer.for_script(__file__) as tracer:
        checker = QualityChecker(rules_path, data_path, zone, tracer=tracer)
        report = checker.run_all_checks()

    # Exit with error if quality checks fail
    if not report['quality_score']['passes_threshold']:
        print("ERROR: Quality score below threshold")
        sys.exit(1)

    if report['quality_score']['blocks_promotion']:
        print("ERROR: Critical failures detected - blocks zone promotion")
        sys.exit(1)

    print("✓ Quality checks passed")
    sys.exit(0)
