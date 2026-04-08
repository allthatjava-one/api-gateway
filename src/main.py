"""
api-gateway — Cloudflare Python Worker
POST /api/v1/pdf-compressor
POST /api/v1/pdf-merger
"""
from workers import WorkerEntrypoint, Response

import asyncio
import json
import time
from urllib.parse import urlparse
import fnmatch
from js import AbortController, Object, clearTimeout, fetch as js_fetch, setTimeout
from pyodide.ffi import to_js

# ---------------------------------------------------------------------------
# Allowed origins are loaded from the ALLOWED_ORIGINS environment variable.
# Set it as a comma-separated string in .dev.vars, wrangler.json vars, or via secret:
#   ALLOWED_ORIGINS = "http://localhost:4173,https://pdf-compressor.thrjtech.com"
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
MAX_COMPRESS_WAIT_SECONDS = 90
DEFAULT_INITIAL_RETRY_DELAY_SECONDS = 1
DEFAULT_COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS = 30
DEFAULT_MERGED_PDF_FETCH_TIMEOUT_SECONDS = 30
MAX_RETRY_DELAY_SECONDS = 5

def _cors_headers(origin: str) -> dict:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Vary": "Origin",
    }


def _json_response(data, status: int = 200, origin: str = "") -> Response:
    headers = {"Content-Type": "application/json"}
    if origin:
        headers.update(_cors_headers(origin))
    return Response(json.dumps(data), status=status, headers=headers)


def _error(status: int, message: str, origin: str = "") -> Response:
    return _json_response({"error": message}, status, origin)


async def _call_compress_service_with_retry(
    external_url: str,
    object_key: str,
    compressed_pdf_fetch_timeout_seconds: float,
):
    deadline = time.monotonic() + MAX_COMPRESS_WAIT_SECONDS
    attempt = 0
    retry_delay = DEFAULT_INITIAL_RETRY_DELAY_SECONDS
    last_error = "Compress service did not become ready in time."

    while time.monotonic() < deadline:
        attempt += 1
        ext_resp, fetch_error = await _fetch_compress_with_timeout(
            external_url,
            object_key,
            compressed_pdf_fetch_timeout_seconds,
        )
        if ext_resp is None:
            last_error = fetch_error

        if ext_resp is not None:
            if ext_resp.ok:
                return ext_resp, ""

            body_text = await ext_resp.text()
            if ext_resp.status not in TRANSIENT_STATUS_CODES:
                return None, f"Compress service returned {ext_resp.status}: {body_text[:200]}"

            last_error = (
                f"Compress service temporary failure ({ext_resp.status}): {body_text[:200]}"
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        sleep_for = min(retry_delay, remaining)
        print(
            f"[pdf-compressor] attempt {attempt} failed, retrying in {sleep_for:.1f}s"
        )
        await asyncio.sleep(sleep_for)
        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)

    return None, last_error


async def _fetch_compress_with_timeout(
    external_url: str,
    object_key: str,
    compressed_pdf_fetch_timeout_seconds: float,
):
    controller = AbortController.new()
    timeout_ms = max(1, int(compressed_pdf_fetch_timeout_seconds * 1000))
    timeout_id = setTimeout(controller.abort, timeout_ms)

    try:
        ext_resp = await js_fetch(
            external_url,
            to_js(
                {
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"objectKey": object_key}),
                    "signal": controller.signal,
                },
                dict_converter=Object.fromEntries,
            ),
        )
        return ext_resp, ""
    except Exception as exc:
        error_name = getattr(exc, "name", "")
        error_text = str(exc)
        if error_name == "AbortError" or "AbortError" in error_text:
            return None, f"Compress service request timed out after {compressed_pdf_fetch_timeout_seconds}s."
        return None, f"Failed to call compress service: {exc}"
    finally:
        clearTimeout(timeout_id)


