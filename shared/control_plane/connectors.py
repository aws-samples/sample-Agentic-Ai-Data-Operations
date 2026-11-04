"""Safe connector health checks for the ADOP control plane.

Connector records contain an identity, scope, provider, and secret reference.
Connection metadata and credentials are resolved inside the backend from the
referenced secret, then discarded after the health check.
"""

from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse


class ConnectorTestError(RuntimeError):
    """A connector could not be tested safely."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.public_message = message


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _secret_value(secret_ref: str) -> dict[str, Any]:
    if not secret_ref:
        raise ConnectorTestError("SECRET_REFERENCE_MISSING", "No secret reference configured")
    if secret_ref.startswith("env://"):
        variable = secret_ref.removeprefix("env://")
        raw = os.getenv(variable)
        if not raw:
            raise ConnectorTestError("SECRET_UNAVAILABLE", "Referenced environment secret is unavailable")
    elif secret_ref.startswith("arn:aws:secretsmanager:") or secret_ref.startswith("adop/"):
        try:
            import boto3

            response = boto3.client("secretsmanager").get_secret_value(SecretId=secret_ref)
            raw = response.get("SecretString") or ""
        except Exception as exc:
            raise ConnectorTestError("SECRET_UNAVAILABLE", "Secrets Manager could not provide the secret") from exc
    else:
        raise ConnectorTestError(
            "INVALID_SECRET_REFERENCE",
            "Secret references must use env:// or AWS Secrets Manager",
        )
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConnectorTestError("SECRET_FORMAT_INVALID", "Secret must contain a JSON object") from exc
    if not isinstance(value, dict):
        raise ConnectorTestError("SECRET_FORMAT_INVALID", "Secret must contain a JSON object")
    return value


def _credential(value: dict[str, Any], *names: str) -> str | None:
    for name in names:
        candidate = value.get(name)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _profile_from_secret(profile: dict[str, Any], secret: dict[str, Any]) -> dict[str, Any]:
    """Resolve all connection metadata from the write-only secret profile."""
    resolved = dict(profile)
    for key in (
        "host",
        "port",
        "database",
        "dbname",
        "schema",
        "account",
        "warehouse",
        "role",
        "http_path",
        "sslmode",
        "jdbc_url",
    ):
        if resolved.get(key) in (None, "", 0) and secret.get(key) not in (None, ""):
            resolved[key] = secret[key]
    jdbc_url = _credential(secret, "jdbc_url", "url")
    if jdbc_url and not resolved.get("host"):
        parsed = urlparse(jdbc_url.removeprefix("jdbc:"))
        if parsed.hostname:
            resolved["host"] = parsed.hostname
        if parsed.port:
            resolved["port"] = parsed.port
        if parsed.path.strip("/"):
            resolved["database"] = parsed.path.strip("/").split("/", 1)[0]
    if str(resolved.get("type") or "").lower() in {"", "jdbc"}:
        secret_provider = _credential(secret, "provider", "driver", "engine", "type")
        if secret_provider:
            resolved["type"] = secret_provider.lower()
    return resolved


def persistent_connector_metadata(_: dict[str, Any] | None) -> dict[str, Any]:
    """Return the only metadata allowed in a durable connector record.

    Endpoint, JDBC, and authentication values belong in the referenced secret,
    not in JSON files or DynamoDB items.
    """
    return {}


def _network_probe(profile: dict[str, Any]) -> dict[str, Any]:
    host = profile.get("host")
    port = profile.get("port")
    if not host or not port:
        raise ConnectorTestError("ENDPOINT_MISSING", "Host and port are required for a network probe")
    started = time.monotonic()
    try:
        with socket.create_connection((str(host), int(port)), timeout=5):
            pass
    except (OSError, ValueError) as exc:
        raise ConnectorTestError("NETWORK_UNREACHABLE", "Connector endpoint is not reachable") from exc
    return {
        "status": "network_reachable",
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "details": {"authentication": "not tested"},
    }


def _test_snowflake(profile: dict[str, Any], secret: dict[str, Any]) -> dict[str, Any]:
    try:
        import snowflake.connector
    except ImportError as exc:
        raise ConnectorTestError(
            "DRIVER_NOT_INSTALLED",
            "snowflake-connector-python is not installed in the API runtime",
        ) from exc
    user = _credential(secret, "username", "user")
    password = _credential(secret, "password")
    account = _credential(profile, "account", "host")
    if not user or not password or not account:
        raise ConnectorTestError("CREDENTIALS_INCOMPLETE", "Snowflake account, username, and password are required")
    started = time.monotonic()
    connection = None
    try:
        connection = snowflake.connector.connect(
            account=account,
            user=user,
            password=password,
            warehouse=profile.get("warehouse"),
            database=profile.get("database"),
            schema=profile.get("schema"),
            role=profile.get("role"),
            login_timeout=10,
            network_timeout=10,
        )
        cursor = connection.cursor()
        try:
            cursor.execute("select current_version()")
            row = cursor.fetchone()
        finally:
            cursor.close()
    except Exception as exc:
        raise ConnectorTestError("AUTH_OR_QUERY_FAILED", "Snowflake authentication or health query failed") from exc
    finally:
        if connection is not None:
            connection.close()
    return {
        "status": "healthy",
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "details": {"provider": "snowflake", "server_version_present": bool(row and row[0])},
    }


def _test_databricks(profile: dict[str, Any], secret: dict[str, Any]) -> dict[str, Any]:
    try:
        from databricks import sql
    except ImportError as exc:
        raise ConnectorTestError(
            "DRIVER_NOT_INSTALLED",
            "databricks-sql-connector is not installed in the API runtime",
        ) from exc
    token = _credential(secret, "token", "password")
    host = _credential(profile, "host", "server_hostname")
    http_path = _credential(profile, "http_path")
    if not token or not host or not http_path:
        raise ConnectorTestError("CREDENTIALS_INCOMPLETE", "Databricks host, HTTP path, and token are required")
    started = time.monotonic()
    connection = None
    try:
        connection = sql.connect(server_hostname=host, http_path=http_path, access_token=token)
        cursor = connection.cursor()
        try:
            cursor.execute("select 1")
            cursor.fetchone()
        finally:
            cursor.close()
    except Exception as exc:
        raise ConnectorTestError("AUTH_OR_QUERY_FAILED", "Databricks authentication or health query failed") from exc
    finally:
        if connection is not None:
            connection.close()
    return {
        "status": "healthy",
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "details": {"provider": "databricks"},
    }


def _test_teradata(profile: dict[str, Any], secret: dict[str, Any]) -> dict[str, Any]:
    try:
        import teradatasql
    except ImportError as exc:
        raise ConnectorTestError(
            "DRIVER_NOT_INSTALLED",
            "teradatasql is not installed in the API runtime",
        ) from exc
    user = _credential(secret, "username", "user")
    password = _credential(secret, "password")
    host = _credential(profile, "host")
    if not user or not password or not host:
        raise ConnectorTestError("CREDENTIALS_INCOMPLETE", "Teradata host, username, and password are required")
    started = time.monotonic()
    connection = None
    try:
        connection = teradatasql.connect(host=host, user=user, password=password)
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            cursor.close()
    except Exception as exc:
        raise ConnectorTestError("AUTH_OR_QUERY_FAILED", "Teradata authentication or health query failed") from exc
    finally:
        if connection is not None:
            connection.close()
    return {
        "status": "healthy",
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "details": {"provider": "teradata"},
    }


def _test_postgres(profile: dict[str, Any], secret: dict[str, Any]) -> dict[str, Any]:
    try:
        import psycopg
    except ImportError as exc:
        raise ConnectorTestError(
            "DRIVER_NOT_INSTALLED",
            "psycopg is not installed in the API runtime",
        ) from exc
    user = _credential(secret, "username", "user")
    password = _credential(secret, "password")
    host = _credential(profile, "host")
    port = profile.get("port") or 5432
    database = _credential(profile, "database", "dbname") or "postgres"
    if not user or not password or not host:
        raise ConnectorTestError("CREDENTIALS_INCOMPLETE", "PostgreSQL host, username, and password are required")
    started = time.monotonic()
    connection = None
    try:
        connection = psycopg.connect(
            host=host,
            port=int(port),
            dbname=database,
            user=user,
            password=password,
            connect_timeout=10,
            sslmode=str(profile.get("sslmode") or "require"),
        )
        with connection.cursor() as cursor:
            cursor.execute("select current_database(), version()")
            row = cursor.fetchone()
    except Exception as exc:
        raise ConnectorTestError("AUTH_OR_QUERY_FAILED", "PostgreSQL authentication or health query failed") from exc
    finally:
        if connection is not None:
            connection.close()
    return {
        "status": "healthy",
        "latency_ms": round((time.monotonic() - started) * 1000, 1),
        "details": {"provider": "postgres", "database_present": bool(row and row[0])},
    }


def test_connector(profile: dict[str, Any]) -> dict[str, Any]:
    """Run a real provider test and return a UI-safe result."""
    provider = str(profile.get("type", "")).lower()
    started = time.monotonic()
    result: dict[str, Any]
    try:
        secret = _secret_value(str(profile.get("secret_ref") or ""))
        profile = _profile_from_secret(profile, secret)
        provider = str(profile.get("type", "")).lower()
        if provider == "snowflake":
            result = _test_snowflake(profile, secret)
        elif provider == "databricks":
            result = _test_databricks(profile, secret)
        elif provider == "teradata":
            result = _test_teradata(profile, secret)
        elif provider == "postgres":
            result = _test_postgres(profile, secret)
        elif provider in {"jdbc", "mysql", "redshift"}:
            result = _network_probe(profile)
        else:
            raise ConnectorTestError("UNSUPPORTED_PROVIDER", f"Provider {provider or 'unknown'} is not supported")
    except ConnectorTestError as exc:
        result = {
            "status": "unhealthy" if exc.code in {"NETWORK_UNREACHABLE", "AUTH_OR_QUERY_FAILED"} else "not_tested",
            "error_code": exc.code,
            "error_message": exc.public_message,
        }
    result.update({"checked_at": utc_now(), "duration_ms": round((time.monotonic() - started) * 1000, 1)})
    return result


def validate_connector_profile(profile: dict[str, Any]) -> None:
    name = profile.get("name")
    provider = str(profile.get("type", "")).lower()
    if not isinstance(name, str) or not name or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for char in name):
        raise ValueError("Connector name must contain only lowercase letters, numbers, hyphens, and underscores")
    if provider not in {"snowflake", "databricks", "teradata", "jdbc", "postgres", "mysql", "redshift"}:
        raise ValueError("Unsupported connector type")
    if not isinstance(profile.get("secret_ref"), str) or not profile["secret_ref"]:
        raise ValueError("secret_ref is required and must reference Secrets Manager or env://")
    if not isinstance(profile.get("metadata"), dict):
        raise ValueError("metadata must be an object")
    if profile.get("access_mode", "read-only") not in {"read-only", "read-write"}:
        raise ValueError("access_mode must be read-only or read-write")


def normalize_connector(record: dict[str, Any]) -> dict[str, Any]:
    safe = {
        "connector_id": record["connector_id"],
        "name": record["name"],
        "type": record["type"],
        "access_mode": record.get("access_mode", "read-only"),
        "scope": record.get("scope", "organization"),
        "scope_name": record.get("scope_name", "default"),
        "metadata": {},
        "secret_configured": bool(record.get("secret_ref")),
        "status": record.get("status", "not_tested"),
        "health": record.get("health"),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }
    return safe

