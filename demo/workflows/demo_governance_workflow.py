#!/usr/bin/env python3
"""
Demo: End-to-End Governance Workflow
=====================================

Simulates the full governance workflow for healthcare_patients dataset:
1. Phase 1: Discovery (regulatory requirements)
2. Phase 3: Profiling + PII detection
3. Phase 4: Build pipeline with masking rules
4. Phase 5: Deploy with LF-Tags and access control

This is a SIMULATION — shows what would happen without creating AWS resources.
"""

import csv
import json
import re
from typing import Dict, List, Any
from pathlib import Path

# PII detection patterns (from shared/utils/pii_detection_and_tagging.py)
PII_PATTERNS = {
    'EMAIL': {
        'column_patterns': ['email', 'e_mail', 'mail'],
        'regex': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        'sensitivity': 'HIGH'
    },
    'PHONE': {
        'column_patterns': ['phone', 'telephone', 'mobile', 'cell'],
        'regex': r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
        'sensitivity': 'MEDIUM'
    },
    'SSN': {
        'column_patterns': ['ssn', 'social_security', 'social_security_number'],
        'regex': r'\b\d{3}-\d{2}-\d{4}\b',
        'sensitivity': 'CRITICAL'
    },
    'NAME': {
        'column_patterns': ['name', 'first_name', 'last_name', 'full_name', 'patient_name'],
        'regex': None,  # High cardinality text
        'sensitivity': 'HIGH'
    },
    'DOB': {
        'column_patterns': ['dob', 'date_of_birth', 'birth_date', 'birthday'],
        'regex': r'\b\d{4}-\d{2}-\d{2}\b',
        'sensitivity': 'HIGH'
    },
    'ADDRESS': {
        'column_patterns': ['address', 'street', 'addr'],
        'regex': r'\d+\s+\w+\s+(St|Ave|Rd|Dr|Ln|Blvd)',
        'sensitivity': 'MEDIUM'
    },
    'CITY': {
        'column_patterns': ['city', 'town'],
        'regex': None,
        'sensitivity': 'MEDIUM'
    },
    'STATE': {
        'column_patterns': ['state', 'province'],
        'regex': r'\b[A-Z]{2}\b',
        'sensitivity': 'MEDIUM'
    },
    'ZIP': {
        'column_patterns': ['zip', 'postal', 'zipcode', 'postal_code'],
        'regex': r'\b\d{5}\b',
        'sensitivity': 'MEDIUM'
    },
    'MEDICAL_RECORD': {
        'column_patterns': ['medical_record', 'mrn', 'patient_number', 'record_number'],
        'regex': r'MRN-\d{4}-\d{3}',
        'sensitivity': 'CRITICAL'
    }
}

def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_step(step: int, description: str):
    """Print formatted step"""
    print(f"\n{'─'*80}")
    print(f"STEP {step}: {description}")
    print(f"{'─'*80}\n")

def detect_pii_by_name(column_name: str) -> Dict[str, Any]:
    """Detect PII based on column name patterns"""
    column_lower = column_name.lower()

    for pii_type, config in PII_PATTERNS.items():
        for pattern in config['column_patterns']:
            if pattern in column_lower:
                return {
                    'pii_type': pii_type,
                    'sensitivity': config['sensitivity'],
                    'detection_method': 'name-based',
                    'confidence': 1.0,
                    'pattern_matched': pattern
                }

    return None

def detect_pii_by_content(column_name: str, sample_values: List[str]) -> Dict[str, Any]:
    """Detect PII based on content patterns"""
    for pii_type, config in PII_PATTERNS.items():
        if config['regex']:
            matches = sum(1 for val in sample_values if re.search(config['regex'], str(val)))
            match_rate = matches / len(sample_values) if sample_values else 0

            if match_rate > 0.8:  # 80% of samples match pattern
                return {
                    'pii_type': pii_type,
                    'sensitivity': config['sensitivity'],
                    'detection_method': 'content-based',
                    'confidence': match_rate,
                    'pattern_matched': config['regex'][:50]
                }

    return None

def analyze_dataset(csv_path: Path) -> Dict[str, Any]:
    """Analyze CSV file and detect PII"""
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    columns = list(rows[0].keys())

    # Sample first 10 rows for content-based detection
    sample_data = {col: [row[col] for row in rows[:10]] for col in columns}

    pii_results = {}

    for col in columns:
        # Try name-based detection first
        name_result = detect_pii_by_name(col)

        if name_result:
            pii_results[col] = name_result
        else:
            # Try content-based detection
            content_result = detect_pii_by_content(col, sample_data[col])
            if content_result:
                pii_results[col] = content_result
            else:
                # Not PII
                pii_results[col] = {
                    'pii_type': 'NONE',
                    'sensitivity': 'NONE',
                    'detection_method': 'none',
                    'confidence': 1.0
                }

    return {
        'total_rows': len(rows),
        'total_columns': len(columns),
        'columns': columns,
        'pii_results': pii_results,
        'sample_data': sample_data
    }

