"""Cached, rate-limited HTTP fetching.

All network access in the pipeline goes through this module so that:
- every request carries a descriptive User-Agent,
- requests are rate-limited (>= 2 s between requests to the same host),
- raw responses are cached on disk and never re-fetched unless the
  caller explicitly allows a max age (used for current-season pages).
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.parse
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "cache"

USER_AGENT = (
    "SvenskFotbollskuriosa/1.0 "
    "(https://github.com/wilandh-prog/svensk-fotbollskuriosa; wilandh@gmail.com) "
    "requests"
)

MIN_INTERVAL_S = 2.0
_last_fetch_by_host: dict[str, float] = {}

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT


class FetchError(RuntimeError):
    pass


def _cache_paths(url: str) -> tuple[Path, Path]:
    h = hashlib.sha256(url.encode()).hexdigest()[:24]
    host = urllib.parse.urlparse(url).netloc.replace(":", "_")
    base = CACHE_DIR / host
    return base / f"{h}.body", base / f"{h}.meta.json"


def cached_get(url: str, *, max_age_s: float | None = None, params: dict | None = None) -> str:
    """GET `url`, returning body text. Serve from disk cache when present.

    max_age_s=None means the cached copy never expires (immutable
    historical pages). Pass a finite age for pages that change, e.g. the
    current season article.
    """
    if params:
        url = url + ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    body_p, meta_p = _cache_paths(url)
    if body_p.exists() and meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        age = time.time() - meta["fetched_at"]
        if max_age_s is None or age < max_age_s:
            return body_p.read_text(encoding="utf-8")

    host = urllib.parse.urlparse(url).netloc
    wait = _last_fetch_by_host.get(host, 0) + MIN_INTERVAL_S - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_fetch_by_host[host] = time.time()

    resp = _session.get(url, timeout=60)
    if resp.status_code != 200:
        raise FetchError(f"GET {url} -> HTTP {resp.status_code}")
    resp.encoding = resp.encoding or "utf-8"
    body_p.parent.mkdir(parents=True, exist_ok=True)
    body_p.write_text(resp.text, encoding="utf-8")
    meta_p.write_text(
        json.dumps({"url": url, "fetched_at": time.time(), "status": resp.status_code}),
        encoding="utf-8",
    )
    return resp.text


def cached_post_json(url: str, payload: dict, *, max_age_s: float | None = None) -> dict:
    """POST JSON and cache the response, keyed by URL + body.

    Used for the league GraphQL API; obeys the same rate limit as GET.
    """
    key = url + "#" + hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()[:32]
    body_p, meta_p = _cache_paths(key)
    if body_p.exists() and meta_p.exists():
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        if max_age_s is None or (time.time() - meta["fetched_at"]) < max_age_s:
            return json.loads(body_p.read_text(encoding="utf-8"))

    host = urllib.parse.urlparse(url).netloc
    wait = _last_fetch_by_host.get(host, 0) + MIN_INTERVAL_S - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_fetch_by_host[host] = time.time()

    resp = _session.post(url, json=payload, timeout=90)
    if resp.status_code != 200:
        raise FetchError(f"POST {url} -> HTTP {resp.status_code}")
    data = resp.json()
    if data.get("errors"):
        raise FetchError(f"POST {url} -> GraphQL errors: {data['errors'][:1]}")
    body_p.parent.mkdir(parents=True, exist_ok=True)
    body_p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    meta_p.write_text(
        json.dumps({"url": url, "fetched_at": time.time(), "status": resp.status_code}),
        encoding="utf-8",
    )
    return data


WIKI_API = "https://{lang}.wikipedia.org/w/api.php"


def wiki_rendered_html(page: str, *, max_age_s: float | None = None, lang: str = "sv") -> str:
    """Rendered article HTML via the MediaWiki parse API (templates expanded)."""
    body = cached_get(
        WIKI_API.format(lang=lang),
        params={
            "action": "parse",
            "page": page,
            "prop": "text",
            "format": "json",
            "formatversion": "2",
        },
        max_age_s=max_age_s,
    )
    data = json.loads(body)
    if "error" in data:
        raise FetchError(f"MediaWiki error for {page!r}: {data['error'].get('info')}")
    return data["parse"]["text"]


def wiki_wikitext(page: str, *, max_age_s: float | None = None, lang: str = "sv") -> str:
    body = cached_get(
        WIKI_API.format(lang=lang),
        params={
            "action": "parse",
            "page": page,
            "prop": "wikitext",
            "format": "json",
            "formatversion": "2",
        },
        max_age_s=max_age_s,
    )
    data = json.loads(body)
    if "error" in data:
        raise FetchError(f"MediaWiki error for {page!r}: {data['error'].get('info')}")
    return data["parse"]["wikitext"]