async def _call_convert_service_with_retry(
    external_url: str,
    body: dict,
    compressed_pdf_fetch_timeout_seconds: float,
):
    deadline = time.monotonic() + MAX_COMPRESS_WAIT_SECONDS
    attempt = 0
    retry_delay = DEFAULT_INITIAL_RETRY_DELAY_SECONDS
    last_error = "Convert service did not become ready in time."

    while time.monotonic() < deadline:
        attempt += 1
        ext_resp, fetch_error = await _fetch_convert_with_timeout(
            external_url,
            body,
            compressed_pdf_fetch_timeout_seconds,
        )
        if ext_resp is None:
            last_error = fetch_error

        if ext_resp is not None:
            if ext_resp.ok:
                return ext_resp, ""

            body_text = await ext_resp.text()
            if ext_resp.status not in TRANSIENT_STATUS_CODES:
                return None, f"Convert service returned {ext_resp.status}: {body_text[:200]}"

            last_error = (
                f"Convert service temporary failure ({ext_resp.status}): {body_text[:200]}"
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        sleep_for = min(retry_delay, remaining)
        print(
            f"[pdf-converter] attempt {attempt} failed, retrying in {sleep_for:.1f}s"
        )
        await asyncio.sleep(sleep_for)
        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)

    return None, last_error


async def _fetch_convert_with_timeout(
    convert_url: str,
    body: dict,
    compressed_pdf_fetch_timeout_seconds: float,
):
    controller = AbortController.new()
    timeout_ms = max(1, int(compressed_pdf_fetch_timeout_seconds * 1000))
    timeout_id = setTimeout(controller.abort, timeout_ms)

    try:
        ext_resp = await js_fetch(
            convert_url,
            to_js(
                {
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(body),
                    "signal": controller.signal,
                },
                dict_converter=Object.fromEntries,
            ),
        )
        return ext_resp, ""
    except Exception as exc:
        error_name = getattr(exc, "name", "")
        error_text = str(exc)
        if error_name == "AbortError" or "AbortError" in error_text:
            return None, f"Convert service request timed out after {compressed_pdf_fetch_timeout_seconds}s."
        return None, f"Failed to call convert service: {exc}"
    finally:
        clearTimeout(timeout_id)


def _handle_preflight(request, allowed_origins: list) -> Response:
    origin = request.headers.get("Origin") or ""
    if not _origin_is_allowed(origin, allowed_origins):
        print(f"[cors] preflight rejected origin={origin!r} allowed={allowed_origins!r}")
        return Response("Forbidden", status=403)
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
        "Vary": "Origin",
    }
    return Response(None, status=204, headers=headers)


def _origin_is_allowed(origin: str, allowed_patterns: list) -> bool:
    """Return True if the request origin matches any allowed pattern.

    Allowed patterns may include shell-style wildcards (e.g. https://*.example.com/*)
    or a single "*" to allow any origin. Path components in patterns are ignored
    since CORS origins do not include paths.
    """
    if not origin:
        return False
    origin_norm = origin.rstrip("/")
    for pat in allowed_patterns:
        p = (pat or "").strip()
        if not p:
            continue
        if p == "*":
            return True
        # Strip any path from the pattern; we only match scheme://netloc
        try:
            parsed = urlparse(p)
            if parsed.scheme and parsed.netloc:
                pattern_origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            else:
                # pattern may be just a host pattern like "*.example.com"
                pattern_origin = p.split("/", 1)[0].rstrip("/")
        except Exception:
            pattern_origin = p.split("/", 1)[0].rstrip("/")

        if fnmatch.fnmatchcase(origin_norm, pattern_origin):
            return True

    return False


# (R2 access removed) Use external compress service instead


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def _handle_hello(origin: str) -> Response:
    return _json_response({"message": "Hello World"}, 200, origin)


async def _handle_pdf_compressor(request, env, origin: str) -> Response:
    # Parse body
    try:
        body = await request.json()
    except Exception:
        return _error(400, "Request body must be valid JSON.", origin)

    if not isinstance(body, dict):
        return _error(400, "Request body must be a JSON object.", origin)

    object_key = body.get("objectKey")
    if not object_key:
        return _error(400, "Missing required field: objectKey.", origin)

    if not isinstance(object_key, str):
        return _error(400, "objectKey must be a string.", origin)
    # Call external compress service which returns a presigned key
    # external_url = "http://localhost:8787/compress"
    external_url = env.SERVICE_PDF_COMPRESS_URL
    # print(
    #     f"[pdf-compressor] external_url resolved to: {external_url}"
    # )


    compressed_pdf_fetch_timeout_seconds = DEFAULT_COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS
    fetch_timeout_raw = getattr(env, "COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS", None)
    if fetch_timeout_raw is not None:
        try:
            configured_timeout = float(fetch_timeout_raw)
            if configured_timeout > 0:
                compressed_pdf_fetch_timeout_seconds = configured_timeout
        except (TypeError, ValueError):
            print(
                "[pdf-compressor] invalid COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS; using default"
            )

    print(f"[pdf-compressor] calling external compress service for: {object_key}")
    ext_resp, call_error = await _call_compress_service_with_retry(
        external_url,
        object_key,
        compressed_pdf_fetch_timeout_seconds,
    )
    if ext_resp is None:
        print(f"[pdf-compressor] external service unavailable: {call_error}")
        return _error(502, call_error, origin)

    print(f"[pdf-compressor] external response status: {ext_resp.status}")

    try:
        result_text = await ext_resp.text()
        result = json.loads(result_text)
    except Exception as exc:
        print(f"[pdf-compressor] invalid json from compress service: {exc}")
        return _error(502, "Compress service returned invalid JSON.", origin)

    presigned = result.get("presignedUrl")
    if not presigned:
        return _error(502, "Compress service did not return presignedUrl.", origin)

    return _json_response({"presignedUrl": presigned}, 200, origin)


