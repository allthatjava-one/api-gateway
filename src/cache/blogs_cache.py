"""
blogs_cache — Cloudflare Cache API helpers for the blog list.

Uses the built-in Cache API (caches.open) which persists across requests
at the same edge PoP without requiring any external bindings.

Eviction strategy:
- Each cached page URL includes a generation number (gen=N).
- An index entry tracks all URLs written in the current generation.
- On eviction: all tracked URLs are deleted via cache.delete(url), then the
  generation is bumped so any stragglers are never matched again.
- Only cache.put(), cache.match(), and cache.delete(url) are used —
  all three are supported by CF Workers (cache.keys() and caches.delete() are not).
"""
import json

from js import Object, Response as js_Response, caches as js_caches
from pyodide.ffi import to_js

_CACHE_TTL_SECONDS = 86400  # 24 hours
_CACHE_NAME = "blogs"
_GEN_URL = "https://api-gateway-internal-cache/v1/blogs/__gen"
_INDEX_URL = "https://api-gateway-internal-cache/v1/blogs/__index"


def _make_js_response(body: str, ttl: int) -> object:
    return js_Response.new(
        body,
        to_js(
            {
                "status": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Cache-Control": f"max-age={ttl}",
                },
            },
            dict_converter=Object.fromEntries,
        ),
    )


async def _get_generation(cache) -> int:
    try:
        resp = await cache.match(_GEN_URL)
        if resp is None:
            return 0
        return int(json.loads(await resp.text()))
    except Exception:
        return 0


async def _get_index(cache) -> list:
    try:
        resp = await cache.match(_INDEX_URL)
        if resp is None:
            return []
        return json.loads(await resp.text())
    except Exception:
        return []


async def _add_to_index(cache, url: str):
    try:
        idx = await _get_index(cache)
        if url not in idx:
            idx.append(url)
            await cache.put(_INDEX_URL, _make_js_response(json.dumps(idx), _CACHE_TTL_SECONDS))
    except Exception as exc:
        print(f"[blogs] cache index update error: {exc}")


def _cache_url(env_name: str, gen: int, page: int, page_size: int) -> str:
    return (
        f"https://api-gateway-internal-cache/{env_name}/v1/blogs"
        f"?gen={gen}&page={page}&page_size={page_size}"
    )


async def get_cached_blogs(env_name: str, page: int = 1, page_size: int = 10):
    """Read paginated blog list from the Cloudflare Cache API. Returns None on miss."""
    try:
        cache = await js_caches.open(_CACHE_NAME)
        gen = await _get_generation(cache)
        resp = await cache.match(_cache_url(env_name, gen, page, page_size))
        if resp is None:
            return None
        data = json.loads(await resp.text())
        print(f"[blogs] cache hit ({env_name}) gen={gen} page={page} size={page_size}")
        return data
    except Exception as exc:
        print(f"[blogs] cache read error: {exc}")
        return None


async def set_cached_blogs(env_name: str, page: int, page_size: int, payload):
    """Write paginated blog list into the Cloudflare Cache API."""
    try:
        cache = await js_caches.open(_CACHE_NAME)
        gen = await _get_generation(cache)
        url = _cache_url(env_name, gen, page, page_size)
        await cache.put(url, _make_js_response(json.dumps(payload), _CACHE_TTL_SECONDS))
        await _add_to_index(cache, url)
        try:
            count = len(payload.get("items", payload))
        except Exception:
            count = 0
        print(f"[blogs] cache set ({env_name}) gen={gen} page={page} size={page_size}: {count} entries")
    except Exception as exc:
        print(f"[blogs] cache write error: {exc}")


async def evict_cached_blogs(env_name: str):
    """Explicitly delete all tracked cache entries then bump the generation."""
    try:
        cache = await js_caches.open(_CACHE_NAME)
        gen = await _get_generation(cache)

        # Delete every tracked URL from the current generation
        deleted = 0
        for url in await _get_index(cache):
            try:
                if await cache.delete(url):
                    deleted += 1
            except Exception:
                pass

        # Clear index and gen, then write new gen
        for meta_url in (_INDEX_URL, _GEN_URL):
            try:
                await cache.delete(meta_url)
            except Exception:
                pass

        new_gen = gen + 1
        await cache.put(_GEN_URL, _make_js_response(json.dumps(new_gen), _CACHE_TTL_SECONDS))
        print(f"[blogs] cache evicted ({env_name}) gen {gen} -> {new_gen} (deleted={deleted})")
    except Exception as exc:
        print(f"[blogs] cache evict error: {exc}")
