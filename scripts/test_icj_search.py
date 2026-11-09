"""Offline tests for ICJSearcher."""
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path

from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import icj_adapter as adapter  # noqa: E402


class FakeHttp:
    def __init__(self, html):
        self.html = html
        self.evidence = []

    def soup(self, url, params=None, headers=None):
        return BeautifulSoup(self.html, "html.parser"), {
            "source_url": "https://www.icj-cij.org/advanced-search",
            "http_status": 200, "content_type": "text/html", "bytes": 100,
            "retrieved_at": "2026-11-09T00:00:00Z", "sha256": "0" * 64,
        }


def args(**kwargs):
    base = dict(limit=1, offset=0, cache=".cache", offline=False, cache_ttl=0, timeout=30)
    base.update(kwargs)
    return argparse.Namespace(**base)


class IcjTests(unittest.TestCase):
    def test_search_parses_document_rows(self):
        html = """
        <html><body><div class="view-document-search">
          <div class="view-header">About 1 results</div>
          <div class="view-content"><div class="views-row">
            <h4><a href="/sites/default/files/case-related/1/1-20200101-JUD-01-00-EN.pdf">Judgment</a></h4>
            <p><a href="/case/1">Case One</a></p>
            <p>Type: Judgment | Date: 2020-01-01</p>
          </div></div>
        </div></body></html>
        """
        out = adapter.search("state immunity", args(), FakeHttp(html))
        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["total"], 1)
        self.assertEqual(out["results"][0]["document_type"], "Judgment")
        self.assertEqual(out["results"][0]["date"], "2020-01-01")


if __name__ == "__main__":
    unittest.main()
