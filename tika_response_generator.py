#!/usr/bin/env python3
"""
Tika-based response generation harness for OCB.

Runs an OCB query set against any OpenAI-compatible chat completions
endpoint (vLLM, Ollama, llama.cpp server, TGI, LM Studio, OpenRouter, ...)
by first extracting the referenced ``.docx`` / ``.xlsx`` / ``.xlsm`` /
``.pptx`` / ``.csv`` files to text with Apache Tika. This lets open-source
models that cannot accept native Office file attachments be benchmarked on
OCB.

The output is a scrape NDJSON in exactly the shape
``compete_response_processor.py`` already consumes::

    {"id": "1", "filepath": "doc.pptx", "query": "...", "response": "..."}

Example::

    # 1. start a Tika Server
    docker run -d -p 9998:9998 apache/tika:latest-full

    # 2. generate responses with a local vLLM / Ollama model
    python tika_response_generator.py \
        --input OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson \
        --model qwen2.5-72b-instruct \
        --base-url http://localhost:8000/v1 \
        --max-concurrent 8

    # 3. evaluate with the existing pipeline
    python compete_response_processor.py \
        --input OfficeBenchmark_PPTQnA_FileFidelity_Sample.ndjson \
        --scrape-file Input/Scrape/qwen2.5-72b-instruct_tika.ndjson \
        --evaluate --eval-majority-vote
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tqdm.asyncio import tqdm

from tika_parser import ParsedDocument, TikaError, TikaParser

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:  # pragma: no cover - dotenv is optional
    pass

from openai import AsyncOpenAI


DEFAULT_QUERY_DIR = Path("Input/Query")
DEFAULT_SCRAPE_DIR = Path("Input/Scrape")
DEFAULT_REFERENCE_DIR = Path("reference_files")

SYSTEM_PROMPT = (
    "You are a document comprehension assistant. You are given the full text "
    "of one or more Microsoft Office or CSV documents, extracted with Apache "
    "Tika, followed by a question about them.\n\n"
    "Rules:\n"
    "- Answer strictly from the provided document text. Do not use outside "
    "knowledge and do not guess.\n"
    "- Spreadsheet and CSV rows are rendered as pipe-delimited cells; slides, "
    "worksheets and speaker notes are introduced by '--- <section> N ---' "
    "markers.\n"
    "- Large files may be cut off. If a document is marked as truncated or "
    "shows an 'characters omitted' marker, only the shown portion is "
    "available: do not state totals, averages, counts or 'the maximum' over "
    "the whole file as if you had seen all of it. Say what the visible "
    "portion supports and that the rest was not available.\n"
    "- If the document text does not contain the information (for example a "
    "purely visual detail that extraction dropped, or a column that is "
    "empty), say so explicitly instead of inventing an answer.\n"
    "- Be specific and complete: include the concrete values, labels, names "
    "and numbers the question asks for.\n"
    "- Do not ask clarifying questions."
)


@dataclass
class GenerationRecord:
    """One query resolved against its documents, ready to be answered."""

    id: str
    filepaths: List[str]
    query: str


def normalize_filenames(value: Any) -> List[str]:
    """Normalize a `filepath` cell (string or list) into a list of filenames."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if x and str(x).strip()]
    text = str(value).strip()
    if not text:
        return []
    for sep in (";", "|"):
        if sep in text:
            parts = [p.strip() for p in text.split(sep) if p.strip()]
            if len(parts) > 1:
                return parts
    return [text]


def resolve_query_path(input_arg: str) -> Path:
    """Resolve --input to a query NDJSON path (bare name -> Input/Query/)."""
    candidate = Path(input_arg)
    if candidate.is_file():
        return candidate
    fallback = DEFAULT_QUERY_DIR / candidate.name
    if fallback.is_file():
        return fallback
    raise FileNotFoundError(
        f"Query NDJSON not found: tried '{candidate}' and '{fallback}'."
    )


def load_records(query_path: Path) -> List[GenerationRecord]:
    """Load query records from an OCB query NDJSON."""
    records: List[GenerationRecord] = []
    with query_path.open("r", encoding="utf-8") as fh:
        for line_num, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Warning: line {line_num} JSON parse error: {exc}")
                continue
            query = str(data.get("query") or "").strip()
            filenames = normalize_filenames(data.get("filepath"))
            if not query or not filenames:
                print(f"Warning: line {line_num} missing query or filepath, skipped")
                continue
            record_id = data.get("id")
            record_id = str(record_id).strip() if record_id is not None else str(line_num)
            records.append(GenerationRecord(id=record_id, filepaths=filenames, query=query))
    return records


def resolve_document(reference_dir: Path, filename: str) -> Path:
    """Resolve a reference filename inside reference_dir.

    Only the basename is used, so a malicious or malformed `filepath` value in
    the query set cannot escape the reference directory.
    """
    safe_name = Path(str(filename).replace("\\", "/")).name
    if not safe_name or safe_name in (".", ".."):
        raise FileNotFoundError(f"Invalid reference filename: {filename!r}")
    path = reference_dir / safe_name
    if not path.is_file():
        raise FileNotFoundError(f"Reference document not found: {path}")
    return path