async def _handle_pdf_converter(request, env, origin: str) -> Response:
    # Parse body (same validation as pdf-compressor)
    try:
        body = await request.json()
    except Exception:
        return _error(400, "Request body must be valid JSON.", origin)

    if not isinstance(body, dict):
        return _error(400, "Request body must be a JSON object.", origin)

    object_key = body.get("objectKey")
    if not object_key:
        return _error(400, "Missing required field: objectKey.", origin)

    if not isinstance(object_key, str):
        return _error(400, "objectKey must be a string.", origin)

    # Read backend convert service URL from env
    convert_url = getattr(env, "SERVICE_PDF_CONVERT_URL", None)
    if not convert_url:
        return _error(500, "Missing required environment variable: SERVICE_PDF_CONVERT_URL.", origin)

    compressed_pdf_fetch_timeout_seconds = DEFAULT_COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS
    fetch_timeout_raw = getattr(env, "COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS", None)
    if fetch_timeout_raw is not None:
        try:
            configured_timeout = float(fetch_timeout_raw)
            if configured_timeout > 0:
                compressed_pdf_fetch_timeout_seconds = configured_timeout
        except (TypeError, ValueError):
            print(
                "[pdf-converter] invalid COMPRESSED_PDF_FETCH_TIMEOUT_SECONDS; using default"
            )

    print(f"[pdf-converter] calling external convert service for: {object_key}")
    ext_resp, call_error = await _call_convert_service_with_retry(
        convert_url,
        body,
        compressed_pdf_fetch_timeout_seconds,
    )
    if ext_resp is None:
        print(f"[pdf-converter] external service unavailable: {call_error}")
        return _error(502, call_error, origin)

    print(f"[pdf-converter] external response status: {ext_resp.status}")

    try:
        result_text = await ext_resp.text()
    except Exception as exc:
        print(f"[pdf-converter] invalid response from convert service: {exc}")
        return _error(502, "Convert service returned invalid response.", origin)

    # Build a passthrough response: preserve status and Content-Type when possible
    # Headers must be passed at construction time — they are immutable afterwards.
    headers = {}
    try:
        ct = ext_resp.headers.get("Content-Type") or ext_resp.headers.get("content-type")
        if ct:
            headers["Content-Type"] = ct
    except Exception:
        pass

    if origin:
        headers.update(_cors_headers(origin))

    return Response(result_text, status=ext_resp.status, headers=headers)



