"""Download (and optionally convert PDF/HTML -> Office) the reference files for OCB.

Reads the OCB source-URL manifest published on Hugging Face
(``ocb_source_urls.parquet``) and downloads each file into the output
directory using the ``filename`` column as the final on-disk name.

If ``conversion_required`` is true:
- PDF sources are converted to ``docx``/``pptx`` via Adobe PDF Services.
- HTML sources are first rendered to PDF with headless Edge/Chrome and then
  converted via Adobe PDF Services. There is **no fallback** for HTML; both
  a Chromium browser and Adobe credentials are required.

Environment (see .env.example):
- PDF_SERVICES_CLIENT_ID
- PDF_SERVICES_CLIENT_SECRET
- HF_TOKEN              (optional: Hugging Face access token for private datasets)
- SEC_USER_AGENT        (required for sec.gov URLs, format: "Name email@example.com")
- CHROMIUM_PATH         (optional: full path to msedge.exe / chrome.exe)
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "reference_files"
HF_PARQUET_URL = (
    "https://huggingface.co/datasets/confanon/OfficeComprehensionBenchmark/"
    "resolve/main/data/ocb_source_urls.parquet"
)
MANIFEST_CACHE = ROOT / "_ocb_source_urls.parquet"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def download_file(url: str, output_path: Path, timeout: int = 60, max_retries: int = 3, is_html_target: bool = False) -> tuple[bool, str | None]:
    """Download `url` to `output_path` with retries. Returns (success, error).

    For Hugging Face URLs, attaches `Authorization: Bearer $HF_TOKEN` if set
    (required for private/gated datasets; public datasets work without it).
    For sec.gov URLs, uses SEC_USER_AGENT (required by EDGAR).
    Set is_html_target=True when the expected response IS HTML (e.g. .htm/.html
    sources) so the HTML-detection guard does not reject the download.
    """
    headers = {"User-Agent": USER_AGENT}
    if "huggingface.co" in url:
        hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_HUB_TOKEN")
        if hf_token:
            headers["Authorization"] = f"Bearer {hf_token}"
    if "sec.gov" in url:
        # SEC EDGAR requires a contact User-Agent or returns 403.
        sec_ua = os.getenv("SEC_USER_AGENT")
        if sec_ua:
            headers["User-Agent"] = sec_ua
        headers.setdefault("Accept-Encoding", "gzip, deflate")
        headers.setdefault("Host", "www.sec.gov")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(max_retries):
        verify = True
        try:
            if attempt:
                logger.info(f"Retry {attempt + 1}/{max_retries}: {url}")
            r = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True, verify=verify)
            r.raise_for_status()
            first_checked = False
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    if not first_checked:
                        head = chunk[:200].lower()
                        if not is_html_target and (b"<html" in head or b"<!doctype" in head):
                            f.close()
                            output_path.unlink(missing_ok=True)
                            return False, "server returned HTML (blocked or forbidden)"
                        first_checked = True
                    f.write(chunk)
            return True, None
        except requests.exceptions.HTTPError as e:
            return False, f"HTTP {e.response.status_code}"
        except requests.exceptions.SSLError:
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                r = requests.get(url, headers=headers, timeout=timeout, stream=True, allow_redirects=True, verify=False)
                r.raise_for_status()
                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True, None
            except Exception as e:
                return False, f"SSL error: {e}"
        except (requests.exceptions.ChunkedEncodingError, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            return False, f"connection error: {type(e).__name__}"
        except requests.exceptions.Timeout:
            return False, f"timeout after {timeout}s"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
    return False, "unknown error"


def is_pdf(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"%PDF"
    except Exception:
        return False


def validate_office_file(path: Path, fmt: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(100)
    except Exception:
        return False
    if any(sig in head for sig in (b"<!DOCTYPE", b"<!doctype", b"<html", b"<HTML")):
        return False
    if fmt in ("docx", "pptx", "xlsx") and not head.startswith(b"PK"):
        return False
    if path.stat().st_size < 1024:
        return False
    return True


def convert_pdf_to_office(pdf_path: Path, output_path: Path, target_format: str) -> tuple[bool, str | None]:
    """Convert PDF to docx/pptx using Adobe PDF Services."""
    try:
        from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
        from adobe.pdfservices.operation.pdf_services import PDFServices
        from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
        from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
        from adobe.pdfservices.operation.io.stream_asset import StreamAsset
        from adobe.pdfservices.operation.pdfjobs.params.export_pdf.export_pdf_params import ExportPDFParams
        from adobe.pdfservices.operation.pdfjobs.params.export_pdf.export_pdf_target_format import ExportPDFTargetFormat
        from adobe.pdfservices.operation.pdfjobs.jobs.export_pdf_job import ExportPDFJob
        from adobe.pdfservices.operation.pdfjobs.result.export_pdf_result import ExportPDFResult
    except ImportError:
        return False, "pdfservices-sdk not installed (pip install pdfservices-sdk)"

    client_id = os.getenv("PDF_SERVICES_CLIENT_ID")
    client_secret = os.getenv("PDF_SERVICES_CLIENT_SECRET")
    if not client_id or not client_secret:
        return False, "PDF_SERVICES_CLIENT_ID / PDF_SERVICES_CLIENT_SECRET not set"

    target_map = {"docx": ExportPDFTargetFormat.DOCX, "pptx": ExportPDFTargetFormat.PPTX}
    if target_format not in target_map:
        return False, f"unsupported target format: {target_format}"

    try:
        credentials = ServicePrincipalCredentials(client_id=client_id, client_secret=client_secret)
        pdf_services = PDFServices(credentials=credentials)
        with open(pdf_path, "rb") as f:
            input_asset = pdf_services.upload(input_stream=f.read(), mime_type=PDFServicesMediaType.PDF)
        params = ExportPDFParams(target_format=target_map[target_format])
        job = ExportPDFJob(input_asset=input_asset, export_pdf_params=params)
        location = pdf_services.submit(job)
        response = pdf_services.get_job_result(location, ExportPDFResult)
        result_asset: CloudAsset = response.get_result().get_asset()
        stream_asset: StreamAsset = pdf_services.get_content(result_asset)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(stream_asset.get_input_stream())
        return True, None
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def _find_chromium() -> str | None:
    """Locate a headless-capable Chromium browser (Edge or Chrome) on Windows."""
    env = os.environ.get("CHROMIUM_PATH")
    if env and Path(env).exists():
        return env
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        rf"{os.environ.get('ProgramFiles', '')}\Microsoft\Edge\Application\msedge.exe",
        rf"{os.environ.get('ProgramFiles(x86)', '')}\Microsoft\Edge\Application\msedge.exe",
        rf"{os.environ.get('ProgramFiles', '')}\Google\Chrome\Application\chrome.exe",
        rf"{os.environ.get('ProgramFiles(x86)', '')}\Google\Chrome\Application\chrome.exe",
        rf"{os.environ.get('LOCALAPPDATA', '')}\Google\Chrome\Application\chrome.exe",
    ]
    for c in candidates:
        if c and Path(c).exists():
            return c
    return None


def convert_html_to_pdf(
    html_path: Path,
    pdf_path: Path,
    timeout: int = 180,
) -> tuple[bool, str | None]:
    """Render an HTML file to PDF using headless Edge/Chrome.

    Uses the browser's built-in ``--print-to-pdf`` so layout matches what the
    user sees in a browser. No network access for sibling images is required
    (missing images are dropped silently, text/tables are preserved).
    """
    browser = _find_chromium()
    if not browser:
        return False, "no Edge/Chrome found (set CHROMIUM_PATH)"

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    file_uri = html_path.resolve().as_uri()
    cmd = [
        browser,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-extensions",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=10000",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        file_uri,
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"chromium timeout after {timeout}s"
    except Exception as e:
        return False, f"chromium error: {type(e).__name__}: {e}"

    if pdf_path.exists() and pdf_path.stat().st_size > 1024:
        return True, None
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] \
        or [f"chromium exit {proc.returncode}"]
    return False, f"chromium: {tail[0]}"


def convert_html_to_docx(html_path: Path, output_path: Path) -> tuple[bool, str | None]:
    """Convert HTML to DOCX via HTML -> PDF (Chromium) -> DOCX (Adobe).

    This is the only supported HTML conversion path. Both a Chromium browser
    (Edge or Chrome) and Adobe PDF Services credentials are required; there
    is no fallback to other converters.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not (os.getenv("PDF_SERVICES_CLIENT_ID")
            and os.getenv("PDF_SERVICES_CLIENT_SECRET")):
        return False, "PDF_SERVICES_CLIENT_ID / PDF_SERVICES_CLIENT_SECRET not set"
    if not _find_chromium():
        return False, "no Edge/Chrome found (set CHROMIUM_PATH)"

    tmp_pdf = output_path.with_suffix(".via_chromium.pdf")
    try:
        ok, err = convert_html_to_pdf(html_path, tmp_pdf)
        if not ok:
            return False, f"HTML->PDF: {err}"
        ok2, err2 = convert_pdf_to_office(tmp_pdf, output_path, "docx")
        if not ok2:
            return False, f"PDF->DOCX: {err2}"
        return True, None
    finally:
        tmp_pdf.unlink(missing_ok=True)


