"""Deterministic RCS/SMS delivery simulator."""
import argparse


def send(message, rcs_available=True, failure=False):
    if rcs_available and not failure:
        return {"message": message, "protocol": "RCS", "status": "delivered", "latency_ms": 340}
    return {"message": message, "protocol": "SMS", "status": "delivered (fallback)", "latency_ms": 1120}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("message", nargs="?", default="test message")
    parser.add_argument("--rcs-unavailable", action="store_true")
    print(send(parser.parse_args().message, not parser.parse_args().rcs_unavailable))