async def _call_merge_service_with_retry(
    merge_url: str,
    object_keys: list,
    merged_pdf_fetch_timeout_seconds: float,
):
    deadline = time.monotonic() + MAX_COMPRESS_WAIT_SECONDS
    attempt = 0
    retry_delay = DEFAULT_INITIAL_RETRY_DELAY_SECONDS
    last_error = "Merge service did not become ready in time."

    while time.monotonic() < deadline:
        attempt += 1
        ext_resp, fetch_error = await _fetch_merge_with_timeout(
            merge_url,
            object_keys,
            merged_pdf_fetch_timeout_seconds,
        )
        if ext_resp is None:
            last_error = fetch_error

        if ext_resp is not None:
            if ext_resp.ok:
                return ext_resp, ""

            body_text = await ext_resp.text()
            if ext_resp.status not in TRANSIENT_STATUS_CODES:
                return None, f"Merge service returned {ext_resp.status}: {body_text[:200]}"

            last_error = (
                f"Merge service temporary failure ({ext_resp.status}): {body_text[:200]}"
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        sleep_for = min(retry_delay, remaining)
        print(
            f"[pdf-merger] attempt {attempt} failed, retrying in {sleep_for:.1f}s"
        )
        await asyncio.sleep(sleep_for)
        retry_delay = min(retry_delay * 2, MAX_RETRY_DELAY_SECONDS)

    return None, last_error


async def _fetch_merge_with_timeout(
    merge_url: str,
    body: dict,
    merged_pdf_fetch_timeout_seconds: float,
):
    controller = AbortController.new()
    timeout_ms = max(1, int(merged_pdf_fetch_timeout_seconds * 1000))
    timeout_id = setTimeout(controller.abort, timeout_ms)

    try:
        ext_resp = await js_fetch(
            merge_url,
            to_js(
                {
                    "method": "POST",
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps(body),
                    "signal": controller.signal,
                },
                dict_converter=Object.fromEntries,
            ),
        )
        return ext_resp, ""
    except Exception as exc:
        error_name = getattr(exc, "name", "")
        error_text = str(exc)
        if error_name == "AbortError" or "AbortError" in error_text:
            return None, f"Merge service request timed out after {merged_pdf_fetch_timeout_seconds}s."
        return None, f"Failed to call merge service: {exc}"
    finally:
        clearTimeout(timeout_id)


async def _handle_pdf_merger(request, env, origin: str) -> Response:
    # Parse body
    try:
        body = await request.json()
    except Exception:
        return _error(400, "Request body must be valid JSON.", origin)

    if not isinstance(body, dict):
        return _error(400, "Request body must be a JSON object.", origin)

    object_keys = body.get("objectKeys")
    if not object_keys:
        return _error(400, "Missing required field: objectKeys.", origin)

    merge_url = getattr(env, "SERVICE_PDF_MERGE_URL", None)
    if not merge_url:
        return _error(500, "Missing required environment variable: SERVICE_PDF_MERGE_URL.", origin)

    merged_pdf_fetch_timeout_seconds = DEFAULT_MERGED_PDF_FETCH_TIMEOUT_SECONDS
    fetch_timeout_raw = getattr(env, "MERGED_PDF_FETCH_TIMEOUT_SECONDS", None)
    if fetch_timeout_raw is not None:
        try:
            configured_timeout = float(fetch_timeout_raw)
            if configured_timeout > 0:
                merged_pdf_fetch_timeout_seconds = configured_timeout
        except (TypeError, ValueError):
            print(
                "[pdf-merger] invalid MERGED_PDF_FETCH_TIMEOUT_SECONDS; using default"
            )

    print(f"[pdf-merger] calling external merge service with full request body")
    ext_resp, call_error = await _call_merge_service_with_retry(
        merge_url,
        body,
        merged_pdf_fetch_timeout_seconds,
    )
    if ext_resp is None:
        print(f"[pdf-merger] external service unavailable: {call_error}")
        return _error(502, call_error, origin)

    print(f"[pdf-merger] external response status: {ext_resp.status}")

    try:
        result_text = await ext_resp.text()
        result = json.loads(result_text)
    except Exception:
        return _error(502, "Merge service returned invalid JSON.", origin)

    presigned = result.get("presignedUrl")
    if not presigned:
        return _error(502, "Merge service did not return presignedUrl.", origin)

    return _json_response({"presignedUrl": presigned}, 200, origin)


# ---------------------------------------------------------------------------
# Blog handlers (D1)
# ---------------------------------------------------------------------------

async def _handle_blogs_list(env, origin: str) -> Response:
    db = getattr(env, "DB", None)
    if db is None:
        return _error(500, "Database binding is not configured.", origin)
    try:
        result = await db.prepare(
            "SELECT slug, title, description, thumbnail FROM blogs ORDER BY id"
        ).all()
        blogs = result.results.to_py()
        try:
            print(f"[blogs] fetched {len(blogs)} rows")
            if len(blogs) > 0:
                print(f"[blogs] first row keys: {list(blogs[0].keys())}")
        except Exception:
            print("[blogs] fetched rows (unable to show length)")
    except Exception as exc:
        print(f"[blogs] DB error: {exc}")
        return _error(500, "Failed to fetch blogs.", origin)
    return _json_response(blogs, 200, origin)


async def _handle_blog_by_slug(slug: str, env, origin: str) -> Response:
    db = getattr(env, "DB", None)
    if db is None:
        return _error(500, "Database binding is not configured.", origin)
    try:
        row = await db.prepare(
            "SELECT slug, title, content FROM blogs WHERE slug = ?1"
        ).bind(slug).first()
    except Exception as exc:
        print(f"[blogs] DB error: {exc}")
        return _error(500, "Failed to fetch blog.", origin)
    if row is None:
        return _error(404, "Blog not found.", origin)
    return _json_response(row.to_py(), 200, origin)


# ---------------------------------------------------------------------------
# Health-check (keep-alive ping)
# ---------------------------------------------------------------------------

async def _run_health_check(env):
    hello_url = getattr(env, "SERVICE_HELLO_URL", None)
    print(f"[health-check] SERVICE_HELLO_URL resolved to: {hello_url!r}")
    if not hello_url:
        print("[health-check] SERVICE_HELLO_URL is not configured; skipping.")
        return
    try:
        resp = await js_fetch(hello_url)
        print(f"[health-check] GET {hello_url} → {resp.status}")
    except Exception as exc:
        print(f"[health-check] failed to ping {hello_url}: {exc}")


# ---------------------------------------------------------------------------
# Cloudflare Workers entry point
# ---------------------------------------------------------------------------
class Default(WorkerEntrypoint):
    async def on_fetch(self, request):
        env = self.env
        method = request.method.upper()

        raw = getattr(env, "ALLOWED_ORIGINS", "") or ""
        allowed_origins = [o.strip() for o in raw.split(",") if o.strip()]
        # Debug: log origin/method/path and configured allowed origins
        try:
            incoming_origin = request.headers.get("Origin") or ""
        except Exception:
            incoming_origin = ""
        print(f"[cors] incoming origin={incoming_origin!r} allowed={allowed_origins!r} method={method} path={urlparse(str(request.url)).path}")

        # Scheduled-trigger shim: wrangler dev routes /__scheduled through on_fetch
        # for Python workers instead of calling the scheduled handler directly.
        # Next 4 lines are only for Development test. In production, scheduled handler is called directly by Cloudflare on schedule.
        # path_early = urlparse(str(request.url)).path.rstrip("/")
        # if path_early == "/__scheduled":
        #     await _run_health_check(env)
        #     return Response.new("ok", {"status": 200})

        # CORS preflight
        if method == "OPTIONS":
            return _handle_preflight(request, allowed_origins)

        # Origin check — all non-preflight requests must come from an allowed origin
        origin = request.headers.get("Origin") or ""
        # Enforce stricter rules: require Origin for non-safe methods.
        # Allow empty Origin only for safe, idempotent requests (GET, HEAD, OPTIONS).
        if not origin:
            if method not in ("GET", "HEAD", "OPTIONS"):
                print(f"[cors] missing Origin rejected method={method} path={urlparse(str(request.url)).path}")
                return _error(403, "Forbidden: Origin header required for this method.")
        else:
            if not _origin_is_allowed(origin, allowed_origins):
                print(f"[cors] request rejected origin={origin!r} allowed={allowed_origins!r}")
                return _error(403, "Forbidden: Origin not allowed.")

        path = urlparse(str(request.url)).path.rstrip("/")

        if path == "/api/v1/hello":
            if method == "GET":
                return _handle_hello(origin)
            return _error(405, "Method Not Allowed: use GET.", origin)

        if path == "/api/v1/pdf-compressor":
            if method == "POST":
                return await _handle_pdf_compressor(request, env, origin)
            return _error(405, "Method Not Allowed: use POST.", origin)

        if path == "/api/v1/pdf-converter":
            if method == "POST":
                return await _handle_pdf_converter(request, env, origin)
            return _error(405, "Method Not Allowed: use POST.", origin)

        if path == "/api/v1/pdf-merger":
            if method == "POST":
                return await _handle_pdf_merger(request, env, origin)
            return _error(405, "Method Not Allowed: use POST.", origin)

        if path == "/api/v1/blogs":
            if method == "GET":
                return await _handle_blogs_list(env, origin)
            return _error(405, "Method Not Allowed: use GET.", origin)

        if path.startswith("/api/v1/blogs/"):
            slug = path[len("/api/v1/blogs/"):]
            if slug:
                if method == "GET":
                    return await _handle_blog_by_slug(slug, env, origin)
                return _error(405, "Method Not Allowed: use GET.", origin)

        return _error(404, "Not Found.", origin)

    async def scheduled(self, controller, env, ctx):
        await _run_health_check(self.env)
