from __future__ import annotations

import argparse
import csv
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "data" / "衢州杭氧1#42000数据.csv"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "nitrogen_demo.db"
TIME_FORMAT = "%d-%b-%y %H:%M:%S"


def normalize_column_name(index: int, raw: str) -> str:
    name = (raw or "").strip()
    if index == 0 or not name:
        return "time_text"
    safe = []
    for char in name:
        if char.isalnum() or char == "_":
            safe.append(char)
        else:
            safe.append("_")
    result = "".join(safe).strip("_")
    return result or f"col_{index}"


def parse_time_ms(value: str) -> int | None:
    try:
        dt = datetime.strptime((value or "").strip(), TIME_FORMAT)
    except ValueError:
        return None
    return int(dt.timestamp() * 1000)


def to_float_or_none(value: str) -> float | None:
    try:
        text = str(value or "").replace("%", "").strip()
        if not text:
            return None
        return float(text)
    except ValueError:
        return None


def build_database(source: Path, output: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        headers = next(reader)
        display_names = next(reader, [""] * len(headers))
        columns = [normalize_column_name(index, header) for index, header in enumerate(headers)]

        # Keep column names unique after normalization.
        seen: dict[str, int] = {}
        unique_columns = []
        for column in columns:
            count = seen.get(column, 0)
            seen[column] = count + 1
            unique_columns.append(column if count == 0 else f"{column}_{count + 1}")

        data_columns = unique_columns[1:]

        conn = sqlite3.connect(output)
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("DROP TABLE IF EXISTS samples")
            conn.execute("DROP TABLE IF EXISTS column_meta")
            column_defs = ["time_ms INTEGER NOT NULL", "time_text TEXT NOT NULL"]
            column_defs.extend(f'"{column}" REAL' for column in data_columns)
            conn.execute(f"CREATE TABLE samples ({', '.join(column_defs)})")
            conn.execute("CREATE INDEX idx_samples_time_ms ON samples(time_ms)")
            conn.execute(
                "CREATE TABLE column_meta (column_name TEXT PRIMARY KEY, source_name TEXT, display_name TEXT)"
            )
            conn.executemany(
                "INSERT INTO column_meta (column_name, source_name, display_name) VALUES (?, ?, ?)",
                [
                    (unique_columns[index], headers[index] if index < len(headers) else "", display_names[index] if index < len(display_names) else "")
                    for index in range(len(unique_columns))
                ],
            )

            placeholders = ", ".join("?" for _ in range(2 + len(data_columns)))
            insert_sql = f"INSERT INTO samples (time_ms, time_text, {', '.join(f'\"{c}\"' for c in data_columns)}) VALUES ({placeholders})"
            batch = []
            total = 0
            for row in reader:
                if not row:
                    continue
                time_text = row[0] if row else ""
                time_ms = parse_time_ms(time_text)
                if time_ms is None:
                    continue
                values = [to_float_or_none(row[index]) if index < len(row) else None for index in range(1, len(unique_columns))]
                batch.append([time_ms, time_text, *values])
                if len(batch) >= 5000:
                    conn.executemany(insert_sql, batch)
                    total += len(batch)
                    batch.clear()
            if batch:
                conn.executemany(insert_sql, batch)
                total += len(batch)
            conn.commit()
            conn.execute("VACUUM")
            print(f"Built {output} with {total} rows and {len(data_columns)} measurement columns.")
        finally:
            conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SQLite database for nitrogen plug demo.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build_database(args.source, args.output)


if __name__ == "__main__":
    main()
