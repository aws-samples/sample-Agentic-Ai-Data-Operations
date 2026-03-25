
# Run this AFTER first pipeline execution creates Silver table

import boto3
lakeformation = boto3.client('lakeformation', region_name='us-east-1')

for phi_col in [{'column': 'ssn', 'classification': 'CRITICAL', 'type': 'SSN', 'sensitivity': 'CRITICAL'}, {'column': 'medical_record_number', 'classification': 'CRITICAL', 'type': 'NATIONAL_ID', 'sensitivity': 'CRITICAL'}, {'column': 'patient_name', 'classification': 'HIGH', 'type': 'NAME', 'sensitivity': 'HIGH'}, {'column': 'email', 'classification': 'HIGH', 'type': 'EMAIL', 'sensitivity': 'HIGH'}, {'column': 'dob', 'classification': 'HIGH', 'type': 'DOB', 'sensitivity': 'HIGH'}, {'column': 'visit_date', 'classification': 'HIGH', 'type': 'DOB', 'sensitivity': 'HIGH'}, {'column': 'phone', 'classification': 'MEDIUM', 'type': 'PHONE', 'sensitivity': 'MEDIUM'}, {'column': 'address', 'classification': 'MEDIUM', 'type': 'ADDRESS', 'sensitivity': 'MEDIUM'}, {'column': 'city', 'classification': 'MEDIUM', 'type': 'ADDRESS', 'sensitivity': 'MEDIUM'}, {'column': 'state', 'classification': 'MEDIUM', 'type': 'ADDRESS', 'sensitivity': 'MEDIUM'}, {'column': 'zip', 'classification': 'MEDIUM', 'type': 'ADDRESS', 'sensitivity': 'MEDIUM'}]:
    try:
        lakeformation.add_lf_tags_to_resource(
            Resource={
                'TableWithColumns': {
                    'DatabaseName': 'healthcare_patients_silver',
                    'Name': 'patient_visits',
                    'ColumnNames': [phi_col['column']]
                }
            },
            LFTags=[
                {'TagKey': 'PII_Classification', 'TagValues': [phi_col['classification']]},
                {'TagKey': 'PII_Type', 'TagValues': [phi_col['type']]},
                {'TagKey': 'Data_Sensitivity', 'TagValues': [phi_col['sensitivity']]}
            ]
        )
        print(f"✅ Tagged: {phi_col['column']} ({phi_col['sensitivity']})")
    except Exception as e:
        print(f"❌ Failed to tag {phi_col['column']}: {e}")
