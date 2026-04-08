#!/usr/bin/env python3
"""Pre-commit hook: validate MCP config files for security invariants.

Checks .mcp.json and .mcp.gateway.json for:
  - Command allowlist (only uv/uvx)
  - No hardcoded credentials in env values
  - No absolute paths in args
  - Gateway auth uses aws-sigv4
  - Custom server scripts under mcp-servers/
  - HTTPS enforcement for gateway URLs
  - Package names match known patterns
"""

import json
import re
import sys
from pathlib import Path

# Only these commands are allowed to execute MCP servers
ALLOWED_COMMANDS = {"uv", "uvx"}

# Known safe package patterns for uvx
KNOWN_PACKAGE_PATTERNS = [
    r"^awslabs-[\w-]+-mcp-server$",
    r"^fastmcp$",
    r"^boto3$",
    r"^mcp$",
]

# Credential patterns that must not appear in env values
CREDENTIAL_PATTERNS = [
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key ID"),
    (r"[A-Za-z0-9/+=]{40}", "Possible AWS Secret Key (40-char base64)"),
    (r"-----BEGIN.*PRIVATE KEY-----", "Private key"),
    (r"(?i)^(password|secret|token)$", "Bare credential value"),
]

# Absolute path patterns
ABSOLUTE_PATH_PATTERNS = [
    r"/Users/\w+",
    r"/home/\w+",
    r"C:\\",
    r"/opt/",
    r"/var/",
]

# Allowed env keys (these are expected to have non-credential values)
SAFE_ENV_KEYS = {
    "AWS_REGION", "AWS_PROFILE", "AWS_DEFAULT_REGION",
    "FASTMCP_LOG_LEVEL", "LOG_LEVEL",
}


def validate_server(name: str, config: dict, filepath: str) -> list[str]:
    """Validate a single MCP server configuration."""
    errors = []

    # Gateway/SSE servers use url+transport instead of command+args
    if "url" in config and "command" not in config:
        return validate_remote_server(name, config, filepath)

    # Check command allowlist
    command = config.get("command", "")
    if command not in ALLOWED_COMMANDS:
        errors.append(
            f"{filepath}: server '{name}' uses disallowed command '{command}' "
            f"(allowed: {', '.join(sorted(ALLOWED_COMMANDS))})"
        )

    args = config.get("args", [])
    env = config.get("env", {})

    # Check for absolute paths in args
    args_str = " ".join(str(a) for a in args)
    for pattern in ABSOLUTE_PATH_PATTERNS:
        if re.search(pattern, args_str):
            errors.append(
                f"{filepath}: server '{name}' has absolute path in args — "
                f"use relative paths only"
            )
            break

    # Check custom server scripts point to mcp-servers/
    if command == "uv":
        script_args = [a for a in args if a.endswith(".py")]
        for script in script_args:
            if not script.startswith("mcp-servers/"):
                errors.append(
                    f"{filepath}: server '{name}' runs script '{script}' "
                    f"outside mcp-servers/ directory"
                )

    # Check uvx package names
    if command == "uvx":
        from_idx = None
        for i, arg in enumerate(args):
            if arg == "--from" and i + 1 < len(args):
                from_idx = i + 1
                break
        if from_idx is not None:
            pkg = args[from_idx]
            if not any(re.match(p, pkg) for p in KNOWN_PACKAGE_PATTERNS):
                errors.append(
                    f"{filepath}: server '{name}' uses unknown package '{pkg}' — "
                    f"verify it's a trusted MCP server package"
                )

    # Check env values for credentials
    for key, value in env.items():
        if key in SAFE_ENV_KEYS:
            continue
        value_str = str(value)
        for pattern, desc in CREDENTIAL_PATTERNS:
            if re.search(pattern, value_str):
                errors.append(
                    f"{filepath}: server '{name}' env '{key}' may contain {desc} — "
                    f"use AWS credential chain instead"
                )

    # Check log level is not DEBUG in committed config
    log_level = env.get("FASTMCP_LOG_LEVEL", env.get("LOG_LEVEL", ""))
    if log_level.upper() == "DEBUG":
        errors.append(
            f"{filepath}: server '{name}' has DEBUG log level — "
            f"use ERROR or WARNING in committed config"
        )

    return errors


def validate_remote_server(name: str, config: dict, filepath: str) -> list[str]:
    """Validate a remote/SSE MCP server (url-based, no local command)."""
    errors = []

    url = config.get("url", "")
    if url and not url.startswith("https://"):
        errors.append(
            f"{filepath}: server '{name}' URL does not use HTTPS — "
            f"gateway endpoints must use HTTPS"
        )

    auth = config.get("auth", {})
    auth_type = auth.get("type", "")
    if auth_type and auth_type != "aws-sigv4":
        errors.append(
            f"{filepath}: server '{name}' uses auth type '{auth_type}' — "
            f"use 'aws-sigv4' for gateway authentication"
        )

    return errors


def validate_gateway(config: dict, filepath: str) -> list[str]:
    """Validate gateway-specific security settings."""
    errors = []

    servers = config.get("mcpServers", {})
    for name, server in servers.items():
        # Check auth method
        auth = server.get("auth", {})
        auth_type = auth.get("type", "")
        if auth and auth_type not in ("aws-sigv4", ""):
            errors.append(
                f"{filepath}: server '{name}' uses auth type '{auth_type}' — "
                f"use 'aws-sigv4' for gateway authentication"
            )

        # Check HTTPS enforcement for URLs
        url = server.get("url", "")
        if url and not url.startswith("https://"):
            errors.append(
                f"{filepath}: server '{name}' URL does not use HTTPS — "
                f"gateway endpoints must use HTTPS"
            )

    return errors


def validate_file(filepath: str) -> list[str]:
    """Validate a single MCP config file."""
    try:
        content = Path(filepath).read_text()
    except OSError as e:
        return [f"{filepath}: cannot read file: {e}"]

    try:
        config = json.loads(content)
    except json.JSONDecodeError as e:
        return [f"{filepath}: invalid JSON: {e}"]

    errors = []
    servers = config.get("mcpServers", {})

    if not servers:
        errors.append(f"{filepath}: no mcpServers defined")
        return errors

    for name, server_config in servers.items():
        errors.extend(validate_server(name, server_config, filepath))

    # Gateway-specific checks
    if "gateway" in filepath.lower():
        errors.extend(validate_gateway(config, filepath))

    return errors


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    all_errors: list[str] = []
    for filepath in sys.argv[1:]:
        errors = validate_file(filepath)
        all_errors.extend(errors)

    if not all_errors:
        return 0

    print("\n  MCP CONFIG VALIDATOR — Security issues found\n")
    for error in all_errors:
        print(f"  [BLOCK] {error}")
    print(f"\n  {len(all_errors)} issue(s) found. Fix before committing.\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
