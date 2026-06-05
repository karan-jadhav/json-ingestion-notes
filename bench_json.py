import csv
import gc
import json
import os
import subprocess
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Annotated, Any, Callable, cast

import psutil
import simdjson
import typer


app = typer.Typer()

JsonEvent = dict[str, Any]
BenchmarkMethod = Callable[[Path], tuple[int, int]]


class MethodName(str, Enum):
    json_load_array = "json_load_array"
    simdjson_load_array = "simdjson_load_array"
    jsonl_stdlib_stream = "jsonl_stdlib_stream"
    jsonl_simdjson_stream = "jsonl_simdjson_stream"


def bytes_to_mb(value: int) -> float:
    return value / 1024 / 1024


class MemorySampler:
    def __init__(self, interval: float = 0.01) -> None:
        self.interval = interval
        self.process = psutil.Process(os.getpid())
        self.peak_rss = 0
        self.running = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while self.running:
            rss = self.process.memory_info().rss
            self.peak_rss = max(self.peak_rss, rss)
            time.sleep(self.interval)

    def __enter__(self):
        self.running = True
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.running = False
        self.thread.join()


def summarize_event(event: JsonEvent) -> tuple[int, int]:
    """
    Small amount of business logic so the benchmark is not only parsing.

    Returns:
    - number of records processed
    - number of ask_ai events
    """
    return 1, 1 if event.get("event_type") == "ask_ai" else 0


def method_json_load_array(path: Path) -> tuple[int, int]:
    with path.open("r", encoding="utf-8") as f:
        records = cast(list[JsonEvent], json.load(f))

    total = 0
    ask_ai_count = 0

    for record in records:
        count, ask_ai = summarize_event(record)
        total += count
        ask_ai_count += ask_ai

    return total, ask_ai_count


def method_simdjson_load_array(path: Path) -> tuple[int, int]:
    parser = simdjson.Parser()

    with path.open("rb") as f:
        data = f.read()

    records = cast(list[JsonEvent], parser.parse(data, recursive=True))

    total = 0
    ask_ai_count = 0

    for record in records:
        count, ask_ai = summarize_event(record)
        total += count
        ask_ai_count += ask_ai

    return total, ask_ai_count


def method_jsonl_stdlib_stream(path: Path) -> tuple[int, int]:
    total = 0
    ask_ai_count = 0

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            record = cast(JsonEvent, json.loads(line))
            count, ask_ai = summarize_event(record)
            total += count
            ask_ai_count += ask_ai

    return total, ask_ai_count


def method_jsonl_simdjson_stream(path: Path) -> tuple[int, int]:
    total = 0
    ask_ai_count = 0

    parser = simdjson.Parser()

    with path.open("rb") as f:
        for line in f:
            record = cast(JsonEvent, parser.parse(line, recursive=True))
            count, ask_ai = summarize_event(record)
            total += count
            ask_ai_count += ask_ai

    return total, ask_ai_count


METHODS: dict[str, BenchmarkMethod] = {
    "json_load_array": method_json_load_array,
    "simdjson_load_array": method_simdjson_load_array,
    "jsonl_stdlib_stream": method_jsonl_stdlib_stream,
    "jsonl_simdjson_stream": method_jsonl_simdjson_stream,
}


def run_one(method_name: MethodName, path: Path) -> None:
    gc.collect()

    method = METHODS[method_name.value]

    start = time.perf_counter()

    with MemorySampler() as mem:
        total, ask_ai_count = method(path)

    elapsed = time.perf_counter() - start

    result = {
        "method": method_name.value,
        "file": str(path),
        "records": total,
        "ask_ai_events": ask_ai_count,
        "time_seconds": round(elapsed, 3),
        "records_per_second": int(total / elapsed) if elapsed > 0 else 0,
        "peak_rss_mb": round(bytes_to_mb(mem.peak_rss), 2),
    }

    print(json.dumps(result))


def print_table(results: list[dict]) -> None:
    headers = [
        "method",
        "records",
        "time_seconds",
        "records_per_second",
        "peak_rss_mb",
    ]

    rows = []

    for r in results:
        rows.append([
            r["method"],
            f'{r["records"]:,}',
            r["time_seconds"],
            f'{r["records_per_second"]:,}',
            r["peak_rss_mb"],
        ])

    widths = []

    for index, header in enumerate(headers):
        width = len(header)

        for row in rows:
            width = max(width, len(str(row[index])))

        widths.append(width)

    def fmt_row(values):
        return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(values))

    print(fmt_row(headers))
    print("-+-".join("-" * width for width in widths))

    for row in rows:
        print(fmt_row(row))


def run_all(array_path: Path, jsonl_path: Path, output_csv: Path) -> None:
    commands = [
        (MethodName.json_load_array, array_path),
        (MethodName.simdjson_load_array, array_path),
        (MethodName.jsonl_stdlib_stream, jsonl_path),
        (MethodName.jsonl_simdjson_stream, jsonl_path),
    ]

    results = []

    for method_name, path in commands:
        cmd = [
            sys.executable,
            __file__,
            "one",
            "--method",
            method_name.value,
            "--path",
            str(path),
        ]

        completed = subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )

        result = json.loads(completed.stdout.strip())
        results.append(result)

    print_table(results)

    output_csv.parent.mkdir(parents=True, exist_ok=True)

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "method",
                "records",
                "time_seconds",
                "records_per_second",
                "peak_rss_mb",
                "ask_ai_events",
                "file",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    print()
    print(f"Saved results to: {output_csv}")


@app.command("one")
def one_command(
    method: Annotated[
        MethodName,
        typer.Option(help="Benchmark method to run."),
    ],
    path: Annotated[
        Path,
        typer.Option(help="Input JSON or JSONL file path."),
    ],
) -> None:
    run_one(method, path)


@app.command("all")
def all_command(
    array_path: Annotated[
        Path,
        typer.Option("--array", help="Input JSON array file path."),
    ] = Path("data/large_array.json"),
    jsonl_path: Annotated[
        Path,
        typer.Option("--jsonl", help="Input JSONL file path."),
    ] = Path("data/large_events.jsonl"),
    output_csv: Annotated[
        Path,
        typer.Option("--out", help="CSV output path."),
    ] = Path("results/benchmark.csv"),
) -> None:
    run_all(
        array_path=array_path,
        jsonl_path=jsonl_path,
        output_csv=output_csv,
    )


if __name__ == "__main__":
    app()
