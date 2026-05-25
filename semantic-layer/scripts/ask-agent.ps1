# Cross-platform thin wrapper. The real script is ask_agent.py.
# Run from anywhere; resolves the .py next to this file.
$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'ask_agent.py'
& python $script @args
exit $LASTEXITCODE
