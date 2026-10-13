"""Print a Prometheus-format snapshot of SupportPilot metrics from the collector.

用 Collector 的 Prometheus 导出端点（默认 http://127.0.0.1:8889/metrics）生成一份
可提交、可对比的指标快照，便于在没有 Prometheus 的环境里留下导出记录。
"""

import argparse
import json
import re
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import urlopen

SAMPLE_PATTERN = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)(?P<labels>\{.*\})?\s+(?P<value>\S+)$"
)
LABEL_PATTERN = re.compile(r'(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)="(?P<value>[^"]*)"')
DEFAULT_PREFIX = "support_pilot_"
# 资源与 SDK 标签对业务看板没有意义，默认剔除以保持快照可读；--keep-resource-labels 可保留。
NOISE_LABELS = frozenset(
    {
        "instance",
        "job",
        "service_name",
        "service_instance_id",
        "telemetry_sdk_language",
        "telemetry_sdk_name",
        "telemetry_sdk_version",
    }
)


def parse_labels(raw: str | None) -> dict[str, str]:
    if not raw:
        return {}
    return {match.group("key"): match.group("value") for match in LABEL_PATTERN.finditer(raw)}


def scrape(endpoint: str, *, timeout: float) -> str:
    with urlopen(endpoint, timeout=timeout) as response:  # noqa: S310 - operator-provided endpoint
        return response.read().decode("utf-8")


def collect(
    text: str,
    *,
    prefix: str,
    drop_labels: frozenset[str] = NOISE_LABELS,
) -> dict[str, list[dict[str, object]]]:
    families: dict[str, list[dict[str, object]]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = SAMPLE_PATTERN.match(line.strip())
        if match is None:
            continue
        name = match.group("name")
        if not name.startswith(prefix):
            continue
        try:
            value = float(match.group("value"))
        except ValueError:
            continue
        labels = {
            key: value for key, value in parse_labels(match.group("labels")).items()
            if key not in drop_labels
        }
        families.setdefault(name, []).append({"labels": labels, "value": value})
    return families


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot SupportPilot metrics from the collector")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8889/metrics")
    parser.add_argument("--prefix", default=DEFAULT_PREFIX)
    parser.add_argument("--output", default="")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument(
        "--keep-resource-labels",
        action="store_true",
        help="保留 instance/job/service_name/telemetry_sdk_* 等资源标签",
    )
    args = parser.parse_args()

    try:
        text = scrape(args.endpoint, timeout=args.timeout)
    except (URLError, OSError) as error:
        raise SystemExit(f"cannot scrape {args.endpoint}: {error}") from error

    families = collect(
        text,
        prefix=args.prefix,
        drop_labels=frozenset() if args.keep_resource_labels else NOISE_LABELS,
    )
    document = {
        "endpoint": args.endpoint,
        "captured_at": datetime.now(UTC).isoformat(),
        "metric_families": {
            name: {"samples": len(samples), "values": samples}
            for name, samples in sorted(families.items())
        },
        "totals": {
            name: round(sum(float(sample["value"]) for sample in samples), 6)
            for name, samples in sorted(families.items())
        },
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False)
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload + "\n")
    print(payload)


if __name__ == "__main__":
    main()
