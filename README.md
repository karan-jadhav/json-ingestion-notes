# JSON Ingestion Notes

Small benchmark comparing Python `json` and `simdjson` for large JSON ingestion.

The point is not to prove one parser is always better.

The point is to show how file shape and processing model affect memory usage.

## Setup

```bash
uv sync
```

## Generate Data

```bash
uv run python make_dataset.py --records 250000 --out data
```

## Run Benchmark

```bash
uv run python bench_json.py all --array data/large_array.json --jsonl data/large_events.jsonl --out results/benchmark.csv
```

Run one parser method:

```bash
uv run python bench_json.py one --method jsonl_stdlib_stream --path data/large_events.jsonl
```
