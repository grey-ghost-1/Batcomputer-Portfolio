"""Small failed-login analyzer."""
import argparse
import re
from collections import Counter

FAILED_LOGIN = re.compile(r"Failed password for (\S+) from (\d+\.\d+\.\d+\.\d+)")


def analyze_log(path, threshold=5):
    counts = Counter()
    with open(path, encoding="utf-8") as log_file:
        for line in log_file:
            match = FAILED_LOGIN.search(line)
            if match:
                counts[match.groups()] += 1
    return {key: count for key, count in counts.items() if count >= threshold}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log")
    parser.add_argument("--threshold", type=int, default=5)
    args = parser.parse_args()
    print(analyze_log(args.log, args.threshold))


if __name__ == "__main__":
    main()
