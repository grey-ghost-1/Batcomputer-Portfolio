"""Standard-library dashboard data service."""
import argparse
import json
import os
import shutil


def metrics(path="."):
    total, used, free = shutil.disk_usage(path)
    return {"cpu_percent": None, "memory_percent": None, "disk_percent": round(used / total * 100, 2), "host": os.name}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".")
    print(json.dumps(metrics(parser.parse_args().path), indent=2))
