from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "observability" / "adot-collector.yaml"


def test_adot_collector_receives_otlp_and_exports_xray():
    config = yaml.safe_load(CONFIG.read_text())

    protocols = config["receivers"]["otlp"]["protocols"]
    assert protocols["grpc"]["endpoint"] == "0.0.0.0:4317"
    assert protocols["http"]["endpoint"] == "0.0.0.0:4318"
    assert config["exporters"]["awsxray"]["region"] == "${AWS_REGION}"

    traces = config["service"]["pipelines"]["traces"]
    assert traces["receivers"] == ["otlp"]
    assert traces["processors"] == ["batch"]
    assert traces["exporters"] == ["awsxray"]


def test_adop_env_example_uses_private_collector_endpoint():
    env_text = (
        ROOT / "config" / "observability" / "adop-otel.env.example"
    ).read_text()
    assert "ADOP_OTEL_ENABLED=true" in env_text
    assert "ADOP_OTEL_ENDPOINT=http://adot-collector.internal:4318/v1/traces" in env_text