def build_user_prompt(docs: List[ParsedDocument], query: str) -> str:
    """Assemble the document-grounded user message."""
    blocks = "\n\n".join(doc.as_prompt_block() for doc in docs)
    label = "DOCUMENT" if len(docs) == 1 else f"{len(docs)} DOCUMENTS"
    return (
        f"{label} CONTENT:\n\n{blocks}\n\n"
        f"QUESTION:\n{query}\n\n"
        "Answer using only the document content above."
    )


def load_completed_ids(output_path: Path) -> Set[str]:
    """Read already-generated record ids from an existing scrape NDJSON."""
    done: Set[str] = set()
    if not output_path.is_file():
        return done
    with output_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            record_id = data.get("id")
            if record_id is not None:
                done.add(str(record_id))
    return done


class TikaResponseGenerator:
    """Generates OCB responses from Tika-extracted text via an OpenAI-compatible API."""

    def __init__(
        self,
        client: AsyncOpenAI,
        parser: TikaParser,
        model: str,
        reference_dir: Path,
        max_tokens: int,
        temperature: Optional[float],
        retries: int,
        request_timeout: float,
    ) -> None:
        self.client = client
        self.parser = parser
        self.model = model
        self.reference_dir = reference_dir
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.retries = retries
        self.request_timeout = request_timeout
        self._parse_lock = asyncio.Lock()

    async def _parse_documents(self, filenames: List[str]) -> List[ParsedDocument]:
        docs: List[ParsedDocument] = []
        for filename in filenames:
            path = resolve_document(self.reference_dir, filename)
            # Tika calls are blocking; keep them off the event loop.
            doc = await asyncio.to_thread(self.parser.parse, path)
            docs.append(doc)
        return docs

    async def _complete(self, user_prompt: str) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(self.retries + 1):
            try:
                kwargs: Dict[str, Any] = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": self.max_tokens,
                    "timeout": self.request_timeout,
                }
                if self.temperature is not None:
                    kwargs["temperature"] = self.temperature

                response = await self.client.chat.completions.create(**kwargs)
                choices = response.choices or []
                content = (choices[0].message.content or "").strip() if choices else ""
                if content:
                    return content
                last_error = RuntimeError("model returned an empty response")
            except Exception as exc:  # transport / rate-limit / server errors
                last_error = exc
            if attempt < self.retries:
                await asyncio.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"completion failed after {self.retries + 1} attempts: {last_error}")

    async def generate(self, record: GenerationRecord) -> Dict[str, Any]:
        start = time.time()
        try:
            docs = await self._parse_documents(record.filepaths)
            prompt = build_user_prompt(docs, record.query)
            answer = await self._complete(prompt)
            return {
                "ok": True,
                "record": {
                    "id": record.id,
                    "filepath": record.filepaths[0]
                    if len(record.filepaths) == 1
                    else record.filepaths,
                    "query": record.query,
                    "response": answer,
                },
                "processing_time": round(time.time() - start, 2),
            }
        except (FileNotFoundError, TikaError, RuntimeError) as exc:
            return {
                "ok": False,
                "error": {
                    "id": record.id,
                    "filepath": record.filepaths,
                    "query": record.query,
                    "error": f"{type(exc).__name__}: {exc}",
                },
                "processing_time": round(time.time() - start, 2),
            }


