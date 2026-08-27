import argparse
import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CHECKS = (
    ("site", "/api/health", {"status": "ok", "service": "batcomputer-website"}),
    ("platform", "/health/live", {"status": "ok", "service": "batcomputer-platform"}),
    ("platform", "/health/ready", {"status": "ready", "database": "reachable"}),
    ("orbital", "/health/live", {"status": "ok", "service": "orbital-data-lab"}),
    ("orbital", "/health/ready", {"status": "ready", "database": "reachable"}),
)


def check_json(base_url, path, expected):
    request = Request(f"{base_url.rstrip('/')}{path}", headers={"Accept": "application/json"})
    with urlopen(request, timeout=8) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        payload = json.load(response)
    mismatches = {
        key: {"expected": value, "actual": payload.get(key)}
        for key, value in expected.items()
        if payload.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"{path} response mismatch: {mismatches}")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Smoke-check the three deployable portfolio services.")
    parser.add_argument("--site", default="http://127.0.0.1:5000")
    parser.add_argument("--platform", default="http://127.0.0.1:8000")
    parser.add_argument("--orbital", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base_urls = vars(args)

    failures = []
    for service, path, expected in CHECKS:
        try:
            check_json(base_urls[service], path, expected)
            print(f"PASS {service} {path}")
        except (
            HTTPError,
            HTTPException,
            URLError,
            TimeoutError,
            RuntimeError,
            json.JSONDecodeError,
        ) as exc:
            failures.append(f"{service} {path}: {exc}")
            print(f"FAIL {service} {path}: {exc}")

    if failures:
        raise SystemExit(1)
    print("All service smoke checks passed.")


if __name__ == "__main__":
    main()
