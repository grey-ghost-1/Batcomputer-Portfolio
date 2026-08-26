"""Safe configuration-plan generator; transport is intentionally not automatic."""
import argparse
import json


def build_plan(devices, config_lines):
    return [{"host": device["host"], "commands": config_lines, "mode": "plan-only"} for device in devices]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("targets", help="JSON list of authorized device records")
    parser.add_argument("--command", action="append", required=True)
    args = parser.parse_args()
    with open(args.targets, encoding="utf-8") as source:
        print(json.dumps(build_plan(json.load(source), args.command), indent=2))
