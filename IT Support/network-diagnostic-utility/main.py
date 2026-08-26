"""Support-oriented DNS and connectivity diagnostics."""
import argparse
import socket
import subprocess


def diagnose(host):
    try:
        address = socket.gethostbyname(host)
    except socket.gaierror as exc:
        return {"host": host, "dns": None, "error": str(exc)}
    result = subprocess.run(["ping", "-n" if __import__("platform").system() == "Windows" else "-c", "1", host], capture_output=True, text=True, timeout=8)
    return {"host": host, "dns": address, "reachable": result.returncode == 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("host", nargs="?", default="localhost")
    print(diagnose(parser.parse_args().host))
