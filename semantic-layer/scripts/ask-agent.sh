#!/usr/bin/env bash
# Cross-platform thin wrapper for ask_agent.py.
# Works on macOS, Linux, and WSL.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/ask_agent.py" "$@"
