"""Plan-only support automation runner."""
import argparse
from pathlib import Path


def collect_logs(root):
    return [str(path) for path in Path(root).glob("*.log")]


def plan(root, dry_run=True):
    return {"root": str(root), "logs": collect_logs(root), "dry_run": dry_run, "changes_applied": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    print(plan(parser.parse_args().root))
