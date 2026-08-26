"""CIDR calculator."""
import argparse
import ipaddress


def describe_subnet(cidr):
    network = ipaddress.ip_network(cidr, strict=False)
    hosts = list(network.hosts())
    return {"network": str(network.network_address), "broadcast": str(network.broadcast_address), "netmask": str(network.netmask), "usable_hosts": len(hosts), "first": str(hosts[0]) if hosts else None, "last": str(hosts[-1]) if hosts else None}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("cidr", nargs="?", default="192.168.1.0/24")
    print(describe_subnet(parser.parse_args().cidr))
