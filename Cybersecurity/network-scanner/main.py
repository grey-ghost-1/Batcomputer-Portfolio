"""Authorized TCP port scanner demo."""
import argparse
import socket


def scan_host(host, ports, timeout=0.3):
    results = []
    for port in ports:
        with socket.socket() as sock:
            sock.settimeout(timeout)
            if sock.connect_ex((host, port)) == 0:
                results.append(port)
    return results


def main():
    parser = argparse.ArgumentParser(description="Scan explicitly authorized hosts")
    parser.add_argument("host", nargs="?", default="127.0.0.1")
    parser.add_argument("--ports", default="22,80,443")
    args = parser.parse_args()
    ports = [int(value) for value in args.ports.split(",")]
    print({"host": args.host, "open_ports": scan_host(args.host, ports)})


if __name__ == "__main__":
    main()
