"""
blogs_cache — Cloudflare Cache API helpers for the blog list.

Uses the built-in Cache API (caches.open) which persists across requests
at the same edge PoP without requiring any external bindings.

Cache-Control: max-age=3600 gives a 1-hour TTL; call evict_cached_blogs()
via POST /api/v1/blogs/evict to invalidate immediately after content changes.
"""
import json

from js import Object, Response as js_Response, caches as js_caches
from pyodide.ffi import to_js

# Must look like a URL; the host is arbitrary — it is never actually fetched.
_BLOGS_CACHE_URL = "https://api-gateway-internal-cache/v1/blogs"
_CACHE_NAME = "blogs"
_CACHE_TTL_SECONDS = 86400  # 24 hours


async def get_cached_blogs():
    """Read blog list from the Cloudflare Cache API. Returns None on miss."""
    try:
        cache = await js_caches.open(_CACHE_NAME)
        resp = await cache.match(_BLOGS_CACHE_URL)
        if resp is None:
            return None
        text = await resp.text()
        data = json.loads(text)
        print(f"[blogs] cache hit: {len(data)} entries")
        return data
    except Exception as exc:
        print(f"[blogs] cache read error: {exc}")
        return None


async def set_cached_blogs(blogs):
    """Write blog list into the Cloudflare Cache API."""
    try:
        cache = await js_caches.open(_CACHE_NAME)
        # Cache API requires a native JS Response, not the Python workers.Response wrapper.
        resp = js_Response.new(
            json.dumps(blogs),
            to_js(
                {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Cache-Control": f"max-age={_CACHE_TTL_SECONDS}",
                    },
                },
                dict_converter=Object.fromEntries,
            ),
        )
        await cache.put(_BLOGS_CACHE_URL, resp)
        print(f"[blogs] cache set: {len(blogs)} entries (TTL {_CACHE_TTL_SECONDS}s)")
    except Exception as exc:
        print(f"[blogs] cache write error: {exc}")


async def evict_cached_blogs():
    """Delete the blog list from the Cloudflare Cache API."""
    try:
        cache = await js_caches.open(_CACHE_NAME)
        deleted = await cache.delete(_BLOGS_CACHE_URL)
        print(f"[blogs] cache evicted (found={deleted})")
    except Exception as exc:
        print(f"[blogs] cache evict error: {exc}")
