"""Workstation diagnostics with actionable thresholds."""
import argparse
import shutil


def diagnose(cpu, memory, disk):
    issues = []
    if cpu > 85: issues.append("high CPU load")
    if memory > 90: issues.append("critical memory usage")
    if disk > 90: issues.append("disk nearly full")
    return {"cpu": cpu, "memory": memory, "disk": disk, "issues": issues, "status": "attention" if issues else "healthy"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpu", type=float, default=32)
    parser.add_argument("--memory", type=float, default=71)
    parser.add_argument("--disk", type=float, default=94)
    print(diagnose(parser.parse_args().cpu, parser.parse_args().memory, parser.parse_args().disk))
