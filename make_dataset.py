import json
import random
import string
from pathlib import Path
from typing import Annotated

import typer


EVENT_TYPES = [
    "page_view",
    "search",
    "export",
    "upload",
    "integration_sync",
    "ask_ai",
    "feedback",
]


WORDS = [
    "onboarding",
    "export",
    "dashboard",
    "latency",
    "integration",
    "permissions",
    "search",
    "customer",
    "analytics",
    "workspace",
    "sync",
    "document",
    "feedback",
    "research",
    "transcript",
]


def random_text(length: int) -> str:
    result = []

    while len(" ".join(result)) < length:
        result.append(random.choice(WORDS))

    return " ".join(result)[:length]


def make_event(i: int) -> dict:
    return {
        "id": i,
        "org_id": random.randint(1, 500),
        "user_id": random.randint(1, 50_000),
        "event_type": random.choice(EVENT_TYPES),
        "created_at": f"2026-06-{random.randint(1, 28):02d}T12:{random.randint(0, 59):02d}:00Z",
        "metadata": {
            "request_id": "".join(random.choices(string.ascii_lowercase + string.digits, k=16)),
            "source": random.choice(["api", "webhook", "batch", "worker"]),
            "region": random.choice(["ap-south-1", "us-east-1", "eu-west-1"]),
        },
        "payload": {
            "title": f"event-{i}",
            "message": random_text(180),
            "score": round(random.random(), 4),
        },
    }


def write_json_array(path: Path, records: int) -> None:
    with path.open("w", encoding="utf-8") as f:
        f.write("[\n")

        for i in range(records):
            if i > 0:
                f.write(",\n")

            json.dump(make_event(i), f, separators=(",", ":"))

        f.write("\n]")


def write_jsonl(path: Path, records: int) -> None:
    with path.open("w", encoding="utf-8") as f:
        for i in range(records):
            f.write(json.dumps(make_event(i), separators=(",", ":")))
            f.write("\n")


def human_size(path: Path) -> str:
    size = path.stat().st_size
    value = float(size)

    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024

    return f"{value:.2f} PB"


def main(
    records: Annotated[
        int,
        typer.Option(help="Number of synthetic records to generate."),
    ] = 250_000,
    out: Annotated[
        Path,
        typer.Option(help="Output directory for generated files."),
    ] = Path("data"),
) -> None:
    out_dir = out
    out_dir.mkdir(parents=True, exist_ok=True)

    array_path = out_dir / "large_array.json"
    jsonl_path = out_dir / "large_events.jsonl"

    print(f"Generating {records:,} records...")

    write_json_array(array_path, records)
    write_jsonl(jsonl_path, records)

    print()
    print("Generated files:")
    print(f"{array_path}: {human_size(array_path)}")
    print(f"{jsonl_path}: {human_size(jsonl_path)}")


if __name__ == "__main__":
    typer.run(main)
