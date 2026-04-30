"""Favicon fetching with a domain-keyed LRU cache."""
from __future__ import annotations

import io
import threading
import urllib.request
from collections import OrderedDict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

_cache: OrderedDict[str, Image | None] = OrderedDict()
_cache_lock = threading.Lock()
_CACHE_MAX = 128
_FAVICON_SIZE = 16
_TIMEOUT = 5.0
_HEADERS = {"User-Agent": "Mozilla/5.0"}


def fetch_favicon(domain: str) -> Image | None:
    with _cache_lock:
        if domain in _cache:
            _cache.move_to_end(domain)
            return _cache[domain]
    # Network fetch outside the lock to avoid blocking other threads.
    result = _fetch(domain)
    with _cache_lock:
        if domain not in _cache:
            _cache[domain] = result
            if len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
        _cache.move_to_end(domain)
        return _cache[domain]


_CANDIDATES = [
    "https://{domain}/favicon.ico",
    "https://icons.duckduckgo.com/ip3/{domain}.ico",
]


def _fetch(domain: str) -> Image | None:
    from PIL import Image  # deferred — not available on Linux test runner
    for template in _CANDIDATES:
        url = template.format(domain=domain)
        try:
            req = urllib.request.Request(url, headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                content_type = resp.headers.get("Content-Type", "")
                data = resp.read()
            if "html" in content_type.lower():
                continue
            img = Image.open(io.BytesIO(data)).convert("RGBA")
            img = img.resize((_FAVICON_SIZE, _FAVICON_SIZE), Image.LANCZOS)
            return img
        except Exception:
            continue
    return None
