"""Local hash-learning lab using generated sample hashes only."""
import argparse
import hashlib


def digest(value, algorithm="sha256"):
    return hashlib.new(algorithm, value.encode()).hexdigest()


def dictionary_attack(target_hash, words, algorithm="sha256"):
    for word in words:
        candidate = word.strip()
        if digest(candidate, algorithm) == target_hash:
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("password", nargs="?", default="training-only")
    parser.add_argument("--algorithm", default="sha256")
    args = parser.parse_args()
    words = ["password", "training-only", "example"]
    print({"match": dictionary_attack(digest(args.password, args.algorithm), words, args.algorithm)})


if __name__ == "__main__":
    main()
