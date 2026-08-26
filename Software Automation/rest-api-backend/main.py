"""Small dependency-free REST-style item service model."""
import argparse
import json


def create_item(name, quantity, owner):
    if not name or quantity < 0:
        raise ValueError("name is required and quantity cannot be negative")
    return {"owner": owner, "item": {"name": name, "quantity": quantity}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("name", nargs="?", default="widget")
    parser.add_argument("--quantity", type=int, default=4)
    parser.add_argument("--owner", default="local-user")
    print(json.dumps(create_item(parser.parse_args().name, parser.parse_args().quantity, parser.parse_args().owner), indent=2))
