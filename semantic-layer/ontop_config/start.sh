#!/bin/sh
set -e

# Pull ontology + R2RML from S3 (managed by Phase 7 deploy script)
echo "Fetching ontology + R2RML from s3://${CONFIG_BUCKET}/..."
aws s3 cp "s3://${CONFIG_BUCKET}/${ONTOLOGY_S3_KEY}" "${ONTOP_ONTOLOGY_FILE}"
aws s3 cp "s3://${CONFIG_BUCKET}/${R2RML_S3_KEY}" "${ONTOP_MAPPING_FILE}"

# Generate ontop.properties from JDBC_URL at runtime
cat > /opt/ontop/input/ontop.properties <<EOF
jdbc.url=${JDBC_URL}
jdbc.driver=com.simba.athena.jdbc.Driver
jdbc.user=
jdbc.password=
ontop.inferDefaultDatatype=true
EOF

echo "=== ontop.properties ==="
cat /opt/ontop/input/ontop.properties
echo "========================"
echo "=== ontology head ==="
head -20 "${ONTOP_ONTOLOGY_FILE}"
echo "=== r2rml head ==="
head -20 "${ONTOP_MAPPING_FILE}"
echo "====================="

exec /opt/ontop/ontop endpoint \
  --ontology="${ONTOP_ONTOLOGY_FILE}" \
  --mapping="${ONTOP_MAPPING_FILE}" \
  --properties=/opt/ontop/input/ontop.properties \
  --port=8080
