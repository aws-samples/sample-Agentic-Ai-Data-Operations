"""Run the offline validation suite for the multi-agent integration bundle."""

from __future__ import annotations

import os
import subprocess
import sys
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str], *, env: dict[str, str] | None = None) -> int:
    print(f"\n== {label} ==")
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=ROOT, env=env)
    return result.returncode


def main() -> int:
    python = sys.executable
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "core") + os.pathsep + env.get("PYTHONPATH", "")

    checks = [
        ("integration structure", [python, "scripts/validate_integrations.py"], env),
        (
            "platform surfaces",
            [python, "scripts/sync_platforms.py", "check"],
            env,
        ),
        (
            "requirements auditor tests",
            [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", "core/tests"],
            env,
        ),
        (
            "Python AST parsing",
            [python, "-c", _ast_check_script()],
            None,
        ),
    ]

    failures = 0
    for label, command, command_env in checks:
        failures += run(label, command, env=command_env)

    if failures:
        print(f"\nFAIL: {failures} check(s) failed")
        return 1

    print("\nPASS: integration bundle validation completed")
    return 0


def _ast_check_script() -> str:
    return (
        "from pathlib import Path; import ast; "
        "[(ast.parse(p.read_text(encoding='utf-8'), filename=str(p))) "
        "for p in Path('.').rglob('*.py')]; print('PASS: Python AST parsing')"
    )


if __name__ == "__main__":
    raise SystemExit(main())