def generate_lf_tags(pii_results: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """Generate Lake Formation tags for each column"""
    lf_tags = {}

    for col, result in pii_results.items():
        if result['sensitivity'] != 'NONE':
            lf_tags[col] = [
                {'TagKey': 'PII_Classification', 'TagValue': result['sensitivity']},
                {'TagKey': 'PII_Type', 'TagValue': result['pii_type']},
                {'TagKey': 'Data_Sensitivity', 'TagValue': result['sensitivity']}
            ]

    return lf_tags

def generate_access_policies(pii_results: Dict[str, Any]) -> Dict[str, List[str]]:
    """Generate tag-based access control policies"""

    # Define role access levels
    roles = {
        'Admin': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE'],
        'DataEngineer': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE'],
        'HealthcareProvider': ['HIGH', 'MEDIUM', 'LOW', 'NONE'],  # Can see patient names, NOT SSN
        'Analyst': ['MEDIUM', 'LOW', 'NONE'],  # Can see city/state, NOT names/SSN
        'DashboardUser': ['LOW', 'NONE']  # Aggregated data only
    }

    access_map = {role: [] for role in roles}

    for col, result in pii_results.items():
        sensitivity = result['sensitivity']
        for role, allowed_levels in roles.items():
            if sensitivity in allowed_levels:
                access_map[role].append(col)

    return access_map

def generate_masking_rules(pii_results: Dict[str, Any]) -> Dict[str, str]:
    """Generate transformation masking rules"""
    masking = {}

    for col, result in pii_results.items():
        if result['sensitivity'] == 'CRITICAL':
            masking[col] = 'hash_sha256'  # One-way hash for SSN, medical records
        elif result['sensitivity'] == 'HIGH':
            if result['pii_type'] == 'EMAIL':
                masking[col] = 'mask_email'  # j***@email.com
            elif result['pii_type'] == 'NAME':
                masking[col] = 'mask_partial'  # John S****
            else:
                masking[col] = 'hash_sha256'
        elif result['sensitivity'] == 'MEDIUM':
            if result['pii_type'] == 'PHONE':
                masking[col] = 'mask_phone'  # (***) ***-4567
            else:
                masking[col] = 'keep'  # City, state - not sensitive enough to mask

    return masking

def main():
    """Run end-to-end governance workflow demo"""

    print_section("🏥 Healthcare Patients Dataset — Governance Workflow Demo")

    print("Dataset: workloads/healthcare_patients/sample_data/patients.csv")
    print("Columns: 16 (patient_id, patient_name, dob, ssn, email, phone, ...)")
    print("Rows: 20 patients")
    print("Regulation: HIPAA (healthcare data)")

    # ========================================================================
    # PHASE 1: DISCOVERY
    # ========================================================================

    print_step(1, "Discovery — Regulatory Requirements")

    print("❓ Claude asks: \"Does this data comply with any regulations?\"")
    print("   □ GDPR  □ CCPA  ☑ HIPAA  □ SOX  □ PCI DSS")
    print()
    print("✅ User selects: HIPAA")
    print()
    print("📋 HIPAA Controls Applied:")
    print("   • PHI (Protected Health Information) encryption required")
    print("   • Column-level access control via Lake Formation")
    print("   • CloudTrail audit logging (7-year retention)")
    print("   • Zone-specific KMS keys")
    print("   • All PII must be tagged for compliance reporting")

    # ========================================================================
    # PHASE 3: PROFILING + PII DETECTION
    # ========================================================================

    print_step(2, "Profiling + PII Detection")

    csv_path = Path("/path/to/claude-data-operations/workloads/healthcare_patients/sample_data/patients.csv")

    print("🔍 Running AI-driven PII detection...")
    print("   • Name-based: Scanning column names for PII patterns")
    print("   • Content-based: Regex validation on sample data (10 rows)")
    print()

    analysis = analyze_dataset(csv_path)

    print(f"📊 Dataset Profile:")
    print(f"   • Total rows: {analysis['total_rows']}")
    print(f"   • Total columns: {analysis['total_columns']}")
    print()

    # Count by sensitivity
    sensitivity_counts = {}
    for result in analysis['pii_results'].values():
        sens = result['sensitivity']
        sensitivity_counts[sens] = sensitivity_counts.get(sens, 0) + 1

    print("🏷️  PII Detection Results:")
    print()
    print(f"   {'Column':<25} {'PII Type':<20} {'Sensitivity':<12} {'Method':<15} {'Confidence'}")
    print(f"   {'-'*25} {'-'*20} {'-'*12} {'-'*15} {'-'*10}")

    for col, result in analysis['pii_results'].items():
        if result['sensitivity'] != 'NONE':
            print(f"   {col:<25} {result['pii_type']:<20} {result['sensitivity']:<12} {result['detection_method']:<15} {result['confidence']:.0%}")

    print()
    print(f"📈 Summary by Sensitivity:")
    print(f"   • CRITICAL: {sensitivity_counts.get('CRITICAL', 0)} columns (SSN, medical records)")
    print(f"   • HIGH: {sensitivity_counts.get('HIGH', 0)} columns (names, emails, DOB)")
    print(f"   • MEDIUM: {sensitivity_counts.get('MEDIUM', 0)} columns (phone, address, city, state, zip)")
    print(f"   • NONE: {sensitivity_counts.get('NONE', 0)} columns (business data)")

    # ========================================================================
    # PHASE 4: BUILD PIPELINE — MASKING RULES
    # ========================================================================

    print_step(3, "Build Pipeline — Transformation Rules")

    masking = generate_masking_rules(analysis['pii_results'])

    print("🔒 PII Masking Rules for Landing → Staging:")
    print()

    for col, rule in masking.items():
        if rule != 'keep' and analysis['pii_results'][col]['sensitivity'] != 'NONE':
            pii_type = analysis['pii_results'][col]['pii_type']
            sensitivity = analysis['pii_results'][col]['sensitivity']

            if rule == 'hash_sha256':
                print(f"   • {col} ({pii_type}, {sensitivity})")
                print(f"     └─ SHA-256 hash (one-way, for joins only)")
            elif rule == 'mask_email':
                print(f"   • {col} ({pii_type}, {sensitivity})")
                print(f"     └─ Partial mask: j***@email.com")
            elif rule == 'mask_phone':
                print(f"   • {col} ({pii_type}, {sensitivity})")
                print(f"     └─ Partial mask: (***) ***-4567")
            elif rule == 'mask_partial':
                print(f"   • {col} ({pii_type}, {sensitivity})")
                print(f"     └─ Partial mask: John S****")

    print()
    print("ℹ️  Non-PII columns (blood_type, diagnosis, visit_date, etc.) pass through unchanged")

    # ========================================================================
    # PHASE 5: DEPLOY — LF-TAGS & ACCESS CONTROL
    # ========================================================================

    print_step(4, "Deploy — Lake Formation Tags")

    lf_tags = generate_lf_tags(analysis['pii_results'])

    print("🏷️  Lake Formation Tags Applied:")
    print()

    for col, tags in lf_tags.items():
        pii_type = analysis['pii_results'][col]['pii_type']
        sensitivity = analysis['pii_results'][col]['sensitivity']
        print(f"   • {col}")
        for tag in tags:
            print(f"     └─ {tag['TagKey']}: {tag['TagValue']}")

    print()
    print(f"✅ Total columns tagged: {len(lf_tags)}/{analysis['total_columns']}")

    # ========================================================================
    # ACCESS CONTROL POLICIES
    # ========================================================================

    print_step(5, "Tag-Based Access Control (TBAC)")

    access_policies = generate_access_policies(analysis['pii_results'])

    print("🔐 Column-Level Permissions by Role:")
    print()

    for role, columns in access_policies.items():
        print(f"   {role}:")

        # Group by sensitivity
        by_sensitivity = {}
        for col in columns:
            sens = analysis['pii_results'][col]['sensitivity']
            if sens != 'NONE':
                by_sensitivity.setdefault(sens, []).append(col)

        if by_sensitivity:
            for sens, cols in sorted(by_sensitivity.items(), key=lambda x: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].index(x[0]) if x[0] in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] else 999):
                print(f"     • {sens}: {len(cols)} columns — {', '.join(cols[:3])}{'...' if len(cols) > 3 else ''}")
        else:
            print(f"     • Non-PII only: {len([c for c in columns if analysis['pii_results'][c]['sensitivity'] == 'NONE'])} columns")

        print(f"     └─ Total accessible columns: {len(columns)}/{analysis['total_columns']}")
        print()

    # ========================================================================
    # QUERY BEHAVIOR EXAMPLE
    # ========================================================================

    print_step(6, "Query Behavior — Column Filtering in Action")

    print("Example: Analyst role queries the patients table:")
    print()
    print("SQL Query:")
    print("   SELECT * FROM healthcare.patients LIMIT 5;")
    print()
    print("🔍 Lake Formation Evaluates:")
    print("   • Analyst has access to: Data_Sensitivity IN ['MEDIUM', 'LOW', 'NONE']")
    print("   • Filters columns: CRITICAL/HIGH columns return NULL")
    print()
    print("Result (what Analyst sees):")
    print()

    # Show what an analyst would see
    print(f"   {'patient_id':<12} {'patient_name':<15} {'dob':<12} {'ssn':<12} {'email':<25} {'phone':<15} {'city':<15} {'diagnosis':<20}")
    print(f"   {'-'*12} {'-'*15} {'-'*12} {'-'*12} {'-'*25} {'-'*15} {'-'*15} {'-'*20}")

    for row in list(csv.DictReader(open(csv_path)))[:5]:
        # Analyst can see MEDIUM and below (phone, city), but NOT HIGH/CRITICAL (name, email, ssn, dob)
        print(f"   {row['patient_id']:<12} {'NULL':<15} {'NULL':<12} {'NULL':<12} {'NULL':<25} {row['phone']:<15} {row['city']:<15} {row['diagnosis']:<20}")

    print()
    print("❌ Blocked: patient_name (HIGH), dob (HIGH), ssn (CRITICAL), email (HIGH)")
    print("✅ Visible: patient_id (NONE), phone (MEDIUM), city (MEDIUM), diagnosis (NONE)")

    # ========================================================================
    # COMPLIANCE REPORTING
    # ========================================================================

    print_step(7, "Compliance Reporting")

    print("📋 PII Inventory Report (for HIPAA audit):")
    print()
    print(json.dumps({
        'dataset': 'healthcare_patients',
        'regulation': 'HIPAA',
        'total_columns': analysis['total_columns'],
        'pii_columns': len(lf_tags),
        'phi_columns': [col for col, result in analysis['pii_results'].items()
                        if result['sensitivity'] in ['CRITICAL', 'HIGH']],
        'summary': {
            'critical': sensitivity_counts.get('CRITICAL', 0),
            'high': sensitivity_counts.get('HIGH', 0),
            'medium': sensitivity_counts.get('MEDIUM', 0),
            'low': sensitivity_counts.get('LOW', 0)
        },
        'audit_trail': 'CloudTrail logs enabled (7-year retention)',
        'encryption': 'Zone-specific KMS keys (re-encrypt at boundaries)',
        'lf_tags_applied': True,
        'access_control': 'Tag-based (TBAC)'
    }, indent=2))

    # ========================================================================
    # MCP INTEGRATION
    # ========================================================================

    print_step(8, "MCP Integration — Natural Language Governance")

    print("With the PII Detection MCP Server, you can manage governance via Claude Code:")
    print()
    print("🗣️  User: \"Grant healthcare-provider-role access to patient names and addresses,\"")
    print("        \"but NOT SSNs or medical record numbers\"")
    print()
    print("🤖 Claude Code:")
    print("   1. Identifies columns:")
    print("      • patient_name (HIGH) ✅")
    print("      • address, city, state, zip (MEDIUM) ✅")
    print("      • ssn (CRITICAL) ❌")
    print("      • medical_record_number (CRITICAL) ❌")
    print()
    print("   2. Calls MCP tool: apply_column_security")
    print("      Principal: arn:aws:iam::ACCOUNT:role/HealthcareProviderRole")
    print("      Sensitivity: ['HIGH', 'MEDIUM']")
    print()
    print("   3. Lake Formation grants permissions:")
    print("      Resource: LFTagPolicy (Data_Sensitivity IN ['HIGH', 'MEDIUM'])")
    print("      Permissions: SELECT")
    print()
    print("✅ Done. Healthcare provider can now query patient data with appropriate access.")

    # ========================================================================
    # SUMMARY
    # ========================================================================

    print_section("✅ Governance Workflow Complete")

    print("Summary:")
    print(f"   • PII Detected: {len(lf_tags)} columns out of {analysis['total_columns']}")
    print(f"   • LF-Tags Applied: {len(lf_tags)} columns")
    print(f"   • Access Policies: {len(access_policies)} roles configured")
    print(f"   • Masking Rules: {len([r for r in masking.values() if r != 'keep'])} transformations")
    print(f"   • Compliance: HIPAA controls applied")
    print(f"   • Audit Logging: CloudTrail enabled (7-year retention)")
    print()
    print("Next Steps:")
    print("   1. Deploy to AWS: create Glue database, apply LF-Tags")
    print("   2. Grant role permissions via Lake Formation")
    print("   3. Test queries with restricted roles")
    print("   4. Generate compliance reports for auditors")
    print()
    print("🎉 All workloads get this governance automatically during onboarding!")

if __name__ == '__main__':
    main()
