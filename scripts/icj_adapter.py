#!/usr/bin/env python3
"""International Court of Justice adapter for ICJSearcher."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from skillkit import HTTP, RetrievalError, clean, pdf_pages, result

PROG = "icj_search.py"
DESCRIPTION = "Search the International Court of Justice official document search."
CACHE_DEFAULT = ".icj-cache"
FETCH_TIMEOUT_DEFAULT = 300

SEARCH_URL = "https://www.icj-cij.org/advanced-search"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/156.0.0.0 Safari/537.36"
)
BYPASS_HELPER = Path(__file__).resolve().parent / "cloudflare_bypass.py"


def _headers() -> dict[str, str]:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def make_http(args: argparse.Namespace) -> HTTP:
    return HTTP(
        args.cache,
        offline=args.offline,
        ttl=args.cache_ttl,
        timeout=args.timeout,
        user_agent=UA,
    )


def add_search_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=10, help="1..50 (default 10)")
    parser.add_argument("--offset", type=int, default=0, help=">= 0 (default 0)")
    parser.add_argument(
        "--phrase",
        help="Exact word or phrase (ICJ advanced-search field search_api_fulltext_1)",
    )
    parser.add_argument(
        "--wildcard",
        help="Wildcard term (ICJ advanced-search field search_api_fulltext_2)",
    )
    parser.add_argument(
        "--document-type",
        dest="document_type",
        help=(
            "Document group id or label fragment, e.g. 486, Judgments, "
            "Advisory opinions, Press releases"
        ),
    )
    parser.add_argument(
        "--incidental",
        help=(
            "Incidental proceeding id or label fragment, e.g. 409, "
            "Provisional measures, Counter-claims"
        ),
    )
    parser.add_argument("--date-from", dest="date_from", help="Document date lower bound YYYY-MM-DD")
    parser.add_argument("--date-to", dest="date_to", help="Document date upper bound YYYY-MM-DD")
    parser.add_argument("--sort", choices=("ASC", "DESC"), default="DESC", help="Date sort order")
    parser.add_argument("--case-id", dest="case_id", help="Numeric ICJ case id for field_doc_case_code_1[]")


def add_fetch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pdf-out", help="Write the retrieved PDF here")
    parser.add_argument("--text-out", help="Write page-marked text here")
    parser.add_argument("--max-mb", type=int, default=250, help="Maximum PDF size in MiB")


DOCUMENT_TYPES = {
    "application": "477",
    "special agreement": "478",
    "request for advisory opinion": "479",
    "written proceedings": "480",
    "other documents": "481",
    "oral proceedings": "482",
    "oral statements": "482",
    "orders": "483",
    "judgments": "486",
    "advisory opinions": "489",
    "summaries": "495",
    "press releases": "496",
    "correspondence": "497",
}
INCIDENTAL = {
    "counter-claims": "411",
    "discontinuance": "414",
    "intervention": "412",
    "preliminary objections": "410",
    "provisional measures": "409",
    "questions of jurisdiction": "413",
    "jurisdiction and/or admissibility": "413",
    "admissibility": "413",
}


def _lookup(value: str | None, mapping: dict[str, str], label: str) -> str:
    if not value:
        return "All"
    text = str(value).strip()
    if text.isdigit():
        return text
    key = text.casefold()
    if key in mapping:
        return mapping[key]
    partial = [(name, ident) for name, ident in mapping.items() if key in name]
    if len(partial) == 1:
        return partial[0][1]
    if len(partial) > 1:
        raise ValueError(
            f"{label} value {value!r} is ambiguous; candidates: "
            + ", ".join(name for name, _ in partial)
        )
    raise ValueError(f"{label} has no known label matching {value!r}")


def _document_type_id(value: str | None) -> str:
    return _lookup(value, DOCUMENT_TYPES, "document-type")


def _incidental_id(value: str | None) -> str:
    if not value:
        return "All"
    return _lookup(value, INCIDENTAL, "incidental")


def search(query: str, args: argparse.Namespace, http: HTTP) -> dict[str, Any]:
    advanced_filters = [
        getattr(args, "phrase", None),
        getattr(args, "wildcard", None),
        getattr(args, "document_type", None),
        getattr(args, "incidental", None),
        getattr(args, "date_from", None),
        getattr(args, "date_to", None),
        getattr(args, "case_id", None),
    ]
    if not query.strip() and not any(advanced_filters):
        raise ValueError("A query or at least one advanced filter is required")
    if not 1 <= args.limit <= 50:
        raise ValueError("limit must be 1..50")
    page_size = max(10, min(args.limit, 100))
    page = args.offset // page_size + 1
    within = args.offset % page_size
    params = {
        "search_api_fulltext": query,
        "search_api_fulltext_1": getattr(args, "phrase", None) or "",
        "search_api_fulltext_2": getattr(args, "wildcard", None) or "",
        "case_selection": "2" if getattr(args, "case_id", None) else "1",
        "field_doc_case_code_1[]": (
            [args.case_id] if getattr(args, "case_id", None) else []
        ),
        "field_document_group_type": _document_type_id(
            getattr(args, "document_type", None)
        ),
        "field_doc_incidental_proceedings": _incidental_id(
            getattr(args, "incidental", None)
        ),
        "field_date_of_the_document[min]": getattr(args, "date_from", None) or "",
        "field_date_of_the_document[max]": getattr(args, "date_to", None) or "",
        "items_per_page": page_size,
        "sort_order": getattr(args, "sort", "DESC"),
        "page": page - 1,
    }
    try:
        soup, meta = http.soup(SEARCH_URL, params, headers=_headers())
    except RetrievalError as exc:
        if args.offline:
            raise
        soup, meta = _search_via_bypass(params, args.timeout)
    view = soup.select_one(".view-document-search")
    if not view:
        raise RetrievalError(
            "ICJ Document Search returned no result container; challenge or schema change"
        )
    header = view.select_one(".view-header")
    total_match = re.search(
        r"About\s+([\d,]+)\s+results?",
        clean(header.get_text(" ")) if header else "",
        re.I,
    )
    total = int(total_match.group(1).replace(",", "")) if total_match else None
    cards = view.select(".view-content .views-row")
    if total and not cards:
        raise RetrievalError(
            "ICJ Document Search reported results but returned no rows; schema change"
        )
    rows: list[dict[str, Any]] = []
    for card in cards:
        heading = card.select_one("h4 a[href]")
        if not heading:
            continue
        target = urljoin(meta["source_url"], heading["href"])
        case_link = card.select_one('p a[href*="/case/"]')
        paragraphs = card.select("p")
        details = clean(paragraphs[1].get_text(" ")) if len(paragraphs) > 1 else ""
        type_match = re.search(r"Type:\s*(.*?)(?:\s*\|\s*Date:|$)", details, re.I)
        date_match = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", details, re.I)
        rows.append(
            result(
                heading.get_text(" ", strip=True),
                target,
                "icj-document-search",
                details,
                case_title=clean(case_link.get_text(" ")) if case_link else "",
                case_url=urljoin(meta["source_url"], case_link["href"]) if case_link else None,
                document_type=clean(type_match.group(1)) if type_match else "",
                date=date_match.group(1) if date_match else "",
                fulltext_url=target,
                access="official document-search metadata; PDF text must be fetched separately",
                content_scope="official ICJ Document Search record, not the judgment text",
            )
        )
    selected = rows[within : within + args.limit]
    page_start = (page - 1) * page_size
    consumed = page_start + within + len(selected)
    next_offset = (
        consumed
        if selected
        and ((total is not None and consumed < total) or (total is None and len(cards) == page_size))
        else None
    )
    return {
        "status": "ok" if rows or total == 0 else "no-results-in-queried-index",
        "query": query,
        "filters": {
            "phrase": getattr(args, "phrase", None),
            "wildcard": getattr(args, "wildcard", None),
            "document_type": getattr(args, "document_type", None),
            "incidental": getattr(args, "incidental", None),
            "date_from": getattr(args, "date_from", None),
            "date_to": getattr(args, "date_to", None),
            "case_id": getattr(args, "case_id", None),
            "sort": getattr(args, "sort", "DESC"),
        },
        "total": total,
        "results": selected,
        "pagination": {
            "offset": args.offset,
            "limit": args.limit,
            "next_offset": next_offset,
            "page": page,
            "page_size": page_size,
        },
        "scope": "Official ICJ Document Search across case-related documents; rows are metadata",
        "evidence": http.evidence,
    }


def _search_via_bypass(params: dict[str, Any], timeout: int) -> tuple[BeautifulSoup, dict[str, Any]]:
    url = SEARCH_URL + "?" + urlencode(params, doseq=True)
    body, meta = _run_bypass(url, "html", timeout)
    return BeautifulSoup(body, "html.parser"), meta


def _run_bypass(url: str, expected: str, timeout: int) -> tuple[bytes, dict[str, Any]]:
    if not BYPASS_HELPER.is_file():
        raise RetrievalError("Cloudflare bypass helper is missing: " + str(BYPASS_HELPER))
    with tempfile.TemporaryDirectory(prefix="icj-cf-") as folder:
        output = Path(folder) / "response.body"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(BYPASS_HELPER),
                    url,
                    "--out",
                    str(output),
                    "--expect",
                    expected,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(240, timeout),
            )
        except subprocess.TimeoutExpired as exc:
            raise RetrievalError("ICJ Cloudflare bypass timed out") from exc
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0 or not output.is_file():
            detail = (stderr or stdout).splitlines()[-1] if (stderr or stdout) else "no diagnostic output"
            raise RetrievalError("ICJ Cloudflare bypass failed: " + detail)
        payload = json.loads(stdout.splitlines()[-1])
        body = output.read_bytes()
        meta = {
            "source_url": payload.get("url") or url,
            "http_status": payload.get("status_code", 200),
            "content_type": payload.get("content_type") or "",
            "retrieved_at": payload.get("retrieved_at")
            or __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
            "transport": "cloudflare-bypass-headless",
            "cloudflare_detected": bool(payload.get("cf_detected")),
            "browser_user_agent": payload.get("user_agent") or "",
            "bypass_elapsed_seconds": payload.get("elapsed_seconds"),
            "sha256": __import__("hashlib").sha256(body).hexdigest(),
            "bytes": len(body),
        }
        return body, meta


def fetch(locator: str, args: argparse.Namespace, http: HTTP) -> dict[str, Any]:
    parsed = urlparse(locator)
    if parsed.scheme != "https" or (parsed.hostname or "").lower() not in {
        "icj-cij.org",
        "www.icj-cij.org",
    }:
        raise ValueError("fetch expects an https://www.icj-cij.org/ URL")
    max_bytes = args.max_mb * 1024 * 1024
    try:
        body, meta = http.get(locator, headers=_headers())
    except RetrievalError as exc:
        if args.offline:
            raise
        expected = "pdf" if parsed.path.lower().endswith(".pdf") else "html"
        body, meta = _run_bypass(locator, expected, args.timeout)
    if len(body) > max_bytes:
        raise RetrievalError(f"Response exceeds --max-mb ({args.max_mb} MiB)")
    if body.startswith(b"%PDF"):
        pages = pdf_pages(body)
        text = "\n\n".join(f"@@PAGE {p['page']}@@\n{p['text']}" for p in pages)
        if args.pdf_out:
            Path(args.pdf_out).write_bytes(body)
        if args.text_out:
            Path(args.text_out).write_text(text, encoding="utf-8")
        return {
            "status": "ok",
            "url": meta["source_url"],
            "content_type": meta["content_type"],
            "pages": len(pages),
            "needs_ocr": not any(p["text"].strip() for p in pages),
            "page_text": pages,
            "pdf_out": str(Path(args.pdf_out).resolve()) if args.pdf_out else None,
            "text_out": str(Path(args.text_out).resolve()) if args.text_out else None,
            "sha256": meta["sha256"],
            "retrieved_at": meta["retrieved_at"],
            "transport": meta.get("transport", "direct-http"),
        }
    soup = BeautifulSoup(body, "html.parser")
    container = soup.select_one("main") or soup.select_one(".content") or soup.body or soup
    for node in container.select("script, style, nav, header, footer, input, select, button, textarea, noscript"):
        node.decompose()
    text = container.get_text("\n", strip=True)
    if len(text) < 100:
        raise RetrievalError("Insufficient ICJ page text; page may be a shell or access page")
    links = []
    seen = set()
    for anchor in container.select("a[href]"):
        href = urljoin(meta["source_url"], anchor["href"])
        if href in seen:
            continue
        seen.add(href)
        links.append({"text": clean(anchor.get_text(" ", strip=True)), "url": href})
    if args.text_out:
        Path(args.text_out).write_text(text, encoding="utf-8")
    return {
        "status": "ok",
        "url": meta["source_url"],
        "title": clean(soup.title.get_text(" ", strip=True)) if soup.title else "",
        "text": text,
        "text_characters": len(text),
        "document_links": links,
        "content_scope": "ICJ HTML page text; linked PDFs must be fetched separately",
        "text_out": str(Path(args.text_out).resolve()) if args.text_out else None,
        "sha256": meta["sha256"],
        "retrieved_at": meta["retrieved_at"],
        "transport": meta.get("transport", "direct-http"),
    }


def doctor(args: argparse.Namespace) -> dict[str, Any]:
    checks = [
        {"check": "python", "ok": True, "detail": "Python runtime available"},
        {"check": "requests", "ok": True, "detail": "requests importable"},
        {"check": "beautifulsoup4", "ok": True, "detail": "bs4 importable"},
    ]
    try:
        import DrissionPage  # noqa: F401
        import curl_cffi  # noqa: F401

        checks.append({"check": "cloudflare-bypass deps", "ok": True, "detail": "DrissionPage and curl_cffi importable"})
        bypass_ok = True
    except Exception as exc:
        checks.append({"check": "cloudflare-bypass deps", "ok": False, "detail": str(exc)})
        bypass_ok = False
    if args.no_probe:
        return {
            "ok": True,
            "status": "ok (probes skipped; Cloudflare bypass is optional for search)",
            "checks": checks,
            "bypass_available": bypass_ok,
        }
    http = make_http(args)
    try:
        soup, meta = http.soup(
            SEARCH_URL,
            {"search_api_fulltext": "state immunity", "items_per_page": 1, "page": 0},
            headers=_headers(),
        )
        checks.append(
            {
                "check": "ICJ Document Search",
                "ok": bool(soup.select_one(".view-document-search")),
                "http_status": meta["http_status"],
                "bytes": meta["bytes"],
            }
        )
        ok = True
    except Exception as exc:
        checks.append(
            {
                "check": "ICJ Document Search",
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "bypass_available": bypass_ok,
            }
        )
        ok = bypass_ok
    return {
        "ok": ok,
        "status": "ok" if ok else "error",
        "checks": checks,
        "catalog": {"search_url": SEARCH_URL},
    }
