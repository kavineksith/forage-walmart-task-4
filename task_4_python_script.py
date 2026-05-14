"""
populate_database.py
--------------------
Reads shipping data from three CSV spreadsheets and inserts all records
into the SQLite shipment database.

Schema
------
  product  : id (PK), name
  shipment : id (PK), product_id (FK), quantity, origin, destination

Spreadsheet contract
--------------------
  shipping_data_0.csv  – self-contained; one product-shipment per row.
      columns: origin_warehouse, destination_store, product,
               on_time, product_quantity, driver_identifier

  shipping_data_1.csv  – one product *item* per row; rows must be
      aggregated by (shipment_identifier, product) to derive quantity.
      columns: shipment_identifier, product, on_time

  shipping_data_2.csv  – one shipment per row; supplies origin /
      destination for every identifier found in spreadsheet 1.
      columns: shipment_identifier, origin_warehouse,
               destination_store, driver_identifier
"""

import csv
import sqlite3
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths – adjust if the files live elsewhere relative to this script
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "shipment_database.db"
CSV_0 = BASE_DIR / "data" / "shipping_data_0.csv"
CSV_1 = BASE_DIR / "data" / "shipping_data_1.csv"
CSV_2 = BASE_DIR / "data" / "shipping_data_2.csv"


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_or_create_product(cursor: sqlite3.Cursor, name: str) -> int:
    """Return the id of an existing product row, or insert and return a new one."""
    cursor.execute("SELECT id FROM product WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO product (name) VALUES (?)", (name,))
    return cursor.lastrowid


def insert_shipment(
    cursor: sqlite3.Cursor,
    product_id: int,
    quantity: int,
    origin: str,
    destination: str,
) -> None:
    """Insert a single shipment record."""
    cursor.execute(
        "INSERT INTO shipment (product_id, quantity, origin, destination)"
        " VALUES (?, ?, ?, ?)",
        (product_id, quantity, origin, destination),
    )


# ---------------------------------------------------------------------------
# Per-spreadsheet processors
# ---------------------------------------------------------------------------

def process_csv0(cursor: sqlite3.Cursor) -> int:
    """
    Load shipping_data_0.csv.
    Each row is a complete, self-contained shipment record.
    Returns the number of rows inserted.
    """
    count = 0
    with open(CSV_0, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            product_id = get_or_create_product(cursor, row["product"])
            insert_shipment(
                cursor,
                product_id,
                int(row["product_quantity"]),
                row["origin_warehouse"],
                row["destination_store"],
            )
            count += 1
    return count


def process_csv1_csv2(cursor: sqlite3.Cursor) -> int:
    """
    Load shipping_data_1.csv (product items) joined with
    shipping_data_2.csv (origin / destination metadata).

    Strategy
    --------
    1. Build a {shipment_id: {origin, destination}} lookup from CSV 2.
    2. Stream CSV 1 and accumulate product counts per
       (shipment_identifier, product) using a nested defaultdict.
    3. For every (shipment_id, product, quantity) triple, resolve the
       origin/destination from the lookup and insert a shipment row.

    Returns the number of rows inserted.
    """
    # Step 1 – build shipment metadata lookup from CSV 2
    shipment_meta: dict[str, dict] = {}
    with open(CSV_2, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            shipment_meta[row["shipment_identifier"]] = {
                "origin":      row["origin_warehouse"],
                "destination": row["destination_store"],
            }

    # Step 2 – aggregate product quantities from CSV 1
    # Structure: {shipment_id: {product_name: count}}
    product_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    with open(CSV_1, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            product_counts[row["shipment_identifier"]][row["product"]] += 1

    # Step 3 – insert one shipment row per (shipment_id, product)
    count = 0
    for shipment_id, products in product_counts.items():
        meta = shipment_meta[shipment_id]
        for product_name, quantity in products.items():
            product_id = get_or_create_product(cursor, product_name)
            insert_shipment(
                cursor,
                product_id,
                quantity,
                meta["origin"],
                meta["destination"],
            )
            count += 1
    return count


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        rows_0 = process_csv0(cursor)
        rows_1_2 = process_csv1_csv2(cursor)

        conn.commit()

    total = rows_0 + rows_1_2
    print(f"Inserted {rows_0:>5} shipment row(s) from shipping_data_0.csv")
    print(f"Inserted {rows_1_2:>5} shipment row(s) from shipping_data_1/2.csv")
    print(f"{'Total':>7}: {total} row(s) committed to {DB_PATH.name}")


if __name__ == "__main__":
    main()
