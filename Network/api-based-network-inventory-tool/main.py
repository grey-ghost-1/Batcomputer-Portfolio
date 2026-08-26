"""Local JSON-to-SQLite network inventory synchronizer."""
import argparse
import json
import sqlite3


def sync_inventory(records, database="inventory.db"):
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT, ip TEXT, type TEXT)")
        for device in records:
            connection.execute("INSERT OR REPLACE INTO devices VALUES (?, ?, ?, ?)", (device["id"], device["name"], device["ip"], device.get("type", "unknown")))
        return connection.execute("SELECT * FROM devices ORDER BY id").fetchall()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", nargs="?", default="inventory.json")
    args = parser.parse_args()
    with open(args.inventory, encoding="utf-8") as source:
        print(sync_inventory(json.load(source)))
