#!/usr/bin/env python3
"""
Apache Tika parsing harness for OCB reference documents.

Extracts structure-preserving plain text from the file types the benchmark
references (``.docx``, ``.xlsx``, ``.xlsm``, ``.pptx``, ``.csv``) so that
models without native file-attachment support (open-source / self-hosted
models) can be benchmarked on OCB.

Extraction goes through a Tika Server REST endpoint (``PUT /rmeta/xml``),
which returns both document metadata and the XHTML rendering of the
document in a single call. The XHTML is then flattened to text that keeps
the structure the benchmark actually asks about:

* ``.xlsx`` / ``.xlsm`` — one section per worksheet, rows rendered as
  pipe-delimited cells instead of being collapsed into a whitespace blob.
* ``.pptx`` — one section per slide, with speaker notes and master
  content labelled separately.
* ``.docx`` — headings, paragraphs, list items and tables preserved.
* ``.csv`` — parsed by Tika's CSV parser, which auto-detects the delimiter
  and character encoding; the first row is the column header.

OCB's CSV corpus is very large (tens to hundreds of MB per file), so every
request carries a Tika ``writeLimit`` header derived from the character
budget. Tika then stops parsing once the limit is reached instead of
materializing a multi-GB response for text that would be truncated anyway.

Usage as a module::

    from tika_parser import TikaParser

    with TikaParser() as parser:
        doc = parser.parse("reference_files/report.xlsx")
        print(doc.text)

Usage from the command line (smoke test / cache warm-up)::

    python tika_parser.py reference_files/report.xlsx
    python tika_parser.py --check
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:  # pragma: no cover - dotenv is optional
    pass


DEFAULT_TIKA_SERVER_URL = "http://localhost:9998"

SUPPORTED_EXTENSIONS = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    # Sent without a charset so Tika auto-detects the encoding and delimiter.
    ".csv": "text/csv",
}

TABULAR_EXTENSIONS = {".csv"}

# Tika counts writeLimit in extracted text characters, while the character
# budget is applied after markup flattening and after boilerplate removal.
# Ask Tika for more than the budget so truncation is driven by the budget.
WRITE_LIMIT_HEADROOM = 2

# Metadata key Tika sets when parsing stopped because of the write limit.
WRITE_LIMIT_KEY = "X-TIKA:EXCEPTION:write_limit_reached"

# Tika emits <div class="..."> wrappers that carry the structural meaning we
# care about for presentations and spreadsheets.
_SECTION_LABELS = {
    "slide-content": "Slide",
    "slide-master-content": "Slide master",
    "slide-notes": "Speaker notes",
    "slideShow-comment": "Comment",
    "page": "Sheet",
    "outline": "Outline",
    "header": "Header",
    "footer": "Footer",
    "endnotes": "Endnotes",
    "footnotes": "Footnotes",
    "annotation": "Annotation",
    "embedded": "Embedded object",
}

# Tika repeats the slide master (template boilerplate) for every single slide,
# which is pure noise for benchmarking and burns context. Dropped by default.
_DEFAULT_SKIP_CLASSES = frozenset({"slide-master-content"})

_METADATA_KEYS_OF_INTEREST = (
    "dc:title",
    "meta:author",
    "dc:creator",
    "Content-Type",
    "csv:delimiter",
    "xmpTPg:NPages",
    "meta:page-count",
    "meta:slide-count",
    "meta:word-count",
    "Application-Name",
)


class TikaError(RuntimeError):
    """Raised when Tika is unreachable or fails to parse a document."""


@dataclass
class ParsedDocument:
    """Result of parsing a single Office document with Tika."""

    filename: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    char_count: int = 0
    truncated: bool = False
    from_cache: bool = False

    def as_prompt_block(self) -> str:
        """Render the document as a labelled block for an LLM prompt."""
        header = f"===== BEGIN DOCUMENT: {self.filename} ====="
        footer = f"===== END DOCUMENT: {self.filename} ====="
        meta_lines = [f"{k}: {v}" for k, v in self.metadata.items() if v]
        if Path(self.filename).suffix.lower() in TABULAR_EXTENSIONS:
            meta_lines.append(
                "Format: delimited table; the first row below is the column header."
            )
        meta_block = ("\n".join(meta_lines) + "\n\n") if meta_lines else ""
        note = (
            "\n\n[NOTE: this document was too large to include in full; the text "
            "above is the beginning of the document and the remainder was "
            "omitted.]"
            if self.truncated
            else ""
        )
        return f"{header}\n{meta_block}{self.text}{note}\n{footer}"


class _XhtmlToTextParser(HTMLParser):
    """Flatten Tika XHTML into structure-preserving plain text.

    Tables become pipe-delimited rows, headings get ``#`` prefixes, and the
    ``<div class="...">`` wrappers Tika uses for slides / worksheets become
    labelled section markers.
    """

    _BLOCK_TAGS = {"p", "li", "div", "h1", "h2", "h3", "h4", "h5", "h6", "br"}

    def __init__(self, skip_classes: Optional[frozenset] = None) -> None:
        super().__init__(convert_charrefs=True)
        self._out: List[str] = []
        self._buffer: List[str] = []
        self._table_depth = 0
        self._row_cells: List[str] = []
        self._heading_level = 0
        self._section_counts: Dict[str, int] = {}
        self._skip_depth = 0
        self._skip_classes = (
            _DEFAULT_SKIP_CLASSES if skip_classes is None else skip_classes
        )
        self._div_depth = 0
        self._skip_div_depth: Optional[int] = None
        self._suppress_until_div = False
        self._pending_marker: Optional[str] = None

    # -- helpers ---------------------------------------------------------
    def _flush(self, prefix: str = "") -> None:
        text = "".join(self._buffer).strip()
        self._buffer.clear()
        if text:
            self._emit(f"{prefix}{text}" if prefix else text)

    def _emit(self, line: str) -> None:
        # Section markers are held back until the section actually produces
        # content, so empty slides / embedded objects do not emit headers.
        if self._pending_marker is not None and line.strip():
            marker, self._pending_marker = self._pending_marker, None
            self._out.append("")
            self._out.append(marker)
        self._out.append(line)

    # -- HTMLParser API --------------------------------------------------
    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        if self._skip_div_depth is not None:
            if tag == "div":
                self._div_depth += 1
            return
        if self._skip_depth:
            if tag in ("script", "style"):
                self._skip_depth += 1
            return
        if tag in ("script", "style", "head"):
            self._skip_depth = 1
            return

        attr_map = {k: (v or "") for k, v in attrs}

        if tag == "table":
            self._flush()
            self._table_depth += 1
            self._emit("")
            return
        if tag == "tr":
            self._row_cells = []
            return
        if tag in ("td", "th"):
            self._buffer.clear()
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self._heading_level = int(tag[1])
            return
        if tag == "div":
            self._flush()
            self._suppress_until_div = False
            self._div_depth += 1
            css_class = attr_map.get("class", "").strip()
            if css_class in self._skip_classes:
                # Still count the section so numbering matches the source file.
                self._section_counts[css_class] = (
                    self._section_counts.get(css_class, 0) + 1
                )
                self._skip_div_depth = self._div_depth
                return
            label = _SECTION_LABELS.get(css_class)
            if label:
                count = self._section_counts.get(css_class, 0) + 1
                self._section_counts[css_class] = count
                self._pending_marker = f"--- {label} {count} ---"
            return
        if tag in self._BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if self._skip_div_depth is not None:
            if tag == "div":
                if self._div_depth <= self._skip_div_depth:
                    self._skip_div_depth = None
                    # Tika trails each slide master with body-level <p> blocks
                    # holding the rest of the template text; drop those too.
                    self._suppress_until_div = True
                self._div_depth = max(0, self._div_depth - 1)
            return
        if self._skip_depth:
            if tag in ("script", "style", "head"):
                self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "div":
            self._div_depth = max(0, self._div_depth - 1)

        if tag in ("td", "th"):
            cell = " ".join("".join(self._buffer).split())
            self._buffer.clear()
            self._row_cells.append(cell)
            return
        if tag == "tr":
            if any(cell for cell in self._row_cells):
                self._emit("| " + " | ".join(self._row_cells) + " |")
            self._row_cells = []
            return
        if tag == "table":
            self._table_depth = max(0, self._table_depth - 1)
            self._emit("")
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = self._heading_level or 1
            self._heading_level = 0
            self._flush(prefix="#" * level + " ")
            return
        if tag in self._BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth or self._skip_div_depth is not None or self._suppress_until_div:
            return
        self._buffer.append(data)

    def close(self) -> None:  # type: ignore[override]
        super().close()
        # A write-limited response is cut mid-markup, so the final row never
        # sees its closing tags. Recover whatever cells were accumulated.
        if self._buffer and (self._row_cells or self._table_depth):
            cell = " ".join("".join(self._buffer).split())
            self._buffer.clear()
            if cell:
                self._row_cells.append(cell)
        if self._row_cells:
            if any(cell for cell in self._row_cells):
                self._emit("| " + " | ".join(self._row_cells) + " |")
            self._row_cells = []
        self._flush()

    def get_text(self) -> str:
        lines: List[str] = []
        blank_run = 0
        for raw in self._out:
            line = raw.rstrip()
            if not line.strip():
                blank_run += 1
                if blank_run > 1 or not lines:
                    continue
                lines.append("")
                continue
            blank_run = 0
            lines.append(line)
        while lines and not lines[-1]:
            lines.pop()
        return "\n".join(lines)


def xhtml_to_text(xhtml: str, include_slide_masters: bool = False) -> str:
    """Convert a Tika XHTML payload to structure-preserving plain text.

    Args:
        xhtml: The XHTML string returned by Tika.
        include_slide_masters: Keep the per-slide master/template boilerplate
            that Tika repeats for every slide. Off by default.
    """
    skip = frozenset() if include_slide_masters else _DEFAULT_SKIP_CLASSES
    parser = _XhtmlToTextParser(skip_classes=skip)
    parser.feed(xhtml)
    parser.close()
    return parser.get_text()


class TikaParser:
    """Client for extracting Office document text via Apache Tika Server.

    Args:
        server_url: Base URL of a running Tika Server. Defaults to
            ``TIKA_SERVER_URL`` or ``http://localhost:9998``.
        jar_path: Optional path to ``tika-server-standard-*.jar``. When set
            (or via ``TIKA_SERVER_JAR``) and the server is not already
            reachable, a local server is launched and stopped on close.
        cache_dir: Directory for cached extractions. ``None`` disables the
            cache.
        max_chars: Truncate extracted text to this many characters.
            ``None`` or ``0`` disables truncation.
        timeout: Per-request timeout in seconds.
        include_metadata: Prepend selected document metadata to the output.
        include_slide_masters: Keep the per-slide master/template boilerplate
            Tika repeats for every slide (off by default — it is duplicated
            noise that consumes context).
        write_limit: Max characters Tika should extract before it stops
            parsing. Defaults to ``max_chars * WRITE_LIMIT_HEADROOM``, which
            keeps huge inputs (OCB ships CSVs up to 400+ MB) bounded in time
            and memory. ``0`` disables the limit.
    """

    def __init__(
        self,
        server_url: Optional[str] = None,
        jar_path: Optional[str] = None,
        cache_dir: Optional[str] = ".tika_cache",
        max_chars: Optional[int] = None,
        timeout: float = 300.0,
        include_metadata: bool = True,
        include_slide_masters: bool = False,
        write_limit: Optional[int] = None,
    ) -> None:
        self.server_url = (
            server_url or os.environ.get("TIKA_SERVER_URL") or DEFAULT_TIKA_SERVER_URL
        ).rstrip("/")
        self.jar_path = jar_path or os.environ.get("TIKA_SERVER_JAR")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.max_chars = max_chars or None
        self.timeout = timeout
        self.include_metadata = include_metadata
        self.include_slide_masters = include_slide_masters
        if write_limit is None:
            self.write_limit = (
                self.max_chars * WRITE_LIMIT_HEADROOM if self.max_chars else None
            )
        else:
            self.write_limit = write_limit or None

        self._session = requests.Session()
        self._process: Optional[subprocess.Popen] = None

        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -- lifecycle -------------------------------------------------------
    def __enter__(self) -> "TikaParser":
        self.ensure_server()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """Stop a locally launched Tika Server and release the session."""
        if self._process is not None:
            proc, self._process = self._process, None
            try:
                proc.terminate()
                proc.wait(timeout=15)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        self._session.close()

    # -- server management ----------------------------------------------
    def is_server_up(self) -> bool:
        try:
            resp = self._session.get(f"{self.server_url}/version", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def ensure_server(self) -> None:
        """Verify the Tika Server is reachable, launching it if configured."""
        if self.is_server_up():
            return

        if self.jar_path:
            self._launch_server()
            return

        raise TikaError(
            f"Tika Server is not reachable at {self.server_url}.\n"
            "Start one of the following, then re-run:\n"
            "  * Docker:  docker run -d -p 9998:9998 apache/tika:latest-full\n"
            "  * Jar:     java -jar tika-server-standard-<version>.jar --host=0.0.0.0\n"
            "Alternatively set TIKA_SERVER_JAR (or pass --tika-jar) to have this\n"
            "harness launch the server for you, or set TIKA_SERVER_URL to point at\n"
            "an existing server."
        )

    def _launch_server(self) -> None:
        jar = Path(self.jar_path or "")
        if not jar.is_file():
            raise TikaError(f"Tika Server jar not found: {jar}")
        if shutil.which("java") is None:
            raise TikaError(
                "Java runtime not found on PATH; it is required to launch the Tika "
                "Server jar. Install a JRE (17+) or point TIKA_SERVER_URL at a "
                "running server."
            )

        port = 9998
        if ":" in self.server_url.split("//", 1)[-1]:
            try:
                port = int(self.server_url.rsplit(":", 1)[1])
            except ValueError:
                port = 9998

        print(f"Launching Tika Server from {jar} on port {port}...")
        self._process = subprocess.Popen(
            ["java", "-jar", str(jar), "--host=127.0.0.1", f"--port={port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        atexit.register(self.close)

        deadline = time.time() + 90
        while time.time() < deadline:
            if self._process.poll() is not None:
                raise TikaError(
                    "Tika Server process exited during startup "
                    f"(exit code {self._process.returncode})."
                )
            if self.is_server_up():
                print(f"Tika Server ready at {self.server_url}")
                return
            time.sleep(1.0)

        raise TikaError(f"Tika Server did not become ready at {self.server_url} in time.")

    # -- caching ---------------------------------------------------------
    def _cache_path(self, path: Path) -> Optional[Path]:
        if not self.cache_dir:
            return None
        # The write limit changes how much content Tika returns, so it is part
        # of the cache identity.
        version = f"v2|wl={self.write_limit or 0}"
        try:
            stat = path.stat()
            signature = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{version}"
        except OSError:
            signature = f"{path.resolve()}|{version}"
        digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()[:32]
        return self.cache_dir / f"{path.stem}.{digest}.json"

    # -- parsing ---------------------------------------------------------
    def parse(self, file_path: str | Path) -> ParsedDocument:
        """Parse a single ``.docx`` / ``.xlsx`` / ``.pptx`` file."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Document not found: {path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise TikaError(
                f"Unsupported file type '{ext}' for {path.name}. "
                f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
            )
        cache_path = self._cache_path(path)
        if cache_path and cache_path.is_file():
            try:
                cached = json.loads(cache_path.read_text(encoding="utf-8"))
                text = xhtml_to_text(cached["xhtml"], self.include_slide_masters)
                return self._finalize(
                    path.name,
                    text,
                    cached.get("metadata", {}),
                    from_cache=True,
                    write_limit_hit=bool(cached.get("write_limit_hit")),
                )
            except (json.JSONDecodeError, KeyError, OSError):
                pass  # corrupt cache entry -> re-parse

        self.ensure_server()
        xhtml, metadata, write_limit_hit = self._request_rmeta(path, ext)
        text = xhtml_to_text(xhtml, self.include_slide_masters)

        if cache_path:
            try:
                cache_path.write_text(
                    json.dumps(
                        {
                            "xhtml": xhtml,
                            "metadata": metadata,
                            "write_limit_hit": write_limit_hit,
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except OSError:
                pass  # cache is best-effort

        return self._finalize(
            path.name, text, metadata, write_limit_hit=write_limit_hit
        )

    def _request_rmeta(self, path: Path, ext: str) -> tuple[str, Dict[str, Any], bool]:
        url = f"{self.server_url}/rmeta/xml"
        headers = {
            "Accept": "application/json",
            "Content-Type": SUPPORTED_EXTENSIONS[ext],
            "X-Tika-OCRskipOcr": "true",
        }
        if self.write_limit:
            # Verified against Tika Server 2.9.2: honoured as a header on
            # /rmeta (the ?writeLimit query parameter is ignored there).
            headers["writeLimit"] = str(self.write_limit)
        try:
            with path.open("rb") as fh:
                resp = self._session.put(url, headers=headers, data=fh, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TikaError(f"Tika request failed for {path.name}: {exc}") from exc

        if resp.status_code != 200:
            raise TikaError(
                f"Tika returned HTTP {resp.status_code} for {path.name}: "
                f"{resp.text[:300]}"
            )

        try:
            payload = resp.json()
        except ValueError as exc:
            raise TikaError(f"Tika returned a non-JSON response for {path.name}") from exc

        if not isinstance(payload, list) or not payload:
            raise TikaError(f"Tika returned no content for {path.name}")

        # payload[0] is the container document; later entries are embedded
        # resources (charts, embedded workbooks, ...). Concatenate them all so
        # embedded-object questions are answerable.
        parts: List[str] = []
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            content = entry.get("X-TIKA:content")
            if content and content.strip():
                parts.append(content)

        if not parts:
            raise TikaError(f"Tika extracted no text from {path.name}")

        container = payload[0] if isinstance(payload[0], dict) else {}
        write_limit_hit = any(
            isinstance(entry, dict) and WRITE_LIMIT_KEY in entry for entry in payload
        )
        metadata: Dict[str, Any] = {}
        if self.include_metadata:
            for key in _METADATA_KEYS_OF_INTEREST:
                value = container.get(key)
                if isinstance(value, list):
                    value = "; ".join(str(v) for v in value)
                if value:
                    metadata[key] = value

        return "\n".join(parts), metadata, write_limit_hit

    def _finalize(
        self,
        filename: str,
        text: str,
        metadata: Dict[str, Any],
        from_cache: bool = False,
        write_limit_hit: bool = False,
    ) -> ParsedDocument:
        truncated = write_limit_hit
        if self.max_chars and len(text) > self.max_chars:
            cut = text[: self.max_chars]
            # Prefer a line boundary so table rows are not sliced mid-row.
            newline = cut.rfind("\n")
            if newline > self.max_chars // 2:
                cut = cut[:newline]
            omitted = len(text) - len(cut)
            text = f"{cut}\n[... {omitted:,} characters omitted ...]"
            truncated = True
        elif write_limit_hit:
            text = f"{text}\n[... remainder of the document omitted ...]"
        return ParsedDocument(
            filename=filename,
            text=text,
            metadata=metadata if self.include_metadata else {},
            char_count=len(text),
            truncated=truncated,
            from_cache=from_cache,
        )

    def parse_many(self, file_paths: List[str | Path]) -> List[ParsedDocument]:
        """Parse several documents, preserving input order."""
        return [self.parse(p) for p in file_paths]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract text from Office/CSV documents with Apache Tika."
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Paths to .docx / .xlsx / .xlsm / .pptx / .csv files.",
    )
    parser.add_argument(
        "--tika-url",
        default=None,
        help=f"Tika Server base URL (default: $TIKA_SERVER_URL or {DEFAULT_TIKA_SERVER_URL}).",
    )
    parser.add_argument(
        "--tika-jar",
        default=None,
        help="Path to tika-server-standard-*.jar; launched if the server is not up.",
    )
    parser.add_argument(
        "--cache-dir",
        default=".tika_cache",
        help="Extraction cache directory (default: .tika_cache).",
    )
    parser.add_argument("--no-cache", action="store_true", help="Disable the extraction cache.")
    parser.add_argument(
        "--max-chars", type=int, default=0, help="Truncate extracted text to N characters."
    )
    parser.add_argument(
        "--write-limit",
        type=int,
        default=None,
        help=(
            "Max characters Tika extracts before it stops parsing "
            "(default: --max-chars x2; 0 disables). Keeps very large CSVs bounded."
        ),
    )
    parser.add_argument(
        "--include-slide-masters",
        action="store_true",
        help="Keep per-slide master/template boilerplate (dropped by default).",
    )
    parser.add_argument(
        "--check", action="store_true", help="Only verify that the Tika Server is reachable."
    )
    args = parser.parse_args()

    tika = TikaParser(
        server_url=args.tika_url,
        jar_path=args.tika_jar,
        cache_dir=None if args.no_cache else args.cache_dir,
        max_chars=args.max_chars,
        include_slide_masters=args.include_slide_masters,
        write_limit=args.write_limit,
    )

    try:
        if args.check:
            tika.ensure_server()
            version = tika._session.get(f"{tika.server_url}/version", timeout=5).text.strip()
            print(f"Tika Server OK at {tika.server_url} (version: {version})")
            return 0

        if not args.files:
            parser.error("provide at least one file path, or use --check")

        for file_path in args.files:
            doc = tika.parse(file_path)
            source = "cache" if doc.from_cache else "tika"
            print(f"\n{'=' * 70}")
            print(f"{doc.filename}  [{doc.char_count} chars, via {source}]")
            print(f"{'=' * 70}")
            print(doc.text)
        return 0
    except (TikaError, FileNotFoundError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        tika.close()


if __name__ == "__main__":
    sys.exit(main())