def process_entry(entry: dict, output_dir: Path) -> dict:
    fname = entry["filename"]
    url = entry["url"]
    final_format = (entry.get("final_format") or "").lower()
    conv_required = bool(entry.get("conversion_required"))
    final_path = output_dir / fname

    if final_path.exists() and final_path.stat().st_size > 1024:
        return {"filename": fname, "status": "exists", "reason": "already downloaded"}

    # Stage download under a temp name (extension matches source for clarity)
    src_ext = (entry.get("original_format") or final_format).lower()
    tmp_path = output_dir / f".tmp_{fname}.{src_ext}" if src_ext else output_dir / f".tmp_{fname}"

    is_html_src = src_ext in ("html", "htm")
    ok, err = download_file(url, tmp_path, is_html_target=is_html_src)
    if not ok:
        tmp_path.unlink(missing_ok=True)
        return {"filename": fname, "status": "failed", "reason": err}

    # HTML -> DOCX path
    if conv_required and is_html_src and final_format == "docx":
        ok, err = convert_html_to_docx(tmp_path, final_path)
        tmp_path.unlink(missing_ok=True)
        if not ok:
            return {"filename": fname, "status": "convert_failed", "reason": err}
        if not validate_office_file(final_path, final_format):
            final_path.unlink(missing_ok=True)
            return {"filename": fname, "status": "invalid", "reason": "converted file failed validation"}
        return {"filename": fname, "status": "converted", "reason": f"HTML -> {final_format}"}

    # If actually a PDF and conversion needed, convert
    needs_conv = conv_required and is_pdf(tmp_path) and final_format in ("docx", "pptx")
    if needs_conv:
        ok, err = convert_pdf_to_office(tmp_path, final_path, final_format)
        tmp_path.unlink(missing_ok=True)
        if not ok:
            return {"filename": fname, "status": "convert_failed", "reason": err}
        if not validate_office_file(final_path, final_format):
            final_path.unlink(missing_ok=True)
            return {"filename": fname, "status": "invalid", "reason": "converted file failed validation"}
        return {"filename": fname, "status": "converted", "reason": f"PDF -> {final_format}"}

    # No conversion: move into place and validate
    if final_path.exists():
        final_path.unlink()
    tmp_path.rename(final_path)

    if final_format in ("docx", "pptx", "xlsx") and not validate_office_file(final_path, final_format):
        final_path.unlink(missing_ok=True)
        return {"filename": fname, "status": "invalid", "reason": "downloaded file failed validation"}

    return {"filename": fname, "status": "downloaded", "reason": None}


