"""Deterministically generate the canonical dirty benchmark dataset."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import duckdb

HEADER = "customer_id,name,email,amount,signup_date,city,notes\n"
CITIES = ["kuala lumpur", "KUALA LUMPUR", "penang", "johor bahru", "ipoh"]
NULL_TOKENS = ["N/A", "null", "-", ""]
FIRST_NAMES = ["Aisha", "Ben", "Chen", "Devi", "Emil", "Farah", "Gopal", "Hana"]
LAST_NAMES = ["Tan", "Lim", "Kumar", "Wong", "Ali", "Ng", "Singh", "Lee"]


def make_row(rng: random.Random, index: int) -> str:
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    name = f"{first} {last}"
    roll = rng.random()
    if roll < 0.1:
        name = f" {name} "
    elif roll < 0.2:
        name = name.upper()
    email = f"{first.lower()}.{last.lower()}{index % 977}@example.com"
    if rng.random() < 0.02:
        email = "not-an-email"
    amount_value = rng.uniform(1, 99_999)
    amount_roll = rng.random()
    if amount_roll < 0.2:
        # Quote: thousands separators contain the CSV delimiter.
        amount = f'"RM {amount_value:,.2f}"'
    elif amount_roll < 0.25:
        amount = rng.choice(NULL_TOKENS)
    else:
        amount = f"{amount_value:.2f}"
    year = rng.randint(2020, 2026)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    if rng.random() < 0.3:
        signup = f"{day}/{month}/{year}"
    else:
        signup = f"{year}-{month:02d}-{day:02d}"
    city = "langkawi" if index % 100_003 == 0 else rng.choice(CITIES)
    notes = rng.choice(NULL_TOKENS) if rng.random() < 0.5 else "ok"
    return f"c{index:09d},{name},{email},{amount},{signup},{city},{notes}\n"


def generate(target_bytes: int, seed: int, destination: Path) -> int:
    rng = random.Random(seed)
    written = 0
    index = 0
    with destination.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(HEADER)
        written += len(HEADER)
        pending_duplicate: str | None = None
        while written < target_bytes:
            if pending_duplicate is not None:
                row = pending_duplicate
                pending_duplicate = None
            else:
                index += 1
                row = make_row(rng, index)
                # Exact duplicates and blocked fuzzy candidates.
                if rng.random() < 0.01:
                    pending_duplicate = row
            stream.write(row)
            written += len(row)
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size-gb", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=20260715)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).parent / "generated"
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = args.output_dir / "canonical.csv"
    parquet_path = args.output_dir / "canonical.parquet"
    target_bytes = int(args.size_gb * 1024**3)

    rows = generate(target_bytes, args.seed, csv_path)
    connection = duckdb.connect()
    # COPY cannot bind parameters; escape the paths as literals instead.
    csv_literal = str(csv_path).replace("'", "''")
    parquet_literal = str(parquet_path).replace("'", "''")
    connection.execute(
        f"COPY (SELECT * FROM read_csv('{csv_literal}', all_varchar=true))"
        f" TO '{parquet_literal}' (FORMAT PARQUET)"
    )
    print(
        f"generated {rows} unique rows: {csv_path}"
        f" ({csv_path.stat().st_size} bytes) and {parquet_path}"
        f" ({parquet_path.stat().st_size} bytes)"
    )


if __name__ == "__main__":
    main()
