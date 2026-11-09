#!/usr/bin/env python3
"""Shared runtime helpers for a standalone international-law search skill.

The module deliberately contains no site-specific logic.  Each skill repository
carries its own copy so it can be installed without any sibling repository.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import io
import json
import re
import sys
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/155.0.0.0 Safari/537.36"
)
MAX_BYTES = 40 * 1024 * 1024


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def clean(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(clean(item) for item in value)
    text = str(value or "")
    if "<" in text:
        return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return html_lib.unescape(text)


def norm(value: Any) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", str(value or "").casefold())
        if not unicodedata.combining(char)
    )


def terms(query: str) -> list[str]:
    return re.findall(r"\w+", norm(query))


def matches(query: str, value: Any) -> bool:
    haystack = norm(value)
    return all(term in haystack for term in terms(query))


def snippet(text: Any, query: str = "", width: int = 800) -> str:
    body = clean(text)
    if not body:
        return ""
    if not query:
        return body[:width]
    folded = norm(body)
    positions = [folded.find(term) for term in terms(query) if folded.find(term) >= 0]
    start = max(0, min(positions) - width // 3) if positions else 0
    return body[start : start + width].strip()


def atomic_write(path: Path, body: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_bytes(body)
    temp.replace(path)


class RetrievalError(RuntimeError):
    """A failed HTTP, parsing, or source-schema operation."""


class HTTP:
    """Small cached HTTP client with evidence and optional persistent cookies."""

    def __init__(
        self,
        cache: str | Path,
        offline: bool = False,
        ttl: int = 86400,
        timeout: int = 60,
        cookie_jar: str | Path | None = None,
        user_agent: str = DEFAULT_UA,
        min_interval: float = 0.0,
    ) -> None:
        self.cache = Path(cache)
        self.offline = offline
        self.ttl = ttl
        self.timeout = timeout
        self.min_interval = min_interval
        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.evidence: list[dict[str, Any]] = []
        self.cookie_jar = Path(cookie_jar) if cookie_jar else None
        self.had_session_cookies = False
        self._last_request = 0.0
        if self.cookie_jar:
            self.cookie_jar.parent.mkdir(parents=True, exist_ok=True)
            self.session.cookies = requests.cookies.RequestsCookieJar()
            try:
                import http.cookiejar

                jar = http.cookiejar.LWPCookieJar(str(self.cookie_jar))
                jar.load(ignore_discard=True)
                self.session.cookies.update(jar)
                self.had_session_cookies = len(self.session.cookies) > 0
            except (OSError, ValueError):
                pass

    def forget_session_cookies(self) -> bool:
        if not self.had_session_cookies:
            return False
        self.had_session_cookies = False
        self.session.cookies.clear()
        if self.cookie_jar:
            try:
                self.cookie_jar.unlink()
            except OSError:
                pass
        return True

    @staticmethod
    def cache_paths(
        cache: str | Path,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[str, Path, Path]:
        prepared = requests.Request("GET", url, params=params).prepare().url
        key_material = prepared
        if headers:
            key_material += "\n" + json.dumps(headers, sort_keys=True, ensure_ascii=True)
        key = hashlib.sha256(key_material.encode("utf-8")).hexdigest()
        cache = Path(cache)
        return prepared, cache / (key + ".bin"), cache / (key + ".json")

    def store(
        self,
        url: str,
        body: bytes,
        meta: dict[str, Any],
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        prepared, body_path, meta_path = self.cache_paths(self.cache, url, params, headers)
        stored = {
            **meta,
            "request_url": prepared,
            "source_url": meta.get("source_url") or prepared,
            "retrieved_at": meta.get("retrieved_at") or now(),
            "cached": False,
            "sha256": hashlib.sha256(body).hexdigest(),
            "bytes": len(body),
        }
        atomic_write(body_path, body)
        atomic_write(meta_path, json.dumps(stored, ensure_ascii=False).encode("utf-8"))
        self.evidence.append(stored)
        return stored

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        if urlparse(url).scheme not in ("http", "https"):
            raise RetrievalError("Only HTTP(S) URLs are supported")
        prepared, body_path, meta_path = self.cache_paths(self.cache, url, params, headers)
        if body_path.exists() and meta_path.exists() and (
            self.offline or time.time() - meta_path.stat().st_mtime < self.ttl
        ):
            body = body_path.read_bytes()
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if hashlib.sha256(body).hexdigest() != meta.get("sha256"):
                raise RetrievalError("Cache hash mismatch: " + prepared)
            meta = {**meta, "cached": True}
            self.evidence.append(meta)
            return body, meta
        if self.offline:
            raise RetrievalError("Offline cache miss: " + prepared)

        if self.min_interval:
            pause = self.min_interval - (time.monotonic() - self._last_request)
            if pause > 0:
                time.sleep(pause)
        self._last_request = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                with self.session.get(
                    prepared,
                    timeout=(12, self.timeout),
                    stream=True,
                    headers=headers,
                    allow_redirects=True,
                ) as response:
                    meta = {
                        "request_url": prepared,
                        "source_url": response.url,
                        "http_status": response.status_code,
                        "content_type": response.headers.get("Content-Type", ""),
                        "retrieved_at": now(),
                        "cached": False,
                    }
                    if headers:
                        meta["request_headers"] = dict(headers)
                    self.evidence.append(meta)
                    if response.status_code != 200:
                        raise RetrievalError(
                            f"HTTP {response.status_code}: {response.url}"
                        )
                    parts: list[bytes] = []
                    size = 0
                    for part in response.iter_content(65536):
                        size += len(part)
                        if size > MAX_BYTES:
                            raise RetrievalError(
                                "Response exceeds 40 MiB limit: " + prepared
                            )
                        parts.append(part)
                    body = b"".join(parts)
                    if not body.strip():
                        raise RetrievalError("Empty HTTP response: " + prepared)
                    if "html" in meta["content_type"].lower():
                        head = body[:30000].lower()
                        challenge_markers = (
                            b"<title>just a moment",
                            b"<title>access denied",
                            b"<title>human verification",
                            b"403 - forbidden",
                            b"our systems have detected unusual traffic",
                            b"you need to enable javascript to run this app",
                        )
                        if any(marker in head for marker in challenge_markers):
                            raise RetrievalError(
                                "Access challenge or JavaScript shell: " + prepared
                            )
                    if re.search(r"/(login|sign-in)(\.|/|\?|$)", response.url, re.I):
                        raise RetrievalError("Redirected to login: " + response.url)
                    meta.update(
                        sha256=hashlib.sha256(body).hexdigest(),
                        bytes=len(body),
                    )
                    atomic_write(body_path, body)
                    atomic_write(
                        meta_path,
                        json.dumps(meta, ensure_ascii=False).encode("utf-8"),
                    )
                    if self.cookie_jar:
                        self._save_cookies()
                    return body, meta
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt == 0:
                    continue
            except requests.RequestException as exc:
                raise RetrievalError(f"{type(exc).__name__}: {prepared}") from exc
        raise RetrievalError(f"{type(last_error).__name__}: {prepared}") from last_error

    def _save_cookies(self) -> None:
        if not self.cookie_jar:
            return
        try:
            import http.cookiejar

            jar = http.cookiejar.LWPCookieJar(str(self.cookie_jar))
            for cookie in self.session.cookies:
                jar.set_cookie(cookie)
            jar.save(ignore_discard=True)
        except (OSError, ValueError):
            pass

    def json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[Any, dict[str, Any]]:
        body, meta = self.get(url, params, headers)
        try:
            return json.loads(body), meta
        except (ValueError, UnicodeError) as exc:
            raise RetrievalError("Expected JSON: " + meta["source_url"]) from exc

    def soup(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[BeautifulSoup, dict[str, Any]]:
        body, meta = self.get(url, params, headers)
        if "html" not in meta["content_type"].lower() and not body.lstrip().startswith(
            b"<"
        ):
            raise RetrievalError("Expected HTML: " + meta["source_url"])
        return BeautifulSoup(body, "html.parser"), meta


def result(
    title: Any,
    url: str,
    via: str,
    snippet_text: Any = "",
    kind: str = "retrieved_metadata",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "title": clean(title),
        "url": url,
        "via": via,
        "result_type": kind,
        "snippet": snippet(snippet_text),
        "retrieved_at": now(),
        **extra,
    }


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = row.get("url") or row.get("title", "")
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def pdf_pages(body: bytes) -> list[dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(body))
    return [
        {"page": index + 1, "text": page.extract_text() or ""}
        for index, page in enumerate(reader.pages)
    ]


def add_common(parser: argparse.ArgumentParser, cache_default: str, timeout_default: int = 60) -> None:
    parser.add_argument("--out", help="Write the full JSON report to this file")
    parser.add_argument("--cache", default=cache_default, help="Cache directory")
    parser.add_argument("--cache-ttl", type=int, default=86400, help="Cache TTL in seconds")
    parser.add_argument("--offline", action="store_true", help="Only read cached responses")
    parser.add_argument("--timeout", type=int, default=timeout_default, help="HTTP timeout in seconds")


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "status",
        "total",
        "returned",
        "next_offset",
        "text_characters",
        "pages",
        "needs_ocr",
        "warnings",
    )
    summary = {key: payload[key] for key in keys if key in payload}
    if "results" in payload:
        summary["results"] = len(payload["results"])
    return summary


def _emit(payload: dict[str, Any], out: str | None) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if out:
        path = Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(json.dumps({"output": str(path.resolve()), **_summary(payload)}, ensure_ascii=False))
    else:
        print(text)


def run_cli(adapter: Any) -> int:
    parser = argparse.ArgumentParser(prog=adapter.PROG, description=adapter.DESCRIPTION)
    sub = parser.add_subparsers(dest="command", required=True)

    search = sub.add_parser("search", help="Search the source")
    search.add_argument("query", help="Keyword query")
    adapter.add_search_args(search)
    add_common(search, adapter.CACHE_DEFAULT)

    if hasattr(adapter, "fetch"):
        fetch = sub.add_parser("fetch", help="Fetch one document or page")
        fetch.add_argument("locator", help="URL or source-specific identifier")
        adapter.add_fetch_args(fetch)
        add_common(fetch, adapter.CACHE_DEFAULT, adapter.FETCH_TIMEOUT_DEFAULT)

    doctor = sub.add_parser("doctor", help="Check dependencies and route reachability")
    doctor.add_argument("--no-probe", action="store_true", help="Skip network probes")
    add_common(doctor, adapter.CACHE_DEFAULT, 30)

    args = parser.parse_args()
    try:
        if args.command == "doctor":
            payload = adapter.doctor(args)
            ok = bool(payload.get("ok"))
        else:
            http = adapter.make_http(args)
            if args.command == "search":
                payload = adapter.search(args.query, args, http)
            else:
                payload = adapter.fetch(args.locator, args, http)
            ok = payload.get("status") not in ("error", "unavailable")
        _emit(payload, getattr(args, "out", None))
        return 0 if ok else 1
    except Exception as exc:  # keep failures machine-readable
        payload = {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
        }
        _emit(payload, getattr(args, "out", None))
        return 1