def load_manifest(parquet_path_or_url: str = HF_PARQUET_URL) -> list[dict]:
    """Load the OCB manifest from the Hugging Face parquet.

    Accepts either a local .parquet path or an http(s) URL pointing to one.
    Returns a list of dicts with keys: filename, url, original_format,
    final_format, conversion_required (bool).
    """
    if parquet_path_or_url.startswith(("http://", "https://")):
        if not MANIFEST_CACHE.exists() or MANIFEST_CACHE.stat().st_size < 256:
            logger.info(f"Fetching manifest: {parquet_path_or_url}")
            ok, err = download_file(parquet_path_or_url, MANIFEST_CACHE)
            if not ok:
                raise RuntimeError(f"Failed to download manifest: {err}")
        path = MANIFEST_CACHE
    else:
        path = Path(parquet_path_or_url)

    import pandas as pd  # local import to keep optional
    df = pd.read_parquet(path)
    col = {c.lower(): c for c in df.columns}

    def pick(*names: str) -> str | None:
        for n in names:
            if n in col:
                return col[n]
        return None

    c_name = pick("filename", "file_name", "name")
    c_url = pick("url", "source_url", "download_url")
    c_orig = pick("original_format", "source_format", "src_format")
    c_final = pick("final_format", "required_format", "target_format", "format")
    c_conv = pick("conversion_required", "convert", "needs_conversion")
    if not (c_name and c_url and c_final):
        raise RuntimeError(
            f"parquet missing required columns; got {list(df.columns)}"
        )

    def to_bool(v) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ("yes", "true", "y", "1")

    out: list[dict] = []
    for _, row in df.iterrows():
        out.append({
            "filename": str(row[c_name]),
            "url": str(row[c_url]),
            "original_format": (
                str(row[c_orig]).lower()
                if c_orig and row[c_orig] is not None else ""
            ),
            "final_format": (
                str(row[c_final]).lower()
                if row[c_final] is not None else ""
            ),
            "conversion_required": to_bool(row[c_conv]) if c_conv else False,
        })
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--manifest",
        default=HF_PARQUET_URL,
        help=(
            "path or URL to the OCB parquet manifest. "
            "Defaults to the Hugging Face copy."
        ),
    )
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="output directory")
    p.add_argument("--limit", type=int, default=0, help="limit number of files (0 = all)")
    p.add_argument("--filter-format", default=None, help="only process this final_format (e.g. docx)")
    p.add_argument("--only-conversions", action="store_true", help="only files where conversion_required=true")
    p.add_argument(
        "--filename",
        "-f",
        action="append",
        default=None,
        help=(
            "process only the named file(s). Repeat the flag or pass a "
            "comma-separated list. Matches the `filename` column exactly "
            "(case-insensitive)."
        ),
    )
    p.add_argument("--delay", type=float, default=0.3, help="seconds between downloads")
    args = p.parse_args()

    manifest = load_manifest(args.manifest)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = manifest
    if args.filename:
        wanted = {
            n.strip().lower()
            for spec in args.filename
            for n in spec.split(",")
            if n.strip()
        }
        items = [e for e in items if e["filename"].lower() in wanted]
        missing = wanted - {e["filename"].lower() for e in items}
        if missing:
            logger.warning(f"No manifest entries for: {', '.join(sorted(missing))}")
    if args.filter_format:
        items = [e for e in items if (e.get("final_format") or "").lower() == args.filter_format.lower()]
    if args.only_conversions:
        items = [e for e in items if e.get("conversion_required")]
    if args.limit > 0:
        items = items[: args.limit]

    logger.info(f"Processing {len(items)} of {len(manifest)} entries -> {output_dir}")

    results = []
    for i, entry in enumerate(items, 1):
        logger.info(f"[{i}/{len(items)}] {entry['filename']}")
        res = process_entry(entry, output_dir)
        results.append(res)
        logger.info(f"   -> {res['status']}{(': ' + res['reason']) if res.get('reason') else ''}")
        time.sleep(args.delay)

    # Summary
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total: {len(results)}")
    for k, v in sorted(by_status.items()):
        print(f"  {k:18s} {v}")
    print("=" * 60)

    summary_path = output_dir / "_download_results.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info(f"Results written to {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
