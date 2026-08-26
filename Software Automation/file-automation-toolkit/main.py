"""Dry-run file organization toolkit."""
import argparse
from pathlib import Path


def plan(folder):
    root = Path(folder)
    return [{"source": str(path), "destination": str(root / (path.suffix.lstrip(".").lower() or "misc") / path.name)} for path in root.iterdir() if path.is_file()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", nargs="?", default=".")
    for item in plan(parser.parse_args().folder):
        print(item)
