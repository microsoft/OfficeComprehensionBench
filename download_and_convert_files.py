"""Download (and optionally convert PDF -> Office) the reference files for OCB.

Reads `files_source_url.json` (next to this script) and downloads each file.
If `conversion_required` is true and the source is a PDF, it converts it to
the target Office format (`docx` or `pptx`) using Adobe PDF Services.

Hugging Face fallback URLs are downloaded directly with no conversion needed.

Environment (see .env.example):
- PDF_SERVICES_CLIENT_ID
- PDF_SERVICES_CLIENT_SECRET
- HF_TOKEN              (optional: Hugging Face access token for private datasets)
- SEC_USER_AGENT        (required for sec.gov URLs, format: "Name email@example.com")
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
DEFAULT_MANIFEST = ROOT / "files_source_url.json"
DEFAULT_OUTPUT = ROOT / "downloaded_files"

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


def convert_html_to_docx(html_path: Path, output_path: Path) -> tuple[bool, str | None]:
    """Convert HTML to DOCX. Prefers pandoc (best fidelity), falls back to htmldocx."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    pandoc = shutil.which("pandoc")
    if pandoc:
        try:
            proc = subprocess.run(
                [pandoc, str(html_path), "-f", "html", "-t", "docx", "-o", str(output_path), "--standalone"],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024:
                return True, None
            err = (proc.stderr or proc.stdout or "").strip().splitlines()[-1:] or ["pandoc returned non-zero"]
            return False, f"pandoc: {err[0]}"
        except subprocess.TimeoutExpired:
            return False, "pandoc timeout (>300s)"
        except Exception as e:
            return False, f"pandoc error: {type(e).__name__}: {e}"

    # Fallback: htmldocx
    try:
        from htmldocx import HtmlToDocx
        from docx import Document
    except ImportError:
        return False, "pandoc not found and htmldocx not installed (pip install htmldocx python-docx, or install pandoc)"
    try:
        html = html_path.read_text(encoding="utf-8", errors="ignore")
        doc = Document()
        HtmlToDocx().add_html_to_document(html, doc)
        doc.save(str(output_path))
        if output_path.exists() and output_path.stat().st_size > 1024:
            return True, None
        return False, "htmldocx produced empty/invalid file"
    except Exception as e:
        return False, f"htmldocx error: {type(e).__name__}: {e}"


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


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="files_source_url.json path")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="output directory")
    p.add_argument("--limit", type=int, default=0, help="limit number of files (0 = all)")
    p.add_argument("--filter-format", default=None, help="only process this final_format (e.g. docx)")
    p.add_argument("--only-conversions", action="store_true", help="only files where conversion_required=true")
    p.add_argument("--delay", type=float, default=0.3, help="seconds between downloads")
    args = p.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    items = manifest
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
