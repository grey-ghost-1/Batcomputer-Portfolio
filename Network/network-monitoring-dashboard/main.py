"""In-memory network telemetry dashboard model."""
from dataclasses import dataclass, asdict
import json


@dataclass
class DeviceStatus:
    name: str
    uptime: str
    latency_ms: int | None
    bandwidth_mbps: int
    status: str


def summarize(devices):
    return {"total": len(devices), "healthy": sum(d.status == "OK" for d in devices), "alerts": sum(d.status != "OK" for d in devices), "devices": [asdict(d) for d in devices]}


if __name__ == "__main__":
    devices = [DeviceStatus("router-01", "41d", 3, 210, "OK"), DeviceStatus("ap-03", "0d", None, 0, "ALERT")]
    print(json.dumps(summarize(devices), indent=2))
