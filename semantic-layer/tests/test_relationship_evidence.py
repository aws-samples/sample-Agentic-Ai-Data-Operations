"""Every cross-workload relationship in manifest.json has match_rate >= 0.05."""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
THRESHOLD = 0.05


def test_all_cross_workload_relationships_have_evidence():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    issues = []
    for w in manifest.get("workloads", []):
        for rel in w.get("cross_workload_relationships", []):
            mr = rel.get("match_rate")
            if mr is None or mr < THRESHOLD:
                issues.append(
                    f"{w['name']} relationship {rel.get('predicate', '?')} "
                    f"has match_rate={mr} < {THRESHOLD}"
                )
    assert not issues, "\n".join(issues)
