import re
from pathlib import Path

COLLECTOR = Path("ops/otel-collector.yaml")
PROMETHEUS = Path("ops/prometheus.yml")
RULES = Path("ops/alerting-rules.yml")
COMPOSE = Path("compose.yaml")
TELEMETRY = Path("src/support_pilot/telemetry.py")
RUNBOOK = Path("docs/operations/runbook.md")

METRIC_REFERENCE = re.compile(r"support_pilot_[a-z0-9_]+")
EMITTED_METRIC = re.compile(r'"(support_pilot\.[a-z_.]+)"')


def _emitted_prometheus_prefixes() -> set[str]:
    """应用埋点的指标名转成 Prometheus 前缀（点号转下划线，去掉单位/类型后缀）。"""

    names = set(EMITTED_METRIC.findall(TELEMETRY.read_text(encoding="utf-8")))
    assert names, "telemetry.py 应包含指标名常量"
    return {name.replace(".", "_") for name in names}


def test_collector_exposes_prometheus_metrics_endpoint() -> None:
    config = COLLECTOR.read_text(encoding="utf-8")

    assert "prometheus:" in config
    assert "endpoint: 0.0.0.0:8889" in config
    metrics_pipeline = config.split("metrics:")[-1]
    assert "exporters: [debug, prometheus]" in metrics_pipeline


def test_compose_runs_prometheus_under_the_observability_profile() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "  prometheus:" in compose
    assert "prom/prometheus:" in compose
    assert '"9090:9090"' in compose
    assert "./ops/prometheus.yml:/etc/prometheus/prometheus.yml:ro" in compose
    assert "./ops/alerting-rules.yml:/etc/prometheus/alerting-rules.yml:ro" in compose


def test_prometheus_scrapes_the_collector_and_loads_alert_rules() -> None:
    config = PROMETHEUS.read_text(encoding="utf-8")

    assert 'targets: ["otel-collector:8889"]' in config
    assert "/etc/prometheus/alerting-rules.yml" in config


def test_alert_rules_only_reference_metrics_that_are_actually_emitted() -> None:
    prefixes = _emitted_prometheus_prefixes()
    referenced = set(METRIC_REFERENCE.findall(RULES.read_text(encoding="utf-8")))

    assert referenced, "告警规则应至少引用一个 support_pilot 指标"
    unknown = {
        name
        for name in referenced
        if not any(name.startswith(prefix) for prefix in prefixes)
    }
    assert unknown == set(), f"告警规则引用了未埋点的指标：{sorted(unknown)}"


def test_runbook_documents_the_metrics_endpoint_and_snapshot_script() -> None:
    runbook = RUNBOOK.read_text(encoding="utf-8")

    assert "8889" in runbook
    assert "metrics_snapshot.py" in runbook
    assert "register_maintenance_task.ps1" in runbook
