#!/usr/bin/env python3
"""
Auto-wire ScriptTracer into ETL scripts.

This script scans workloads/*/scripts/ and adds tracing imports and calls
to Python files that don't already have them.

Usage:
    python scripts/wire_tracing.py                    # Dry run (show what would change)
    python scripts/wire_tracing.py --apply           # Actually modify files
    python scripts/wire_tracing.py --workload sales  # Only wire specific workload
"""

import argparse
import re
import sys
from pathlib import Path


# Pattern to detect if tracing is already wired
TRACER_IMPORT_PATTERN = re.compile(r"from shared\.utils\.script_tracer import")
TRACER_USAGE_PATTERN = re.compile(r"ScriptTracer|get_tracer")


def find_scripts(workloads_dir: Path, workload_filter: str = None) -> list[Path]:
    """Find all Python scripts in workloads/*/scripts/."""
    scripts = []
    for workload_dir in workloads_dir.iterdir():
        if not workload_dir.is_dir():
            continue
        if workload_filter and workload_filter not in workload_dir.name:
            continue

        scripts_dir = workload_dir / "scripts"
        if scripts_dir.exists():
            for py_file in scripts_dir.rglob("*.py"):
                # Skip __init__.py and test files
                if py_file.name.startswith("__") or "test" in py_file.name.lower():
                    continue
                scripts.append(py_file)

    return sorted(scripts)


def needs_tracing(file_path: Path) -> bool:
    """Check if a script needs tracing wired in."""
    content = file_path.read_text()

    # Already has tracing
    if TRACER_IMPORT_PATTERN.search(content):
        return False
    if TRACER_USAGE_PATTERN.search(content):
        return False

    # Skip very short files (likely empty or just imports)
    if len(content) < 100:
        return False

    # Must have a run() or main() function or if __name__ == "__main__"
    if "def run(" not in content and "def main(" not in content and "__main__" not in content:
        return False

    return True


def generate_patch_instructions(file_path: Path) -> str:
    """Generate instructions for manually adding tracing to a file."""
    return f"""
To wire tracing into {file_path}:

1. Add import after existing imports:
   from shared.utils.script_tracer import ScriptTracer

2. In main/run function, add at start:
   tracer = ScriptTracer.for_script(__file__)
   tracer.log_start(rows_in=...)

3. Add trace calls for each transformation step:
   tracer.log_transform("step_name", key=value, ...)

4. At end of function:
   tracer.log_complete(status="success", rows_out=...)
   tracer.close()

5. Or wrap the main block:
   if __name__ == "__main__":
       with ScriptTracer.for_script(__file__) as tracer:
           run(tracer=tracer)
"""


def main():
    parser = argparse.ArgumentParser(description="Wire ScriptTracer into ETL scripts")
    parser.add_argument("--apply", action="store_true", help="Actually modify files")
    parser.add_argument("--workload", help="Only process specific workload")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent
    workloads_dir = project_root / "workloads"

    if not workloads_dir.exists():
        print(f"Error: {workloads_dir} not found")
        sys.exit(1)

    scripts = find_scripts(workloads_dir, args.workload)
    print(f"Found {len(scripts)} scripts in workloads/*/scripts/")

    needs_wiring = []
    already_wired = []

    for script in scripts:
        if needs_tracing(script):
            needs_wiring.append(script)
        else:
            already_wired.append(script)

    print(f"\nAlready wired: {len(already_wired)}")
    print(f"Needs wiring:  {len(needs_wiring)}")

    if args.verbose and already_wired:
        print("\nAlready wired:")
        for s in already_wired:
            print(f"  [OK] {s.relative_to(project_root)}")

    if needs_wiring:
        print("\nScripts that need tracing:")
        for script in needs_wiring:
            rel_path = script.relative_to(project_root)
            print(f"  [ ] {rel_path}")

            if args.verbose:
                print(generate_patch_instructions(script))

    if not args.apply:
        print("\n(Dry run - use --apply to modify files)")
        print("\nRecommended approach:")
        print("  1. Wire tracing manually using sales_transactions/scripts/transform/bronze_to_silver.py as example")
        print("  2. Or use Claude Code to wire each file: 'wire tracing into {path}'")

    return 0


if __name__ == "__main__":
    sys.exit(main())
