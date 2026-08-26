"""Portable system health report using standard-library checks."""
import argparse
import shutil


def health(path=".", free_threshold_gb=10):
    total, used, free = shutil.disk_usage(path)
    free_gb = free / 2**30
    return {"path": path, "free_gb": round(free_gb, 2), "status": "healthy" if free_gb >= free_threshold_gb else "attention"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".")
    print(health(parser.parse_args().path))
