"""Multi-host latency report using the system ping command."""
import argparse
import platform
import subprocess


def ping(host, count=2):
    flag = "-n" if platform.system() == "Windows" else "-c"
    result = subprocess.run(["ping", flag, str(count), host], capture_output=True, text=True, timeout=10)
    return {"host": host, "reachable": result.returncode == 0, "output": result.stdout.strip()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("hosts", nargs="*", default=["127.0.0.1"])
    args = parser.parse_args()
    for host in args.hosts:
        print(ping(host))
