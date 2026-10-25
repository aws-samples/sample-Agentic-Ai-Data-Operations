import hashlib
from pathlib import Path

from shared.codegen.drift_validator import parse_artifact_header, verify_artifact
from shared.codegen.renderer import render_dry_run
from shared.codegen.spec_loader import load_spec


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
QUALITY_SCRIPT = ROOT / "scripts" / "quality" / "quality_check.py"


def test_quality_script_round_trips_from_quality_spec():
    quality, spec_hash = load_spec(CONFIG / "quality_rules.yaml", "quality")
    script = QUALITY_SCRIPT.read_text()

    rendered, artifact_hash = render_dry_run(
        quality,
        spec_hash,
        "quality_check",
        "1.2.0",
        "2026-10-22T18:18:44Z",
    )

    assert rendered.decode() == script
    assert hashlib.sha256(script.encode()).hexdigest() == artifact_hash
    assert parse_artifact_header(script)["spec_hash"] == spec_hash
    assert verify_artifact(QUALITY_SCRIPT).ok


def test_token_rule_cannot_pass_when_source_pan_key_has_no_target_token():
    script = QUALITY_SCRIPT.read_text()

    target_filter = script.index('F.expr("credit_card_token IS NOT NULL")')
    source_count = script.index("source_present_count = source_present_df.count()")
    failure_count = script.index(
        "tokenization_failures = source_present_df.join(", source_count
    )

    assert target_filter < source_count < failure_count
    assert "left_anti" in script[failure_count:failure_count + 400]
    assert "critical_failures" in script