async def run(args: argparse.Namespace) -> int:
    query_path = resolve_query_path(args.input)
    reference_dir = Path(args.reference_dir)
    if not reference_dir.is_dir():
        print(
            f"Error: reference directory not found: {reference_dir}\n"
            "Run `python download_and_convert_files.py --output-dir reference_files` first.",
            file=sys.stderr,
        )
        return 1

    records = load_records(query_path)
    if args.limit:
        records = records[: args.limit]
    if not records:
        print(f"Error: no usable records in {query_path}", file=sys.stderr)
        return 1

    safe_model = re.sub(r"[^A-Za-z0-9._-]+", "_", args.model).strip("_") or "model"
    output_path = (
        Path(args.output)
        if args.output
        else DEFAULT_SCRAPE_DIR / f"{safe_model}_tika.ndjson"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    error_path = output_path.with_suffix(".errors.ndjson")

    completed: Set[str] = set()
    if args.resume:
        completed = load_completed_ids(output_path)
        if completed:
            records = [r for r in records if r.id not in completed]
            print(f"Resuming: {len(completed)} record(s) already generated.")
        if not records:
            print("Nothing left to generate.")
            return 0

    api_key = os.environ.get(args.api_key_env) or "not-needed"
    base_url = args.base_url or os.environ.get("OPENAI_BASE_URL")
    if not base_url:
        print(
            "Error: no endpoint configured. Pass --base-url (e.g. "
            "http://localhost:8000/v1) or set OPENAI_BASE_URL.",
            file=sys.stderr,
        )
        return 1

    parser = TikaParser(
        server_url=args.tika_url,
        jar_path=args.tika_jar,
        cache_dir=None if args.no_cache else args.cache_dir,
        max_chars=args.max_doc_chars or None,
        include_slide_masters=args.include_slide_masters,
        write_limit=args.write_limit,
    )

    try:
        parser.ensure_server()
    except TikaError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        parser.close()
        return 1

    client = AsyncOpenAI(base_url=base_url, api_key=api_key, max_retries=0)
    generator = TikaResponseGenerator(
        client=client,
        parser=parser,
        model=args.model,
        reference_dir=reference_dir,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        retries=args.retries,
        request_timeout=args.request_timeout,
    )

    semaphore = asyncio.Semaphore(args.max_concurrent)
    write_lock = asyncio.Lock()
    mode = "a" if (args.resume and output_path.exists()) else "w"
    succeeded = 0
    failed = 0

    print(
        f"Model: {args.model}\nEndpoint: {base_url}\nTika: {parser.server_url}\n"
        f"Queries: {len(records)}  Concurrency: {args.max_concurrent}\n"
        f"Output: {output_path}"
    )

    with output_path.open(mode, encoding="utf-8") as out_fh, error_path.open(
        mode, encoding="utf-8"
    ) as err_fh:

        async def worker(record: GenerationRecord) -> None:
            nonlocal succeeded, failed
            async with semaphore:
                result = await generator.generate(record)
            async with write_lock:
                if result["ok"]:
                    out_fh.write(json.dumps(result["record"], ensure_ascii=False) + "\n")
                    out_fh.flush()
                    succeeded += 1
                else:
                    err_fh.write(json.dumps(result["error"], ensure_ascii=False) + "\n")
                    err_fh.flush()
                    failed += 1

        tasks = [worker(record) for record in records]
        await tqdm.gather(*tasks, desc="Generating responses")

    parser.close()
    await client.close()

    print(f"\nDone. {succeeded} response(s) -> {output_path}")
    if failed:
        print(f"{failed} failure(s) -> {error_path}")
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate OCB responses with an OpenAI-compatible model using "
            "Apache Tika for .docx/.xlsx/.xlsm/.pptx/.csv text extraction."
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Query NDJSON: a path, or a bare filename resolved under Input/Query/.",
    )
    parser.add_argument("--model", required=True, help="Model name as served by the endpoint.")
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible base URL (default: $OPENAI_BASE_URL), e.g. http://localhost:8000/v1.",
    )
    parser.add_argument(
        "--api-key-env",
        default="OPENAI_API_KEY",
        help="Env var holding the API key (default: OPENAI_API_KEY; ignored by most local servers).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output scrape NDJSON (default: Input/Scrape/<model>_tika.ndjson).",
    )
    parser.add_argument(
        "--reference-dir",
        default=str(DEFAULT_REFERENCE_DIR),
        help="Directory holding the reference documents (default: reference_files).",
    )
    parser.add_argument(
        "--tika-url",
        default=None,
        help="Tika Server base URL (default: $TIKA_SERVER_URL or http://localhost:9998).",
    )
    parser.add_argument(
        "--tika-jar",
        default=None,
        help="Path to tika-server-standard-*.jar; launched if no server is reachable.",
    )
    parser.add_argument(
        "--cache-dir", default=".tika_cache", help="Tika extraction cache (default: .tika_cache)."
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable the extraction cache.")
    parser.add_argument(
        "--include-slide-masters",
        action="store_true",
        help="Keep per-slide master/template boilerplate (dropped by default).",
    )
    parser.add_argument(
        "--max-doc-chars",
        type=int,
        default=200000,
        help="Truncate each extracted document to N characters (default: 200000; 0 disables).",
    )
    parser.add_argument(
        "--write-limit",
        type=int,
        default=None,
        help=(
            "Max characters Tika extracts per file before it stops parsing "
            "(default: --max-doc-chars x2; 0 disables). Bounds very large CSVs."
        ),
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048, help="Max completion tokens (default: 2048)."
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Sampling temperature (default: 0.0). Use -1 to omit the parameter entirely.",
    )
    parser.add_argument(
        "--max-concurrent", type=int, default=4, help="Concurrent generations (default: 4)."
    )
    parser.add_argument(
        "--retries", type=int, default=2, help="Retries per query on failure (default: 2)."
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=600.0,
        help="Per-request timeout in seconds (default: 600).",
    )
    parser.add_argument("--limit", type=int, default=0, help="Only process the first N queries.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Append to an existing output file, skipping ids already present.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.temperature is not None and args.temperature < 0:
        args.temperature = None
    try:
        return asyncio.run(run(args))
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
