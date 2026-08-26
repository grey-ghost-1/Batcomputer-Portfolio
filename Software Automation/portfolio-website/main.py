"""Portfolio inventory checker."""
import argparse
from pathlib import Path


def inventory(root):
    root = Path(root)
    pages = sorted(path.name for path in root.glob("*.html"))
    return {"root": str(root), "page_count": len(pages), "pages": pages}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    print(inventory(parser.parse_args().root))
