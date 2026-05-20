"""Generate per-track query NDJSON files from the OCB Hugging Face parquet.

Reads ``data/ocb_qna_data.parquet`` from the OCB Hugging Face dataset and
writes one NDJSON file per (track, app_type) bucket under ``Input/Query/``,
matching the format consumed by ``compete_response_processor.py``.

Output schema (one JSON object per line):
    {
        "id":              "<row index>",
        "filepath":        "doc.docx"  |  ["a.docx", "b.docx"],
        "query":           "...",
        "gold":            ["assertion 1", "assertion 2", ...],
        "weights":         [7.5, 2.5, ...],
        "original_format": "docx" | "xlsx" | "pptx" | ...,
        "track":           "Domain" | "FileFidelity",
        "app_type":        "Word"   | "Excel" | "PPT",
        "domain":          "...",
        "feature":         "..."
    }

Bucketing rule (mirrors the existing file naming):
- track == "Domain"        -> OfficeBenchmark_DomainQnA.ndjson
- track == "FileFidelity"  -> OfficeBenchmark_<AppType>QnA_FileFidelity.ndjson
"""
from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
HF_PARQUET_URL = (
    "https://huggingface.co/datasets/microsoft/OfficeComprehensionBenchmark/"
    "resolve/main/data/ocb_qna_data.parquet"
)
DEFAULT_OUTPUT_DIR = ROOT / "Input" / "Query"


def _as_list(value: Any) -> list[Any]:
    """Normalize numpy arrays / tuples / scalars to a plain list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if hasattr(value, "tolist"):  # numpy ndarray, pandas Series
        return list(value.tolist())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return list(value)
    return [value]


def _filepath(value: Any) -> Any:
    """Return a string for single-file rows, otherwise the list."""
    files = _as_list(value)
    if len(files) == 1:
        return files[0]
    return files


_APP_ALIAS = {
    "powerpoint": "PPT",
    "ppt": "PPT",
    "excel": "Excel",
    "word": "Word",
}


def _bucket(track: str, app_type: str) -> str:
    track_n = (track or "").strip()
    app_n = (app_type or "").strip()
    app_key = _APP_ALIAS.get(app_n.lower(), app_n or "Unknown")
    if track_n.lower() == "domain":
        return "OfficeBenchmark_DomainQnA"
    if "file fidelity" in track_n.lower() or track_n.lower().replace("_", "").replace(" ", "") == "filefidelity":
        return f"OfficeBenchmark_{app_key}QnA_FileFidelity"
    # Fallback: collapse whitespace/underscores into CamelCase-ish suffix
    suffix = "".join(part.capitalize() for part in track_n.replace("_", " ").split()) or "Unknown"
    return f"OfficeBenchmark_{app_key}QnA_{suffix}"


def load_qna(parquet_url: str = HF_PARQUET_URL) -> pd.DataFrame:
    logger.info(f"Loading parquet: {parquet_url}")
    df = pd.read_parquet(parquet_url)
    logger.info(f"Loaded {len(df)} rows, columns: {list(df.columns)}")
    return df


def row_to_record(idx: int, row: pd.Series) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": str(idx),
        "filepath": _filepath(row.get("reference_files")),
        "query": row.get("question") or "",
        "gold": _as_list(row.get("expected_assertions")),
    }
    weights = _as_list(row.get("weights"))
    if weights:
        record["weights"] = weights
    for src, dst in (
        ("file_format", "original_format"),
        ("track", "track"),
        ("app_type", "app_type"),
        ("domain", "domain"),
        ("feature", "feature"),
        ("version", "version"),
    ):
        value = row.get(src)
        if value is None or (isinstance(value, float) and pd.isna(value)):
            continue
        if isinstance(value, str) and not value.strip():
            continue
        record[dst] = value
    return record


def write_buckets(df: pd.DataFrame, output_dir: Path, suffix: str) -> dict[str, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    handles: dict[str, Any] = {}
    try:
        for idx, row in df.iterrows():
            bucket = _bucket(row.get("track", ""), row.get("app_type", ""))
            name = f"{bucket}{suffix}.ndjson"
            path = output_dir / name
            if name not in handles:
                handles[name] = path.open("w", encoding="utf-8")
                counts[name] = 0
            record = row_to_record(int(idx), row)
            handles[name].write(json.dumps(record, ensure_ascii=False) + "\n")
            counts[name] += 1
    finally:
        for h in handles.values():
            h.close()
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--parquet", default=HF_PARQUET_URL,
                        help="Parquet URL or local path (default: HF ocb_qna_data.parquet)")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help="Directory to write NDJSON files into (default: Input/Query)")
    parser.add_argument("--suffix", default="",
                        help="Optional suffix to append before .ndjson (e.g. '_0519')")
    args = parser.parse_args()

    df = load_qna(args.parquet)
    counts = write_buckets(df, args.output_dir, args.suffix)

    total = sum(counts.values())
    logger.info(f"Wrote {total} records across {len(counts)} files in {args.output_dir}:")
    for name, n in sorted(counts.items()):
        logger.info(f"  {name}: {n}")


if __name__ == "__main__":
    main()
