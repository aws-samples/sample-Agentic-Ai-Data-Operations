#!/bin/sh
# ADOP hook entry point for Kiro.
#
# Kiro invokes this; all of the work is in adop_launcher.py beside it, which adapts the
# shared ADOP gate contract to Kiro's payload shape and exit codes. See that file's
# docstring for what the adaptation involves and why.
#
# This wrapper exists only so the hook command stays a stable shell path and so the
# gate directory is resolved from the script's own location rather than from the
# working directory, which Kiro does not guarantee.
#
# Usage: adop-hook.sh <script-name-in-this-directory>
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec python3 "$SCRIPT_DIR/adop_launcher.py" "$@"
